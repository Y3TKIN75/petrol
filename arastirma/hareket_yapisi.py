"""Buyuk hareket gunlerinin yapisi: sok mu yayilma mi, hangi saat, sonraki gunlerde kalicilik.

Girdi: veri/gunluk_bz_cl.csv, veri/saatlik_cl.csv (gecmis_hareketler.py uretir). Saatlik veri WTI'dir.
"""
import csv
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

VERI = Path(__file__).parent / "veri"


def load():
    daily = list(csv.DictReader((VERI / "gunluk_bz_cl.csv").open(encoding="utf-8")))
    hourly = [(datetime.fromisoformat(r["ts_utc"]), float(r["close"]))
              for r in csv.DictReader((VERI / "saatlik_cl.csv").open(encoding="utf-8"))]
    return daily, hourly


def main(bas="2026-02-01", son="2026-08-31", esik=3.0):
    sys.stdout.reconfigure(encoding="utf-8")
    daily, hourly = load()
    idx = {r["day"]: i for i, r in enumerate(daily)}
    # Saatlik getiriler (seans boslugu dahil: pazar acilisi gibi)
    hret = []
    for (t0, p0), (t1, p1) in zip(hourly, hourly[1:]):
        hret.append((t1, (p1 / p0 - 1) * 100, (t1 - t0).total_seconds() / 3600))
    # Vadeli seans bir onceki gun 22:00 UTC'de acilir: saatleri takvim gunune degil seans gunune ata
    by_day = defaultdict(list)
    for t, r, gap in hret:
        by_day[(t + timedelta(hours=2)).date().isoformat()].append((t, r, gap))

    rows = []
    for r in daily:
        if not (bas <= r["day"] <= son):
            continue
        w = float(r["wti_pct"])
        if abs(w) < esik or r["flag"]:
            continue
        hours = by_day.get(r["day"], [])
        if not hours:
            continue
        top = max(hours, key=lambda x: abs(x[1]))
        share = abs(top[1]) / abs(w) if w else 0
        i = idx[r["day"]]
        nxt = [float(daily[j]["wti_pct"]) for j in range(i + 1, min(i + 4, len(daily)))]
        rows.append({"day": r["day"], "wti": w, "top_hour": top[0].strftime("%H:%M"), "top_ret": top[1],
                     "gap": top[2] > 1.5, "share": share, "d1": nxt[0] if nxt else None,
                     "d3": sum(nxt) if len(nxt) == 3 else None})

    print(f"Tutarli buyuk WTI gunleri (|%| >= {esik}, Brent/WTI ayrismasi olanlar haric): {len(rows)}")
    shock = [x for x in rows if x["share"] >= 0.5]
    print(f"  Hareketin >= %50'si tek saatte: {len(shock)}/{len(rows)} gun (sok tipi)")
    print(f"  En buyuk saat seans acilisi/boslugu sonrasi: {sum(x['gap'] for x in rows)}/{len(rows)}")
    hours = Counter(x["top_hour"][:2] for x in rows)
    print("  En buyuk saatin UTC dagilimi:", dict(sorted(hours.items())))

    # Kalicilik: buyuk gunden sonra ayni yonde devam mi, geri donus mu
    def sgn(v):
        return 1 if v > 0 else -1
    d1 = [x for x in rows if x["d1"] is not None]
    cont1 = sum(1 for x in d1 if sgn(x["d1"]) == sgn(x["wti"]))
    d3 = [x for x in rows if x["d3"] is not None]
    rev = [-x["d3"] * sgn(x["wti"]) for x in d3]   # pozitif = geri donus
    print(f"  Ertesi gun ayni yonde devam: {cont1}/{len(d1)}")
    print(f"  Sonraki 3 gunde geri donus (hareketin yuzdesi olarak, medyan): "
          f"{statistics.median([g / abs(x['wti']) * 100 for g, x in zip(rev, d3)]):.0f}%")
    for kind, sel in (("yukselis", [x for x in d3 if x["wti"] > 0]), ("dusus", [x for x in d3 if x["wti"] < 0])):
        if sel:
            m = statistics.median([-x["d3"] * sgn(x["wti"]) / abs(x["wti"]) * 100 for x in sel])
            print(f"    {kind}: {len(sel)} gun, 3 gunluk medyan geri donus {m:.0f}%")

    print("\nGun bazinda (WTI):")
    for x in rows:
        d1s = f"{x['d1']:+.1f}" if x["d1"] is not None else "  -"
        d3s = f"{x['d3']:+.1f}" if x["d3"] is not None else "  -"
        print(f"  {x['day']} {x['wti']:+6.2f}% | en buyuk saat {x['top_hour']} {x['top_ret']:+5.2f}%"
              f"{' (acilis)' if x['gap'] else '':9} pay {x['share']*100:3.0f}% | ertesi {d1s} | 3 gun {d3s}")


if __name__ == "__main__":
    main()
