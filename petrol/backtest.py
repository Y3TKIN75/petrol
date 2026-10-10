"""Geriye donuk test: arsiv basliklarini canli akisla AYNI filtre + analiz + skor kodundan gecirir.

Ilkeler:
- Sizinti yok: fiyat hareketini anlatan basliklar vaka olarak kullanilmaz; her vakaya yalnizca o tarihe
  kadar bilinenler (baslangic dunya durumu + onceki vakalarin basliklari + onceki gunun olaylari) verilir.
- Butun basliklar arsivde birebir aranir; bulunamayan varsa test calismaz.
- Token kullanimi canli veritabanina yazilir; canli akisa pay (reserve) birakilir.
"""
import csv
import json
import random
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from .analyze import Analysis, build_prompt, format_articles, keep_known_related, score, system_prompt
from .config import (
    DEFAULT_NORMAL_MOVE_PCT,
    ANALYSIS_MODEL,
    ANALYSIS_REASONING,
    ANALYZE_MIN_IMPORTANCE,
    DAILY_TOKEN_BUDGET,
    PROJECT_DIR,
    TRIAGE_MODEL,
    TRIAGE_REASONING,
)
from .db import connect, tokens_last_24h, usage_logger
from .llm import LLMClient, RateLimited
from .regime import normal_move_from_closes, recent_trend_from_closes
from .triage import SYSTEM as TRIAGE_SYSTEM
from .triage import TriageResult, build_prompt as triage_prompt, effective_importance

ARASTIRMA = PROJECT_DIR / "arastirma"
ARCHIVE = ARASTIRMA / "veri" / "haberler.json"
DAILY_PRICES = ARASTIRMA / "veri" / "gunluk_bz_cl.csv"   # gecmis_hareketler.py uretir (Brent + WTI)
BASELINE_STATE = ARASTIRMA / "backtest" / "dunya_durumu_2026-08-30.md"


@dataclass(frozen=True)
class Sources:
    """Bir vaka setinin arsivi, gunluk kapanislari ve baslangic dunya durumu."""
    archive: Path = ARCHIVE
    prices: Path = DAILY_PRICES
    baseline: Path = BASELINE_STATE


def sources_for(spec: dict) -> Sources:
    """Vaka dosyasi 'kaynaklar' ile kendi dosyalarini secebilir (proje kokune gore); yoksa Eylul seti."""
    paths = {k: PROJECT_DIR / v for k, v in spec.get("kaynaklar", {}).items()}
    return Sources(**paths)

# "top" yalnizca fiyatla birlikte ("tops $100"): "oil cargoes ..., top buyer" bir fiyat basligi degildir
PRICE_HEADLINE = re.compile(
    r"\b(oil|crude|brent|wti)( prices?| futures)?\b.{0,40}\b((surge|soar|jump|spike|rall|rise|climb|gain|fall|drop|"
    r"slide|slump|tumble|plunge|sink|retreat|ease|pull back|whipsaw|swing|settle|dip|extend|pare|leap)\w*"
    r"|tops? (\$|above \$|\d))",
    re.I,
)
# Piyasa tepkisini ima eden her baslik baglamdan cikarilir (or. "Oil prices off highs after ...")
MARKET_WORDS = re.compile(r"\b(oil|crude|brent|wti)\b.*\b(price|prices|futures|market|markets|highs?|lows?)\b|\$\d",
                          re.I)
EVENT_WORDS = re.compile(
    r"\b(hormuz|aramco|opec|saudi|iran|ceasefire|truce|pipeline|tanker|sanction|reserve|spr|g7|iea|houthi|strike|"
    r"attack|talks|export)\b", re.I,
)


class BudgetExceeded(RuntimeError):
    pass


def _archive_day(published: str) -> str:
    m = re.search(r"(\d{1,2}) (\w{3}) (\d{4})", published)
    months = {"Aug": "08", "Sep": "09", "Oct": "10"}
    return f"{m.group(3)}-{months.get(m.group(2), '??')}-{int(m.group(1)):02d}" if m else ""


