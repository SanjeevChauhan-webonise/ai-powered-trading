"""Offline scripted model ("mock:demo", enabled with ENABLE_MOCK_LLM=true).

Lets the whole pipeline (agents, tools, retries, persistence, SSE) run without any API key or network. It is
deterministic: it calls the same tools a real model would and builds its outputs from tool results and from the
JSON blocks in the prompts. It is a demo/testing aid, not an LLM.
"""

import json
import re
from typing import Any

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.engine.templates import TEMPLATES


def block(prompt: str, label: str) -> Any:
    """Parse the JSON in a fenced block that follows '<label>:' in a prompt."""
    m = re.search(rf"{label}:\s*```json\s*(.*?)\s*```", prompt, re.S)
    if not m:
        raise ValueError(f"mock model: block '{label}' not found in prompt")
    return json.loads(m.group(1))


def _user_prompt(messages: list[ModelMessage]) -> str:
    for msg in messages:
        if isinstance(msg, ModelRequest):
            for part in msg.parts:
                if isinstance(part, UserPromptPart) and isinstance(part.content, str):
                    return part.content
    return ""


def _tool_results(messages: list[ModelMessage]) -> list[Any]:
    return [
        p.content for m in messages if isinstance(m, ModelRequest) for p in m.parts if isinstance(p, ToolReturnPart)
    ]


def _call(name: str, args: dict[str, Any]) -> ModelResponse:
    return ModelResponse(parts=[ToolCallPart(tool_name=name, args=args)])


_OFF_TOPIC = re.compile(
    r"\b(poem|recipe|biryani|joke|python|javascript|bitcoin|crypto|ethereum|weather|cricket|election|movie|"
    r"ignore (all |your |the )?(previous |prior )?(instructions|rules)|system prompt|you are now)\b",
    re.I,
)
_REFUSAL = (
    "This tool only handles NIFTY and BANKNIFTY options trading. "
    "Ask me about a strategy, a backtest or an option concept."
)


def off_topic(text: str) -> bool:
    return bool(_OFF_TOPIC.search(text)) or not text.strip("?!. \n")


