import asyncio
from pathlib import Path
from typing import Any

import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models import Model
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.agents import mock
from app.agents.orchestrator import Pipeline, mark_interrupted
from app.core.config import Settings
from app.core.models import BacktestRun, PipelineRun
from app.engine.templates import TEMPLATES
from app.llm.registry import build_model
from app.schemas.agents import StepRecord
from tests.pipeline_helpers import Env


@pytest.fixture
def env(tmp_path: Path) -> Env:
    return Env(tmp_path)


def execute(env: Env, run_id: str, builder: Any = build_model, settings: Settings | None = None) -> PipelineRun:
    asyncio.run(Pipeline(settings or env.settings, env.maker, env.store, env.embedder, builder).execute(run_id))
    return env.run(run_id)


def steps(run: PipelineRun) -> dict[str, StepRecord]:
    return {s["name"]: StepRecord.model_validate(s) for s in run.steps}


def builder_with(model_fn: Any) -> Any:
    def build(settings: Settings, model_id: str) -> Model:
        return FunctionModel(model_fn, model_name="scripted")

    return build


def roles(info: AgentInfo) -> set[str]:
    return set(info.output_tools[0].parameters_json_schema.get("properties", {}))


def turn(messages: list[ModelMessage]) -> int:
    return sum(isinstance(m, ModelResponse) for m in messages)


def call(info: AgentInfo, args: dict[str, Any]) -> ModelResponse:
    return ModelResponse(parts=[ToolCallPart(tool_name=info.output_tools[0].name, args=args)])


# ---- happy paths ------------------------------------------------------------------------------


def test_full_pipeline_with_idea(env: Env) -> None:
    run = execute(env, env.create_run(idea="Buy CE when the 9 EMA crosses above the 21 EMA on 5 minute candles"))
    assert run.status == "completed" and run.error is None
    st = steps(run)
    assert [s.status for s in st.values()] == ["completed"] * 5
    assert all(s.model == "mock:demo" and s.usage and s.usage["requests"] >= 1 for s in st.values())
    assert st["research"].output and st["research"].output["sources"]  # real RAG retrieval through the tool
    assert st["strategy"].output and st["strategy"].output["source"] == "agent"
    assert st["strategy"].output["spec"]["name"] == "EMA Crossover"
    bt = st["backtest"].output
    assert bt and run.backtest_run_id == bt["backtest_run_id"] and "(mock)" in bt["notes"]
    with env.maker() as s:
        rec = s.get(BacktestRun, run.backtest_run_id)
        assert rec is not None and rec.status == "completed" and rec.result
        # numbers come from the engine, not the LLM: step metrics == stored engine result
        assert bt["metrics"]["total_pnl"] == rec.result["metrics"]["total_pnl"] == rec.total_pnl
        assert rec.num_trades == len(rec.result["trades"]) > 0
    risk = st["risk"].output
    assert risk and {"review", "facts"} <= set(risk)
    assert {f["code"] for f in risk["facts"]["flags"]} <= {
        "too_few_trades", "short_period", "high_drawdown", "profit_concentration", "cost_sensitive", "net_loss",
    }  # fmt: skip
    assert risk["facts"]["stress"]["description"].startswith("+1.0 point")
    assert len(risk["review"]["red_flags"]) == len(risk["facts"]["flags"])


def test_template_skips_strategy_agent(env: Env) -> None:
    run = execute(env, env.create_run(template_id="rsi_reversal"))
    assert run.status == "completed"
    st = steps(run)
    assert st["strategy"].status == "skipped" and st["strategy"].usage is None
    assert st["strategy"].output == {"spec": TEMPLATES["rsi_reversal"].model_dump(mode="json"), "source": "template"}
    assert st["research"].status == st["backtest"].status == st["risk"].status == "completed"
    with env.maker() as s:
        rec = s.get(BacktestRun, run.backtest_run_id)
        assert rec is not None and rec.strategy_name == "RSI Reversal"


def test_idea_with_template_adapts_starting_spec(env: Env) -> None:
    run = execute(env, env.create_run(idea="tweak it", template_id="rsi_reversal"))
    assert steps(run)["strategy"].output["spec"]["name"] == "RSI Reversal"  # mock keeps the starting spec