def load_archive(path: Path = ARCHIVE) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    seen, items = set(), []
    for day_items in data["daily"].values():
        for it in day_items:
            if it["title"] not in seen:
                seen.add(it["title"])
                items.append({"title": it["title"], "day": _archive_day(it["published"])})
    return items


def verify_headlines(spec: dict, archive: list[dict]) -> list[str]:
    """Her baslik (turetilmislerde kaynak baslik) arsivde birebir bulunmali."""
    titles = {a["title"] for a in archive}
    missing = []
    for case in spec["cases"]:
        for h in case["headlines"]:
            full = h["source_title"] if h.get("derived") else f"{h['title']} - {h['publisher']}"
            if full not in titles:
                missing.append(f"{case['id']}: {full}")
    for c in spec["controls"]:
        full = f"{c['title']} - {c['publisher']}"
        if full not in titles:
            missing.append(f"kontrol: {full}")
    return missing


def _closes(path: Path = DAILY_PRICES) -> tuple[dict[str, float], dict[str, float]]:
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    return {r["day"]: float(r["brent"]) for r in rows}, {r["day"]: float(r["wti"]) for r in rows}


def previous_close(day: str, prices: Path = DAILY_PRICES) -> tuple[str, float] | None:
    brent, _ = _closes(prices)
    before = sorted(d for d in brent if d < day)
    return (before[-1], brent[before[-1]]) if before else None


def normal_move_before(day: str, prices: Path = DAILY_PRICES) -> float:
    brent, wti = _closes(prices)
    return normal_move_from_closes(brent, wti, day) or DEFAULT_NORMAL_MOVE_PCT


def trend_before(day: str, prices: Path = DAILY_PRICES) -> str | None:
    brent, wti = _closes(prices)
    return recent_trend_from_closes(brent, wti, day)


def prior_day_events(archive: list[dict], day: str, exclude: set[str], limit: int = 8) -> list[str]:
    """Vakadan EN AZ 2 gun onceki son arsiv gununun olay basliklari.

    Google News tarihleri +-1 gun kayabiliyor (or. pazar tarihli "petrol kapanista yukseldi"). 1 gun
    oncesini almak ayni gunun haberini, yani sonucu sizdirabilir. Petrol/fiyat iceren basliklar da
    tepkiyi ele verebilecegi icin baglama hic alinmaz.
    """
    limit_day = (datetime.fromisoformat(day) - timedelta(days=2)).date().isoformat()
    days = sorted({a["day"] for a in archive if a["day"] and a["day"] <= limit_day})
    if not days:
        return []
    prev = days[-1]
    out = []
    for a in archive:
        t = a["title"]
        if (a["day"] == prev and EVENT_WORDS.search(t) and not PRICE_HEADLINE.search(t)
                and not MARKET_WORDS.search(t) and t not in exclude):
            out.append(f"[{prev}] {t}")
        if len(out) == limit:
            break
    return out


def world_state_for(case: dict, cases: list[dict], baseline: Path = BASELINE_STATE) -> str:
    """Baslangic notu + bu vakadan ONCEKI vakalarin olay basliklari (kullanicinin guncelledigi notu taklit eder)."""
    base = baseline.read_text(encoding="utf-8")
    earlier = sorted((c for c in cases if c["now"] < case["now"]), key=lambda c: c["now"])
    if not earlier:
        return base
    lines = [f"- {c['now'][:10]}: {c['headlines'][0]['title']}" for c in earlier]
    return base + "\n\n## Donem gelismeleri (eskiden yeniye)\n" + "\n".join(lines)


def _guard(conn, model: str, reserve: int) -> None:
    used = tokens_last_24h(conn, model)
    if used + reserve >= DAILY_TOKEN_BUDGET:
        raise BudgetExceeded(f"{model}: son 24 saatte {used} token; canli akis icin {reserve} pay birakiliyor")


