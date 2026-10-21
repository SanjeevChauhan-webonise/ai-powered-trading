import json
from datetime import date
from typing import Any

from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.agent import AgentRetries

from app.agents import prompts
from app.agents.deps import AgentDeps
from app.rag.retriever import search
from app.schemas.agents import BacktestNotes, ResearchOutput, RiskReview, StrategyDraft
from app.schemas.strategy import StrategySpec

RETRIES = AgentRetries(tools=2, output=3)


def search_knowledge(ctx: RunContext[AgentDeps], query: str, k: int = 4) -> list[dict[str, Any]]:
    """Search the options/strategy knowledge base. Returns passages with their source file and heading."""
    hits = search(ctx.deps.store, ctx.deps.embedder, query, max(1, min(k, 8)))
    return [{"source": h.source, "heading": h.heading, "score": h.score, "text": h.text} for h in hits]


research_agent = Agent(
    output_type=ResearchOutput,
    deps_type=AgentDeps,
    instructions=prompts.RESEARCH_INSTRUCTIONS,
    tools=[search_knowledge],
    retries=RETRIES,
    name="research_agent",
)

strategy_agent = Agent(
    output_type=StrategyDraft,
    deps_type=AgentDeps,
    instructions=prompts.STRATEGY_INSTRUCTIONS,
    tools=[search_knowledge],
    retries=RETRIES,
    name="strategy_agent",
)


@strategy_agent.instructions
def _dataset_context(ctx: RunContext[AgentDeps]) -> str:
    return f"Dataset to be tested: {ctx.deps.dataset_summary}"


@strategy_agent.output_validator
def _check_timeframe(ctx: RunContext[AgentDeps], draft: StrategyDraft) -> StrategyDraft:
    tf, base = draft.spec.timeframe_minutes, ctx.deps.dataset_timeframe_minutes
    if tf is not None and base is not None and (tf <= base or tf % base != 0):
        raise ModelRetry(
            f"timeframe_minutes={tf} is invalid for a {base}-minute dataset: it must be a multiple of {base} "
            f"and larger than {base}. Choose a valid value or omit timeframe_minutes."
        )
    return draft


backtest_agent = Agent(
    output_type=BacktestNotes,
    deps_type=AgentDeps,
    instructions=prompts.BACKTEST_INSTRUCTIONS,
    retries=RETRIES,
    name="backtest_agent",
)


@backtest_agent.tool
def run_backtest(
    ctx: RunContext[AgentDeps], spec: StrategySpec, dataset_id: str, start: date | None = None, end: date | None = None
) -> dict[str, Any]:
    """Run the deterministic backtest engine. Arguments must be exactly those given in the prompt."""
    deps = ctx.deps
    assert deps.canonical is not None and deps.run_engine is not None
    c = deps.canonical
    if spec != c.spec or dataset_id != c.dataset_id or start != c.start or end != c.end:
        args = {
            "spec": c.spec.model_dump(mode="json"),
            "dataset_id": c.dataset_id,
            "start": c.start.isoformat() if c.start else None,
            "end": c.end.isoformat() if c.end else None,
        }
        raise ModelRetry(
            "Arguments differ from the approved backtest. Call run_backtest again with exactly these arguments: "
            + json.dumps(args)
        )
    result = deps.run_engine(c.spec, c.start, c.end)
    deps.result = result
    first = [
        {
            "entry_time": t.entry_time.isoformat(),
            "option": f"{t.strike:g}{t.option_type}",
            "net_pnl": t.net_pnl,
            "exit": t.exit_reason,
        }
        for t in result.trades[:5]
    ]
    return {
        "metrics": result.metrics.model_dump(exclude={"daily_pnl"}),
        "trades": len(result.trades),
        "engine_events": len(result.events),
        "first_trades": first,
    }


risk_agent = Agent(
    output_type=RiskReview,
    deps_type=AgentDeps,
    instructions=prompts.RISK_INSTRUCTIONS,
    tools=[search_knowledge],
    retries=RETRIES,
    name="risk_agent",
)