def test_date_range_is_respected(env: Env) -> None:
    run = execute(env, env.create_run(template_id="ema_crossover", start="2024-01-03", end="2024-01-04"))
    with env.maker() as s:
        rec = s.get(BacktestRun, run.backtest_run_id)
        assert rec and rec.start and rec.start.isoformat() == "2024-01-03" and rec.result
        assert all("2024-01-03" <= t["entry_time"][:10] <= "2024-01-04" for t in rec.result["trades"])


# ---- retries and guard rails ------------------------------------------------------------------


def test_strategy_invalid_output_is_retried(env: Env) -> None:
    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if "spec" in roles(info) and turn(messages) == 0:
            return call(info, {"spec": {"name": "broken", "lots": 0}, "explanation": "x"})  # fails validation
        return mock._mock(messages, info)

    run = execute(env, env.create_run(idea="ema crossover"), builder_with(model))
    assert run.status == "completed"
    assert steps(run)["strategy"].usage["requests"] == 2  # type: ignore[index]


def _run_strategy_agent(timeframes: list[int], base: int = 5) -> Any:
    from pydantic_ai.models.function import FunctionModel

    from app.agents.agents import strategy_agent
    from app.agents.deps import AgentDeps
    from app.rag.store import InMemoryStore
    from tests.rag_helpers import HashEmbedder

    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        tf = timeframes[min(turn(messages), len(timeframes) - 1)]
        spec = TEMPLATES["ema_crossover"].model_copy(update={"timeframe_minutes": tf}).model_dump(mode="json")
        return call(info, {"spec": spec, "explanation": "x"})

    deps = AgentDeps(store=InMemoryStore(), embedder=HashEmbedder(), dataset_timeframe_minutes=base)
    return strategy_agent.run_sync("idea", model=FunctionModel(model), deps=deps)


def test_strategy_timeframe_equal_to_dataset_is_normalized_not_retried() -> None:
    out = _run_strategy_agent([5])  # a 5-minute spec on a 5-minute dataset: nothing to resample
    assert out.output.spec.timeframe_minutes is None and out.usage.requests == 1


def test_strategy_timeframe_not_a_multiple_of_dataset_is_retried() -> None:
    out = _run_strategy_agent([7, 10])  # 7 is not a multiple of the 5-minute dataset
    assert out.output.spec.timeframe_minutes == 10 and out.usage.requests == 2


def test_strategy_timeframe_smaller_than_dataset_is_retried() -> None:
    out = _run_strategy_agent([3, 15])
    assert out.output.spec.timeframe_minutes == 15 and out.usage.requests == 2


def test_strategy_gives_up_after_retries(env: Env) -> None:
    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if "spec" in roles(info):
            return call(info, {"spec": {"name": "broken"}, "explanation": "x"})
        return mock._mock(messages, info)

    run = execute(env, env.create_run(idea="anything"), builder_with(model))
    st = steps(run)
    assert run.status == "failed" and run.error and run.error.startswith("strategy step failed")
    assert st["research"].status == "completed" and st["strategy"].status == "failed"
    assert st["backtest"].status == st["risk"].status == "skipped"
    assert run.backtest_run_id is None


def test_backtest_tool_rejects_changed_spec_then_accepts_canonical(env: Env) -> None:
    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if "notes" in roles(info) and turn(messages) == 0:
            args = mock.block(mock._user_prompt(messages), "BACKTEST_ARGS")
            args["spec"]["lots"] = 7  # the agent tries to change what is tested
            return ModelResponse(parts=[ToolCallPart(tool_name="run_backtest", args=args)])
        if "notes" in roles(info) and turn(messages) == 1:  # retry: copy the canonical args from the rejection
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="run_backtest", args=mock.block(mock._user_prompt(messages), "BACKTEST_ARGS")
                    )
                ]
            )
        return mock._mock(messages, info)

    run = execute(env, env.create_run(template_id="ema_crossover"), builder_with(model))
    assert run.status == "completed"
    assert steps(run)["backtest"].usage["requests"] == 3  # type: ignore[index]
    with env.maker() as s:
        rec = s.get(BacktestRun, run.backtest_run_id)
        assert rec is not None and rec.spec["lots"] == 1  # canonical spec, not the agent's


