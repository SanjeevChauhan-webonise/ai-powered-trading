import asyncio
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.api.deps import Cfg, PipelineDep, SessionFactory
from app.api.spec_source import resolve_spec
from app.core.models import PipelineRun
from app.data.models import Dataset
from app.llm.registry import ModelError, resolve_model
from app.schemas.agents import STEP_ORDER, RunOut, RunRequest, RunSummary, StepRecord

router = APIRouter(prefix="/runs", tags=["runs"])

POLL_SECONDS = 0.5
HEARTBEAT_SECONDS = 15.0
TERMINAL = ("completed", "failed")
_TASKS: set[asyncio.Task[None]] = set()  # keep references so background runs aren't garbage collected


def _summary(r: PipelineRun) -> RunSummary:
    return RunSummary(
        id=r.id,
        dataset_id=r.dataset_id,
        status=r.status,
        idea=r.request.get("idea"),
        backtest_run_id=r.backtest_run_id,
        error=r.error,
        created_at=r.created_at,
        updated_at=r.updated_at,
    )


def _out(r: PipelineRun) -> RunOut:
    return RunOut(
        **_summary(r).model_dump(),
        request=RunRequest.model_validate(r.request),
        steps=[StepRecord.model_validate(s) for s in r.steps],
    )


@router.post("", response_model=RunSummary, status_code=202, summary="Start the multi-agent pipeline")
async def create_run(req: RunRequest, settings: Cfg, factory: SessionFactory, pipeline: PipelineDep) -> RunSummary:
    """Returns immediately; follow progress with GET /runs/{id} or GET /runs/{id}/stream (SSE)."""

    def create() -> RunSummary:
        with factory() as db:
            ds = db.get(Dataset, req.dataset_id)
            if ds is None:
                raise HTTPException(404, "Dataset not found")
            if not ds.underlying_rows or not ds.options_rows:
                raise HTTPException(400, "Dataset needs both underlying and option candles")
            resolve_spec(db, spec=req.spec, template_id=req.template_id, strategy_id=req.strategy_id)
            has_idea = bool(req.idea and req.idea.strip())
            try:
                for agent in STEP_ORDER:
                    if agent != "strategy" or has_idea:
                        resolve_model(settings, req.model, agent=agent)
            except ModelError as e:
                raise HTTPException(400, str(e)) from e
            row = PipelineRun(
                id=uuid.uuid4().hex,
                dataset_id=ds.id,
                status="queued",
                request=req.model_dump(mode="json"),
                steps=[StepRecord(name=n).model_dump(mode="json") for n in STEP_ORDER],
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            return _summary(row)

    summary = await run_in_threadpool(create)
    task = asyncio.create_task(pipeline.execute(summary.id))
    _TASKS.add(task)
    task.add_done_callback(_TASKS.discard)
    return summary


@router.get("", response_model=list[RunSummary], summary="List pipeline runs")
def list_runs(factory: SessionFactory) -> list[RunSummary]:
    with factory() as db:
        return [_summary(r) for r in db.scalars(select(PipelineRun).order_by(PipelineRun.created_at.desc()))]


@router.get("/{run_id}", response_model=RunOut, summary="Run status, step outputs and backtest link")
def get_run(run_id: str, factory: SessionFactory) -> RunOut:
    with factory() as db:
        row = db.get(PipelineRun, run_id)
        if row is None:
            raise HTTPException(404, "Run not found")
        return _out(row)


def _sse(event: str, data: str) -> str:
    return f"event: {event}\ndata: {data}\n\n"


@router.get(
    "/{run_id}/stream",
    summary="Server-sent events: step progress, then run status, then done",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {}}, "description": "events: step, run, done"}},
)
async def stream_run(run_id: str, request: Request, factory: SessionFactory) -> StreamingResponse:
    def snapshot() -> RunOut | None:
        with factory() as db:
            row = db.get(PipelineRun, run_id)
            return _out(row) if row else None

    if await run_in_threadpool(snapshot) is None:
        raise HTTPException(404, "Run not found")

    async def events() -> AsyncIterator[str]:
        sent: dict[str, tuple[str, str | None]] = {}
        last_status: str | None = None
        idle = 0.0
        while True:
            run = await run_in_threadpool(snapshot)
            if run is None:
                return
            for step in run.steps:
                marker = (step.status, step.finished_at.isoformat() if step.finished_at else None)
                if step.status != "pending" and sent.get(step.name) != marker:
                    sent[step.name] = marker
                    yield _sse("step", step.model_dump_json())
                    idle = 0.0
            if run.status != last_status:
                last_status = run.status
                yield _sse("run", _summary_json(run))
                idle = 0.0
            if run.status in TERMINAL:
                yield _sse("done", _summary_json(run))
                return
            if await request.is_disconnected():
                return
            idle += POLL_SECONDS
            if idle >= HEARTBEAT_SECONDS:
                idle = 0.0
                yield ": heartbeat\n\n"
            await asyncio.sleep(POLL_SECONDS)

    headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    return StreamingResponse(events(), media_type="text/event-stream", headers=headers)


def _summary_json(run: RunOut) -> str:
    return RunSummary.model_validate(run.model_dump()).model_dump_json()
