"""Asama 1: ucuz model ile eleme, onem puani ve anlamsal olay eslestirme."""
import sqlite3
from collections.abc import Mapping, Sequence
from datetime import timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .config import (
    ANALYZE_MIN_IMPORTANCE,
    DAILY_TOKEN_BUDGET,
    MAX_LLM_ATTEMPTS,
    TRIAGE_BATCH,
    TRIAGE_MAX_AGE_HOURS,
    TRIAGE_MODEL,
    TRIAGE_REASONING,
)
from .db import iso, tokens_last_24h, utcnow
from .kategoriler import ANALIZ_ZORUNLU, KATEGORILER, kategori_listesi
from .llm import LLMClient, LLMError, RateLimited

SYSTEM = """You screen news for an oil-market monitoring system. For each article decide:

relevant: true if the news could plausibly move global crude prices (Brent/WTI) within hours to weeks:
supply disruptions or restorations (production, pipelines, refineries, shipping, chokepoints such as
Hormuz or the Red Sea), OPEC+ or producer decisions, sanctions, wars/ceasefires/escalation involving
producers or shipping routes, strategic reserve releases, export bans, statements by leaders or
ministers on energy or war, inventory data, major demand or macro shocks (China, recession, Fed).
false for: retail or local pump-price updates, consumer advice, company earnings without supply
impact, opinion pieces on domestic politics, conflicts with no link to oil supply or shipping,
multi-topic news roundups/digests, stock-market wraps.
Statements by heads of state or government, ministers or governments about a war or conflict that
involves oil producers or shipping routes ARE relevant even if the headline never mentions oil:
accepting or rejecting a deal or peace proposal, ruling talks in or out, vowing to fight on, urging
an ally to stop attacks, announcing or ruling out military action. Markets trade these directly.

price_report: true if the headline mainly reports a market/price move ("Oil rises 3% on ...",
"Oil prices fall as ...", "Brent tops $100"), even when it names a cause. false for headlines that
report the underlying event itself ("Saudi Arabia shuts pipeline after drone attack").

kategori: the best matching category of the underlying news:
{kategoriler}

importance: 1-5 expected market significance of the underlying news. 5 = major supply/geopolitical
shock or official producer decision; 3 = notable development; 1 = marginal. Irrelevant articles get 1.
Such leader/government statements on war, peace or supply are at least 3; 4 when they accept or
reject a deal or announce/rule out military action.

event_ref: if the article reports the SAME concrete occurrence or statement as an item in RECENT
EVENTS, give that event's numeric id (E42 -> 42). Same topic is not enough. Otherwise null.

same_as_article: if event_ref is null but the article reports the same occurrence as ANOTHER article
in this list, give that other article's numeric id (A17 -> 17); use the same id for all articles
of that occurrence. Otherwise null.

Return exactly one item per article, using the article's numeric id (A17 -> 17)."""

# Fiyat haberi = piyasa zaten tepki verdi; kaynak sayisina katkı yapar ama derin analize girmez
PRICE_REPORT_MAX_IMPORTANCE = 2
SYSTEM = SYSTEM.replace("{kategoriler}", kategori_listesi(referansli=False))


class TriageItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: int
    relevant: bool
    price_report: bool
    kategori: Literal[tuple(KATEGORILER)]
    importance: int = Field(ge=1, le=5)
    event_ref: int | None
    same_as_article: int | None


class TriageResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[TriageItem]


def effective_importance(item: TriageItem) -> int:
    """Fiyat haberi derin analize girmez; savas/diplomasi/arz kategorilerindeki ilgili haber mutlaka girer.

    Eylul testinde 20b, lider ve diplomasi haberlerine dusuk onem verip eledi; Subat-Agustos verisinde ise
    buyuk hareketlerin %60'inda bir lider/bakan beyani belirleyiciydi. Bu yuzden alt sinir kodla konur.
    """
    if item.price_report:
        return min(item.importance, PRICE_REPORT_MAX_IMPORTANCE)
    if item.relevant and item.kategori in ANALIZ_ZORUNLU:
        return max(item.importance, ANALYZE_MIN_IMPORTANCE)
    return item.importance


def _inherit_known_events(conn: sqlite3.Connection) -> int:
    """Daha once filtrelenmis bir olaya baslik benzerligiyle baglanan haberler LLM'e gitmeden karar alir."""
    cur = conn.execute(
        """UPDATE articles SET triage_status =
               CASE (SELECT relevant FROM events e WHERE e.id = articles.event_id)
                    WHEN 1 THEN 'relevant' ELSE 'irrelevant' END
           WHERE triage_status = 'pending'
             AND (SELECT relevant FROM events e WHERE e.id = articles.event_id) IS NOT NULL"""
    )
    return cur.rowcount


def _expire_old(conn: sqlite3.Connection) -> int:
    cutoff = iso(utcnow() - timedelta(hours=TRIAGE_MAX_AGE_HOURS))
    cur = conn.execute(
        """UPDATE articles SET triage_status = 'stale'
           WHERE triage_status = 'pending' AND COALESCE(published_at, first_seen_at) < ?""",
        (cutoff,),
    )
    return cur.rowcount