def test_backtest_agent_skipping_the_tool_falls_back_to_engine(env: Env) -> None:
    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if "notes" in roles(info):
            return call(info, {"notes": "I did not run anything"})
        return mock._mock(messages, info)

    run = execute(env, env.create_run(template_id="ema_crossover"), builder_with(model))
    bt = steps(run)["backtest"]
    assert run.status == "completed" and bt.warnings and "did not call run_backtest" in bt.warnings[0]
    assert run.backtest_run_id and bt.output and bt.output["metrics"]["num_trades"] > 0


# ---- failure handling -------------------------------------------------------------------------


def test_risk_failure_keeps_earlier_steps_and_backtest(env: Env) -> None:
    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if "red_flags" in roles(info):
            raise RuntimeError("provider exploded")
        return mock._mock(messages, info)

    run = execute(env, env.create_run(template_id="ema_crossover"), builder_with(model))
    st = steps(run)
    assert run.status == "failed" and "provider exploded" in (run.error or "")
    assert st["risk"].status == "failed" and "provider exploded" in (st["risk"].error or "")
    assert st["backtest"].status == "completed" and run.backtest_run_id  # partial results are kept
    with env.maker() as s:
        assert s.get(BacktestRun, run.backtest_run_id) is not None


def test_step_timeout(tmp_path: Path) -> None:
    env = Env(tmp_path, agent_timeout_seconds=0.2)

    async def slow(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        await asyncio.sleep(2)
        return mock._mock(messages, info)

    run = execute(env, env.create_run(template_id="ema_crossover"), builder_with(slow))
    assert run.status == "failed" and steps(run)["research"].error == "TimeoutError: step timed out"


def test_unconfigured_provider_fails_run_cleanly(tmp_path: Path) -> None:
    env = Env(tmp_path, mock_llm=False)
    run = execute(env, env.create_run(template_id="ema_crossover"))
    assert run.status == "failed" and "not configured" in (run.error or "")
    assert all(s.status == "skipped" for s in steps(run).values())


def test_crash_before_steps_marks_run_failed(env: Env) -> None:
    rid = env.create_run(template_id="ema_crossover")
    with env.maker() as s:
        row = s.get(PipelineRun, rid)
        assert row is not None
        row.dataset_id = "missing"
        s.commit()
    run = execute(env, rid)
    assert run.status == "failed" and "not found" in (run.error or "")


def test_per_agent_model_overrides(tmp_path: Path) -> None:
    env = Env(tmp_path, openai_api_key="k", risk_model="mock:demo", default_model="openai:gpt-4o")
    used: dict[str, str] = {}

    def build(settings: Settings, model_id: str) -> Model:
        used[f"{len(used)}"] = model_id
        return mock.build_mock_model()

    run = execute(env, env.create_run(template_id="ema_crossover"), build)
    assert run.status == "completed"
    assert [s.model for s in steps(run).values()] == [
        "openai:gpt-4o",
        None,
        "openai:gpt-4o",
        "openai:gpt-4o",
        "mock:demo",
    ]  # skipped step has no model
    assert list(used.values()) == [
        "openai:gpt-4o",
        "openai:gpt-4o",
        "openai:gpt-4o",
        "mock:demo",
    ]  # strategy skipped: no model built


def test_mark_interrupted(env: Env) -> None:
    running = env.create_run(template_id="ema_crossover")
    done = env.create_run(template_id="ema_crossover")
    with env.maker() as s:
        r = s.get(PipelineRun, running)
        d = s.get(PipelineRun, done)
        assert r is not None and d is not None
        r.status = "running"
        r.steps = [{**r.steps[0], "status": "running"}, *r.steps[1:]]
        d.status = "completed"
        s.commit()
    assert mark_interrupted(env.maker) == 1
    row = env.run(running)
    assert row.status == "failed" and "restart" in (row.error or "")
    assert [s["status"] for s in row.steps] == ["failed", "skipped", "skipped", "skipped", "skipped"]
    assert env.run(done).status == "completed"