def _call(client: LLMClient, **kw):
    try:
        return client.chat_json(**kw)
    except RateLimited:
        time.sleep(60)  # dakika basi token siniri; bir kez daha dene
        return client.chat_json(**kw)


def build_triage_inputs(cases: list[dict], controls: list[dict]) -> tuple[list[dict], dict]:
    articles, owner = [], {}
    for case in cases:
        for h in case["headlines"]:
            aid = len(articles) + 1
            articles.append({"id": aid, "title": h["title"], "summary": "", "publisher": h["publisher"],
                             "feed": "", "published_at": case["now"]})
            owner[aid] = ("case", case["id"])
    for i, c in enumerate(controls):
        aid = len(articles) + 1
        articles.append({"id": aid, "title": c["title"], "summary": "", "publisher": c["publisher"],
                         "feed": "", "published_at": c["date"] + "T12:00:00Z"})
        owner[aid] = ("control", i)
    random.Random(42).shuffle(articles)
    return articles, owner


def triage_round(client: LLMClient, conn, articles: list[dict], reserve: int) -> dict[int, dict]:
    triage: dict[int, dict] = {}
    for start in range(0, len(articles), 20):
        _guard(conn, TRIAGE_MODEL, reserve)
        batch = articles[start:start + 20]
        res = _call(client, model=TRIAGE_MODEL, system=TRIAGE_SYSTEM, user=triage_prompt([], batch),
                    out=TriageResult, stage="bt_triage", reasoning_effort=TRIAGE_REASONING)
        for item in res.items:
            triage[item.id] = {"relevant": item.relevant, "price_report": item.price_report,
                               "importance": item.importance, "effective": effective_importance(item)}
    return triage


def triage_eval(cases_path: Path, repeats: int, reserve: int) -> None:
    """Yalnizca filtre: her vaka/kontrol kac turda analize gecti (model cevaplari turdan tura degisebilir)."""
    spec = json.loads(cases_path.read_text(encoding="utf-8"))
    conn = connect()
    client = LLMClient(on_usage=usage_logger(conn))
    articles, owner = build_triage_inputs(spec["cases"], spec["controls"])
    passes: dict[str, int] = {}
    imps: dict[str, list] = {}
    for _ in range(repeats):
        tri = triage_round(client, conn, articles, reserve)
        per_key: dict[str, list] = {}
        for aid, (kind, key) in owner.items():
            k = key if kind == "case" else f"kontrol:{spec['controls'][key]['title'][:45]}"
            per_key.setdefault(k, []).append(tri.get(aid))
        for k, ts in per_key.items():
            rel = [t for t in ts if t and t["relevant"]]
            imp = max((t["effective"] for t in rel), default=0)
            imps.setdefault(k, []).append(imp)
            passes[k] = passes.get(k, 0) + int(bool(rel) and imp >= ANALYZE_MIN_IMPORTANCE)
    split = {c["id"]: c["split"] for c in spec["cases"]}
    for k in passes:
        tag = split.get(k, "kontrol")
        print(f"  {k:<50} {tag:<11} gecti {passes[k]}/{repeats}  onem={imps[k]}")


