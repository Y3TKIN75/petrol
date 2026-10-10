"""Asama 2: guclu model ile olay analizi + kodla skor ve seviye hesabi."""
import json
import math
import re
import sqlite3
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .config import (
    ANALYSIS_FALLBACK_MODEL,
    ANALYSIS_MODEL,
    ANALYSIS_REASONING,
    ANALYZE_MAX_AGE_HOURS,
    ANALYZE_MIN_IMPORTANCE,
    ANALYZE_PER_CYCLE,
    CALIBRATION_PATH,
    DAILY_TOKEN_BUDGET,
    LEVEL_RED,
    LEVEL_YELLOW,
    MARKET_STALE_MIN,
    MAX_LLM_ATTEMPTS,
    PRICED_IN_PCT,
    WORLD_STATE_PATH,
)
from .db import iso, tokens_last_24h, utcnow
from .kategoriler import KATEGORILER, kategori_listesi
from .llm import LLMClient, LLMError, RateLimited
from .merge import run_merge
from .regime import normal_daily_move, recent_trend

SYSTEM = """You are a senior crude-oil market analyst. Assess how the news EVENT is likely to move
Brent/WTI futures. WORLD STATE and RECENT EVENTS describe what the market already knows.
Your training data may be out of date: for who currently holds which office and for ongoing conflicts,
trust WORLD STATE over your own memory.

Lessons from Feb-Aug 2026 (war regime) that you must apply:
- Markets react to CREDIBLE REPORTS immediately ("US and Iran close to a deal, sources say" moved oil
  ~8%). A sourced report from a major outlet is not a weak signal just because it is unconfirmed.
- Concrete steps move prices; rhetoric does not. The first credible "the war is ending" moved oil 11%;
  the same words repeated the next day had no effect. Threats matter when specific (target, deadline).
- Rhetoric means repeating a known stance or vague words. A NEW position is not rhetoric: a principal
  refusing talks, rejecting a proposal or vowing not to yield; a party offering (even conditionally) to
  reopen supply; a major power pressing a party to de-escalate. These moved oil 1-2.4x a normal day.
- The other side's response matters: a denial often reverses an earlier move.
- RECENT TREND (under MARKET) shows what the market has been pricing. News that cuts against a multi-day
  trend (a rejection after days of optimism-driven declines, a disruption after days of easing) tends to
  reverse part of it; news that only extends an already long trend is often partly priced in.
- Supply returning (reopening, restart) moves prices about as much as the disruption did.
- During acute crises reserve releases, sanctions waivers and structural news barely moved prices.
- Keep size and certainty apart: beklenen_etki is the move IF the news is the day's driver; doubt about
  whether it happens, how long repairs take or whether a request is obeyed goes into guven, not into a
  smaller beklenen_etki.

Fields:
- etki_kanali: arz (supply), talep (demand) or risk_primi (geopolitical risk premium).
- olay_turu: one of these categories [history = typical move when it was the day's dominant driver,
  in multiples of a normal day]:
{kategoriler}
- yon: implied price direction. yukari = up, asagi = down, notr = no meaningful effect,
  belirsiz = effects conflict.
- beklenen_etki: expected move if this news is the main driver that day, relative to the NORMAL DAILY
  MOVE given under MARKET: normalin_alti (< 0.75x), normal (0.75-1.5x), buyuk (1.5-3x),
  cok_buyuk (> 3x). Start from the category history; first-of-kind concrete events can be cok_buyuk,
  repeated rhetoric is normalin_alti. Move away from the history only for scale (how much supply or
  risk is at stake) or novelty, never because the outcome is uncertain: that lowers guven instead.
- sure: how long the effect plays out: saatler (hours), gunler (days), haftalar (weeks).
- kaynak_guvenilirligi: resmi = the acting party's own statement or data (government, ministry,
  military, company, OPEC, IEA); ana_akim = major outlet reporting, including sourced scoops
  (Reuters, AP, Bloomberg, WSJ, FT, NYT, Axios, CNN, CNBC, BBC, Al Jazeera); tek_kaynak_zayif = smaller
  outlet, unclear sourcing, or specialist sites and aggregators (OilPrice.com, Seeking Alpha,
  Investing.com, FXEmpire); taraf_medyasi = state/partisan media of a party to the conflict (IRNA,
  Tasnim, Fars, Press TV, SABA, Al-Masirah, ...); soylenti = social media, rumour, tabloid, unverified
  video.
- somutluk: somut_eylem = an action, decision or physical event has happened (ceasefire declared,
  strikes paused, blockade ordered, facility hit, pipeline restarted, talks scheduled for a date);
  gelisme_raporu = credible report that a concrete development is under way or imminent (deal close,
  draft agreed, talks advanced), or a new position or request by a principal or major power (proposal
  rejected, talks refused, pressure on a party); somut_tehdit = specific threat with target or deadline;
  sartli_soz = conditional offer or promise; soylem = repeating a known stance, general optimism or vague
  threat; analiz = commentary, forecast or explainer with no new event.
- yenilik: yeni = new information; gelisme = meaningful update of a known story;
  tekrar = repeats what WORLD STATE / RECENT EVENTS already contain, or the event itself happened
  more than a day ago (likely priced in).
- lider_beyani: true if the core of the news is a statement by a head of state/government or a
  senior official (president, minister, Saudi/OPEC energy minister) about war, peace, sanctions or
  oil supply.
- baglam_destegi: how strongly OTHER recent news (RECENT EVENTS, WORLD STATE) corroborates this news
  or makes it more likely to come true: yok, zayif, guclu.
- ilgili_olaylar: ids of RECENT EVENTS connected to this news (E42 -> 42), at most 5, [] if none.
- guven: 0-100, your calibrated confidence that the price moves in the stated direction BECAUSE of
  this news.
- gerekce: 2-3 sentences IN NATURAL, FLUENT TURKISH (translate English terms properly, e.g.
  "Strait of Hormuz" -> "Hürmüz Boğazı", "projectile" -> "mermi/füze"): the mechanism (supply/demand/
  risk premium) and the main uncertainty. Only if MARKET says CLOSED, say the effect is expected at the
  next open; if it says OPEN, the effect is immediate and "the open" must not be mentioned.
- anahtar_aktorler: up to 5 key actors (companies, countries, people)."""

