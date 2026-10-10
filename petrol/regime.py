"""Piyasa rejimi: 'normal bir gun' ne kadar oynuyor?

Etki buyuklugu yuzde olarak degil normal gunun kati olarak tahmin edilir: Mart 2026'da normal gun ~%4.7,
Subat'ta ~%1.0 idi; ayni haber farkli rejimlerde farkli yuzde hareket uretir.
"""
import sqlite3
import statistics
from datetime import datetime, timezone

from .config import DEFAULT_NORMAL_MOVE_PCT, TREND_SESSIONS, VOL_WINDOW_DAYS


def daily_move(brent_pct: float, wti_pct: float) -> float:
    """Iki piyasanin gunluk hareketi. Ayrisma vade kalintisi olabilir: o gunlerde WTI esas alinir."""
    diverged = (brent_pct * wti_pct < 0 and max(abs(brent_pct), abs(wti_pct)) > 1.5) or abs(brent_pct - wti_pct) > 3
    return wti_pct if diverged else (brent_pct + wti_pct) / 2


def normal_move_from_closes(brent: dict[str, float], wti: dict[str, float], before: str,
                            window: int = VOL_WINDOW_DAYS) -> float | None:
    """`before` gununden ONCEKI son `window` islem gununun medyan |gunluk hareket|i (yuzde)."""
    days = sorted(d for d in set(brent) & set(wti) if d < before)
    moves = []
    for prev, day in zip(days, days[1:]):
        b = (brent[day] / brent[prev] - 1) * 100
        w = (wti[day] / wti[prev] - 1) * 100
        moves.append(abs(daily_move(b, w)))
    recent = moves[-window:]
    return round(statistics.median(recent), 2) if len(recent) >= window // 2 else None


def recent_trend_from_closes(brent: dict[str, float], wti: dict[str, float], before: str,
                             sessions: int = TREND_SESSIONS) -> str | None:
    """`before` gununden ONCEKI son seanslarin Brent/WTI hareketleri (model baglami icin).

    Iki piyasa ayri ayri verilir: tek gunluk Brent/WTI ayrismasi vade gecisi kalintisi olabilir,
    hangisinin gercek oldugunu model haber akisiyla birlikte yorumlar.
    """
    days = sorted(d for d in set(brent) & set(wti) if d < before)[-(sessions + 1):]
    if len(days) < 2:
        return None
    steps = [f"{day[5:]} {(brent[day] / brent[prev] - 1) * 100:+.1f}/{(wti[day] / wti[prev] - 1) * 100:+.1f}"
             for prev, day in zip(days, days[1:])]
    b_total = (brent[days[-1]] / brent[days[0]] - 1) * 100
    w_total = (wti[days[-1]] / wti[days[0]] - 1) * 100
    return (f"last {len(steps)} sessions Brent/WTI %: {', '.join(steps)}; "
            f"total Brent {b_total:+.1f}%, WTI {w_total:+.1f}%")


def _daily_series(conn: sqlite3.Connection) -> dict[str, dict[str, float]]:
    series = {"BZ=F": {}, "CL=F": {}}
    for r in conn.execute("SELECT symbol, day, close FROM daily_prices"):
        series.setdefault(r["symbol"], {})[r["day"]] = r["close"]
    return series


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def normal_daily_move(conn: sqlite3.Connection, before: str | None = None) -> float:
    """Canli akista: bugunden (tamamlanmamis gun haric) onceki 20 islem gunu; veri yoksa varsayilan."""
    series = _daily_series(conn)
    value = normal_move_from_closes(series["BZ=F"], series["CL=F"], before or _today())
    return value if value is not None else DEFAULT_NORMAL_MOVE_PCT


def recent_trend(conn: sqlite3.Connection, before: str | None = None) -> str | None:
    """Canli akista: bugunden (tamamlanmamis gun haric) onceki son seanslar."""
    series = _daily_series(conn)
    return recent_trend_from_closes(series["BZ=F"], series["CL=F"], before or _today())
