from datetime import datetime, timezone

import httpx

from .config import PRICE_SYMBOLS
from .db import iso

URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1m&range=1d"


async def fetch_prices(client: httpx.AsyncClient) -> list[tuple[str, str, float]]:
    """Dakikalik (sembol, zaman, fiyat) uclulerini dondurur. Hata olursa bos liste."""
    rows: list[tuple[str, str, float]] = []
    for symbol in PRICE_SYMBOLS:
        try:
            resp = await client.get(URL.format(symbol=symbol))
            resp.raise_for_status()
            result = resp.json()["chart"]["result"][0]
            closes = result["indicators"]["quote"][0]["close"]
            for ts, close in zip(result["timestamp"], closes):
                if close is not None:
                    rows.append((symbol, iso(datetime.fromtimestamp(ts, tz=timezone.utc)), float(close)))
        except Exception:
            continue
    return rows


DAILY_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=3mo"


def fetch_daily_closes(user_agent: str) -> list[tuple[str, str, float]]:
    """Son ~3 ayin gunluk kapanislari: (sembol, gun, kapanis). Normal gunluk hareket hesabi icin."""
    rows: list[tuple[str, str, float]] = []
    with httpx.Client(headers={"User-Agent": user_agent}, timeout=30) as client:
        for symbol in PRICE_SYMBOLS:
            try:
                resp = client.get(DAILY_URL.format(symbol=symbol))
                resp.raise_for_status()
                result = resp.json()["chart"]["result"][0]
                closes = result["indicators"]["quote"][0]["close"]
                for ts, close in zip(result["timestamp"], closes):
                    if close is not None:
                        day = datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()
                        rows.append((symbol, day, float(close)))
            except Exception:
                continue
    return rows