CALIBRATION_HEADER = """

ADDITIONAL REACTION REFERENCE (use it to calibrate beklenen_etki and guven, but judge each event on
its own facts):
"""

OlayTuru = Literal[tuple(KATEGORILER)]


class Analysis(BaseModel):
    model_config = ConfigDict(extra="forbid")
    etki_kanali: Literal["arz", "talep", "risk_primi"]
    olay_turu: OlayTuru
    yon: Literal["yukari", "asagi", "notr", "belirsiz"]
    beklenen_etki: Literal["normalin_alti", "normal", "buyuk", "cok_buyuk"]
    sure: Literal["saatler", "gunler", "haftalar"]
    kaynak_guvenilirligi: Literal["resmi", "ana_akim", "tek_kaynak_zayif", "taraf_medyasi", "soylenti"]
    somutluk: Literal["somut_eylem", "gelisme_raporu", "somut_tehdit", "sartli_soz", "soylem", "analiz"]
    yenilik: Literal["yeni", "gelisme", "tekrar"]
    lider_beyani: bool
    baglam_destegi: Literal["yok", "zayif", "guclu"]
    ilgili_olaylar: list[int]
    guven: int = Field(ge=0, le=100)
    gerekce: str
    anahtar_aktorler: list[str]


# Skor katsayilari. Seviye esikleri (config) bu katsayilardan turetildi, veriye gore ayarlanmadi.
EFFECT = {"normalin_alti": 0.35, "normal": 0.6, "buyuk": 0.85, "cok_buyuk": 1.0}
EFFECT_MULTIPLE = {"normalin_alti": 0.5, "normal": 1.0, "buyuk": 2.0, "cok_buyuk": 3.5}  # gosterim icin
SOURCE = {"resmi": 1.0, "ana_akim": 0.95, "tek_kaynak_zayif": 0.7, "taraf_medyasi": 0.5, "soylenti": 0.35}
CONCRETENESS = {"somut_eylem": 1.0, "gelisme_raporu": 0.85, "somut_tehdit": 0.85, "sartli_soz": 0.7,
                "soylem": 0.45, "analiz": 0.25}
