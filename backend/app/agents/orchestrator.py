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

from app.agents.agents import (
    ask_agent,
    backtest_agent,
    intake_agent,
    research_agent,
    risk_agent,
    strategy_agent,
    verify_agent,
)
from app.agents.deps import AgentDeps, Canonical
from app.agents.trade_plan import build_trade_plan
from app.api.spec_source import resolve_spec
from app.core.config import Settings
from app.core.logging import run_id_var
from app.core.models import PipelineRun, User
from app.core.tracing import run_span
from app.data.backtest_io import build_run_record, load_frames
from app.data.models import Dataset
from app.engine.backtest import run_backtest
from app.engine.lots import LOT_SCHEDULES
from app.engine.sizing import Sizing, apply_money_limits, estimate_entry_premium, expiry_kind
from app.engine.spec_check import check_spec
from app.engine.summary import build_facts, stress_spec
from app.llm.registry import ModelError, build_model, resolve_model
from app.news.feeds import NewsFetcher, parse_feeds
from app.rag.embeddings import Embedder
from app.rag.store import VectorStore
from app.schemas.agents import (
    STEP_ORDER,
    AskAnswer,
    ParsedQuery,
    ResearchOutput,
    RunRequest,
    StepName,
    VerifyOutput,
)
from app.schemas.backtest import BacktestResult
from app.schemas.strategy import StrategySpec
from upstox.expiries import ExpiryService, get_service

log = logging.getLogger(__name__)
T = TypeVar("T")
SessionFactory = Callable[[], Session]
ModelBuilder = Callable[[Settings, str], Model]
BEGINNER_MAX_TRADES_PER_DAY = 3
MAX_REVISIONS = 2  # verify -> strategy revision rounds
REASONING_KEYS = ("explanation", "assumptions", "reasons", "when_to_trade")
REQUEST_LIMIT = 25  # max model requests per agent run (guards runaway tool/retry loops)

_semaphores: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore]" = weakref.WeakKeyDictionary()


def _semaphore(limit: int) -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    if loop not in _semaphores:
        _semaphores[loop] = asyncio.Semaphore(limit)
    return _semaphores[loop]


def _trace_info(run: PipelineRun | None) -> dict[str, Any]:
    """Langfuse trace title, user, tags and metadata for a run, so it is easy to find: 'NIFTY | <idea>' by user."""
    req = (run.request if run else None) or {}
    underlying = str(req.get("underlying") or "")
    idea = " ".join(str(req.get("idea") or req.get("template_id") or "strategy").split())
    model = str(req.get("model") or "default")
    kind = "idea" if req.get("idea") else "template" if req.get("template_id") else "spec"
    tags = [t for t in (underlying, f"model:{model}", f"source:{kind}") if t and t != "model:default"]
    return {
        "title": f"strategy-desk | {underlying or 'auto'} | {idea[:60]}",
        "user_id": run.user_id if run else None,
        "tags": tags,
        "metadata": {
            "model": model,
            "capital": str(req.get("capital", "")),
            "dataset_id": str(req.get("dataset_id", "")),
        },
    }


class StepFailed(Exception):
    pass


def _now() -> str:
    return datetime.now(UTC).replace(tzinfo=None).isoformat()


class OutOfScope(Exception):
    """The request is not about NIFTY / BANKNIFTY options trading. The message is for the trader."""


DEFAULT_REFUSAL = "This tool only handles NIFTY and BANKNIFTY options trading: strategies, backtests and paper trading."


def _err(e: BaseException) -> str:
    if isinstance(e, TimeoutError):
        return "TimeoutError: step timed out"
    if isinstance(e, OutOfScope):
        return str(e)
    return f"{type(e).__name__}: {e}"[:1000]


def _add_usage(a: dict[str, int], b: dict[str, int]) -> dict[str, int]:
    return {k: a.get(k, 0) + b.get(k, 0) for k in {*a, *b}}


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
    underlying: str
    user_id: str | None = None
    level: str = "advanced"  # beginner | advanced | expert; unowned (legacy / test) runs behave like advanced


