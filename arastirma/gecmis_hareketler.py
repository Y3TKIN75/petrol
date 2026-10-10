"""Savas donemi (Subat 2026 - ) Brent/WTI gunluk ve saatlik hareketleri.

Ciktilar (arastirma/veri/):
  gunluk_bz_cl.csv  : gunluk kapanis, Brent ve WTI % degisim, tutarlilik bayragi
  saatlik_cl.csv    : WTI saatlik (Brent saatlik veri vade sonlarinda karisik oldugu icin WTI esas alinir)
Kullanim: python arastirma/gecmis_hareketler.py [--esik 3] [--bas 2026-02-01] [--son 2026-08-31]
"""
import argparse
import csv
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

OUT = Path(__file__).parent / "veri"
URL = "https://query1.finance.yahoo.com/v8/finance/chart/{s}?interval={i}&range={r}"


def fetch(symbol: str, interval: str, rng: str) -> list[tuple[datetime, float, float, float, float]]:
    resp = httpx.get(URL.format(s=symbol, i=interval, r=rng), headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
    resp.raise_for_status()
    res = resp.json()["chart"]["result"][0]
    q = res["indicators"]["quote"][0]
    out = []
    for i, ts in enumerate(res["timestamp"]):
        o, h, l, c = q["open"][i], q["high"][i], q["low"][i], q["close"][i]
        if None not in (o, h, l, c):
            out.append((datetime.fromtimestamp(ts, tz=timezone.utc), o, h, l, c))
    return out


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--esik", type=float, default=3.0)
    ap.add_argument("--bas", default="2026-02-01")
    ap.add_argument("--son", default="2026-08-31")
    args = ap.parse_args()
    OUT.mkdir(exist_ok=True)

    bz = {d.date().isoformat(): (o, h, l, c) for d, o, h, l, c in fetch("BZ=F", "1d", "1y")}
    cl = {d.date().isoformat(): (o, h, l, c) for d, o, h, l, c in fetch("CL=F", "1d", "1y")}
    days = sorted(set(bz) & set(cl))
    rows = []
    for prev, day in zip(days, days[1:]):
        b = (bz[day][3] / bz[prev][3] - 1) * 100
        w = (cl[day][3] / cl[prev][3] - 1) * 100
        # Vade gecislerinde ya da veri hatasinda iki piyasa ayrisir: isaretle, analizde dikkat et
        flag = "TUTARSIZ" if (b * w < 0 and max(abs(b), abs(w)) > 1.5) or abs(b - w) > 3 else ""
        rng = (bz[day][1] - bz[day][2]) / bz[prev][3] * 100
        rows.append({"day": day, "brent": round(bz[day][3], 2), "wti": round(cl[day][3], 2),
                     "brent_pct": round(b, 2), "wti_pct": round(w, 2), "brent_range_pct": round(rng, 1), "flag": flag})
    with open(OUT / "gunluk_bz_cl.csv", "w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=list(rows[0]))
        wr.writeheader()
        wr.writerows(rows)

    hourly = fetch("CL=F", "60m", "1y")
    with open(OUT / "saatlik_cl.csv", "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["ts_utc", "open", "high", "low", "close"])
        for ts, o, h, l, c in hourly:
            wr.writerow([ts.strftime("%Y-%m-%d %H:%M"), f"{o:.2f}", f"{h:.2f}", f"{l:.2f}", f"{c:.2f}"])

    sel = [r for r in rows if args.bas <= r["day"] <= args.son]
    big = [r for r in sel if max(abs(r["brent_pct"]), abs(r["wti_pct"])) >= args.esik]
    print(f"Donem {sel[0]['day']}..{sel[-1]['day']}: {len(sel)} islem gunu, |hareket| >= %{args.esik}: {len(big)} gun")
    print(f"Saatlik WTI: {hourly[0][0]:%Y-%m-%d} .. {hourly[-1][0]:%Y-%m-%d} ({len(hourly)} cubuk)")
    for r in big:
        print(f"  {r['day']} {datetime.fromisoformat(r['day']):%a}  Brent {r['brent']:7.2f} {r['brent_pct']:+6.2f}%  "
              f"WTI {r['wti']:7.2f} {r['wti_pct']:+6.2f}%  aralik {r['brent_range_pct']:4.1f}%  {r['flag']}")


if __name__ == "__main__":
    main()
