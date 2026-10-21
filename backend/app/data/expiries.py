"""Real upcoming NIFTY / BANKNIFTY option expiries and lot sizes, from Upstox's public instruments file (no login).

The file lists the exchange's live contracts, so holiday-shifted expiries are right. It is downloaded at most every
TTL seconds, cached in memory and on disk, and the last good copy is used if the download fails.
"""

import gzip
import json
import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

import httpx

log = logging.getLogger(__name__)

URL = "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz"
UNDERLYINGS = ("NIFTY", "BANKNIFTY")
IST = timezone(timedelta(hours=5, minutes=30))
TTL_SECONDS = 6 * 3600


class ExpiryError(RuntimeError):
    """Expiries could not be loaded and there is no cached copy."""


@dataclass(frozen=True)
class ExpiryRow:
    date: date
    kind: Literal["weekly", "monthly"]
    days: int


@dataclass(frozen=True)
class ExpiryTable:
    fetched_at: datetime
    lot_sizes: dict[str, int]
    expiries: dict[str, dict[str, bool]]  # underlying -> ISO date -> weekly?

    def to_json(self) -> str:
        return json.dumps(
            {"fetched_at": self.fetched_at.isoformat(), "lot_sizes": self.lot_sizes, "expiries": self.expiries}
        )

    @staticmethod
    def from_json(text: str) -> "ExpiryTable":
        d = json.loads(text)
        return ExpiryTable(datetime.fromisoformat(d["fetched_at"]), d["lot_sizes"], d["expiries"])


def parse_instruments(raw: bytes, now: datetime) -> ExpiryTable:
    lots: dict[str, int] = {}
    exps: dict[str, dict[str, bool]] = {u: {} for u in UNDERLYINGS}
    for x in json.loads(gzip.decompress(raw)):
        if x.get("segment") != "NSE_FO" or x.get("instrument_type") not in ("CE", "PE"):
            continue
        u = x.get("underlying_symbol")
        if u not in exps:
            continue
        d = datetime.fromtimestamp(x["expiry"] / 1000, IST).date().isoformat()
        exps[u][d] = exps[u].get(d, False) or bool(x.get("weekly"))
        lots[u] = int(x["lot_size"])
    if not any(exps.values()):
        raise ValueError("no NIFTY/BANKNIFTY option contracts found in the instruments file")
    return ExpiryTable(now, lots, exps)


class ExpiryService:
    def __init__(
        self,
        cache_path: Path,
        *,
        client: httpx.Client | None = None,
        ttl: float = TTL_SECONDS,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.cache_path, self.ttl, self.clock = cache_path, ttl, clock
        self._client = client or httpx.Client(timeout=60.0, follow_redirects=True)
        self._table: ExpiryTable | None = None
        self._lock = threading.Lock()

    def _load_disk(self) -> ExpiryTable | None:
        try:
            return ExpiryTable.from_json(self.cache_path.read_text())
        except (OSError, ValueError, KeyError):
            return None

    def table(self, *, fetch: bool = True) -> tuple[ExpiryTable | None, bool]:
        """(table, stale). With fetch=False only cached data is used, never the network."""
        with self._lock:
            table = self._table or self._load_disk()
            if table and (self.clock() - table.fetched_at).total_seconds() < self.ttl:
                self._table = table
                return table, False
            if not fetch:
                self._table = table
                return table, table is not None
            try:
                resp = self._client.get(URL)
                resp.raise_for_status()
                fresh = parse_instruments(resp.content, self.clock())
            except (httpx.HTTPError, OSError, ValueError, KeyError, EOFError) as e:
                log.warning("could not refresh expiries: %s", e)
                self._table = table
                return table, table is not None
            self._table = fresh
            try:
                self.cache_path.parent.mkdir(parents=True, exist_ok=True)
                self.cache_path.write_text(fresh.to_json())
            except OSError as e:
                log.warning("could not write the expiry cache: %s", e)
            return fresh, False

    def upcoming(
        self, underlying: str, count: int, today: date | None = None
    ) -> tuple[list[ExpiryRow], ExpiryTable, bool]:
        table, stale = self.table()
        if table is None:
            raise ExpiryError("Could not download the exchange's expiry list and there is no cached copy")
        today = today or datetime.now(IST).date()
        rows = [
            ExpiryRow(date.fromisoformat(d), "weekly" if weekly else "monthly", (date.fromisoformat(d) - today).days)
            for d, weekly in sorted(table.expiries.get(underlying, {}).items())
            if date.fromisoformat(d) >= today
        ]
        return rows[:count], table, stale

    def kind_of(self, underlying: str, expiry: date) -> Literal["weekly", "monthly"] | None:
        """Real weekly/monthly flag for a listed expiry, from cached data only. None if unknown."""
        table, _ = self.table(fetch=False)
        flag = table.expiries.get(underlying, {}).get(expiry.isoformat()) if table else None
        return None if flag is None else ("weekly" if flag else "monthly")

    def is_listed(self, underlying: str, expiry: date) -> bool | None:
        """Whether the exchange currently lists this expiry. None if there is no cached list."""
        table, _ = self.table(fetch=False)
        return None if table is None else expiry.isoformat() in table.expiries.get(underlying, {})


_SERVICES: dict[str, ExpiryService] = {}


def get_service(storage_dir: str) -> ExpiryService:
    path = str(Path(storage_dir) / "upstox_expiries.json")
    if path not in _SERVICES:
        _SERVICES[path] = ExpiryService(Path(path))
    return _SERVICES[path]