class Pipeline:
    def __init__(
        self,
        settings: Settings,
        session_factory: SessionFactory,
        store: VectorStore,
        embedder: Embedder,
        model_builder: ModelBuilder = build_model,
        news: NewsFetcher | None = None,
        expiries: ExpiryService | None = None,
    ) -> None:
        self.settings, self.session_factory = settings, session_factory
        self.store, self.embedder, self.model_builder = store, embedder, model_builder
        self.expiries = expiries or get_service(settings.storage_dir)
        self.news = news or (
            NewsFetcher(parse_feeds(settings.news_feeds), max_age_days=settings.news_max_age_days)
            if settings.news_enabled
            else None
        )

    async def parse_query(self, query: str, model: str | None) -> ParsedQuery:
        """Turn the trader's free-text request into structured fields for POST /runs (shown to the user to confirm)."""
        model_id = resolve_model(self.settings, model, agent="intake")
        deps = AgentDeps(store=self.store, embedder=self.embedder)
        out, _ = await self._agent(
            intake_agent, f"Today: {date.today().isoformat()}\nTrader request:\n{query}", model_id, deps
        )
        return out  # type: ignore[no-any-return]

    async def ask(self, query: str, model: str | None, level: str = "advanced") -> AskAnswer:
        """Answer a general trading question from the knowledge base and recent news (no strategy, no backtest)."""
        model_id = resolve_model(self.settings, model, agent="ask")
        deps = AgentDeps(store=self.store, embedder=self.embedder, news=self.news)
        out, _ = await self._agent(
            ask_agent, f"Trader experience level: {level}\nTrader question:\n{query}", model_id, deps
        )
        return out  # type: ignore[no-any-return]

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
            info = await self._db(lambda s: _trace_info(s.get(PipelineRun, run_id)))
            async with _semaphore(self.settings.max_concurrent_runs):
                with run_span(run_id, **info):
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
            base, strategy_id = resolve_spec(
                s, spec=req.spec, template_id=req.template_id, strategy_id=req.strategy_id, user_id=run.user_id
            )
            owner = s.get(User, run.user_id) if run.user_id else None
            run.status = "running"
            return RunContext(
                req,
                base,
                strategy_id,
                ds.lot_size,
                dataset_summary(ds),
                ds.timeframe_minutes,
                ds.underlying,
                run.user_id,
                owner.level if owner else "advanced",
            )

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
            news=self.news,
            dataset_timeframe_minutes=ctx.timeframe,
            dataset_summary=ctx.deps_summary,
        )

        def run_engine(spec: StrategySpec, start: date | None, end: date | None) -> BacktestResult:
            return run_backtest(
                spec, under, opts, lot_size=ctx.lot_size, start=start, end=end, capital=req.capital,
                lot_schedule=LOT_SCHEDULES.get(ctx.underlying),
            )  # fmt: skip

        sizing: Sizing | None = None

        async def finalize(s: StrategySpec) -> StrategySpec:
            """Apply the user's expiry and rupee limits in code: expiry kind, lots, stop loss and target %."""
            nonlocal sizing
            if req.expiry:
                real = self.expiries.kind_of(ctx.underlying, req.expiry)  # cached exchange list only, no network
                kind = ("monthly" if real == "monthly" else "nearest_weekly") if real else expiry_kind(req.expiry)
                s = s.model_copy(update={"instrument": s.instrument.model_copy(update={"expiry": kind})})
            if req.max_loss or req.target_profit:
                premium = await asyncio.to_thread(estimate_entry_premium, under, opts, s)
                s, sizing = apply_money_limits(s, premium, ctx.lot_size, req.max_loss, req.target_profit)
            if ctx.level == "beginner" and s.risk.max_trades_per_day is None:  # guardrail: no overtrading for beginners
                s = s.model_copy(
                    update={"risk": s.risk.model_copy(update={"max_trades_per_day": BEGINNER_MAX_TRADES_PER_DAY})}
                )
            return s

        trader = {
            "underlying": ctx.underlying,
            "expiry": req.expiry.isoformat() if req.expiry else None,
            "capital": req.capital,
            "max_loss_per_trade": req.max_loss,
            "target_profit_per_trade": req.target_profit,
            "experience_level": ctx.level,
        }

        # 1. research
        topic = req.idea if has_idea else describe_spec(ctx.base_spec) if ctx.base_spec else ""

        async def research() -> tuple[Any, dict[str, Any], dict[str, int] | None, list[str]]:
            out, usage = await self._agent(
                research_agent,
                f"Index: {ctx.underlying}\nTrading idea or strategy to research:\n{topic}",
                models["research"],
                deps,
            )
            if not out.in_scope:  # the first step is also the scope gate for direct POST /runs calls
                raise OutOfScope(out.refusal or DEFAULT_REFUSAL)
            return out, out.model_dump(mode="json"), usage, []

        research_out: ResearchOutput = await self._step(run_id, "research", models["research"], research)

        # 2. strategy
        strategy_draft: dict[str, Any] = {}
        reasoning: dict[str, Any] = {}
        base_strategy_prompt = ""
        if has_idea:
            prompt = f"User idea:\n{req.idea}"
            prompt += "\n\n" + _json_block("RESEARCH", research_out.model_dump(mode="json"))
            prompt += "\n\n" + _json_block("TRADER_CONTEXT", trader)
            if ctx.base_spec is not None:
                prompt += "\n\n" + _json_block("STARTING_SPEC", ctx.base_spec.model_dump(mode="json"))
            base_strategy_prompt = prompt

            async def strategy() -> tuple[Any, dict[str, Any], dict[str, int] | None, list[str]]:
                draft, usage = await self._agent(strategy_agent, prompt, models["strategy"], deps)
                strategy_draft.update(draft.model_dump(mode="json"))
                return draft.spec, {**draft.model_dump(mode="json"), "source": "agent"}, usage, []

            spec: StrategySpec = await self._step(run_id, "strategy", models["strategy"], strategy)
            reasoning = {
                k: v
                for k, v in strategy_draft.items()
                if k in ("explanation", "assumptions", "reasons", "when_to_trade")
            }
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

        spec = await finalize(spec)

        # 3. verify. Loop: when the agent-made spec is not approved, its issues go back to the strategy agent for a
        # revision (at most MAX_REVISIONS), then it is verified again. Never blocks: the backtest always runs.
        async def verify() -> tuple[Any, dict[str, Any], dict[str, int] | None, list[str]]:
            nonlocal spec, reasoning
            usage: dict[str, int] = {}
            history: list[dict[str, Any]] = []
            for attempt in range(MAX_REVISIONS + 1):
                facts = check_spec(spec)
                prompt = "Verify this strategy.\n"
                if has_idea:
                    prompt += f"User idea:\n{req.idea}\n\n"
                prompt += "\n\n".join(
                    [
                        _json_block("RESEARCH", research_out.model_dump(mode="json")),
                        _json_block("STRATEGY_SPEC", spec.model_dump(mode="json")),
                        _json_block("SPEC_FACTS", facts.model_dump(mode="json")),
                        _json_block("STRATEGY_REASONING", reasoning),
                        _json_block("TRADER_CONTEXT", trader),
                    ]
                )
                out, u = await self._agent(verify_agent, prompt, models["verify"], deps)
                usage = _add_usage(usage, u)
                history.append(
                    {"attempt": attempt, "verdict": out.verdict, "issues": [i.model_dump() for i in out.issues]}
                )
                if out.verdict == "approved" or not strategy_draft or attempt == MAX_REVISIONS:
                    break
                revise = "\n\n".join(
                    [
                        base_strategy_prompt,
                        "Revise the previous spec to fix the verifier's issues. Keep everything else unchanged.",
                        _json_block("PREVIOUS_SPEC", spec.model_dump(mode="json")),
                        _json_block("VERIFY_ISSUES", [i.model_dump() for i in out.issues]),
                    ]
                )
                draft, u = await self._agent(strategy_agent, revise, models["strategy"], deps)
                usage = _add_usage(usage, u)
                spec = await finalize(draft.spec)
                reasoning = {k: v for k, v in draft.model_dump(mode="json").items() if k in REASONING_KEYS}
            warnings = []
            if out.verdict != "approved":
                warnings.append(
                    f"Strategy verification: {out.verdict} ({len(out.issues)} issue(s)). See the verify step."
                )
            if len(history) > 1:
                warnings.append(f"The strategy was revised {len(history) - 1} time(s) after verification.")
            payload = {
                **out.model_dump(mode="json"),
                "facts": facts.model_dump(mode="json"),
                "revisions": len(history) - 1,
                "history": history,
                "final_spec": spec.model_dump(mode="json"),
                "reasoning": reasoning,
            }
            return out, payload, usage, warnings

        verify_out: VerifyOutput = await self._step(run_id, "verify", models["verify"], verify)

        # 4. backtest
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
                user_id=ctx.user_id,
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

        # 5. risk review
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
                f"Review this backtest. TRADER_LEVEL: {ctx.level}\n"
                + _json_block("STRATEGY_SPEC", spec.model_dump(mode="json"))
                + "\n"
                + _json_block("BACKTEST_FACTS", payload)
            )
            review, usage = await self._agent(risk_agent, prompt, models["risk"], deps)
            plan = build_trade_plan(
                req,
                ctx.underlying,
                spec,
                sizing,
                reasoning,
                verify_out.model_dump(mode="json"),
                payload["metrics"],
                ctx.level,
            )
            out = {"review": review.model_dump(mode="json"), "facts": payload["facts"], "trade_plan": plan}
            return review, out, usage, warnings

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
