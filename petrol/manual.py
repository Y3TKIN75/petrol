"""Disaridan (or. bir Claude oturumunda) yapilmis analizleri JSON dosyasindan canli veritabanina aktarir.

Skor ve seviye yine canli akistaki `score` fonksiyonuyla hesaplanir; bagimsiz kaynak sayisi analizcinin
verdigi degerdir. Aktarimdan once mevcut analizler yedeklenir.
"""
import json
import sqlite3
from pathlib import Path

from .analyze import Analysis, market_context, score, store_analysis
from .merge import _merge_into

ANALYSIS_FIELDS = list(Analysis.model_fields)


def backup_analyses(conn: sqlite3.Connection, path: Path) -> int:
    rows = [dict(r) for r in conn.execute(
        "SELECT a.*, e.title FROM analyses a JOIN events e ON e.id = a.event_id ORDER BY a.event_id"
    )]
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    return len(rows)


def apply_manual_analyses(conn: sqlite3.Connection, spec: dict) -> list[dict]:
    model = spec["model"]
    for m in spec.get("merges", []):
        conn.execute("DELETE FROM analyses WHERE event_id = ?", (m["dup"],))
        _merge_into(conn, m["dup"], m["target"])
    for d in spec.get("drop_analysis", []):
        conn.execute("DELETE FROM analyses WHERE event_id = ?", (d["event_id"],))
        conn.execute(
            "UPDATE events SET analysis_status = 'skipped', relevant = CASE WHEN ? THEN 0 ELSE relevant END WHERE id = ?",
            (int(d.get("irrelevant", False)), d["event_id"]),
        )

    results = []
    for item in spec["analyses"]:
        a = Analysis(**{k: item[k] for k in ANALYSIS_FIELDS})
        event = conn.execute("SELECT id, title, first_seen_at FROM events WHERE id = ?", (item["event_id"],)).fetchone()
        if event is None:
            raise ValueError(f"olay bulunamadi: {item['event_id']}")
        ctx = market_context(conn, event["first_seen_at"])
        n = item["independent_sources"]
        s, priced_in, level = score(a, n, ctx["move_pct"])
        store_analysis(conn, event["id"], model, a, n, n, ctx, s, priced_in, level)
        conn.execute("UPDATE events SET analysis_status = 'done' WHERE id = ?", (event["id"],))
        results.append({"event_id": event["id"], "title": event["title"], "yon": a.yon, "score": s, "level": level})
    conn.commit()
    return results
