import re
import sqlite3
from datetime import timedelta

from rapidfuzz import fuzz

from .config import DEDUPE_SHORT_THRESHOLD, DEDUPE_THRESHOLD, DEDUPE_WINDOW_HOURS
from .db import iso, utcnow

_NON_WORD = re.compile(r"[^\w\s]+", re.UNICODE)
_WS = re.compile(r"\s+")


def normalize(title: str) -> str:
    return _WS.sub(" ", _NON_WORD.sub(" ", title.lower())).strip()


def _similar(a: str, b: str) -> bool:
    # Kisa basliklarda token_set_ratio yanlislikla 100 verebilir; daha siki olcu kullan
    if min(len(a.split()), len(b.split())) < 4:
        return fuzz.ratio(a, b) >= DEDUPE_SHORT_THRESHOLD
    return fuzz.token_set_ratio(a, b) >= DEDUPE_THRESHOLD


def assign_event(conn: sqlite3.Connection, title: str) -> int:
    """Basligi son DEDUPE_WINDOW_HOURS saatteki bir olaya baglar, yoksa yeni olay acar."""
    now = iso(utcnow())
    cutoff = iso(utcnow() - timedelta(hours=DEDUPE_WINDOW_HOURS))
    norm = normalize(title)

    rows = conn.execute(
        "SELECT id, norm_title FROM events WHERE last_seen_at >= ?", (cutoff,)
    ).fetchall()
    for row in rows:
        if _similar(norm, row["norm_title"]):
            conn.execute(
                "UPDATE events SET last_seen_at = ?, article_count = article_count + 1 WHERE id = ?",
                (now, row["id"]),
            )
            return row["id"]

    cur = conn.execute(
        "INSERT INTO events (title, norm_title, first_seen_at, last_seen_at) VALUES (?, ?, ?, ?)",
        (title, norm, now, now),
    )
    return cur.lastrowid
