"""Analizden once: farkli kelimelerle yazilmis ayni olaylari tek olayda birlestirir."""
import sqlite3
from datetime import timedelta

from pydantic import BaseModel, ConfigDict

from .config import DAILY_TOKEN_BUDGET, MERGE_MODEL
from .db import iso, tokens_last_24h, utcnow
from .llm import LLMClient

SYSTEM = """You deduplicate oil-market news events. Each CANDIDATE may describe the same concrete
occurrence as an EXISTING event or as an earlier-listed CANDIDATE.

Same occurrence = the same decision, attack, statement, deal or data release, even if worded
differently or written from a commentary angle ("will it lower prices?", "diesel is still the problem").
A new development in the same story (another attack, a follow-up decision, a reaction by another
party) is a DISTINCT occurrence.

For every candidate return duplicate_of = the id of the EXISTING event it duplicates (preferred),
or of an EARLIER-listed candidate; null if it is distinct. Use numeric ids (E42 -> 42)."""


class MergeItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: int
    duplicate_of: int | None


class MergeResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[MergeItem]


def _describe(conn: sqlite3.Connection, event_id: int, title: str) -> str:
    others = conn.execute(
        """SELECT DISTINCT title FROM articles WHERE event_id = ? AND triage_status = 'relevant' AND title != ?
           LIMIT 2""",
        (event_id, title),
    ).fetchall()
    extra = "".join(f" || {o['title']}" for o in others)
    return f"E{event_id}: {title}{extra}"


def _merge_into(conn: sqlite3.Connection, dup: int, target: int) -> None:
    moved = conn.execute("UPDATE articles SET event_id = ? WHERE event_id = ?", (target, dup)).rowcount
    conn.execute(
        """UPDATE events SET article_count = article_count + ?, last_seen_at = ?,
                  importance = MAX(COALESCE(importance, 0), (SELECT COALESCE(importance, 0) FROM events WHERE id = ?))
           WHERE id = ?""",
        (moved, iso(utcnow()), dup, target),
    )
    conn.execute("UPDATE events SET article_count = 0, analysis_status = 'merged' WHERE id = ?", (dup,))


def run_merge(conn: sqlite3.Connection, client: LLMClient) -> int:
    candidates = conn.execute(
        """SELECT id, title FROM events WHERE relevant = 1 AND analysis_status = 'none'
           ORDER BY first_seen_at LIMIT 30"""
    ).fetchall()
    since = iso(utcnow() - timedelta(hours=24))
    existing = conn.execute(
        """SELECT e.id, e.title FROM events e JOIN analyses a ON a.event_id = e.id
           WHERE e.analysis_status = 'done' AND e.last_seen_at >= ? ORDER BY e.last_seen_at DESC LIMIT 30""",
        (since,),
    ).fetchall()
    if not candidates or (len(candidates) == 1 and not existing):
        return 0
    if tokens_last_24h(conn, MERGE_MODEL) >= DAILY_TOKEN_BUDGET:
        return 0

    prompt = "EXISTING EVENTS:\n" + ("\n".join(_describe(conn, e["id"], e["title"]) for e in existing) or "(none)")
    prompt += "\n\nCANDIDATES:\n" + "\n".join(_describe(conn, c["id"], c["title"]) for c in candidates)
    result = client.chat_json(MERGE_MODEL, SYSTEM, prompt, MergeResult, stage="merge", reasoning_effort="low")

    existing_ids = {e["id"] for e in existing}
    order = [c["id"] for c in candidates]
    resolved: dict[int, int] = {}  # aday -> nihai hedef
    by_id = {i.event_id: i.duplicate_of for i in result.items}
    for pos, cid in enumerate(order):
        target = by_id.get(cid)
        if target in existing_ids:
            resolved[cid] = target
        elif target in order[:pos]:
            # Zincir: hedef aday baska bir yere birlestiyse oraya git
            resolved[cid] = resolved.get(target, target)
    for dup, target in resolved.items():
        _merge_into(conn, dup, target)
    conn.commit()
    return len(resolved)
