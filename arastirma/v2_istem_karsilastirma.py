"""Eski istem (model v2, 3 Ekim) ile geriye donuk test: uretim kodunu degistirmeden v2 metinlerini geri yukler.

v2.1 farklari (10 Ekim): kategori referanslari, istem dersleri, somutluk/kaynak tanimlari, beklenen_etki kurali,
RECENT TREND satiri. Olay numarasi filtresi (keep_known_related) skoru etkilemedigi icin acik kalir.
Kullanim (proje kokunden): PYTHONPATH=. python arastirma/v2_istem_karsilastirma.py <vaka dosyasi> <etiket> [--ids E1,E2] [--reserve N] [--dry-run ID]
"""
import argparse
import sys
from pathlib import Path

from petrol import analyze, backtest, kategoriler

V2_KATEGORILER = {
    "savas": ("new wave of military strikes, war start, ceasefire collapse, combat resumes",
              "~3.5x normal when dominant (war start, 'ceasefire is over')"),
    "diplomasi_ileri": ("talks agreed/scheduled, progress reported, ceasefire, deal, strikes paused",
                        "~2x normal; ceasefire or signed deal up to ~5x"),
    "diplomasi_cikmaz": ("talks fail, proposal rejected, claims denied by the other side, truce fragile, hard conditions",
                         "~1.3x normal; a denial often reverses an earlier optimism move"),
    "altyapi": ("attack on or outage of energy infrastructure (field, refinery, pipeline, port), force majeure, output cut",
                "~1x normal; single facility hits often fade next day unless major export capacity is lost"),
    "diger": ("anything else", "-"),
}

# (v2.1 metni, v2 metni)
V2_SYSTEM_EDITS = [
    ("""- Rhetoric means repeating a known stance or vague words. A NEW position is not rhetoric: a principal
  refusing talks, rejecting a proposal or vowing not to yield; a party offering (even conditionally) to
  reopen supply; a major power pressing a party to de-escalate. These moved oil 1-2.4x a normal day.
""", ""),
    ("""- RECENT TREND (under MARKET) shows what the market has been pricing. News that cuts against a multi-day
  trend (a rejection after days of optimism-driven declines, a disruption after days of easing) tends to
  reverse part of it; news that only extends an already long trend is often partly priced in.
""", ""),
    ("""
- Keep size and certainty apart: beklenen_etki is the move IF the news is the day's driver; doubt about
  whether it happens, how long repairs take or whether a request is obeyed goes into guven, not into a
  smaller beklenen_etki.""", ""),
    ("""Start from the category history; first-of-kind concrete events can be cok_buyuk,
  repeated rhetoric is normalin_alti. Move away from the history only for scale (how much supply or
  risk is at stake) or novelty, never because the outcome is uncertain: that lowers guven instead.""",
     """Use the category history; first-of-kind concrete events can be cok_buyuk,
  repeated rhetoric is normalin_alti."""),
    ("""  outlet, unclear sourcing, or specialist sites and aggregators (OilPrice.com, Seeking Alpha,
  Investing.com, FXEmpire); taraf_medyasi""", """  outlet or unclear sourcing; taraf_medyasi"""),
    ("""draft agreed, talks advanced), or a new position or request by a principal or major power (proposal
  rejected, talks refused, pressure on a party); somut_tehdit = specific threat with target or deadline;
  sartli_soz = conditional offer or promise; soylem = repeating a known stance, general optimism or vague
  threat; analiz = commentary, forecast or explainer with no new event.""",
     """draft agreed, talks advanced); somut_tehdit = specific threat with target or deadline; sartli_soz =
  conditional offer or promise; soylem = general rhetoric, optimism or vague threat; analiz =
  commentary, forecast or explainer with no new event."""),
    ("""risk premium) and the main uncertainty. Only if MARKET says CLOSED, say the effect is expected at the
  next open; if it says OPEN, the effect is immediate and "the open" must not be mentioned.""",
     """risk premium) and the main uncertainty. Mention if the market is closed and the effect is expected
  at the open."""),
]


def restore_v2() -> None:
    system = analyze.SYSTEM
    for new, old in V2_SYSTEM_EDITS:
        assert system.count(new) == 1, f"v2.1 metni bulunamadi:\n{new}"
        system = system.replace(new, old)
    analyze.SYSTEM = system
    triage_v21_list = kategoriler.kategori_listesi(referansli=False)
    kategoriler.KATEGORILER.update(V2_KATEGORILER)
    assert backtest.TRIAGE_SYSTEM.count(triage_v21_list) == 1
    backtest.TRIAGE_SYSTEM = backtest.TRIAGE_SYSTEM.replace(
        triage_v21_list, kategoriler.kategori_listesi(referansli=False))
    backtest.trend_before = lambda day, prices=None: None   # v2'de egilim satiri yoktu


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("cases")
    ap.add_argument("label")
    ap.add_argument("--ids", default=None)
    ap.add_argument("--reserve", type=int, default=20000)
    ap.add_argument("--dry-run", default=None)
    args = ap.parse_args()
    restore_v2()
    out = backtest.run_backtest(Path(args.cases), "all", None, args.label, args.reserve, dry_run=args.dry_run,
                                only_ids=set(args.ids.split(",")) if args.ids else None)
    if out:
        out_path = Path(out["path"])
        import json
        data = json.loads(out_path.read_text(encoding="utf-8"))
        data["istem"] = "v2 (3 Ekim) - v2_karsilastirma.py ile geri yuklendi"
        out_path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        backtest.print_result(out)


if __name__ == "__main__":
    main()
