import calendar
import html
import re
from dataclasses import dataclass
from datetime import datetime, timezone

import feedparser
import httpx

from .config import Feed

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


@dataclass
class Item:
    feed: str
    publisher: str | None
    title: str
    url: str
    summary: str
    published_at: datetime | None


@dataclass
class FetchResult:
    feed: str
    items: list[Item]
    etag: str | None = None
    last_modified: str | None = None
    not_modified: bool = False
    error: str | None = None


def _clean(text: str, limit: int = 600) -> str:
    text = html.unescape(_TAG_RE.sub(" ", text or ""))
    return _WS_RE.sub(" ", text).strip()[:limit]


def _published(entry) -> datetime | None:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if not parsed:
        return None
    return datetime.fromtimestamp(calendar.timegm(parsed), tz=timezone.utc)


def _strip_publisher(title: str, publisher: str | None) -> str:
    # Google News basliklari "Baslik - Yayinci" bicimindedir
    if publisher and title.endswith(f" - {publisher}"):
        return title[: -len(publisher) - 3].strip()
    return title


async def fetch_feed(
    client: httpx.AsyncClient, feed: Feed, etag: str | None, last_modified: str | None
) -> FetchResult:
    headers = {}
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified
    try:
        resp = await client.get(feed.url, headers=headers)
        if resp.status_code == 304:
            return FetchResult(feed.name, [], etag, last_modified, not_modified=True)
        resp.raise_for_status()
    except Exception as exc:  # ag hatasi tum turu tek kaynakta yutulur, digerleri devam eder
        return FetchResult(feed.name, [], error=f"{type(exc).__name__}: {str(exc)[:120]}")

    parsed = feedparser.parse(resp.content)
    items: list[Item] = []
    for entry in parsed.entries:
        url = entry.get("link")
        title = _clean(entry.get("title", ""), 300)
        if not url or not title:
            continue
        publisher = (entry.get("source") or {}).get("title")
        items.append(
            Item(
                feed=feed.name,
                publisher=publisher,
                title=_strip_publisher(title, publisher),
                url=url,
                summary=_clean(entry.get("summary", "")),
                published_at=_published(entry),
            )
        )
    return FetchResult(
        feed.name,
        items,
        resp.headers.get("etag"),
        resp.headers.get("last-modified"),
    )
