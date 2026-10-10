"""Etiketli gunlerden kategori bazinda istatistik (veri/etiketli_gunler.json + gunluk_bz_cl.csv)."""
import csv
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

VERI = Path(__file__).parent / "veri"


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    data = json.loads((VERI / "etiketli_gunler.json").read_text(encoding="utf-8"))
    daily = list(csv.DictReader((VERI / "gunluk_bz_cl.csv").open(encoding="utf-8")))
    idx = {r["day"]: i for i, r in enumerate(daily)}

    def nxt(day, k):
        """Sonraki k gunun toplam hareketi (WTI ve Brent ortalamasi; tutarsiz gunlerde WTI)."""
        i = idx[day]
        tot = 0.0
        for r in daily[i + 1:i + 1 + k]:
            b, w = float(r["brent_pct"]), float(r["wti_pct"])
            tot += w if r["flag"] else (b + w) / 2
        return tot

    rows = data["buyuk"]
    print(f"Buyuk gun: {len(rows)} | haber yonu ile fiyat yonu tutarli: {sum(r['yon_tutarli'] for r in rows)}/{len(rows)}")

    def summary(sel):
        mags = [abs(r["hareket_pct"]) for r in sel]
        # Ertesi 1 ve 3 gunde ayni yonde devam (+) ya da geri donus (-), hareketin yuzdesi olarak
        f1 = [nxt(r["gun"], 1) * (1 if r["hareket_pct"] > 0 else -1) / abs(r["hareket_pct"]) * 100 for r in sel]
        f3 = [nxt(r["gun"], 3) * (1 if r["hareket_pct"] > 0 else -1) / abs(r["hareket_pct"]) * 100 for r in sel]
        return (f"n={len(sel):>2} medyan |%|={statistics.median(mags):4.1f} ort={statistics.mean(mags):4.1f} "
                f"aralik={min(mags):.1f}-{max(mags):.1f} | ertesi gun devam medyan {statistics.median(f1):+4.0f}% "
                f"| 3 gun {statistics.median(f3):+4.0f}%")

    print("\n== Birincil kategoriye gore ==")
    by = defaultdict(list)
    for r in rows:
        by[r["kategori"]].append(r)
    for k in sorted(by, key=lambda k: -statistics.median([abs(r["hareket_pct"]) for r in by[k]])):
        print(f"  {k:<17} {summary(by[k])}")

    print("\n== Yenilik ==")
    for y in ("ilk", "gelisme", "tekrar"):
        sel = [r for r in rows if r["yenilik"] == y]
        if sel:
            print(f"  {y:<8} {summary(sel)}")

    print("\n== Lider/bakan beyani birincil veya ikincil mi ==")
    for v in (True, False):
        sel = [r for r in rows if r["lider_beyani"] == v]
        print(f"  lider={v!s:<5} {summary(sel)}")
    lider_kat = Counter(r["kategori"] for r in rows if r["lider_beyani"])
    print("  lider beyanli gunlerin kategorileri:", dict(lider_kat))

    print("\n== Pazartesi (hafta sonu haberi) ==")
    mon = [r for r in rows if r["hafta_sonu_haberi"]]
    print(f"  {summary(mon)}  | tum buyuk gunlerin %{len(mon) / len(rows) * 100:.0f}'i "
          f"(pazartesi normalde ~%20)")

    print("\n== Yon ==")
    up = [r for r in rows if r["hareket_pct"] > 0]
    dn = [r for r in rows if r["hareket_pct"] < 0]
    print(f"  yukselis {summary(up)}")
    print(f"  dusus    {summary(dn)}")

    print("\n== Sessiz gun nedenleri (20 gun) ==")
    c = Counter(n for s in data["sessiz"] for n in s["nedenler"])
    for k, v in c.most_common():
        print(f"  {k:<14} {v}")


if __name__ == "__main__":
    main()
