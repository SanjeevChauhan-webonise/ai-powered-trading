"""Budget guards against runaway use (OWASP "unbounded consumption"): a per-user rate limit on model calls, a cap on runs
in progress and a daily cap on runs, plus hard sanity limits on the risk a trader may ask for."""

import threading
import time
from collections import deque
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.models import PipelineRun

# Largest max loss per trade, as % of capital, accepted for each experience level. Above it the request is refused.
HARD_MAX_RISK_PCT = {"beginner": 5.0, "advanced": 10.0, "expert": 25.0}
MAX_TARGET_TO_CAPITAL = 5.0


class SlidingWindow:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str, limit: int, window: float, now: float | None = None) -> float | None:
        """Record a hit. Returns None when allowed, else the seconds to wait."""
        now = time.monotonic() if now is None else now
        with self._lock:
            q = self._hits.setdefault(key, deque())
            while q and now - q[0] >= window:
                q.popleft()
            if len(q) >= limit:
                return max(0.0, window - (now - q[0]))
            q.append(now)
            return None


_LLM = SlidingWindow()


def throttle_llm(user_id: str, settings: Settings) -> None:
    """429 when the user makes more than `llm_calls_per_minute` model-backed requests in a minute."""
    wait = _LLM.hit(user_id, settings.llm_calls_per_minute, 60.0)
    if wait is not None:
        raise HTTPException(
            429, f"Too many requests. Please wait {int(wait) + 1} seconds.", headers={"Retry-After": str(int(wait) + 1)}
        )


def check_run_quota(db: Session, user_id: str, settings: Settings) -> None:
    """429 when too many runs are in progress or the daily cap is used up."""
    active = db.scalar(
        select(func.count()).select_from(PipelineRun).where(
            PipelineRun.user_id == user_id, PipelineRun.status.in_(("queued", "running"))
        )
    )  # fmt: skip
    if (active or 0) >= settings.max_active_runs_per_user:
        raise HTTPException(429, "You already have runs in progress. Wait for them to finish before starting another.")
    since = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=24)
    today = db.scalar(
        select(func.count())
        .select_from(PipelineRun)
        .where(PipelineRun.user_id == user_id, PipelineRun.created_at >= since)
    )
    if (today or 0) >= settings.runs_per_day:
        raise HTTPException(429, f"Daily limit of {settings.runs_per_day} strategy runs reached. Try again tomorrow.")


def risk_limit_problem(level: str, capital: float, max_loss: float | None, target_profit: float | None) -> str | None:
    """A message when the rupee limits are unreasonable for the level, else None."""
    if max_loss is not None:
        if max_loss > capital:
            return f"Max loss per trade (Rs {max_loss:,.0f}) is more than your capital (Rs {capital:,.0f})."
        limit = HARD_MAX_RISK_PCT.get(level, 10.0)
        pct = max_loss / capital * 100
        if pct > limit:
            return (
                f"Max loss per trade is {pct:.1f}% of your capital, above the {limit:g}% limit for the {level} level. "
                f"Lower it to about Rs {capital * limit / 100:,.0f}, or change your level in Settings."
            )
    if target_profit is not None and target_profit > capital * MAX_TARGET_TO_CAPITAL:
        return f"Target per trade (Rs {target_profit:,.0f}) is more than {MAX_TARGET_TO_CAPITAL:g} times your capital. Check the number."
    return None
