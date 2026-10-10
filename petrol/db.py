import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import DATA_DIR, DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    norm_title TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    article_count INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY,
    feed TEXT NOT NULL,
    publisher TEXT,
    title TEXT NOT NULL,
    url TEXT NOT NULL UNIQUE,
    summary TEXT,
    published_at TEXT,
    first_seen_at TEXT NOT NULL,
    initial INTEGER NOT NULL DEFAULT 0,      -- ilk taramada gelen eski haber (gecikme olcumune girmez)
    prefilter_pass INTEGER NOT NULL DEFAULT 1,
    event_id INTEGER REFERENCES events(id),
    triage_status TEXT NOT NULL DEFAULT 'pending'  -- pending | relevant | irrelevant | skipped
);
CREATE INDEX IF NOT EXISTS idx_articles_event ON articles(event_id);
CREATE INDEX IF NOT EXISTS idx_articles_seen ON articles(first_seen_at);

CREATE TABLE IF NOT EXISTS feed_state (
    feed TEXT PRIMARY KEY,
    etag TEXT,
    last_modified TEXT,
    last_ok_at TEXT,
    last_error TEXT
);

CREATE TABLE IF NOT EXISTS prices (
    symbol TEXT NOT NULL,
    ts TEXT NOT NULL,
    price REAL NOT NULL,
    PRIMARY KEY (symbol, ts)
);

CREATE TABLE IF NOT EXISTS daily_prices (
    symbol TEXT NOT NULL,
    day TEXT NOT NULL,
    close REAL NOT NULL,
    PRIMARY KEY (symbol, day)
);

CREATE TABLE IF NOT EXISTS analyses (
    event_id INTEGER PRIMARY KEY REFERENCES events(id),
    created_at TEXT NOT NULL,
    model TEXT NOT NULL,
    etki_kanali TEXT, olay_turu TEXT, yon TEXT, buyukluk TEXT, sure TEXT,
    kesinlik TEXT, yenilik TEXT, guven INTEGER, gerekce TEXT, aktorler TEXT,
    n_sources INTEGER,
    brent_at_event REAL,
    brent_move_pct REAL,
    market_open INTEGER,
    priced_in INTEGER,
    score INTEGER,
    level TEXT,                -- red | yellow | digest
    notified INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS llm_usage (
    ts TEXT NOT NULL,
    stage TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    total_tokens INTEGER
);
"""

# Sonradan eklenen kolonlar (mevcut veritabanlarini bozmadan)
MIGRATIONS = {
    "events": {
        "relevant": "INTEGER",           # NULL = henuz filtrelenmedi
        "importance": "INTEGER",
        "analysis_status": "TEXT NOT NULL DEFAULT 'none'",  # none | done | skipped | failed | merged
        "analysis_attempts": "INTEGER NOT NULL DEFAULT 0",
    },
    "articles": {
        "triage_attempts": "INTEGER NOT NULL DEFAULT 0",
        "price_report": "INTEGER",       # 1 = baslik yalnizca fiyat hareketini anlatiyor
        "kategori": "TEXT",
    },
    "analyses": {
        "lider_beyani": "INTEGER",
        "baglam_destegi": "TEXT",       # yok | zayif | guclu
        "ilgili_olaylar": "TEXT",       # JSON olay id listesi
        "wti_move_pct": "REAL",
        "move_pct": "REAL",             # Brent ve WTI'nin birlikte teyit ettigi hareket (skorda kullanilan)
        # Analizcinin belirledigi BAGIMSIZ kaynak sayisi. Doluysa yeniden skorlamada haber sayisinin yerine
        # gecer: ayni ajans haberinin 11 kopyasi 11 teyit degildir.
        "independent_sources": "INTEGER",
        # Model v2 (Subat-Agustos bulgulari): buyukluk/kesinlik yerine
        "beklenen_etki": "TEXT",          # normalin_alti | normal | buyuk | cok_buyuk (normal gunun kati)
        "kaynak_guvenilirligi": "TEXT",   # resmi | ana_akim | tek_kaynak_zayif | taraf_medyasi | soylenti
        "somutluk": "TEXT",               # somut_eylem | gelisme_raporu | somut_tehdit | sartli_soz | soylem | analiz
        "normal_hareket_pct": "REAL",     # analiz anindaki normal gunluk hareket
        "beklenen_pct": "REAL",           # beklenen_etki x normal hareket (gosterim icin)
    },
}


def _migrate(conn: sqlite3.Connection) -> None:
    for table, cols in MIGRATIONS.items():
        existing = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        for col, decl in cols.items():
            if col not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def connect(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Varsayilan canli veritabani; testler ':memory:' veya gecici dosya verebilir."""
    if db_path is None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        db_path = DB_PATH
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    _migrate(conn)
    conn.commit()
    return conn


def log_usage(conn: sqlite3.Connection, stage: str, model: str, usage: dict) -> None:
    conn.execute(
        "INSERT INTO llm_usage VALUES (?, ?, ?, ?, ?, ?)",
        (
            iso(utcnow()),
            stage,
            model,
            usage.get("prompt_tokens"),
            usage.get("completion_tokens"),
            usage.get("total_tokens"),
        ),
    )
    conn.commit()


def usage_logger(conn: sqlite3.Connection):
    """LLMClient(on_usage=...) icin: her cevabin token kullanimini aninda kaydeder."""
    return lambda stage, model, usage: log_usage(conn, stage, model, usage)


def tokens_last_24h(conn: sqlite3.Connection, model: str) -> int:
    since = iso(utcnow() - timedelta(hours=24))
    row = conn.execute(
        "SELECT COALESCE(SUM(total_tokens), 0) FROM llm_usage WHERE model = ? AND ts >= ?", (model, since)
    ).fetchone()
    return row[0]
