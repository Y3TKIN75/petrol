import statistics
from collections import Counter
from datetime import datetime

from .config import PRICE_SYMBOLS
from .db import connect


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def print_report() -> None:
    conn = connect()

    print("\n== Kaynak bazinda ==")
    print(f"{'kaynak':<16}{'toplam':>8}{'canli':>8}{'filtre+':>9}{'medyan gecikme':>17}  son hata")
    feeds = conn.execute("SELECT feed, last_error FROM feed_state ORDER BY feed").fetchall()
    for f in feeds:
        rows = conn.execute(
            "SELECT published_at, first_seen_at, initial, prefilter_pass FROM articles WHERE feed = ?",
            (f["feed"],),
        ).fetchall()
        live = [r for r in rows if not r["initial"]]
        # Gecikme yalnizca ilk taramadan sonra gelen (canli) haberlerde anlamli
        lags = [
            (_parse(r["first_seen_at"]) - _parse(r["published_at"])).total_seconds() / 60
            for r in live
            if r["published_at"]
        ]
        lag = f"{statistics.median(lags):.1f} dk (n={len(lags)})" if lags else "-"
        passed = sum(r["prefilter_pass"] for r in rows)
        print(f"{f['feed']:<16}{len(rows):>8}{len(live):>8}{passed:>9}{lag:>17}  {f['last_error'] or ''}")

    print("\n== Coklu kaynakli olaylarda ilk yakalayan ==")
    first = Counter()
    multi = 0
    for (event_id,) in conn.execute(
        """SELECT event_id FROM articles WHERE event_id IS NOT NULL AND initial = 0
           GROUP BY event_id HAVING COUNT(DISTINCT feed) > 1"""
    ):
        multi += 1
        arts = conn.execute(
            "SELECT feed, first_seen_at FROM articles WHERE event_id = ? AND initial = 0", (event_id,)
        ).fetchall()
        earliest = min(a["first_seen_at"] for a in arts)
        first.update({a["feed"] for a in arts if a["first_seen_at"] == earliest})
    print(f"olay sayisi: {multi}")
    for feed, n in first.most_common():
        print(f"  {feed:<16}{n}")

    total_events = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    pending = conn.execute("SELECT COUNT(*) FROM articles WHERE triage_status = 'pending'").fetchone()[0]
    print(f"\nToplam olay (tekrarlar birlesik): {total_events} | AI filtresini bekleyen haber: {pending}")

    triage = dict(
        conn.execute("SELECT triage_status, COUNT(*) FROM articles GROUP BY triage_status").fetchall()
    )
    print("Filtre durumu: " + ", ".join(f"{k}={v}" for k, v in sorted(triage.items())))

    print("\n== AI kullanimi (son 24 saat) ==")
    usage = conn.execute(
        """SELECT model, stage, COUNT(*) AS calls, SUM(total_tokens) AS tokens FROM llm_usage
           WHERE ts >= strftime('%Y-%m-%dT%H:%M:%SZ', 'now', '-1 day') GROUP BY model, stage"""
    ).fetchall()
    for u in usage:
        print(f"  {u['model']:<24}{u['stage']:<10}{u['calls']:>5} cagri {u['tokens'] or 0:>9} token")
    if not usage:
        print("  (henuz yok)")

    print("\n== Son fiyatlar ==")
    for symbol, name in PRICE_SYMBOLS.items():
        row = conn.execute(
            "SELECT ts, price FROM prices WHERE symbol = ? ORDER BY ts DESC LIMIT 1", (symbol,)
        ).fetchone()
        print(f"  {name:<6} {row['price']:.2f} ({row['ts']})" if row else f"  {name:<6} veri yok")