def case_prompt(case: dict, all_cases: list[dict], archive: list[dict],
                src: Sources = Sources()) -> tuple[str, str]:
    """(istem, RECENT EVENTS metni). Fiyat baglami yalnizca vaka gununden ONCEKI kapanislardan."""
    day = case["now"][:10]
    prev = previous_close(day, src.prices)
    state = "OPEN" if case["market_open"] else "CLOSED (effect expected at next open)"
    normal = normal_move_before(day, src.prices)
    market = (f"Brent {prev[1]:.2f} USD (previous close {prev[0]}), market {state}; "
              f"NORMAL DAILY MOVE (median of last 20 sessions): {normal:.1f}%; "
              "confirmed move since the event was first seen: +0.00%") if prev else "no price data"
    trend = trend_before(day, src.prices)
    if trend:
        market += f"\nRECENT TREND: {trend}"
    own = {h["title"] for h in case["headlines"]}
    recent = prior_day_events(archive, day, own)
    recent_text = "\n".join(f"- E{i + 1} {line}" for i, line in enumerate(recent)) or "(none)"
    arts = [{"title": h["title"], "summary": "", "publisher": h["publisher"], "feed": "",
             "published_at": case["now"], "first_seen_at": case["now"]} for h in case["headlines"]]
    prompt = build_prompt(case["now"], world_state_for(case, all_cases, src.baseline), market, recent_text, case["now"],
                          len(arts), format_articles(arts))
    return prompt, recent_text


def run_backtest(cases_path: Path, split: str, calibration: Path | None, label: str, reserve: int,
                 dry_run: str | None = None, only_ids: set[str] | None = None) -> dict | None:
    spec = json.loads(cases_path.read_text(encoding="utf-8"))
    src = sources_for(spec)
    archive = load_archive(src.archive)
    missing = verify_headlines(spec, archive)
    if missing:
        raise SystemExit("Arsivde bulunamayan basliklar:\n  " + "\n  ".join(missing))

    all_cases = spec["cases"]
    cases = [c for c in all_cases if (split == "all" or c["split"] == split) and (not only_ids or c["id"] in only_ids)]
    calibration_text = calibration.read_text(encoding="utf-8").strip() if calibration else None
    if dry_run:
        # API cagirmadan: tum basliklar dogrulandi; secilen vakanin istemini goster
        case = next(c for c in all_cases if c["id"] == dry_run)
        print(f"Basliklar arsivde dogrulandi ({len(all_cases)} vaka, {len(spec['controls'])} kontrol).")
        print(f"Secilen split: {split} -> {len(cases)} vaka\n")
        print("===== SYSTEM (son 600 karakter) =====\n" + system_prompt(calibration_text)[-600:])
        print("\n===== USER =====\n" + case_prompt(case, all_cases, archive, src)[0])
        return None

    conn = connect()
    client = LLMClient(on_usage=usage_logger(conn))

    # ---- 1) Filtre: vaka basliklari + kontroller karisik, canli akistaki gibi 20'serli gruplar
    articles, owner = build_triage_inputs(cases, spec["controls"])
    triage = triage_round(client, conn, articles, reserve)

    # ---- 2) Vaka bazinda analiz
    results = []
    analysis_queue = []
    for case in cases:
        ids = [aid for aid, (kind, key) in owner.items() if kind == "case" and key == case["id"]]
        t = [triage.get(aid) for aid in ids]
        rel = [x for x in t if x and x["relevant"]]
        importance = max((x["effective"] for x in rel), default=0)
        results.append({
            "id": case["id"], "split": case["split"], "expected": case["expected"], "strength": case["strength"],
            "headline": case["headlines"][0]["title"], "triage": t, "importance": importance,
            "passed": bool(rel) and importance >= ANALYZE_MIN_IMPORTANCE,
        })
        if results[-1]["passed"]:
            analysis_queue.append((case, results[-1]))

    controls = []
    for aid, (kind, idx) in owner.items():
        if kind != "control":
            continue
        c, t = spec["controls"][idx], triage.get(aid)
        passed = bool(t and t["relevant"] and t["effective"] >= ANALYZE_MIN_IMPORTANCE)
        controls.append({"title": c["title"], "expect": c["expect"], "triage": t, "passed": passed})

    for case, row in analysis_queue:
        try:
            _guard(conn, ANALYSIS_MODEL, reserve)
        except BudgetExceeded as exc:
            row["error"] = str(exc)
            continue
        prompt, recent_text = case_prompt(case, all_cases, archive, src)
        a: Analysis = _call(client, model=ANALYSIS_MODEL, system=system_prompt(calibration_text), user=prompt,
                            out=Analysis, stage="bt_analysis", reasoning_effort=ANALYSIS_REASONING)
        a = keep_known_related(a, recent_text)
        n_sources = len({h["publisher"] for h in case["headlines"]})
        s, _, level = score(a, n_sources, 0.0)
        row.update({"analysis": a.model_dump(), "score": s, "level": level,
                    "direction_ok": a.yon == case["expected"]})

    summary = summarize(results, controls)
    out = {"label": label, "split": split, "calibration": str(calibration) if calibration else None,
           "run_at": datetime.now().isoformat(timespec="seconds"), "model": ANALYSIS_MODEL,
           "reasoning": ANALYSIS_REASONING, "summary": summary, "cases": results, "controls": controls}
    out_path = ARASTIRMA / "backtest" / f"sonuc_{label}.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    out["path"] = str(out_path)
    return out


