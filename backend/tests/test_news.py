from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from pathlib import Path
from typing import Any

import httpx
from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, ToolCallPart, UserPromptPart
from pydantic_ai.models.function import AgentInfo

from app.news.feeds import NewsFetcher, parse_feeds
from tests.pipeline_helpers import Env
from tests.test_pipeline import builder_with, call, execute, roles, steps, turn


def _rss(*items: tuple[str, str, datetime]) -> bytes:
    body = "".join(
        f"<item><title>{t}</title><description>&lt;p&gt;{d}&lt;/p&gt;</description>"
        f"<pubDate>{format_datetime(p)}</pubDate></item>"
        for t, d, p in items
    )
    return f"<rss><channel>{body}</channel></rss>".encode()


NOW = datetime.now(UTC)
FEED_A = _rss(
    ("Nifty ends higher as banks rally", "Bank Nifty gains 1% on private lenders", NOW - timedelta(hours=2)),
    ("RBI keeps repo rate unchanged", "Policy outcome in line with estimates", NOW - timedelta(days=1)),
    ("Old story", "too old", NOW - timedelta(days=30)),
)
FEED_B = _rss(("Nifty ends higher as banks rally", "duplicate headline", NOW - timedelta(hours=1)))


def _fetcher(**kw: Any) -> NewsFetcher:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "a.test":
            return httpx.Response(200, content=FEED_A)
        if request.url.host == "b.test":
            return httpx.Response(200, content=FEED_B)
        return httpx.Response(500)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    feeds = {"A": "https://a.test/rss", "B": "https://b.test/rss", "Broken": "https://c.test/rss"}
    return NewsFetcher(feeds, client=client, **kw)


def test_parse_feeds_override_and_default():
    assert parse_feeds("X=https://x/rss, Y=https://y/rss") == {"X": "https://x/rss", "Y": "https://y/rss"}
    assert "Economic Times Markets" in parse_feeds("")


def test_search_ranks_dedupes_filters_old_and_survives_broken_feed():
    items = _fetcher().search("banknifty banks outlook")
    titles = [i["title"] for i in items]
    assert titles[0] == "Nifty ends higher as banks rally" and titles.count(titles[0]) == 1
    assert "Old story" not in titles
    assert items[0]["summary"] == "Bank Nifty gains 1% on private lenders"  # html stripped


def test_no_keyword_match_falls_back_to_latest():
    items = _fetcher().search("zzzz qqqq")
    assert items and items[0]["published"] >= items[-1]["published"]


def test_feed_is_cached():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(200, content=FEED_A)

    f = NewsFetcher({"A": "https://a.test/rss"}, client=httpx.Client(transport=httpx.MockTransport(handler)))
    f.search("nifty")
    f.search("rbi")
    assert len(calls) == 1


def test_rejects_entity_declarations():
    evil = b'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY a "x">]><rss><channel><item><title>&a;</title></item></channel></rss>'
    f = NewsFetcher(
        {"E": "https://e.test/rss"},
        client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=evil))),
    )
    assert f.search("x") == []


def test_research_output_reaches_strategy_agent(tmp_path: Path):
    env = Env(tmp_path, news_enabled=False)  # tests never touch the network
    seen: dict[str, str] = {}

    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        props = roles(info)
        prompt = "".join(
            p.content for m in messages if isinstance(m, ModelRequest) for p in m.parts if isinstance(p, UserPromptPart)
        )
        if "concepts" in props:
            if turn(messages) == 0:
                return ModelResponse(parts=[ToolCallPart(tool_name="search_news", args={"query": "nifty"})])
            return call(info, {
                "concepts": ["trend"], "considerations": [], "sources": [],
                "market_context": ["Banks rallying (Mint)"], "news_sources": ["Mint Markets"],
            })  # fmt: skip
        if "spec" in props:
            seen["strategy_prompt"] = prompt
            return call(info, {"spec": _spec(), "explanation": "x", "assumptions": []})
        return _mock_rest(messages, info)

    from app.agents import mock

    def _mock_rest(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        return mock._mock(messages, info)

    def _spec() -> dict[str, Any]:
        from app.engine.templates import TEMPLATES

        return TEMPLATES["ema_crossover"].model_dump(mode="json")

    run = execute(env, env.create_run(idea="buy CE on EMA crossover"), builder=builder_with(model))
    assert run.status == "completed", run.error
    assert "RESEARCH:" in seen["strategy_prompt"] and "Banks rallying (Mint)" in seen["strategy_prompt"]
    out = steps(run)["research"].output
    assert out["market_context"] == ["Banks rallying (Mint)"]


def test_strategy_step_exposes_reasons(tmp_path: Path):
    env = Env(tmp_path, news_enabled=False)
    run = execute(env, env.create_run(idea="buy CE when 9 EMA crosses above 21 EMA"))
    out = steps(run)["strategy"].output
    assert out["reasons"] and out["when_to_trade"] and out["explanation"]


def test_verify_step_flags_bad_spec_and_does_not_block_backtest(tmp_path: Path):
    from app.agents import mock
    from app.engine.spec_check import check_spec
    from app.engine.templates import TEMPLATES

    risky = TEMPLATES["ema_crossover"].model_copy(
        update={"risk": TEMPLATES["ema_crossover"].risk.model_copy(update={"stop_loss_pct": None, "target_pct": 10})}
    )
    facts = check_spec(risky)
    assert {f.code for f in facts.flags} >= {"no_stop_loss"} and facts.reward_to_risk is None

    env = Env(tmp_path, news_enabled=False)

    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if "spec" in roles(info):
            return call(info, {"spec": risky.model_dump(mode="json"), "explanation": "x"})
        return mock._mock(messages, info)

    run = execute(env, env.create_run(idea="ema crossover"), builder=builder_with(model))
    st = steps(run)
    assert run.status == "completed" and st["backtest"].status == "completed"
    assert st["verify"].output["verdict"] == "needs_changes"
    assert any(i["title"] == "no_stop_loss" for i in st["verify"].output["issues"])
    assert st["verify"].warnings and "needs_changes" in st["verify"].warnings[0]


def test_verify_loop_sends_issues_back_to_strategy_agent(tmp_path: Path):
    from app.agents import mock
    from app.engine.templates import TEMPLATES

    base = TEMPLATES["ema_crossover"]
    risky = base.model_copy(update={"risk": base.risk.model_copy(update={"stop_loss_pct": None})})
    env = Env(tmp_path, news_enabled=False)
    strategy_prompts: list[str] = []

    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if "spec" in roles(info):
            prompt = "".join(
                p.content
                for m in messages
                if isinstance(m, ModelRequest)
                for p in m.parts
                if isinstance(p, UserPromptPart)
            )
            strategy_prompts.append(prompt)
            spec = base if "VERIFY_ISSUES:" in prompt else risky  # the revision fixes the stop loss
            return call(info, {"spec": spec.model_dump(mode="json"), "explanation": "x"})
        return mock._mock(messages, info)

    run = execute(env, env.create_run(idea="ema crossover"), builder=builder_with(model))
    v = steps(run)["verify"].output
    assert run.status == "completed" and len(strategy_prompts) == 2 and "no_stop_loss" in strategy_prompts[1]
    assert v["verdict"] == "approved" and v["revisions"] == 1
    assert [h["verdict"] for h in v["history"]] == ["needs_changes", "approved"]
    assert v["final_spec"]["risk"]["stop_loss_pct"] == base.risk.stop_loss_pct  # the backtest ran the revised spec
