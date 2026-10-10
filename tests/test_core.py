"""Cekirdek mantik testleri: AI cagrisi yapmaz (sahte istemci / sahte HTTP kullanir)."""
import json
from datetime import timedelta

import httpx
import pytest
from pydantic import BaseModel, ConfigDict

from petrol import llm
from petrol.analyze import Analysis, confirmed_move, market_context, run_analysis, score
from petrol.config import LEVEL_RED, LEVEL_YELLOW, MAX_LLM_ATTEMPTS
from petrol.db import connect, iso, utcnow
from petrol.dedupe import _similar, normalize
from petrol.llm import LLMClient, LLMError, RateLimited, _strict_schema
from petrol.merge import MergeItem, MergeResult, run_merge
from petrol.triage import TriageItem, TriageResult, _apply, _count_attempt


# ---------------------------------------------------------------- yardimcilar

@pytest.fixture
def conn(tmp_path):
    c = connect(tmp_path / "test.db")
    yield c
    c.close()


class FakeClient:
    """Sirayla hazir cevap veren / hata firlatan sahte LLM istemcisi."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.models = []

    def chat_json(self, model, system, user, out, stage, **kw):
        self.calls.append(stage)
        self.models.append(model)
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def make_analysis(**kw) -> Analysis:
    base = dict(
        etki_kanali="arz", olay_turu="altyapi", yon="yukari", beklenen_etki="buyuk", sure="gunler",
        kaynak_guvenilirligi="resmi", somutluk="somut_eylem", yenilik="yeni", lider_beyani=False,
        baglam_destegi="yok", ilgili_olaylar=[], guven=75, gerekce="-", anahtar_aktorler=[],
    )
    base.update(kw)
    return Analysis(**base)


def add_event(conn, eid, title, relevant=None, importance=None, status="none", minutes_ago=5):
    ts = iso(utcnow() - timedelta(minutes=minutes_ago))
    conn.execute(
        """INSERT INTO events (id, title, norm_title, first_seen_at, last_seen_at, article_count, relevant,
                               importance, analysis_status) VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?)""",
        (eid, title, normalize(title), ts, ts, relevant, importance, status),
    )


def add_article(conn, aid, event_id, title, status="pending", publisher="P"):
    ts = iso(utcnow() - timedelta(minutes=5))
    conn.execute(
        """INSERT INTO articles (id, feed, publisher, title, url, published_at, first_seen_at, event_id, triage_status)
           VALUES (?, 'f', ?, ?, ?, ?, ?, ?, ?)""",
        (aid, publisher, title, f"http://x/{aid}", ts, ts, event_id, status),
    )


def add_prices(conn, symbol, points):
    """points: [(dakika_once, fiyat)]"""
    conn.executemany(
        "INSERT INTO prices (symbol, ts, price) VALUES (?, ?, ?)",
        [(symbol, iso(utcnow() - timedelta(minutes=m)), p) for m, p in points],
    )


# ---------------------------------------------------------------- fiyat teyidi

def test_confirmed_move_requires_both_markets():
    assert confirmed_move(5.0, 0.0) == 0.0          # Brent sahte sicrama, WTI yerinde
    assert confirmed_move(5.0, -0.5) == 0.0         # zit yon: teyit yok
    assert confirmed_move(2.0, 1.5) == 1.5          # ayni yon: kucuk olan
    assert confirmed_move(-3.0, -1.2) == -1.2
    assert confirmed_move(None, 1.1) == 1.1         # tek veri varsa onu kullan
    assert confirmed_move(None, None) is None


def test_market_context_ignores_brent_contract_glitch(conn):
    # Olaydan once ve sonra: Brent %5 "sicrar" (kontrat karisikligi), WTI neredeyse yerinde
    add_prices(conn, "BZ=F", [(30, 100.0), (1, 105.0)])
    add_prices(conn, "CL=F", [(30, 90.0), (1, 90.1)])
    ctx = market_context(conn, iso(utcnow() - timedelta(minutes=20)))
    assert ctx["brent"]["move_pct"] == pytest.approx(5.0)
    assert abs(ctx["move_pct"]) < 0.2
    assert ctx["market_open"]
    _, priced_in, _ = score(make_analysis(), 1, ctx["move_pct"])
    assert not priced_in


def test_market_context_real_move_marks_priced_in(conn):
    add_prices(conn, "BZ=F", [(30, 100.0), (1, 101.6)])
    add_prices(conn, "CL=F", [(30, 90.0), (1, 91.35)])
    ctx = market_context(conn, iso(utcnow() - timedelta(minutes=20)))
    assert ctx["move_pct"] == pytest.approx(1.5, abs=0.01)
    _, priced_in, _ = score(make_analysis(yon="yukari"), 1, ctx["move_pct"])
    assert priced_in


def test_market_closed_when_ticks_stale(conn):
    add_prices(conn, "BZ=F", [(600, 100.0)])
    add_prices(conn, "CL=F", [(600, 90.0)])
    assert not market_context(conn, iso(utcnow()))["market_open"]


# ---------------------------------------------------------------- skor

def test_score_scenarios_from_design():
    # Aramco boru hatti yeniden basladi: resmi, somut, normalin 2 kati -> kirmizi
    restart = make_analysis(yon="asagi", olay_turu="toparlanma")
    fresh, priced, lvl = score(restart, 1, 0.0)
    assert lvl == "red" and fresh >= LEVEL_RED and not priced
    late, priced, lvl = score(restart, 3, -1.5)
    assert priced and late < fresh


def test_credible_report_is_not_crushed():
    # 6 Mayis: "ABD ve Iran anlasmaya yakin" (CNN, kaynak) -%7.8 -> en az sari olmali
    report = make_analysis(olay_turu="diplomasi_ileri", yon="asagi", etki_kanali="risk_primi",
                           kaynak_guvenilirligi="ana_akim", somutluk="gelisme_raporu", guven=70)
    assert score(report, 1, 0.0)[2] in ("yellow", "red")
    # Ayni icerik taraf medyasindan soylem olarak gelirse ozette kalir
    propaganda = report.model_copy(update={"kaynak_guvenilirligi": "taraf_medyasi", "somutluk": "soylem"})
    assert score(propaganda, 1, 0.0)[2] == "digest"


def test_weak_policy_news_stays_in_digest():
    # Kriz aninda rezerv salimi: resmi ve somut ama etkisi normalin alti
    spr = make_analysis(olay_turu="rezerv_yaptirim", yon="asagi", beklenen_etki="normalin_alti", guven=50)
    assert score(spr, 2, 0.0)[2] == "digest"


def test_repeated_rhetoric_scores_near_zero():
    repeat = make_analysis(olay_turu="lider_iyimser", yon="asagi", beklenen_etki="normalin_alti",
                           somutluk="soylem", yenilik="tekrar", lider_beyani=True, guven=30)
    s, _, lvl = score(repeat, 1, 0.0)
    assert lvl == "digest" and s < 10


def test_leader_floor_and_context():
    trump = make_analysis(olay_turu="lider_iyimser", yon="asagi", beklenen_etki="normal", somutluk="soylem",
                          lider_beyani=True, guven=55, etki_kanali="risk_primi")
    s_none, _, lvl = score(trump, 1, 0.0)
    assert lvl == "yellow" and s_none == LEVEL_YELLOW      # taban
    concrete = trump.model_copy(update={"olay_turu": "diplomasi_ileri", "somutluk": "somut_eylem",
                                        "beklenen_etki": "cok_buyuk", "guven": 85})
    assert score(concrete, 1, 0.0)[2] == "red"              # somut adimla kirmiziya cikabilir
    small = trump.model_copy(update={"beklenen_etki": "normalin_alti"})
    assert score(small, 1, 0.0)[2] == "digest"              # kucuk etki: taban uygulanmaz
    # Taraf medyasinin iddiasi, diger haberlerle guclu destekleniyorsa guvenilirlik acigi kapanir
    claim = make_analysis(kaynak_guvenilirligi="taraf_medyasi", baglam_destegi="yok")
    assert score(claim.model_copy(update={"baglam_destegi": "guclu"}), 1, 0.0)[0] > score(claim, 1, 0.0)[0]


def test_neutral_direction_never_alerts():
    assert score(make_analysis(yon="notr", guven=100), 4, 0.0) == (0, False, "digest")


# ---------------------------------------------------------------- tekrar eleme

def test_dedupe_keeps_distinct_eia_reports_apart():
    a = normalize("United States on track for record crude oil production in 2026")
    b = normalize("United States on track for record natural gas production in 2026")
    assert not _similar(a, b)


def test_dedupe_merges_syndicated_copies():
    t = normalize("US-Russia talks on Ukraine involve multi-billion dollar oil deal, NYT reports")
    assert _similar(t, t)


# ---------------------------------------------------------------- sema

def test_strict_schema_valid_for_all_models():
    for model in (TriageResult, Analysis, MergeResult):
        def check(node):
            if isinstance(node, dict):
                if node.get("type") == "object":
                    assert node.get("additionalProperties") is False
                    assert set(node.get("required", [])) == set(node.get("properties", {}))
                for v in node.values():
                    check(v)
            elif isinstance(node, list):
                for v in node:
                    check(v)
        check(_strict_schema(model.model_json_schema()))


def test_strict_schema_keeps_fields_named_like_keywords():
    class M(BaseModel):
        model_config = ConfigDict(extra="forbid")
        title: str
        default: int

    sch = _strict_schema(M.model_json_schema())
    assert set(sch["properties"]) == {"title", "default"}
    assert "title" not in sch["properties"]["title"]      # alanin ic "title" etiketi temizlenir


# ---------------------------------------------------------------- filtre

def test_triage_apply_price_report_caps_importance_and_merges(conn):
    add_event(conn, 1, "Saudi shuts pipeline", relevant=1, importance=5, status="done")
    add_event(conn, 10, "Oil jumps 4% on pipeline")
    add_event(conn, 11, "Aramco suspends Yanbu loadings")
    add_event(conn, 12, "Yanbu loadings halted by Aramco")
    add_event(conn, 13, "Gas prices in Ohio")
    add_article(conn, 100, 10, "Oil jumps 4% on pipeline")
    add_article(conn, 101, 11, "Aramco suspends Yanbu loadings")
    add_article(conn, 102, 12, "Yanbu loadings halted by Aramco")
    add_article(conn, 103, 13, "Gas prices in Ohio")
    batch = conn.execute("SELECT * FROM articles WHERE triage_status = 'pending'").fetchall()
    result = TriageResult(items=[
        TriageItem(id=100, relevant=True, price_report=True, kategori="altyapi", importance=5, event_ref=1,
                   same_as_article=None),
        TriageItem(id=102, relevant=True, price_report=False, kategori="altyapi", importance=4, event_ref=None,
                   same_as_article=101),
        TriageItem(id=101, relevant=True, price_report=False, kategori="altyapi", importance=4, event_ref=None,
                   same_as_article=None),
        TriageItem(id=103, relevant=False, price_report=False, kategori="diger", importance=1, event_ref=None,
                   same_as_article=None),
    ])
    applied = _apply(conn, batch, result, known_ids={1})
    assert applied == {100, 101, 102, 103}
    art = {r["id"]: r for r in conn.execute("SELECT * FROM articles")}
    assert art[100]["event_id"] == 1 and art[100]["price_report"] == 1
    assert art[102]["event_id"] == 11                       # ayni turdaki habere baglandi
    assert art[103]["triage_status"] == "irrelevant"
    ev = {r["id"]: r for r in conn.execute("SELECT * FROM events")}
    assert ev[1]["importance"] == 5                          # fiyat haberi onemi yukseltmedi (MAX)
    assert 12 not in ev                                      # bosalan olay silindi
    assert ev[13]["relevant"] == 0


def test_triage_price_report_alone_never_reaches_analysis(conn):
    add_event(conn, 20, "Oil prices rise 3% as tensions mount")
    add_article(conn, 200, 20, "Oil prices rise 3% as tensions mount")
    batch = conn.execute("SELECT * FROM articles").fetchall()
    _apply(conn, batch, TriageResult(items=[
        TriageItem(id=200, relevant=True, price_report=True, kategori="savas", importance=5, event_ref=None,
                   same_as_article=None)
    ]), known_ids=set())
    assert conn.execute("SELECT importance FROM events WHERE id = 20").fetchone()[0] == 2


def test_triage_category_floor_sends_leader_news_to_analysis():
    from petrol.config import ANALYZE_MIN_IMPORTANCE
    from petrol.triage import effective_importance

    def item(**kw):
        base = dict(id=1, relevant=True, price_report=False, kategori="diplomasi_cikmaz", importance=1,
                    event_ref=None, same_as_article=None)
        base.update(kw)
        return TriageItem(**base)

    # 20b 'Trump teklifi reddetti' haberine onem 1-2 verse bile analiz esigine cikar
    assert effective_importance(item()) == ANALYZE_MIN_IMPORTANCE
    assert effective_importance(item(importance=5)) == 5
    assert effective_importance(item(price_report=True, importance=5)) == 2      # fiyat haberi yine girmez
    assert effective_importance(item(relevant=False)) == 1                       # ilgisizse taban yok
    assert effective_importance(item(kategori="talep_makro")) == 1               # zorunlu kategori degil


def test_triage_attempts_fail_after_limit(conn):
    add_event(conn, 30, "x")
    add_article(conn, 300, 30, "x")
    for _ in range(MAX_LLM_ATTEMPTS - 1):
        assert _count_attempt(conn, [300]) == 0
    assert _count_attempt(conn, [300]) == 1
    assert conn.execute("SELECT triage_status FROM articles WHERE id = 300").fetchone()[0] == "failed"


# ---------------------------------------------------------------- analiz hata yonetimi

def test_rate_limit_does_not_burn_attempts(conn):
    add_event(conn, 40, "Pipeline restarts", relevant=1, importance=4)
    add_article(conn, 400, 40, "Pipeline restarts", status="relevant")
    out = run_analysis(conn, FakeClient([RateLimited("429")]))
    row = conn.execute("SELECT analysis_status, analysis_attempts FROM events WHERE id = 40").fetchone()
    assert tuple(row) == ("none", 0)
    assert any("hiz siniri" in e for e in out["errors"])


def test_llm_errors_retry_then_fail(conn):
    add_event(conn, 41, "Pipeline restarts", relevant=1, importance=4)
    add_article(conn, 410, 41, "Pipeline restarts", status="relevant")
    for i in range(MAX_LLM_ATTEMPTS):
        run_analysis(conn, FakeClient([LLMError("bozuk cikti")]))
        status = conn.execute("SELECT analysis_status FROM events WHERE id = 41").fetchone()[0]
        assert status == ("failed" if i == MAX_LLM_ATTEMPTS - 1 else "none")


def test_successful_analysis_is_stored_with_confirmed_move(conn):
    add_event(conn, 42, "Saudi pipeline reopens", relevant=1, importance=5, minutes_ago=20)
    add_article(conn, 420, 42, "Saudi pipeline reopens", status="relevant")
    add_prices(conn, "BZ=F", [(30, 100.0), (1, 95.0)])     # Brent sahte -%5
    add_prices(conn, "CL=F", [(30, 90.0), (1, 89.9)])
    a = make_analysis(yon="asagi", olay_turu="toparlanma")
    out = run_analysis(conn, FakeClient([a]))
    assert out["done"][0]["level"] == "red"                  # sahte Brent dususu "fiyata yansimis" saymadi
    row = conn.execute("SELECT * FROM analyses WHERE event_id = 42").fetchone()
    assert row["priced_in"] == 0 and abs(row["move_pct"]) < 0.2 and row["brent_move_pct"] < -4
    # Gunluk veri yokken varsayilan normal hareket; beklenen yuzde = kat x normal
    from petrol.config import DEFAULT_NORMAL_MOVE_PCT
    assert row["normal_hareket_pct"] == DEFAULT_NORMAL_MOVE_PCT
    assert row["beklenen_pct"] == pytest.approx(2.0 * DEFAULT_NORMAL_MOVE_PCT)
    assert row["beklenen_etki"] == "buyuk" and row["buyukluk"] is None


# ---------------------------------------------------------------- birlestirme

def test_merge_resolves_chains_and_ignores_invalid_targets(conn):
    add_event(conn, 1, "G7 approves 100M barrel release", relevant=1, importance=5, status="done")
    conn.execute(
        "INSERT INTO analyses (event_id, created_at, model, yon, score, level) VALUES (1, ?, 'm', 'asagi', 60, 'yellow')",
        (iso(utcnow()),),
    )
    for eid, title in [(2, "G7 to release 100m barrels"), (3, "G7 releases oil and diesel"),
                       (4, "Tanker hit near Hormuz"), (5, "Something else")]:
        add_event(conn, eid, title, relevant=1, importance=3)
        add_article(conn, eid * 10, eid, title, status="relevant")
    client = FakeClient([MergeResult(items=[
        MergeItem(event_id=2, duplicate_of=1),
        MergeItem(event_id=3, duplicate_of=2),      # zincir -> 1
        MergeItem(event_id=4, duplicate_of=None),
        MergeItem(event_id=5, duplicate_of=999),    # gecersiz hedef -> yok sayilir
    ])])
    assert run_merge(conn, client) == 2
    ev = {r["id"]: r for r in conn.execute("SELECT * FROM events")}
    assert ev[2]["analysis_status"] == "merged" and ev[3]["analysis_status"] == "merged"
    assert ev[4]["analysis_status"] == "none" and ev[5]["analysis_status"] == "none"
    assert conn.execute("SELECT event_id FROM articles WHERE id = 30").fetchone()[0] == 1


# ---------------------------------------------------------------- LLM istemcisi (sahte HTTP)

def _client(handler, usage_log=None):
    http = httpx.Client(base_url="https://llm.test", transport=httpx.MockTransport(handler))
    return LLMClient(on_usage=(lambda *a: usage_log.append(a)) if usage_log is not None else None, http=http)


def _ok(content, tokens=10):
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}],
                                     "usage": {"total_tokens": tokens}})


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)


def test_client_only_429_raises_rate_limited():
    c = _client(lambda req: httpx.Response(429, headers={"retry-after": "0"}))
    with pytest.raises(RateLimited):
        c.chat_json("m", "s", "u", MergeResult, stage="t")


def test_client_mixed_errors_raise_plain_llm_error():
    responses = iter([httpx.Response(500)] + [httpx.Response(429)] * 4)
    c = _client(lambda req: next(responses))
    with pytest.raises(LLMError) as exc:
        c.chat_json("m", "s", "u", MergeResult, stage="t")
    assert not isinstance(exc.value, RateLimited)


def test_client_logs_tokens_of_invalid_attempts_too():
    valid = json.dumps({"items": [{"event_id": 1, "duplicate_of": None}]})
    responses = iter([_ok("bozuk json", 30), _ok(valid, 20)])
    log = []
    c = _client(lambda req: next(responses), usage_log=log)
    result = c.chat_json("m", "s", "u", MergeResult, stage="merge")
    assert result.items[0].event_id == 1
    assert [entry[2]["total_tokens"] for entry in log] == [30, 20]   # basarisiz deneme de sayildi


def test_client_sends_strict_schema_and_temperature():
    seen = {}

    def handler(req):
        seen.update(json.loads(req.content))
        return _ok(json.dumps({"items": []}))

    _client(handler).chat_json("m", "s", "u", MergeResult, stage="t")
    assert seen["response_format"]["json_schema"]["strict"] is True
    assert "temperature" in seen and seen["include_reasoning"] is False


# ---------------------------------------------------------------- tekil dongu kilidi

def test_single_instance_lock(tmp_path, monkeypatch):
    from petrol import pipeline
    monkeypatch.setattr(pipeline, "DATA_DIR", tmp_path)
    first = pipeline.acquire_single_instance_lock("t.lock")
    assert first is not None
    import subprocess, sys
    # Kilit surec duzeyinde: ikinci bir surec ayni kilidi alamamali
    code = (
        "import sys; from pathlib import Path; from petrol import pipeline; "
        f"pipeline.DATA_DIR = Path(r'{tmp_path}'); "
        "sys.exit(0 if pipeline.acquire_single_instance_lock('t.lock') is None else 1)"
    )
    assert subprocess.run([sys.executable, "-c", code]).returncode == 0
    first.close()
    assert subprocess.run([sys.executable, "-c", code]).returncode == 1   # kilit birakilinca alinabilir


# ---------------------------------------------------------------- yedek model

def _burn(conn, model, tokens):
    conn.execute("INSERT INTO llm_usage (ts, stage, model, total_tokens) VALUES (?, 't', ?, ?)",
                 (iso(utcnow()), model, tokens))
    conn.commit()


def test_fallback_model_used_when_main_budget_exhausted(conn):
    from petrol.config import ANALYSIS_FALLBACK_MODEL, ANALYSIS_MODEL, DAILY_TOKEN_BUDGET
    _burn(conn, ANALYSIS_MODEL, DAILY_TOKEN_BUDGET)
    add_event(conn, 50, "Pipeline restarts", relevant=1, importance=4)
    add_article(conn, 500, 50, "Pipeline restarts", status="relevant")
    client = FakeClient([make_analysis(yon="asagi")])
    out = run_analysis(conn, client)
    assert client.models == [ANALYSIS_FALLBACK_MODEL]
    assert conn.execute("SELECT model FROM analyses WHERE event_id = 50").fetchone()[0] == ANALYSIS_FALLBACK_MODEL
    assert any("yedek" in e for e in out["errors"])


def test_no_call_when_both_budgets_exhausted(conn):
    from petrol.config import ANALYSIS_FALLBACK_MODEL, ANALYSIS_MODEL, DAILY_TOKEN_BUDGET
    _burn(conn, ANALYSIS_MODEL, DAILY_TOKEN_BUDGET)
    _burn(conn, ANALYSIS_FALLBACK_MODEL, DAILY_TOKEN_BUDGET)
    add_event(conn, 51, "Pipeline restarts", relevant=1, importance=4)
    add_article(conn, 510, 51, "Pipeline restarts", status="relevant")
    client = FakeClient([])
    run_analysis(conn, client)
    assert client.models == []
    assert conn.execute("SELECT analysis_status FROM events WHERE id = 51").fetchone()[0] == "none"


# ---------------------------------------------------------------- bagimsiz kaynak

def test_rescore_respects_analyst_independent_sources(conn):
    from petrol.analyze import rescore_recent
    add_event(conn, 60, "US-Russia talks involve oil deal, NYT reports", relevant=1, importance=4, status="done")
    for i in range(11):   # ayni NYT haberinin 11 kopyasi
        add_article(conn, 600 + i, 60, "US-Russia talks involve oil deal, NYT reports", status="relevant",
                    publisher=f"Yayinci{i}")
    a = make_analysis(yon="asagi", beklenen_etki="normalin_alti", kaynak_guvenilirligi="tek_kaynak_zayif", guven=40)
    s1, _, lvl1 = score(a, 1, 0.0)
    conn.execute(
        """INSERT INTO analyses (event_id, created_at, model, etki_kanali, olay_turu, yon, beklenen_etki, sure,
               kaynak_guvenilirligi, somutluk, yenilik, guven, gerekce, aktorler, lider_beyani, baglam_destegi,
               ilgili_olaylar, n_sources, independent_sources, score, level, market_open, priced_in)
           VALUES (60, ?, 'claude-test', 'arz', 'altyapi', 'asagi', 'normalin_alti', 'gunler', 'tek_kaynak_zayif',
                   'somut_eylem', 'yeni', 40, '-', '[]', 0, 'yok', '[]', 1, 1, ?, ?, 0, 0)""",
        (iso(utcnow()), s1, lvl1),
    )
    rescore_recent(conn)
    row = conn.execute("SELECT n_sources, score FROM analyses WHERE event_id = 60").fetchone()
    assert tuple(row) == (1, s1)          # 11 kopya skoru sisirmedi
    conn.execute("UPDATE analyses SET independent_sources = NULL WHERE event_id = 60")
    rescore_recent(conn)
    assert conn.execute("SELECT n_sources FROM analyses WHERE event_id = 60").fetchone()[0] == 11  # eski davranis


# ---------------------------------------------------------------- manuel analiz aktarimi

def test_apply_manual_analyses_merges_drops_and_scores(conn):
    from petrol.manual import apply_manual_analyses
    add_event(conn, 70, "Tanker hit off Oman", relevant=1, importance=4, status="done")
    add_event(conn, 71, "Kuwait tanker struck near Hormuz", relevant=1, importance=4, status="done")
    add_event(conn, 72, "Oil prices rise on tensions", relevant=1, importance=3, status="done")
    for eid in (70, 71, 72):
        add_article(conn, eid * 10, eid, f"t{eid}", status="relevant")
        conn.execute("INSERT INTO analyses (event_id, created_at, model, yon, score, level) VALUES (?, ?, 'groq', 'yukari', 50, 'yellow')",
                     (eid, iso(utcnow())))
    fields = dict(etki_kanali="risk_primi", olay_turu="sevkiyat", yon="yukari", beklenen_etki="normal",
                  sure="gunler", kaynak_guvenilirligi="resmi", somutluk="somut_eylem", yenilik="gelisme",
                  lider_beyani=False, baglam_destegi="guclu", ilgili_olaylar=[], guven=60, gerekce="-",
                  anahtar_aktorler=[])
    spec = {"model": "claude-test",
            "merges": [{"dup": 71, "target": 70}],
            "drop_analysis": [{"event_id": 72, "irrelevant": False}],
            "analyses": [dict(event_id=70, independent_sources=2, **fields)]}
    out = apply_manual_analyses(conn, spec)
    expected, _, lvl = score(make_analysis(**fields), 2, None)
    assert out[0]["score"] == expected and out[0]["level"] == lvl
    rows = {r["event_id"]: r for r in conn.execute("SELECT * FROM analyses")}
    assert set(rows) == {70} and rows[70]["model"] == "claude-test" and rows[70]["independent_sources"] == 2
    ev = {r["id"]: r for r in conn.execute("SELECT * FROM events")}
    assert ev[71]["analysis_status"] == "merged" and ev[72]["analysis_status"] == "skipped"


# ---------------------------------------------------------------- model v2: rejim ve eski satirlar

def test_normal_move_uses_wti_on_divergent_days():
    from petrol.regime import daily_move, normal_move_from_closes
    assert daily_move(2.0, 1.0) == pytest.approx(1.5)
    assert daily_move(-14.5, -1.2) == -1.2          # 1 Nisan vade kalintisi: WTI esas
    days = [f"2026-09-{d:02d}" for d in range(1, 23)]
    brent = {d: 100 * 1.01 ** i for i, d in enumerate(days)}     # her gun tam %1
    wti = {d: 90 * 1.01 ** i for i, d in enumerate(days)}
    v = normal_move_from_closes(brent, wti, before="2026-09-30")
    assert v == pytest.approx(1.0, abs=0.01)
    assert normal_move_from_closes(brent, wti, before="2026-09-05") is None   # yetersiz veri


def test_prompts_have_categories_filled_in():
    from petrol.analyze import system_prompt
    from petrol.kategoriler import KATEGORILER
    from petrol.triage import SYSTEM as TRIAGE_SYSTEM
    sp = system_prompt(None)
    assert "{kategoriler}" not in sp and "{kategoriler}" not in TRIAGE_SYSTEM
    assert all(k in sp and k in TRIAGE_SYSTEM for k in KATEGORILER)
    assert "history" in sp and "history" not in TRIAGE_SYSTEM


def test_legacy_rows_are_not_rescored(conn):
    from petrol.analyze import rescore_recent
    add_event(conn, 80, "eski", relevant=1, importance=4, status="done")
    add_article(conn, 800, 80, "eski", status="relevant")
    conn.execute(
        """INSERT INTO analyses (event_id, created_at, model, yon, buyukluk, kesinlik, guven, score, level, n_sources)
           VALUES (80, ?, 'groq', 'yukari', 'orta', 'iddia', 60, 47, 'yellow', 1)""", (iso(utcnow()),))
    assert rescore_recent(conn) == []
    assert conn.execute("SELECT score FROM analyses WHERE event_id = 80").fetchone()[0] == 47


# ---------------------------------------------------------------- model v2.1: egilim baglami, olay numarasi

def test_recent_trend_excludes_event_day_and_shows_both_markets():
    from petrol.regime import recent_trend_from_closes
    brent = {"2026-09-15": 100.0, "2026-09-16": 98.0, "2026-09-17": 97.0, "2026-09-18": 120.0}
    wti = {"2026-09-15": 90.0, "2026-09-16": 89.0, "2026-09-17": 88.0, "2026-09-18": 80.0}
    text = recent_trend_from_closes(brent, wti, before="2026-09-18")
    assert "09-17" in text and "09-18" not in text                      # olay gunu (sonuc) sizmaz
    assert "total Brent -3.0%, WTI -2.2%" in text
    assert recent_trend_from_closes(brent, wti, before="2026-09-16") is None   # tek kapanis yetmez


def test_market_text_carries_trend(conn):
    from petrol.analyze import format_market
    conn.execute("INSERT INTO daily_prices (symbol, day, close) VALUES ('BZ=F', '2026-01-05', 60), "
                 "('BZ=F', '2026-01-06', 63), ('CL=F', '2026-01-05', 55), ('CL=F', '2026-01-06', 57)")
    add_prices(conn, "BZ=F", [(30, 63.0), (1, 64.0)])
    add_prices(conn, "CL=F", [(30, 57.0), (1, 58.0)])
    text = format_market(market_context(conn, iso(utcnow() - timedelta(minutes=30))))
    assert "RECENT TREND: last 1 sessions" in text and "total Brent +5.0%" in text


def test_unknown_related_event_ids_are_dropped():
    from petrol.analyze import keep_known_related
    recent = "- E12 [2026-09-24T10:00] Houthis attack Yanbu -> yukari, normal\n- E15 [2026-09-24T11:00] Saudi says"
    a = keep_known_related(make_analysis(ilgili_olaylar=[15, 24, 12, 29]), recent)
    assert a.ilgili_olaylar == [15, 12]
    assert keep_known_related(make_analysis(ilgili_olaylar=[3]), "(none)").ilgili_olaylar == []
