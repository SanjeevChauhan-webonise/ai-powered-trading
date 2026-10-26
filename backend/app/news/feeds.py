"""Recent market news from public RSS feeds of trading / investing websites (no API key, headlines + summaries only)."""

import html
import logging
import re
import threading
import time
import xml.etree.ElementTree as ET
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from app.guardrails.text import looks_like_injection

log = logging.getLogger(__name__)

DEFAULT_FEEDS = {
    "Economic Times Markets": "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
    "Mint Markets": "https://www.livemint.com/rss/markets",
    "Business Standard Markets": "https://www.business-standard.com/rss/markets-106.rss",
    "Moneycontrol Market Reports": "https://www.moneycontrol.com/rss/marketreports.xml",
    "Investing.com India": "https://in.investing.com/rss/news_25.rss",
}
MAX_FEED_BYTES = 2_000_000
SUMMARY_CHARS = 300
_STOP = {"the", "and", "for", "with", "when", "that", "this", "from", "into", "buy", "sell", "idea", "trade"}
_TAG = re.compile(r"<[^>]+>")


def parse_feeds(spec: str) -> dict[str, str]:
    """'Name=url,Name2=url2' -> dict. Empty -> DEFAULT_FEEDS."""
    pairs = [p.split("=", 1) for p in spec.split(",") if "=" in p]
    return {n.strip(): u.strip() for n, u in pairs if n.strip() and u.strip()} or dict(DEFAULT_FEEDS)


def _clean(text: str | None) -> str:
    return re.sub(r"\s+", " ", html.unescape(_TAG.sub(" ", text or ""))).strip()


def _parse(source: str, content: bytes) -> list[dict[str, Any]]:
    if b"<!DOCTYPE" in content[:2000].upper() or b"<!ENTITY" in content.upper():
        raise ValueError("DTD/entity declarations are not accepted")
    out = []
    for item in ET.fromstring(content).iter("item"):
        title = _clean(item.findtext("title"))
        if not title:
            continue
        if looks_like_injection(f"{title} {item.findtext('description') or ''}"):
            log.warning(
                "dropped a news item that looks like prompt injection",
                extra={"event": "news_injection", "source": source},
            )
            continue
        try:
            published = parsedate_to_datetime(item.findtext("pubDate") or "")
            published = published.astimezone(UTC) if published.tzinfo else published.replace(tzinfo=UTC)
        except (TypeError, ValueError):
            published = None
        out.append(
            {
                "source": source,
                "title": title,
                "published": published,
                "summary": _clean(item.findtext("description"))[:SUMMARY_CHARS],
            }
        )
    return out


class NewsFetcher:
    """Fetches the configured feeds (cached for `ttl` seconds) and returns the items matching a query."""

    def __init__(
        self,
        feeds: dict[str, str] | None = None,
        *,
        max_age_days: int = 3,
        ttl: float = 600.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.feeds = feeds or dict(DEFAULT_FEEDS)
        self.max_age = timedelta(days=max_age_days)
        self.ttl = ttl
        self._client = client or httpx.Client(
            timeout=10.0, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"}
        )
        self._cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
        self._lock = threading.Lock()

    def _feed(self, source: str, url: str) -> list[dict[str, Any]]:
        with self._lock:
            hit = self._cache.get(url)
            if hit and time.monotonic() - hit[0] < self.ttl:
                return hit[1]
        try:
            resp = self._client.get(url)
            resp.raise_for_status()
            items = _parse(source, resp.content[:MAX_FEED_BYTES])
        except (httpx.HTTPError, ET.ParseError, ValueError) as e:  # one bad feed must not break the others
            log.warning("news feed %s failed: %s", source, e)
            items = []
        with self._lock:
            self._cache[url] = (time.monotonic(), items)
        return items

    def search(self, query: str, limit: int = 8) -> list[dict[str, Any]]:
        """Newest-first items from the last `max_age_days`; ranked by query-word matches, else just the latest."""
        cutoff = datetime.now(UTC) - self.max_age
        items = [
            i
            for source, url in self.feeds.items()
            for i in self._feed(source, url)
            if i["published"] is None or i["published"] >= cutoff
        ]
        unique = list({i["title"].lower(): i for i in reversed(items)}.values())  # dedupe by headline
        words = {w for w in re.findall(r"[a-z0-9]+", query.lower()) if len(w) >= 3 and w not in _STOP}

        def score(i: dict[str, Any]) -> int:
            text = f"{i['title']} {i['summary']}".lower()
            return sum(w in text for w in words)

        floor = datetime.min.replace(tzinfo=UTC)
        ranked = sorted(unique, key=lambda i: (score(i), i["published"] or floor), reverse=True)
        matched = [i for i in ranked if score(i) > 0] or sorted(
            unique, key=lambda i: i["published"] or floor, reverse=True
        )
        return [{**i, "published": i["published"].isoformat() if i["published"] else None} for i in matched[:limit]]
