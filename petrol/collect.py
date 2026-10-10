import asyncio
import sqlite3
import time

import httpx

from .config import DAILY_REFRESH_HOURS, FEEDS, POLL_INTERVAL_SEC, PREFILTER_RE, USER_AGENT
from .db import connect, iso, utcnow
from .dedupe import assign_event
from .prices import fetch_daily_closes, fetch_prices
from .sources import FetchResult, fetch_feed

FEEDS_BY_NAME = {f.name: f for f in FEEDS}
_last_daily_refresh: float | None = None


def refresh_daily_prices(conn: sqlite3.Connection, force: bool = False) -> int:
    """Gunluk kapanislari birkac saatte bir yeniler (normal gunluk hareket hesabi icin)."""
    global _last_daily_refresh
    if not force and _last_daily_refresh is not None and             time.monotonic() - _last_daily_refresh < DAILY_REFRESH_HOURS * 3600:
        return 0
    rows = fetch_daily_closes(USER_AGENT)
    if rows:
        conn.executemany(
            """INSERT INTO daily_prices (symbol, day, close) VALUES (?, ?, ?)
               ON CONFLICT(symbol, day) DO UPDATE SET close = excluded.close""",
            rows,
        )
        _last_daily_refresh = time.monotonic()
    return len(rows)


async def _fetch_all(state: dict[str, dict]) -> tuple[list[FetchResult], list[tuple[str, str, float]]]:
    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT}, timeout=20, follow_redirects=True
    ) as client:
        feed_tasks = [
            fetch_feed(client, f, state.get(f.name, {}).get("etag"), state.get(f.name, {}).get("last_modified"))
            for f in FEEDS
        ]
        results = await asyncio.gather(*feed_tasks)
        prices = await fetch_prices(client)
    return list(results), prices


def _save_feed(conn: sqlite3.Connection, res: FetchResult, first_run: bool, seen_at: str) -> tuple[int, int]:
    """Yeni haberleri yazar. (yeni, on_filtreden_gecen) sayilarini dondurur."""
    feed = FEEDS_BY_NAME[res.feed]
    new = passed = 0
    for item in res.items:
        if conn.execute("SELECT 1 FROM articles WHERE url = ?", (item.url,)).fetchone():
            continue
        passes = not feed.prefilter or bool(PREFILTER_RE.search(f"{item.title} {item.summary}"))
        event_id = assign_event(conn, item.title) if passes else None
        conn.execute(
            """INSERT INTO articles (feed, publisher, title, url, summary, published_at, first_seen_at,
                                     initial, prefilter_pass, event_id, triage_status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                item.feed,
                item.publisher,
                item.title,
                item.url,
                item.summary,
                iso(item.published_at) if item.published_at else None,
                seen_at,
                int(first_run),
                int(passes),
                event_id,
                "pending" if passes else "skipped",
            ),
        )
        new += 1
        passed += int(passes)
    return new, passed


def collect_once(conn: sqlite3.Connection) -> dict:
    state = {r["feed"]: dict(r) for r in conn.execute("SELECT * FROM feed_state")}
    results, prices = asyncio.run(_fetch_all(state))
    seen_at = iso(utcnow())

    stats = {"new": 0, "passed": 0, "errors": [], "prices": len(prices)}
    for res in results:
        if res.error:
            conn.execute(
                """INSERT INTO feed_state (feed, last_error) VALUES (?, ?)
                   ON CONFLICT(feed) DO UPDATE SET last_error = excluded.last_error""",
                (res.feed, res.error),
            )
            stats["errors"].append(f"{res.feed}: {res.error}")
            continue
        first_run = not state.get(res.feed, {}).get("last_ok_at")
        new, passed = _save_feed(conn, res, first_run, seen_at)
        stats["new"] += new
        stats["passed"] += passed
        conn.execute(
            """INSERT INTO feed_state (feed, etag, last_modified, last_ok_at, last_error)
               VALUES (?, ?, ?, ?, NULL)
               ON CONFLICT(feed) DO UPDATE SET etag = excluded.etag, last_modified = excluded.last_modified,
                                               last_ok_at = excluded.last_ok_at, last_error = NULL""",
            (res.feed, res.etag, res.last_modified, seen_at),
        )

    # Son dakika cubugu tamamlanmadan gelir; sonraki turlarda kesinlesen degerle guncelle
    conn.executemany(
        """INSERT INTO prices (symbol, ts, price) VALUES (?, ?, ?)
           ON CONFLICT(symbol, ts) DO UPDATE SET price = excluded.price""",
        prices,
    )
    stats["daily"] = refresh_daily_prices(conn)
    conn.commit()
    return stats


def run(once: bool = False, interval: int = POLL_INTERVAL_SEC) -> None:
    conn = connect()
    while True:
        started = time.monotonic()
        stats = collect_once(conn)
        print(
            f"[{iso(utcnow())}] yeni={stats['new']} filtreden_gecen={stats['passed']} "
            f"fiyat_noktasi={stats['prices']} hata={len(stats['errors'])}",
            flush=True,
        )
        for err in stats["errors"]:
            print(f"   ! {err}", flush=True)
        if once:
            break
        time.sleep(max(0.0, interval - (time.monotonic() - started)))
