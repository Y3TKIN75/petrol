import json
import os
import sqlite3
import sys
import time

from .analyze import run_analysis
from .collect import collect_once
from .config import ANALYSIS_MODEL, DATA_DIR, POLL_INTERVAL_SEC
from .db import connect, iso, usage_logger, utcnow
from .llm import LLMClient, LLMError
from .triage import run_triage

LEVEL_ICON = {"red": "🔴", "yellow": "🟡", "digest": "📋"}
ARROW = {"yukari": "↑", "asagi": "↓", "notr": "→", "belirsiz": "↕"}


def process(conn: sqlite3.Connection, client: LLMClient) -> None:
    """Bekleyen haberleri filtreler ve onemli olaylari analiz eder."""
    try:
        t = run_triage(conn, client)
        print(
            f"   filtre: llm={t['llm']} ({t['batches']} cagri) miras={t['inherited']} eski={t['stale']}"
            + (f" basarisiz={t['failed']}" if t["failed"] else "")
            + (" [butce doldu]" if t.get("budget_exhausted") else ""),
            flush=True,
        )
        for err in t["errors"]:
            print(f"   ! filtre: {err}", flush=True)
        a = run_analysis(conn, client)
    except LLMError as exc:
        print(f"   ! AI hatasi: {exc}", flush=True)
        return
    if a["merged"]:
        print(f"   birlestirilen olay: {a['merged']}", flush=True)
    for d in a["done"]:
        print(f"   {LEVEL_ICON[d['level']]} {d['score']:>3} {ARROW[d['yon']]} {d['title'][:100]}", flush=True)
    for d in (d for d in a["rescored"] if d["old"] != d["score"]):
        print(f"   ↻ {LEVEL_ICON[d['level']]} {d['old']}→{d['score']} {d['title'][:90]}", flush=True)
    for err in a["errors"]:
        print(f"   ! {err}", flush=True)


def acquire_single_instance_lock(name: str = "pipeline.lock"):
    """Ayni anda tek dongu: iki kopya butceyi iki kat harcar ve ayni kayitlar icin yarisir.

    Isletim sistemi kilidi surec bitince (cokme dahil) kendiliginden kalkar. Dondurulen dosya
    nesnesi surec boyunca acik tutulmalidir.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    handle = open(DATA_DIR / name, "a+")
    try:
        if os.name == "nt":
            import msvcrt
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    return handle


def run(once: bool = False, interval: int = POLL_INTERVAL_SEC, collect: bool = True) -> None:
    lock = acquire_single_instance_lock()
    if lock is None:
        print("Baska bir dongu zaten calisiyor; cikiliyor.", flush=True)
        sys.exit(2)
    conn = connect()
    client = LLMClient(on_usage=usage_logger(conn))
    while True:
        started = time.monotonic()
        if collect:
            stats = collect_once(conn)
            print(f"[{iso(utcnow())}] yeni={stats['new']} filtreden_gecen={stats['passed']} hata={len(stats['errors'])}", flush=True)
        process(conn, client)
        if once:
            break
        time.sleep(max(0.0, interval - (time.monotonic() - started)))


def _pct(v: float | None) -> str:
    return f"{v:+.2f}%" if v is not None else "-"


def print_signals(limit: int = 20, include_digest: bool = False) -> None:
    conn = connect()
    levels = ("red", "yellow", "digest") if include_digest else ("red", "yellow")
    rows = conn.execute(
        f"""SELECT a.*, e.title, e.first_seen_at FROM analyses a JOIN events e ON e.id = a.event_id
            WHERE a.level IN ({','.join('?' * len(levels))})
            ORDER BY e.first_seen_at DESC LIMIT ?""",
        (*levels, limit),
    ).fetchall()
    if not rows:
        print("Henuz sinyal yok.")
    for r in rows:
        flags = []
        if r["lider_beyani"]:
            flags.append("lider beyani")
        if r["baglam_destegi"] and r["baglam_destegi"] != "yok":
            flags.append(f"baglam: {r['baglam_destegi']}")
        if r["priced_in"]:
            flags.append("fiyata yansimis")
        if not r["market_open"]:
            flags.append("piyasa kapali")
        move = f"teyitli {_pct(r['move_pct'])} (Brent {_pct(r['brent_move_pct'])}, WTI {_pct(r['wti_move_pct'])})"
        if r["model"].startswith("claude"):
            source = " (Claude analizi)"
        elif r["model"] != ANALYSIS_MODEL:
            source = " (yedek model)"
        else:
            source = ""
        print(f"\n{LEVEL_ICON[r['level']]} [{r['score']}] {ARROW[r['yon']]} {r['title']}{source}")
        if r["beklenen_etki"]:
            # Model v2: beklenen etki normal gunun kati olarak, yanina yaklasik yuzde
            etki = f"{r['beklenen_etki']} (~%{r['beklenen_pct']:.1f}, normal gun %{r['normal_hareket_pct']:.1f})"
            nitelik = f"{r['kaynak_guvenilirligi']}, {r['somutluk']}, {r['yenilik']}"
        else:
            etki, nitelik = r["buyukluk"], f"{r['kesinlik']}, {r['yenilik']}"   # eski sema
        print(
            f"   {r['first_seen_at'][:16]}Z | {r['olay_turu']} / {r['etki_kanali']} | {etki}, {r['sure']} | "
            f"{nitelik} | guven {r['guven']} | kaynak {r['n_sources']} | {move}"
            + (f" | {', '.join(flags)}" if flags else "")
        )
        print(f"   {r['gerekce']}")
        actors = json.loads(r["aktorler"] or "[]")
        if actors:
            print(f"   aktorler: {', '.join(actors)}")
        for rel_id in json.loads(r["ilgili_olaylar"] or "[]"):
            rel = conn.execute("SELECT title FROM events WHERE id = ?", (rel_id,)).fetchone()
            if rel:
                print(f"   ↳ baglantili: {rel['title'][:100]}")