# Baska haberlerle desteklenen haber, kaynak guvenilirligi acigini bu oranda kapatir
CONTEXT_SUPPORT = {"yok": 0.0, "zayif": 0.35, "guclu": 0.85}
NOVELTY = {"yeni": 1.0, "gelisme": 0.85, "tekrar": 0.5}


# ---------------------------------------------------------------- fiyat baglami

def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _symbol_move(conn: sqlite3.Connection, symbol: str, since: str) -> dict:
    at = conn.execute(
        "SELECT price FROM prices WHERE symbol = ? AND ts <= ? ORDER BY ts DESC LIMIT 1", (symbol, since)
    ).fetchone()
    last = conn.execute(
        "SELECT ts, price FROM prices WHERE symbol = ? ORDER BY ts DESC LIMIT 1", (symbol,)
    ).fetchone()
    if not last:
        return {"at": None, "last": None, "last_ts": None, "move_pct": None}
    at_price = at["price"] if at else None
    move = (last["price"] / at_price - 1) * 100 if at_price else None
    return {"at": at_price, "last": last["price"], "last_ts": last["ts"], "move_pct": move}


def confirmed_move(brent: float | None, wti: float | None) -> float | None:
    """Iki piyasanin birlikte teyit ettigi hareket.

    Yahoo'nun Brent verisi vade sonlarinda iki kontrat ayini karistirip sahte %5 sicramalar uretiyor.
    Bu yuzden hareket ancak WTI ayni yonde gittiyse kabul edilir; buyuklugu kucuk olandir. Bilincli
    olarak temkinli: sahte "fiyata yansimis" isareti gercek bir uyariyi gizler, tersi daha az zararli.
    """
    if brent is None:
        return wti
    if wti is None:
        return brent
    if brent * wti <= 0:
        return 0.0
    return math.copysign(min(abs(brent), abs(wti)), brent)


def market_context(conn: sqlite3.Connection, since: str) -> dict:
    brent = _symbol_move(conn, "BZ=F", since)
    wti = _symbol_move(conn, "CL=F", since)
    ticks = [_parse(x["last_ts"]) for x in (brent, wti) if x["last_ts"]]
    market_open = bool(ticks) and (utcnow() - max(ticks)) <= timedelta(minutes=MARKET_STALE_MIN)
    return {
        "brent": brent,
        "wti": wti,
        "move_pct": confirmed_move(brent["move_pct"], wti["move_pct"]),
        "market_open": market_open,
        "normal_move": normal_daily_move(conn),
        "trend": recent_trend(conn),
    }


def format_market(ctx: dict) -> str:
    b, w = ctx["brent"], ctx["wti"]
    normal = f"NORMAL DAILY MOVE (median of last 20 sessions): {ctx['normal_move']:.1f}%"
    if b["last"] is None and w["last"] is None:
        return f"no price data; {normal}"
    parts = []
    if b["last"] is not None:
        parts.append(f"Brent {b['last']:.2f} USD")
    if w["last"] is not None:
        parts.append(f"WTI {w['last']:.2f} USD")
    state = "OPEN" if ctx["market_open"] else "CLOSED (effect expected at next open)"
    text = f"{', '.join(parts)} (last tick {b['last_ts'] or w['last_ts']}), market {state}; {normal}"
    if ctx["move_pct"] is not None:
        text += f"; confirmed move since the event was first seen: {ctx['move_pct']:+.2f}%"
    if ctx.get("trend"):
        text += f"\nRECENT TREND: {ctx['trend']}"
    return text


# ---------------------------------------------------------------- skor