def _recent_events(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    since = iso(utcnow() - timedelta(hours=24))
    return conn.execute(
        """SELECT id, title FROM events WHERE relevant = 1 AND last_seen_at >= ?
           ORDER BY last_seen_at DESC LIMIT 40""",
        (since,),
    ).fetchall()


def _move_article(conn: sqlite3.Connection, article_id: int, old_event: int | None, new_event: int) -> None:
    conn.execute("UPDATE articles SET event_id = ? WHERE id = ?", (new_event, article_id))
    if old_event is not None:
        conn.execute("UPDATE events SET article_count = article_count - 1 WHERE id = ?", (old_event,))
        # Bos kalan olayi ve henuz analiz edilmemisse kaydini temizle
        conn.execute(
            "DELETE FROM events WHERE id = ? AND article_count <= 0 AND analysis_status = 'none'", (old_event,)
        )
    conn.execute(
        "UPDATE events SET article_count = article_count + 1, last_seen_at = ? WHERE id = ?",
        (iso(utcnow()), new_event),
    )


def build_prompt(events: Sequence[Mapping], articles: Sequence[Mapping]) -> str:
    """Canli akista ve geriye donuk testte ortak kullanilir."""
    lines = ["RECENT EVENTS:"]
    lines += [f"E{e['id']}: {e['title']}" for e in events] or ["(none)"]
    lines.append("\nARTICLES:")
    for a in articles:
        summary = a["summary"] or ""
        # Google News ozeti genelde basligin tekrari; anlamli degilse gonderme (token tasarrufu)
        extra = f" | {summary[:200]}" if summary and a["title"][:40] not in summary else ""
        lines.append(f"A{a['id']} [{a['publisher'] or a['feed']}, {(a['published_at'] or '')[:16]}]: {a['title']}{extra}")
    return "\n".join(lines)


def _apply(conn: sqlite3.Connection, batch: list[sqlite3.Row], result: TriageResult, known_ids: set[int]) -> set[int]:
    """Sonuclari yazar; karar verilen makale id'lerini dondurur."""
    by_id = {a["id"]: a for a in batch}
    items = [i for i in result.items if i.id in by_id]
    final_event: dict[int, int] = {}  # makale id -> bu turda karar verilen olay id

    # Once kendi olayina veya bilinen bir olaya baglananlar, sonra ayni turdaki baska habere baglananlar
    items.sort(key=lambda i: i.relevant and i.event_ref is None and i.same_as_article is not None)
    for item in items:
        art = by_id[item.id]
        conn.execute("UPDATE articles SET price_report = ?, kategori = ? WHERE id = ?",
                     (int(item.price_report), item.kategori, art["id"]))
        if not item.relevant:
            conn.execute("UPDATE articles SET triage_status = 'irrelevant' WHERE id = ?", (art["id"],))
            conn.execute("UPDATE events SET relevant = 0 WHERE id = ? AND relevant IS NULL", (art["event_id"],))
            continue

        event_id = art["event_id"]
        target = None
        if item.event_ref in known_ids:
            target = item.event_ref
        elif item.same_as_article in final_event:
            target = final_event[item.same_as_article]
        if target is not None and target != event_id:
            _move_article(conn, art["id"], event_id, target)
            event_id = target
        final_event[art["id"]] = event_id
        conn.execute("UPDATE articles SET triage_status = 'relevant' WHERE id = ?", (art["id"],))
        conn.execute(
            "UPDATE events SET relevant = 1, importance = MAX(COALESCE(importance, 0), ?) WHERE id = ?",
            (effective_importance(item), event_id),
        )
    return {i.id for i in items}


def _count_attempt(conn: sqlite3.Connection, ids: list[int]) -> int:
    """Deneme sayacini artirir; hakki biten makaleleri 'failed' yapar."""
    if not ids:
        return 0
    marks = ",".join("?" * len(ids))
    conn.execute(f"UPDATE articles SET triage_attempts = triage_attempts + 1 WHERE id IN ({marks})", ids)
    return conn.execute(
        f"""UPDATE articles SET triage_status = 'failed'
            WHERE id IN ({marks}) AND triage_status = 'pending' AND triage_attempts >= ?""",
        (*ids, MAX_LLM_ATTEMPTS),
    ).rowcount


def run_triage(conn: sqlite3.Connection, client: LLMClient, max_batches: int = 10) -> dict:
    stats = {"inherited": _inherit_known_events(conn), "stale": _expire_old(conn), "llm": 0, "batches": 0,
             "failed": 0, "errors": []}
    conn.commit()

    for _ in range(max_batches):
        if tokens_last_24h(conn, TRIAGE_MODEL) >= DAILY_TOKEN_BUDGET:
            stats["budget_exhausted"] = True
            break
        batch = conn.execute(
            """SELECT id, feed, publisher, title, summary, published_at, event_id FROM articles
               WHERE triage_status = 'pending' ORDER BY COALESCE(published_at, first_seen_at) DESC LIMIT ?""",
            (TRIAGE_BATCH,),
        ).fetchall()
        if not batch:
            break
        ids = [a["id"] for a in batch]
        events = _recent_events(conn)
        try:
            result = client.chat_json(
                TRIAGE_MODEL, SYSTEM, build_prompt(events, batch), TriageResult,
                stage="triage", reasoning_effort=TRIAGE_REASONING,
            )
        except RateLimited as exc:
            # Gecici: deneme hakkindan dusmez, sonraki turda tekrar denenir
            stats["errors"].append(f"hiz siniri: {exc}")
            break
        except LLMError as exc:
            stats["failed"] += _count_attempt(conn, ids)
            conn.commit()
            stats["errors"].append(str(exc))
            break
        applied = _apply(conn, batch, result, {e["id"] for e in events})
        # Modelin atladigi makaleler bir sonraki turda tekrar denenir (sinirli sayida)
        stats["failed"] += _count_attempt(conn, [i for i in ids if i not in applied])
        conn.commit()
        # Ayni olaya baslik benzerligiyle baglanan diger bekleyenler simdi karar alabilir
        stats["inherited"] += _inherit_known_events(conn)
        stats["llm"] += len(applied)
        stats["batches"] += 1
    conn.commit()
    return stats