def _mock(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    out = info.output_tools[0]
    props = set(out.parameters_json_schema.get("properties", {}))
    prompt = _user_prompt(messages)
    returns = _tool_results(messages)

    if "concepts" in props:  # research
        if not returns and off_topic(prompt.split(":", 1)[-1]):
            return _call(
                out.name, {"in_scope": False, "refusal": _REFUSAL, "concepts": [], "considerations": [], "sources": []}
            )
        if not returns:
            query = re.sub(r"\s+", " ", prompt.split(":", 1)[-1]).strip()[:200] or "options strategy"
            return _call("search_knowledge", {"query": query, "k": 4})
        hits: list[dict[str, Any]] = returns[-1]
        return _call(
            out.name,
            {
                "concepts": list(dict.fromkeys(h["heading"] for h in hits if h["heading"]))[:5],
                "considerations": [
                    "(mock) Review the cited passages before relying on this idea; no LLM analysis was performed."
                ],
                "sources": list(dict.fromkeys(h["source"] for h in hits)),
            },
        )

    if "answer" in props:  # ask
        if not returns and off_topic(prompt.split("Trader question:", 1)[-1]):
            return _call(out.name, {"in_scope": False, "answer": _REFUSAL})
        if not returns:
            q = prompt.split("Trader question:", 1)[-1].strip()[:200] or "options"
            return _call("search_knowledge", {"query": q, "k": 3})
        found: list[dict[str, Any]] = returns[-1]
        return _call(
            out.name,
            {
                "answer": "(mock) " + (found[0]["text"][:300] if found else "Nothing relevant was found."),
                "key_points": list(dict.fromkeys(h["heading"] for h in found if h["heading"]))[:4],
                "caveats": ["(mock) Scripted retrieval only; no LLM analysis was performed."],
                "sources": list(dict.fromkeys(h["source"] for h in found)),
            },
        )

    if "max_loss" in props:  # intake: a crude regex parse, no language understanding
        text = prompt.split("Trader request:", 1)[-1]
        lower = text.lower()
        if off_topic(text):
            return _call(
                out.name, {"intent": "off_topic", "refusal": _REFUSAL, "idea": "", "notes": ["(mock) Out of scope."]}
            )
        num = r"(\d[\d,]*(?:\.\d+)?)\s*(k|lakh)?"

        def amount(*words: str) -> float | None:
            m = re.search(rf"(?:{'|'.join(words)})\D{{0,12}}{num}", lower)
            if not m:
                return None
            return float(m.group(1).replace(",", "")) * {"k": 1_000, "lakh": 100_000}.get(m.group(2) or "", 1)

        under = "BANKNIFTY" if re.search(r"bank\s*nifty", lower) else "NIFTY" if "nifty" in lower else None
        is_question = bool(re.match(r"\s*(what|why|how|explain|kya|kaise|kyun)\b", lower)) or lower.rstrip().endswith(
            "?"
        )
        indicators = [i for i in ("ema", "rsi", "vwap", "supertrend", "macd", "bollinger") if i in lower]
        return _call(
            out.name,
            {
                "underlying": under,
                "capital": amount("capital", "amount"),
                "max_loss": amount("loss"),
                "target_profit": amount("target"),
                "intent": "question" if is_question else "strategy",
                "preferred_indicators": indicators,
                "idea": text.strip(),
                "notes": ["(mock) Regex parse only; check every field."],
            },
        )

    if "verdict" in props:  # verify
        facts = block(prompt, "SPEC_FACTS")
        issues = [
            {"title": f["code"], "severity": f["severity"], "detail": f["message"], "suggestion": ""}
            for f in facts["flags"]
        ]
        high = any(i["severity"] == "high" for i in issues)
        return _call(
            out.name,
            {
                "verdict": "needs_changes" if high else "approved",
                "matches_idea": True,
                "summary": "(mock) Verdict derived only from the code-computed spec flags; no LLM judgement.",
                "checks_passed": ["(mock) Spec validated by the schema."],
                "issues": issues,
            },
        )

    if "spec" in props:  # strategy
        idea = prompt.split("User idea:", 1)[-1].split("RESEARCH:", 1)[0].split("STARTING_SPEC:", 1)[0].strip().lower()
        if "PREVIOUS_SPEC:" in prompt:
            spec, how = block(prompt, "PREVIOUS_SPEC"), "kept the previous spec (no revision logic)"
        elif "STARTING_SPEC:" in prompt:
            spec, how = block(prompt, "STARTING_SPEC"), "kept the provided starting spec"
        else:
            key = "rsi_reversal" if "rsi" in idea else "ema_crossover"
            spec, how = TEMPLATES[key].model_dump(mode="json"), f"mapped the idea to the '{key}' template"
        return _call(
            out.name,
            {
                "spec": spec,
                "explanation": f"(mock) The offline mock model {how}; no LLM was used.",
                "assumptions": ["(mock) All parameters are the template defaults."],
                "reasons": [f"(mock) {how}; no reasoning was performed."],
                "when_to_trade": "(mock) See the entry rules in the spec.",
            },
        )

    if "notes" in props:  # backtest
        if not returns:
            return _call("run_backtest", block(prompt, "BACKTEST_ARGS"))
        res = returns[-1]
        note = f"(mock) Ran the approved backtest: {res['trades']} trades, {res['engine_events']} engine events."
        return _call(out.name, {"notes": note})

    # risk review
    if not returns:
        return _call("search_knowledge", {"query": "backtesting pitfalls overfitting risk management", "k": 3})
    data = block(prompt, "BACKTEST_FACTS")
    m, facts = data["metrics"], data["facts"]
    strengths = [f"Net P&L {m['total_pnl']} over {facts['num_trades']} trades."] if m["total_pnl"] > 0 else []
    weaknesses = [f"Max drawdown {m['max_drawdown_pct']}% of peak equity."]
    return _call(
        out.name,
        {
            "summary": "(mock) Deterministic summary of the rule-based flags; no LLM judgement was applied.",
            "strengths": strengths,
            "weaknesses": weaknesses,
            "red_flags": [
                {"title": f["code"], "severity": f["severity"], "detail": f["message"]} for f in facts["flags"]
            ],
            "suggestions": ["(mock) Compare nearby parameter values and higher slippage on a longer, real dataset."],
        },
    )


def build_mock_model() -> FunctionModel:
    return FunctionModel(_mock, model_name="demo")