def score(a: Analysis, n_sources: int, move_pct: float | None) -> tuple[int, bool, str]:
    """(skor 0-100, fiyata_yansimis_mi, seviye). Seviyeyi AI degil kod belirler."""
    if a.yon in ("notr", "belirsiz"):
        return 0, False, "digest"
    credibility = SOURCE[a.kaynak_guvenilirligi]
    credibility += (1 - credibility) * CONTEXT_SUPPORT[a.baglam_destegi]
    s = a.guven * EFFECT[a.beklenen_etki] * credibility * CONCRETENESS[a.somutluk] * NOVELTY[a.yenilik]
    s += min(n_sources - 1, 3) * 4  # birden fazla bagimsiz kaynak teyidi
    priced_in = False
    if move_pct is not None:
        same_direction = move_pct if a.yon == "yukari" else -move_pct
        if same_direction >= PRICED_IN_PCT:
            s *= 0.6
            priced_in = True
    s = round(min(s, 100))
    # Liderin savas/baris/petrol beyani en az akista gorunur; ust siniri baglam belirler
    if a.lider_beyani and a.beklenen_etki != "normalin_alti":
        s = max(s, LEVEL_YELLOW)
    level = "red" if s >= LEVEL_RED else "yellow" if s >= LEVEL_YELLOW else "digest"
    return s, priced_in, level


# ---------------------------------------------------------------- istem (canli + geriye donuk test)

def read_optional(path: Path) -> str | None:
    try:
        text = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None
    return text or None


def system_prompt(calibration: str | None) -> str:
    base = SYSTEM.replace("{kategoriler}", kategori_listesi(referansli=True))
    return base + (CALIBRATION_HEADER + calibration if calibration else "")


def format_articles(articles: Sequence[Mapping]) -> str:
    return "\n".join(
        f"- [{a['publisher'] or a['feed']}, {(a['published_at'] or a['first_seen_at'])[:16]}] {a['title']}"
        + (f" | {a['summary'][:300]}" if a["summary"] and a["title"][:40] not in a["summary"] else "")
        for a in articles
    )


def build_prompt(now: str, world_state: str | None, market: str, recent: str, first_seen: str,
                 n_articles: int, articles_text: str) -> str:
    return (
        f"NOW: {now}\n\nWORLD STATE (maintained by the user):\n{world_state or '(none)'}\n\n"
        f"MARKET: {market}\n\nRECENT EVENTS (last 24h, oil-relevant; '->' marks our earlier assessment):\n"
        f"{recent}\n\n"
        f"EVENT TO ANALYSE (first seen {first_seen}, {n_articles} source articles):\n{articles_text}"
    )


def keep_known_related(a: Analysis, recent: str) -> Analysis:
    """Model bazen RECENT EVENTS'te olmayan olay numarasi uyduruyor; yalnizca istemde verilenler kalir."""
    known = {int(x) for x in re.findall(r"^- E(\d+)", recent, re.M)}
    return a.model_copy(update={"ilgili_olaylar": [i for i in a.ilgili_olaylar if i in known][:5]})


def _recent_events(conn: sqlite3.Connection, exclude: int) -> str:
    """Baglam icin son 24 saatin petrolle ilgili olaylari (analiz edilmemis olanlar dahil)."""
    since = iso(utcnow() - timedelta(hours=24))
    rows = conn.execute(
        """SELECT e.id, e.first_seen_at, e.title, a.yon, COALESCE(a.beklenen_etki, a.buyukluk) AS etki
           FROM events e
           LEFT JOIN analyses a ON a.event_id = e.id
           WHERE e.relevant = 1 AND e.analysis_status IN ('done', 'skipped') AND e.id != ?
             AND e.last_seen_at >= ?
           ORDER BY e.first_seen_at DESC LIMIT 30""",
        (exclude, since),
    ).fetchall()
    return "\n".join(
        f"- E{r['id']} [{r['first_seen_at'][:16]}] {r['title']}" + (f" -> {r['yon']}, {r['etki']}" if r["yon"] else "")
        for r in rows
    ) or "(none)"


# ---------------------------------------------------------------- canli akis

def _n_sources(conn: sqlite3.Connection, event_id: int) -> int:
    row = conn.execute(
        """SELECT COUNT(DISTINCT COALESCE(publisher, feed)) FROM articles
           WHERE event_id = ? AND triage_status = 'relevant'""",
        (event_id,),
    ).fetchone()
    return max(row[0], 1)


