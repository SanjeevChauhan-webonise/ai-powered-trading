from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.strategy import StrategySpec

StepName = Literal["research", "strategy", "backtest", "risk"]
StepStatus = Literal["pending", "running", "completed", "failed", "skipped"]
RunStatus = Literal["queued", "running", "completed", "failed"]
STEP_ORDER: tuple[StepName, ...] = ("research", "strategy", "backtest", "risk")


# ---- typed agent outputs -----------------------------------------------------------------------
class ResearchOutput(BaseModel):
    concepts: list[str] = Field(description="Key concepts relevant to the idea, each one short and self-contained")
    considerations: list[str] = Field(description="Practical considerations, risks and caveats for this idea")
    sources: list[str] = Field(description="Knowledge-base source file names the points are based on")


class StrategyDraft(BaseModel):
    spec: StrategySpec
    explanation: str = Field(description="One short paragraph: how the spec implements the user's idea")
    assumptions: list[str] = Field(
        default_factory=list, description="Defaults or choices you made that the user did not specify"
    )


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
    dataset_id: str
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
