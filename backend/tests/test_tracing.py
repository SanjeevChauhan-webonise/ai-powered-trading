import asyncio
from collections.abc import Iterator
from pathlib import Path

import pytest
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.agents.orchestrator import Pipeline
from app.core import tracing
from app.core.config import Settings
from tests.pipeline_helpers import Env


@pytest.fixture(autouse=True)
def _reset() -> Iterator[None]:
    yield
    tracing.reset_tracing()


def test_tracing_disabled_without_keys() -> None:
    assert tracing.tracing_enabled(Settings()) is False
    assert tracing.setup_tracing(Settings(langfuse_public_key="pk")) is False  # needs both keys
    assert tracing._provider is None


def test_tracing_enabled_with_both_keys() -> None:
    s = Settings(langfuse_public_key="pk", langfuse_secret_key="sk", langfuse_host="http://localhost:1")
    assert tracing.tracing_enabled(s) and tracing.setup_tracing(s) is True


def test_pipeline_emits_one_trace_tagged_with_run_id(tmp_path: Path) -> None:
    exporter = InMemorySpanExporter()
    assert tracing.setup_tracing(Settings(), processor=SimpleSpanProcessor(exporter)) is True
    env = Env(tmp_path)
    run_id = env.create_run(idea="ema crossover")
    asyncio.run(Pipeline(env.settings, env.maker, env.store, env.embedder).execute(run_id))
    assert env.run(run_id).status == "completed"

    spans = exporter.get_finished_spans()
    root = next(s for s in spans if s.name == "pipeline_run")
    assert root.attributes is not None
    assert root.attributes["run_id"] == run_id and root.attributes["langfuse.session.id"] == run_id
    assert "ai-powered-trading" in root.attributes["langfuse.trace.tags"]
    assert {s.context.trace_id for s in spans if s.context} == {
        root.context.trace_id if root.context else 0
    }  # one trace
    agent_spans = [s for s in spans if s.name.startswith("invoke_agent")]
    assert {s.attributes["gen_ai.agent.name"] for s in agent_spans if s.attributes} == {
        "research_agent", "strategy_agent", "verify_agent", "backtest_agent", "risk_agent",
    }  # fmt: skip
    assert any(s.name.startswith("execute_tool") for s in spans)  # tool calls (search_knowledge / run_backtest)