def analyze_event(conn: sqlite3.Connection, client: LLMClient, event: sqlite3.Row,
                  model: str = ANALYSIS_MODEL) -> dict:
    articles = conn.execute(
        """SELECT feed, publisher, title, summary, published_at, first_seen_at FROM articles
           WHERE event_id = ? AND triage_status = 'relevant' ORDER BY first_seen_at LIMIT 8""",
        (event["id"],),
    ).fetchall()
    ctx = market_context(conn, event["first_seen_at"])
    recent = _recent_events(conn, event["id"])
    prompt = build_prompt(
        iso(utcnow()), read_optional(WORLD_STATE_PATH), format_market(ctx), recent,
        event["first_seen_at"], len(articles), format_articles(articles),
    )
    result = client.chat_json(
        model, system_prompt(read_optional(CALIBRATION_PATH)), prompt, Analysis,
        stage="analysis", reasoning_effort=ANALYSIS_REASONING,
    )
    result = keep_known_related(result, recent)

    n_sources = _n_sources(conn, event["id"])
    s, priced_in, level = score(result, n_sources, ctx["move_pct"])
    store_analysis(conn, event["id"], model, result, n_sources, None, ctx, s, priced_in, level)
    conn.execute("UPDATE events SET analysis_status = 'done' WHERE id = ?", (event["id"],))
    conn.commit()
    return {"event_id": event["id"], "title": event["title"], "level": level, "score": s, "yon": result.yon}


