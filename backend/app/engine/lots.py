"""NSE index option lot sizes by first expiry date they apply to (NSE circulars, Nov 2024 - Jan 2026)."""

from datetime import date

LOT_SCHEDULES: dict[str, list[tuple[date, int]]] = {
    "NIFTY": [(date(2024, 11, 20), 75), (date(2026, 1, 6), 65)],
    "BANKNIFTY": [(date(2024, 11, 20), 30), (date(2025, 7, 1), 35), (date(2026, 1, 27), 30)],
}
