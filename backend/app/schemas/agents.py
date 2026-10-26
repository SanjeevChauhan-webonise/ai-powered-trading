from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.strategy import StrategySpec

StepName = Literal["research", "strategy", "verify", "backtest", "risk"]
StepStatus = Literal["pending", "running", "completed", "failed", "skipped"]
RunStatus = Literal["queued", "running", "completed", "failed"]
STEP_ORDER: tuple[StepName, ...] = ("research", "strategy", "verify", "backtest", "risk")


# ---- typed agent outputs -----------------------------------------------------------------------
class ResearchOutput(BaseModel):
    in_scope: bool = Field(True, description="False when the idea is not a NIFTY / BANKNIFTY options trading idea")
    refusal: str | None = Field(None, description="When in_scope is false: one calm sentence for the trader")
    concepts: list[str] = Field(description="Key concepts relevant to the idea, each one short and self-contained")
    considerations: list[str] = Field(description="Practical considerations, risks and caveats for this idea")
    sources: list[str] = Field(description="Knowledge-base source file names the points are based on")
    market_context: list[str] = Field(
        default_factory=list,
        description="Current market backdrop from recent news (mood, key events, risk days), each point short",
    )
    news_sources: list[str] = Field(
        default_factory=list, description="Publisher names (and headlines) the market_context points are based on"
    )


class StrategyDraft(BaseModel):
    spec: StrategySpec
    explanation: str = Field(description="One short paragraph: how the spec implements the user's idea")
    assumptions: list[str] = Field(
        default_factory=list, description="Defaults or choices you made that the user did not specify"
    )
    reasons: list[str] = Field(
        default_factory=list,
        description="Why each key choice was made (indicators, entry, exit, stop/target, strike, expiry, sizing), "
        "citing the RESEARCH concepts or market-news points that shaped it",
    )
    when_to_trade: str = Field(
        "", description="Plain-language summary of when this strategy takes a trade and when it stays out"
    )


class AskAnswer(BaseModel):
    in_scope: bool = Field(True, description="False when the question is not about NIFTY / BANKNIFTY options trading")
    answer: str = Field(description="A clear, direct answer; when in_scope is false, the one-sentence refusal instead")
    key_points: list[str] = Field(default_factory=list, description="Short supporting points")
    caveats: list[str] = Field(default_factory=list, description="Limits, risks or what you could not know")
    sources: list[str] = Field(default_factory=list, description="Knowledge-base file names the answer is based on")
    news_sources: list[str] = Field(default_factory=list, description="Publishers / headlines used")
    suggest_strategy_desk: bool = Field(
        False, description="True when the trader would be better served by building and backtesting a strategy"
    )


class ParsedQuery(BaseModel):
    intent: Literal["strategy", "question", "off_topic"] = Field(
        "strategy",
        description="'strategy' to build/test a trade plan, 'question' for an in-scope trading question, "
        "'off_topic' for anything outside NIFTY / BANKNIFTY options trading",
    )
    refusal: str | None = Field(None, description="When intent is off_topic: one calm sentence for the trader")
    underlying: Literal["NIFTY", "BANKNIFTY"] | None = Field(None, description="NIFTY (Nifty 50) or BANKNIFTY")
    expiry: date | None = Field(None, description="Option expiry the trader named, as an absolute date")
    capital: float | None = Field(None, description="Trading amount in rupees, as stated")
    max_loss: float | None = Field(None, description="Maximum loss per trade in rupees, as stated")
    target_profit: float | None = Field(None, description="Target profit per trade in rupees, as stated")
    preferred_indicators: list[str] = Field(
        default_factory=list, description="Indicators the trader asked for (ema, rsi, vwap, supertrend, ...)"
    )
    idea: str = Field("", description="The strategy request in plain English, keeping any indicators the trader named")
    notes: list[str] = Field(default_factory=list, description="What is missing or was ambiguous; never guess amounts")


class VerifyIssue(BaseModel):
    title: str
    severity: Literal["low", "medium", "high"]
    detail: str
    suggestion: str = Field("", description="How to fix it, if fixable")


class VerifyOutput(BaseModel):
    verdict: Literal["approved", "needs_changes", "rejected"]
    matches_idea: bool = Field(description="Does the spec actually implement what the user asked for?")
    summary: str = Field(description="Two or three sentences: is this strategy sound and why")
    checks_passed: list[str] = Field(default_factory=list, description="What was checked and found fine")
    issues: list[VerifyIssue] = Field(default_factory=list)


class BacktestNotes(BaseModel):
    notes: str = Field(
        description="One or two sentences on what was run (strategy, dataset, range) and any notable engine events"
    )


class RiskFlag(BaseModel):
    title: str
    severity: Literal["low", "medium", "high"]
    detail: str


class RiskReview(BaseModel):
    summary: str
    strengths: list[str]
    weaknesses: list[str]
    red_flags: list[RiskFlag]
    suggestions: list[str]


# ---- run request / record ----------------------------------------------------------------------
class RunRequest(BaseModel):
    dataset_id: str = Field(
        "",
        description="Dataset to test on. Leave empty and set `underlying` to use the newest dataset of that underlying",
    )
    underlying: Literal["NIFTY", "BANKNIFTY"] | None = None
    expiry: date | None = Field(
        None, description="The option expiry you plan to trade (weekly vs monthly follows from it)"
    )
    max_loss: float | None = Field(None, gt=0, description="Maximum loss per trade in rupees")
    target_profit: float | None = Field(None, gt=0, description="Target profit per trade in rupees")
    idea: str | None = Field(
        None, max_length=2000, description="Plain-English strategy idea (Strategy Agent translates it)"
    )
    template_id: str | None = None
    strategy_id: str | None = None
    spec: StrategySpec | None = None
    start: date | None = None
    end: date | None = None
    capital: float = Field(100_000.0, gt=0)
    model: str | None = Field(None, description="'provider:model'; defaults to per-agent setting, then DEFAULT_MODEL")

    @model_validator(mode="after")
    def _check(self) -> "RunRequest":
        if not self.dataset_id and not self.underlying:
            raise ValueError("Provide dataset_id, or underlying to use the newest dataset of that underlying")
        sources = sum(x is not None for x in (self.template_id, self.strategy_id, self.spec))
        if sources > 1:
            raise ValueError("Provide at most one of template_id, strategy_id, spec")
        if not (self.idea and self.idea.strip()) and sources == 0:
            raise ValueError("Provide an idea, or one of template_id / strategy_id / spec")
        if self.start and self.end and self.start > self.end:
            raise ValueError("start must be <= end")
        return self


class StepRecord(BaseModel):
    name: StepName
    status: StepStatus = "pending"
    model: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    output: dict[str, Any] | None = None
    error: str | None = None
    usage: dict[str, int] | None = None
    warnings: list[str] = Field(default_factory=list)


class RunSummary(BaseModel):
    id: str
    dataset_id: str
    status: RunStatus
    idea: str | None
    backtest_run_id: str | None
    error: str | None
    created_at: datetime
    updated_at: datetime


class RunOut(RunSummary):
    request: RunRequest
    steps: list[StepRecord]