def store_analysis(conn: sqlite3.Connection, event_id: int, model: str, a: Analysis, n_sources: int,
                   independent_sources: int | None, ctx: dict, s: int, priced_in: bool, level: str) -> None:
    """Canli analiz ve disaridan aktarilan (manuel) analiz ayni yoldan yazilir."""
    conn.execute(
        """INSERT OR REPLACE INTO analyses
           (event_id, created_at, model, etki_kanali, olay_turu, yon, beklenen_etki, sure, kaynak_guvenilirligi,
            somutluk, yenilik, guven, gerekce, aktorler, lider_beyani, baglam_destegi, ilgili_olaylar, n_sources,
            independent_sources, brent_at_event, brent_move_pct, wti_move_pct, move_pct, market_open, priced_in,
            normal_hareket_pct, beklenen_pct, score, level)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            event_id, iso(utcnow()), model, a.etki_kanali, a.olay_turu, a.yon, a.beklenen_etki, a.sure,
            a.kaynak_guvenilirligi, a.somutluk, a.yenilik, a.guven, a.gerekce,
            json.dumps(a.anahtar_aktorler, ensure_ascii=False), int(a.lider_beyani), a.baglam_destegi,
            json.dumps(a.ilgili_olaylar), n_sources, independent_sources, ctx["brent"]["at"],
            ctx["brent"]["move_pct"], ctx["wti"]["move_pct"], ctx["move_pct"], int(ctx["market_open"]),
            int(priced_in), ctx["normal_move"], round(EFFECT_MULTIPLE[a.beklenen_etki] * ctx["normal_move"], 2),
            s, level,
        ),
    )


def analysis_from_row(r: Mapping) -> Analysis:
    return Analysis(
        etki_kanali=r["etki_kanali"], olay_turu=r["olay_turu"], yon=r["yon"], beklenen_etki=r["beklenen_etki"],
        sure=r["sure"], kaynak_guvenilirligi=r["kaynak_guvenilirligi"], somutluk=r["somutluk"],
        yenilik=r["yenilik"], guven=r["guven"], gerekce=r["gerekce"],
        anahtar_aktorler=json.loads(r["aktorler"] or "[]"), lider_beyani=bool(r["lider_beyani"]),
        baglam_destegi=r["baglam_destegi"] or "yok", ilgili_olaylar=json.loads(r["ilgili_olaylar"] or "[]"),
    )


def rescore_recent(conn: sqlite3.Connection) -> list[dict]:
    """AI cagirmadan: yeni kaynak eklenen veya fiyati oynayan olaylarin skorunu gunceller."""
    since = iso(utcnow() - timedelta(hours=24))
    changed = []
    for r in conn.execute(
        # Eski semayla (buyukluk/kesinlik) yazilmis analizler yeniden skorlanmaz; saklanan skorlari kalir
        """SELECT a.*, e.title, e.first_seen_at FROM analyses a JOIN events e ON e.id = a.event_id
           WHERE a.created_at >= ? AND a.beklenen_etki IS NOT NULL""",
        (since,),
    ).fetchall():
        n_sources = r["independent_sources"] or _n_sources(conn, r["event_id"])
        ctx = market_context(conn, r["first_seen_at"])
        s, priced_in, level = score(analysis_from_row(r), n_sources, ctx["move_pct"])
        if (s, level, n_sources) != (r["score"], r["level"], r["n_sources"]):
            conn.execute(
                """UPDATE analyses SET n_sources = ?, brent_move_pct = ?, wti_move_pct = ?, move_pct = ?,
                          market_open = ?, priced_in = ?, score = ?, level = ? WHERE event_id = ?""",
                (n_sources, ctx["brent"]["move_pct"], ctx["wti"]["move_pct"], ctx["move_pct"],
                 int(ctx["market_open"]), int(priced_in), s, level, r["event_id"]),
            )
            changed.append({"title": r["title"], "old": r["score"], "score": s, "level": level, "yon": r["yon"]})
    conn.commit()
    return changed


def pick_analysis_model(conn: sqlite3.Connection) -> str | None:
    """Ana modelin gunluk butcesi bittiyse yedek model (daha zayif ama analiz durmaz); o da bittiyse None."""
    if tokens_last_24h(conn, ANALYSIS_MODEL) < DAILY_TOKEN_BUDGET:
        return ANALYSIS_MODEL
    if ANALYSIS_FALLBACK_MODEL and tokens_last_24h(conn, ANALYSIS_FALLBACK_MODEL) < DAILY_TOKEN_BUDGET:
        return ANALYSIS_FALLBACK_MODEL
    return None


def run_analysis(conn: sqlite3.Connection, client: LLMClient) -> dict:
    errors: list[str] = []
    try:
        merged = run_merge(conn, client)
    except LLMError as exc:
        # Birlestirme yapilamazsa analiz yine de devam eder (en kotu ihtimalle cift olay)
        merged = 0
        errors.append(f"birlestirme: {exc}")

    cutoff = iso(utcnow() - timedelta(hours=ANALYZE_MAX_AGE_HOURS))
    # Onemsiz veya eski olaylar derin analize girmez (gunluk token butcesi icin)
    skipped = conn.execute(
        """UPDATE events SET analysis_status = 'skipped'
           WHERE relevant = 1 AND analysis_status = 'none'
             AND (COALESCE(importance, 0) < ? OR first_seen_at < ?)""",
        (ANALYZE_MIN_IMPORTANCE, cutoff),
    ).rowcount
    conn.commit()

    done: list[dict] = []
    events = conn.execute(
        """SELECT id, title, first_seen_at FROM events
           WHERE relevant = 1 AND analysis_status = 'none'
           ORDER BY importance DESC, first_seen_at DESC LIMIT ?""",
        (ANALYZE_PER_CYCLE,),
    ).fetchall()
    for event in events:
        model = pick_analysis_model(conn)
        if model is None:
            errors.append("gunluk token butcesi doldu (ana ve yedek model)")
            break
        if model != ANALYSIS_MODEL and not any("yedek" in e for e in errors):
            errors.append(f"ana model butcesi doldu; yedek modelle analiz: {model}")
        try:
            done.append(analyze_event(conn, client, event, model))
        except RateLimited as exc:
            errors.append(f"hiz siniri, sonraki turda devam: {exc}")
            break
        except LLMError as exc:
            conn.execute(
                """UPDATE events SET analysis_attempts = analysis_attempts + 1,
                          analysis_status = CASE WHEN analysis_attempts + 1 >= ? THEN 'failed' ELSE 'none' END
                   WHERE id = ?""",
                (MAX_LLM_ATTEMPTS, event["id"]),
            )
            conn.commit()
            errors.append(f"olay {event['id']}: {exc}")
    return {"merged": merged, "skipped": skipped, "done": done, "rescored": rescore_recent(conn), "errors": errors}
