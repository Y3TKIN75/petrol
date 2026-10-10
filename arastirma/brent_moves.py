"""Brent'in son donemdeki en sert gunluk ve saatlik hareketlerini bulur.

Kullanim: python arastirma/brent_moves.py [--range 3mo] [--top 10]
Cikti: arastirma/veri/brent_daily.csv, brent_15m.csv ve konsolda siralama.
"""
import argparse
import csv
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

URL = "https://query1.finance.yahoo.com/v8/finance/chart/BZ=F?interval={interval}&range={range}"
OUT = Path(__file__).parent / "veri"


def fetch(interval: str, rng: str) -> list[tuple[datetime, float, float, float, float]]:
    resp = httpx.get(URL.format(interval=interval, range=rng), headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    resp.raise_for_status()
    res = resp.json()["chart"]["result"][0]
    q = res["indicators"]["quote"][0]
    rows = []
    for i, ts in enumerate(res["timestamp"]):
        o, h, l, c = q["open"][i], q["high"][i], q["low"][i], q["close"][i]
        if None not in (o, h, l, c):
            rows.append((datetime.fromtimestamp(ts, tz=timezone.utc), o, h, l, c))
    return rows


def save(name: str, rows) -> None:
    OUT.mkdir(exist_ok=True)
    with open(OUT / name, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ts_utc", "open", "high", "low", "close"])
        for ts, o, h, l, c in rows:
            w.writerow([ts.strftime("%Y-%m-%d %H:%M"), f"{o:.2f}", f"{h:.2f}", f"{l:.2f}", f"{c:.2f}"])


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--range", default="3mo")
    ap.add_argument("--top", type=int, default=10)
    args = ap.parse_args()

    daily = fetch("1d", args.range)
    save("brent_daily.csv", daily)
    changes = [
        (daily[i][0], daily[i - 1][4], daily[i][4], (daily[i][4] / daily[i - 1][4] - 1) * 100,
         (daily[i][2] - daily[i][3]) / daily[i - 1][4] * 100)
        for i in range(1, len(daily))
    ]
    print(f"== Gunluk kapanis degisimi, en sert {args.top} ({daily[0][0]:%Y-%m-%d} .. {daily[-1][0]:%Y-%m-%d}) ==")
    for d, prev, close, pct, rng in sorted(changes, key=lambda x: -abs(x[3]))[: args.top]:
        print(f"  {d:%Y-%m-%d %a}  {prev:7.2f} -> {close:7.2f}  {pct:+6.2f}%  (gun ici aralik {rng:.1f}%)")

    # 15 dk veri Yahoo'da son 60 gun icin var; 1 saatlik pencerelerdeki en sert hareketler
    bars = fetch("15m", "1mo")
    save("brent_15m.csv", bars)
    windows = []
    for i in range(4, len(bars)):
        start, end = bars[i - 4], bars[i]
        if (end[0] - start[0]).total_seconds() > 3600 * 1.5:  # seans arasi bosluklari atla
            continue
        windows.append((start[0], end[0], start[4], end[4], (end[4] / start[4] - 1) * 100))
    picked: list = []
    for w in sorted(windows, key=lambda x: -abs(x[4])):
        # Ayni hareketin ust uste binen pencerelerini tek say
        if all(abs((w[1] - p[1]).total_seconds()) > 3 * 3600 for p in picked):
            picked.append(w)
        if len(picked) == args.top:
            break
    print(f"\n== 1 saatlik pencerede en sert {args.top} hareket (15 dk veri, UTC) ==")
    for s, e, p0, p1, pct in sorted(picked, key=lambda x: x[0]):
        print(f"  {s:%Y-%m-%d %a %H:%M} -> {e:%H:%M}  {p0:7.2f} -> {p1:7.2f}  {pct:+6.2f}%")


if __name__ == "__main__":
    main()