def summarize(results: list[dict], controls: list[dict]) -> dict:
    analysed = [r for r in results if "analysis" in r]
    strong = [r for r in results if r["strength"] == "strong"]

    def share(rows, pred):
        return f"{sum(1 for r in rows if pred(r))}/{len(rows)}" if rows else "0/0"

    by_strength = {}
    for k in ("strong", "medium", "weak"):
        rows = [r for r in analysed if r["strength"] == k]
        by_strength[k] = round(sum(r["score"] for r in rows) / len(rows), 1) if rows else None
    return {
        "filtreden_gecen": share(results, lambda r: r["passed"]),
        "yon_dogru": share(analysed, lambda r: r["direction_ok"]),
        "guclu_olay_en_az_sari": share(strong, lambda r: r.get("level") in ("red", "yellow")),
        "guclu_olay_kirmizi": share(strong, lambda r: r.get("level") == "red"),
        "ortalama_skor": by_strength,
        "kontrol_yanlis_alarm": share(controls, lambda c: c["passed"]),
        "fiyat_basligi_tespiti": share(
            [c for c in controls if c["expect"] == "price_report"],
            lambda c: bool(c["triage"] and c["triage"]["price_report"]),
        ),
    }


ICON = {"red": "🔴", "yellow": "🟡", "digest": "📋"}
ARROW = {"yukari": "↑", "asagi": "↓", "notr": "→", "belirsiz": "↕"}


def print_result(out: dict) -> None:
    print(f"\n== Geriye donuk test: {out['label']} (split={out['split']}, kalibrasyon={out['calibration']}) ==")
    for r in out["cases"]:
        exp = ARROW[r["expected"]]
        if "analysis" in r:
            a = r["analysis"]
            mark = "✓" if r["direction_ok"] else "✗"
            print(f"{r['id']:<4} {r['split'][:5]:<6} beklenen {exp} {r['strength']:<6} -> {ICON[r['level']]} {r['score']:>3} "
                  f"{ARROW[a['yon']]} {mark}  {a['olay_turu']}/{a['beklenen_etki']}/{a['kaynak_guvenilirligi']}/"
                  f"{a['somutluk']}/{a['yenilik']}/g{a['guven']} | {r['headline'][:50]}")
        else:
            why = r.get("error") or f"filtre: onem={r['importance']} {[(x or {}).get('price_report') for x in r['triage']]}"
            print(f"{r['id']:<4} {r['split'][:5]:<6} beklenen {exp} {r['strength']:<6} -> analiz yok ({why}) | {r['headline'][:60]}")
    print("\nKontroller:")
    for c in out["controls"]:
        t = c["triage"] or {}
        flag = "YANLIS ALARM" if c["passed"] else "ok"
        print(f"  {flag:<12} ilgili={t.get('relevant')} fiyat={t.get('price_report')} onem={t.get('importance')} | {c['title'][:70]}")
    print("\nOzet:", json.dumps(out["summary"], ensure_ascii=False, indent=1))
    print("Kaydedildi:", out["path"])
