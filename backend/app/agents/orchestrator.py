"""Multi-agent pipeline: research -> strategy -> backtest -> risk review.

Each step's status/output/usage is persisted to the pipeline_runs row as it happens (the SSE endpoint just reads
that row). Numbers always come from the deterministic engine; agents only retrieve, translate and explain.
"""

import asyncio
import copy
import json
import logging
import weakref
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, TypeVar

from pydantic_ai import Agent
from pydantic_ai.models import Model
from pydantic_ai.usage import UsageLimits
from sqlalchemy.orm import Session

from app.agents.agents import backtest_agent, research_agent, risk_agent, strategy_agent
from app.agents.deps import AgentDeps, Canonical
from app.api.spec_source import resolve_spec
from app.core.config import Settings
from app.core.logging import run_id_var
from app.core.models import PipelineRun
from app.core.tracing import run_span
from app.data.backtest_io import build_run_record, load_frames
from app.data.models import Dataset
from app.engine.backtest import run_backtest
from app.engine.summary import build_facts, stress_spec
from app.llm.registry import ModelError, build_model, resolve_model
from app.rag.embeddings import Embedder
from app.rag.store import VectorStore
from app.schemas.agents import STEP_ORDER, RunRequest, StepName
from app.schemas.backtest import BacktestResult
from app.schemas.strategy import StrategySpec

log = logging.getLogger(__name__)
T = TypeVar("T")
SessionFactory = Callable[[], Session]
ModelBuilder = Callable[[Settings, str], Model]
REQUEST_LIMIT = 25  # max model requests per agent run (guards runaway tool/retry loops)

_semaphores: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore]" = weakref.WeakKeyDictionary()


def _semaphore(limit: int) -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    if loop not in _semaphores:
        _semaphores[loop] = asyncio.Semaphore(limit)
    return _semaphores[loop]


class StepFailed(Exception):
    pass


def _now() -> str:
    return datetime.now(UTC).replace(tzinfo=None).isoformat()


def _err(e: BaseException) -> str:
    if isinstance(e, TimeoutError):
        return "TimeoutError: step timed out"
    return f"{type(e).__name__}: {e}"[:1000]


def _json_block(label: str, payload: Any) -> str:
    return f"{label}:\n```json\n{json.dumps(payload)}\n```"


def describe_spec(spec: StrategySpec) -> str:
    inds = ", ".join(f"{i.type}({', '.join(f'{k}={v:g}' for k, v in i.params.items())})" for i in spec.indicators)
    return f"{spec.name}. {spec.description} Indicators: {inds or 'none'}. Direction: {spec.direction}."


def dataset_summary(ds: Dataset) -> str:
    strikes = sorted(ds.strikes)
    step = min((b - a for a, b in zip(strikes, strikes[1:], strict=False)), default=None)
    lo, hi = (strikes[0], strikes[-1]) if strikes else ("?", "?")
    return (
        f"{ds.underlying}, {ds.timeframe_minutes}-minute candles, {ds.start_date} to {ds.end_date}, "
        f"lot size {ds.lot_size}, strikes {lo}-{hi} (step {step})"
    )


@dataclass
class RunContext:
    req: RunRequest
    base_spec: StrategySpec | None
    strategy_id: str | None
    lot_size: int
    deps_summary: str
    timeframe: int | None


