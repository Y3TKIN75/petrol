"""Belirli gun / saat araliklari icin gecmis petrol haberlerini toplar.

- Gunluk: Google News RSS (after:/before: filtresi, gun hassasiyeti)
- Gun ici: GDELT DOC API (dakika hassasiyetinde 'seendate'; istekler arasi >= 5 sn)

Kullanim: python arastirma/haber_tarama.py
Cikti: arastirma/veri/haberler.json
"""
import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import quote

import feedparser
import httpx

UA = {"User-Agent": "Mozilla/5.0"}
OUT = Path(__file__).parent / "veri" / "haberler.json"

DAYS = [
    "2026-08-31", "2026-09-01", "2026-09-09", "2026-09-10", "2026-09-11", "2026-09-13", "2026-09-14",
    "2026-09-15", "2026-09-16", "2026-09-17", "2026-09-18", "2026-09-21", "2026-09-23", "2026-09-24",
    "2026-09-25", "2026-09-28", "2026-09-29", "2026-10-01", "2026-10-02",
]
GN_QUERIES = ["oil prices", "Brent OR crude", "Hormuz OR Aramco OR OPEC OR Saudi oil", "Iran war OR ceasefire OR Trump Iran"]

# Brent ve WTI'nin birlikte hareket ettigi (gercek) gun ici soklar, UTC
WINDOWS = [
    ("2026-09-13 sonrasi pazar acilisi", "20260913180000", "20260913230000"),
    ("2026-09-18 07:30 dusus", "20260918050000", "20260918080000"),
    ("2026-09-24 16:15 dusus", "20260924150000", "20260924170000"),
    ("2026-09-28 16:15-17:00 dusus", "20260928150000", "20260928173000"),
    ("2026-10-01 17:45 yukselis", "20261001163000", "20261001184500"),
]


def google_news(day: str) -> list[dict]:
    d = date.fromisoformat(day)
    seen, out = set(), []
    for q in GN_QUERIES:
        full = f"{q} after:{d - timedelta(days=1)} before:{d + timedelta(days=1)}"
        url = f"https://news.google.com/rss/search?q={quote(full)}&hl=en-US&gl=US&ceid=US:en"
        feed = feedparser.parse(httpx.get(url, headers=UA, timeout=30).content)
        for e in feed.entries:
            if e.title in seen:
                continue
            seen.add(e.title)
            out.append({"published": e.get("published", ""), "title": e.title})
        time.sleep(1)
    return out


def gdelt(start: str, end: str) -> list[dict]:
    url = (
        "https://api.gdeltproject.org/api/v2/doc/doc?query="
        + quote("(oil OR crude OR brent OR hormuz OR aramco) sourcelang:english")
        + f"&mode=artlist&format=json&maxrecords=75&sort=dateasc&startdatetime={start}&enddatetime={end}"
    )
    for attempt in range(6):
        r = httpx.get(url, headers=UA, timeout=90)
        if r.status_code == 200:
            try:
                return [
                    {"seen": a["seendate"], "domain": a.get("domain", ""), "title": a["title"]}
                    for a in r.json().get("articles", [])
                ]
            except json.JSONDecodeError:
                return []
        time.sleep(10 * (attempt + 1))
    return [{"error": f"HTTP {r.status_code}"}]


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--gunler", help="Virgulle ayrilmis gun listesi veya dosya (her satir bir gun)")
    ap.add_argument("--cikti", default=str(OUT))
    ap.add_argument("--gun-ici-yok", action="store_true", help="GDELT gun ici pencerelerini atla")
    args = ap.parse_args()
    days = DAYS
    if args.gunler:
        src = Path(args.gunler)
        days = src.read_text(encoding="utf-8").split() if src.exists() else args.gunler.split(",")
    out_path = Path(args.cikti)
    result = {"daily": {}, "intraday": {}}
    for day in days:
        result["daily"][day] = google_news(day)
        print(f"{day}: {len(result['daily'][day])} baslik", flush=True)
    for label, start, end in ([] if args.gun_ici_yok else WINDOWS):
        time.sleep(6)
        result["intraday"][label] = gdelt(start, end)
        print(f"{label}: {len(result['intraday'][label])} haber", flush=True)
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"kaydedildi: {out_path}")


if __name__ == "__main__":
    main()
