"""Etiketleme icin gun ozeti: fiyat hareketi + o gunun (pazartesi ise hafta sonunun da) basliklari.

Kullanim: python arastirma/gun_ozeti.py veri/haberler_buyuk.json 2026-03-02 2026-03-03 ...
"""
import csv
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

VERI = Path(__file__).parent / "veri"
MONTHS = {m: f"{i:02d}" for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}
CAUSE = re.compile(r"\b(oil|crude|brent|wti)\b.*\b(on|as|after|amid|over|following|despite)\b", re.I)
EVENT = re.compile(r"\b(hormuz|aramco|opec|saudi|iran|iraq|israel|ceasefire|truce|talks|deal|strike|attack|"
                   r"blockade|sanction|pipeline|tanker|reserve|spr|iea|houthi|trump|kuwait|uae|qatar|force majeure|"
                   r"export|navy|missile|drone|war)\b", re.I)
JUNK = re.compile(r"obituar|olive oil|essential oil|motley|zacks|stock to buy|dividend|brent (rooker|burns|venables|hinds)",
                  re.I)


def pub_day(p: str) -> str:
    m = re.search(r"(\d{1,2}) (\w{3}) (\d{4})", p)
    return f"{m.group(3)}-{MONTHS.get(m.group(2), '??')}-{int(m.group(1)):02d}" if m else ""


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    data = json.loads((VERI.parent / sys.argv[1]).read_text(encoding="utf-8"))["daily"]
    prices = {r["day"]: r for r in csv.DictReader((VERI / "gunluk_bz_cl.csv").open(encoding="utf-8"))}
    for day in sys.argv[2:]:
        d = date.fromisoformat(day)
        # Pazartesi: cuma kapanisindan sonraki hafta sonu haberleri de bu gunun hareketini aciklar
        span = [d - timedelta(days=k) for k in range(0, 4 if d.weekday() == 0 else 2)]
        wanted = {x.isoformat() for x in span}
        items, seen = [], set()
        for it in data.get(day, []):
            t = it["title"]
            if t in seen or JUNK.search(t) or pub_day(it["published"]) not in wanted:
                continue
            seen.add(t)
            items.append((pub_day(it["published"]), t))
        cause = [x for x in items if CAUSE.search(x[1])]
        events = [x for x in items if x not in cause and EVENT.search(x[1])]
        p = prices.get(day, {})
        print(f"\n######## {day} {d:%a} | Brent {p.get('brent_pct', '?')}%  WTI {p.get('wti_pct', '?')}%  "
              f"{p.get('flag', '')} | {len(items)} baslik")
        for pd, t in sorted(cause, reverse=True)[:14]:
            print(f"  $ [{pd[5:]}] {t[:140]}")
        for pd, t in sorted(events, reverse=True)[:12]:
            print(f"  * [{pd[5:]}] {t[:140]}")


if __name__ == "__main__":
    main()