class Pipeline:
    def __init__(
        self,
        settings: Settings,
        session_factory: SessionFactory,
        store: VectorStore,
        embedder: Embedder,
        model_builder: ModelBuilder = build_model,
    ) -> None:
        self.settings, self.session_factory = settings, session_factory
        self.store, self.embedder, self.model_builder = store, embedder, model_builder

    # ---- persistence ---------------------------------------------------------------------------
    async def _db(self, fn: Callable[[Session], T]) -> T:
        def run() -> T:
            with self.session_factory() as s:
                out = fn(s)
                s.commit()
                return out

        return await asyncio.to_thread(run)

    async def _patch_step(self, run_id: str, name: str, **fields: Any) -> None:
        def fn(s: Session) -> None:
            run = s.get(PipelineRun, run_id)
            assert run is not None
            steps = copy.deepcopy(run.steps)
            for st in steps:
                if st["name"] == name:
                    st.update(fields)
            run.steps = steps

        await self._db(fn)

    async def _set_run(self, run_id: str, **fields: Any) -> None:
        def fn(s: Session) -> None:
            run = s.get(PipelineRun, run_id)
            assert run is not None
            for k, v in fields.items():
                setattr(run, k, v)

        await self._db(fn)

    async def _fail(self, run_id: str, message: str) -> None:
        def fn(s: Session) -> None:
            run = s.get(PipelineRun, run_id)
            assert run is not None
            steps = copy.deepcopy(run.steps)
            for st in steps:
                if st["status"] == "pending":
                    st["status"] = "skipped"
            run.steps, run.status, run.error = steps, "failed", message

        await self._db(fn)

    # ---- entry point ---------------------------------------------------------------------------
    async def execute(self, run_id: str) -> None:
        token = run_id_var.set(run_id)
        try:
            async with _semaphore(self.settings.max_concurrent_runs):
                with run_span(run_id):
                    await self._run(run_id)
        except StepFailed as e:
            log.warning("run failed: %s", e)
            await self._fail(run_id, str(e))
        except Exception as e:
            log.exception("run crashed")
            await self._fail(run_id, _err(e))
        finally:
            run_id_var.reset(token)

    # ---- pipeline ------------------------------------------------------------------------------
    def _load_context(self, run_id: str) -> Callable[[Session], RunContext]:
        def fn(s: Session) -> RunContext:
            run = s.get(PipelineRun, run_id)
            ds = s.get(Dataset, run.dataset_id) if run else None
            if run is None or ds is None:
                raise StepFailed("Run or dataset not found")
            req = RunRequest.model_validate(run.request)
            base, strategy_id = resolve_spec(s, spec=req.spec, template_id=req.template_id, strategy_id=req.strategy_id)
            run.status = "running"
            return RunContext(req, base, strategy_id, ds.lot_size, dataset_summary(ds), ds.timeframe_minutes)

        return fn

    async def _step(
        self,
        run_id: str,
        name: StepName,
        model: str | None,
        work: Callable[[], Awaitable[tuple[T, dict[str, Any], dict[str, int] | None, list[str]]]],
    ) -> T:
        await self._patch_step(run_id, name, status="running", started_at=_now(), model=model)
        try:
            value, output, usage, warnings = await asyncio.wait_for(work(), self.settings.agent_timeout_seconds)
        except Exception as e:
            msg = _err(e)
            await self._patch_step(run_id, name, status="failed", finished_at=_now(), error=msg)
            raise StepFailed(f"{name} step failed: {msg}") from e
        await self._patch_step(
            run_id, name, status="completed", finished_at=_now(), output=output, usage=usage, warnings=warnings
        )
        return value

    async def _agent(
        self, agent: Agent[AgentDeps, Any], prompt: str, model_id: str, deps: AgentDeps
    ) -> tuple[Any, dict[str, int]]:
        result = await agent.run(
            prompt,
            model=self.model_builder(self.settings, model_id),
            deps=deps,
            usage_limits=UsageLimits(request_limit=REQUEST_LIMIT),
        )
        u = result.usage
        usage = {
            "requests": u.requests,
            "input_tokens": u.input_tokens,
            "output_tokens": u.output_tokens,
            "tool_calls": u.tool_calls,
        }
        return result.output, usage

    async def _run(self, run_id: str) -> None:
        ctx = await self._db(self._load_context(run_id))
        req = ctx.req
        has_idea = bool(req.idea and req.idea.strip())
        try:
            models = {n: resolve_model(self.settings, req.model, agent=n) for n in STEP_ORDER}
        except ModelError as e:
            raise StepFailed(str(e)) from e

        under, opts = await asyncio.to_thread(load_frames, self.settings, req.dataset_id)
        deps = AgentDeps(
            store=self.store,
            embedder=self.embedder,
            dataset_timeframe_minutes=ctx.timeframe,
            dataset_summary=ctx.deps_summary,
        )

        def run_engine(spec: StrategySpec, start: date | None, end: date | None) -> BacktestResult:
            return run_backtest(spec, under, opts, lot_size=ctx.lot_size, start=start, end=end, capital=req.capital)

        # 1. research
        topic = req.idea if has_idea else describe_spec(ctx.base_spec) if ctx.base_spec else ""

        async def research() -> tuple[Any, dict[str, Any], dict[str, int] | None, list[str]]:
            out, usage = await self._agent(
                research_agent, f"Trading idea or strategy to research:\n{topic}", models["research"], deps
            )
            return out, out.model_dump(mode="json"), usage, []

        await self._step(run_id, "research", models["research"], research)

        # 2. strategy
        if has_idea:
            prompt = f"User idea:\n{req.idea}"
            if ctx.base_spec is not None:
                prompt += "\n\n" + _json_block("STARTING_SPEC", ctx.base_spec.model_dump(mode="json"))

            async def strategy() -> tuple[Any, dict[str, Any], dict[str, int] | None, list[str]]:
                draft, usage = await self._agent(strategy_agent, prompt, models["strategy"], deps)
                return draft.spec, {**draft.model_dump(mode="json"), "source": "agent"}, usage, []

            spec: StrategySpec = await self._step(run_id, "strategy", models["strategy"], strategy)
        else:
            assert ctx.base_spec is not None
            spec = ctx.base_spec
            source = "spec" if req.spec else "template" if req.template_id else "saved_strategy"
            await self._patch_step(
                run_id,
                "strategy",
                status="skipped",
                started_at=_now(),
                finished_at=_now(),
                output={"spec": spec.model_dump(mode="json"), "source": source},
            )

        # 3. backtest
        canonical = Canonical(spec, req.dataset_id, req.start, req.end)
        deps.canonical, deps.run_engine = canonical, run_engine
        args = {
            "spec": spec.model_dump(mode="json"),
            "dataset_id": req.dataset_id,
            "start": req.start.isoformat() if req.start else None,
            "end": req.end.isoformat() if req.end else None,
        }

        async def backtest() -> tuple[Any, dict[str, Any], dict[str, int] | None, list[str]]:
            warnings: list[str] = []
            notes, usage = await self._agent(
                backtest_agent, "Run this backtest.\n" + _json_block("BACKTEST_ARGS", args), models["backtest"], deps
            )
            if deps.result is None:
                warnings.append("Backtest agent did not call run_backtest; the pipeline ran the engine directly.")
                deps.result = await asyncio.to_thread(run_engine, spec, req.start, req.end)
            result = deps.result
            record = build_run_record(
                dataset_id=req.dataset_id,
                spec=spec,
                strategy_id=ctx.strategy_id,
                start=req.start,
                end=req.end,
                capital=req.capital,
                result=result,
            )

            def save(s: Session) -> str:
                s.add(record)
                return record.id

            backtest_id = await self._db(save)
            await self._set_run(run_id, backtest_run_id=backtest_id)
            out = {
                "backtest_run_id": backtest_id,
                "notes": notes.notes,
                "metrics": result.metrics.model_dump(mode="json", exclude={"daily_pnl"}),
            }
            return result, out, usage, warnings

        result: BacktestResult = await self._step(run_id, "backtest", models["backtest"], backtest)

        # 4. risk review
        async def risk() -> tuple[Any, dict[str, Any], dict[str, int] | None, list[str]]:
            warnings: list[str] = []
            stress, desc = stress_spec(spec)
            stress_result: BacktestResult | None = None
            try:
                stress_result = await asyncio.to_thread(run_engine, stress, req.start, req.end)
            except Exception as e:  # the review is still useful without the stress test
                warnings.append(f"Cost stress test failed: {_err(e)}")
            facts = build_facts(result, stress_result, desc)
            payload = {
                "metrics": result.metrics.model_dump(mode="json", exclude={"daily_pnl"}),
                "facts": facts.model_dump(mode="json"),
            }
            prompt = (
                "Review this backtest.\n"
                + _json_block("STRATEGY_SPEC", spec.model_dump(mode="json"))
                + "\n"
                + _json_block("BACKTEST_FACTS", payload)
            )
            review, usage = await self._agent(risk_agent, prompt, models["risk"], deps)
            return review, {"review": review.model_dump(mode="json"), "facts": payload["facts"]}, usage, warnings

        await self._step(run_id, "risk", models["risk"], risk)
        await self._set_run(run_id, status="completed")


def mark_interrupted(session_factory: SessionFactory) -> int:
    """Runs still queued/running after a restart can never finish; mark them failed."""
    n = 0
    with session_factory() as s:
        for run in s.query(PipelineRun).filter(PipelineRun.status.in_(("queued", "running"))):
            steps = copy.deepcopy(run.steps)
            for st in steps:
                if st["status"] == "running":
                    st.update(status="failed", error="Interrupted by server restart", finished_at=_now())
                elif st["status"] == "pending":
                    st["status"] = "skipped"
            run.steps, run.status, run.error = steps, "failed", "Interrupted by server restart"
            n += 1
        s.commit()
    return n


__all__ = ["Pipeline", "mark_interrupted", "StepFailed"]
