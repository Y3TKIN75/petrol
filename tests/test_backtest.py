"""Geriye donuk test motorunun sizinti korumalari (API cagrisi yok)."""
import json

from petrol import backtest
from petrol.config import PROJECT_DIR


def _archive():
    return [
        {"title": "Saudi pipeline attacked by drones - Reuters", "day": "2026-09-10"},
        {"title": "Oil prices off highs after pipeline restart - CNBC", "day": "2026-09-10"},
        {"title": "Brent tops $100 on Hormuz fears - X", "day": "2026-09-10"},
        {"title": "Iran signals talks on Hormuz - AP", "day": "2026-09-11"},   # 1 gun once: alinmamali
        {"title": "Houthis attack Saudi port - AP", "day": "2026-09-12"},      # ayni gun: alinmamali
    ]


def test_prior_events_skip_previous_day_and_price_headlines():
    out = backtest.prior_day_events(_archive(), "2026-09-12", exclude=set())
    assert out == ["[2026-09-10] Saudi pipeline attacked by drones - Reuters"]


def test_prior_events_exclude_case_own_headlines():
    out = backtest.prior_day_events(_archive(), "2026-09-12",
                                    exclude={"Saudi pipeline attacked by drones - Reuters"})
    assert out == []


def test_world_state_timeline_only_contains_earlier_cases():
    cases = [
        {"now": "2026-09-01T12:00:00Z", "headlines": [{"title": "A"}]},
        {"now": "2026-09-10T12:00:00Z", "headlines": [{"title": "B"}]},
        {"now": "2026-09-20T12:00:00Z", "headlines": [{"title": "C"}]},
    ]
    text = backtest.world_state_for(cases[1], cases)
    assert "- 2026-09-01: A" in text and "B" not in text.split("gelismeleri")[-1] and "C" not in text


def test_case_file_headlines_exist_in_archive():
    spec = json.loads((PROJECT_DIR / "arastirma/backtest/vakalar.json").read_text(encoding="utf-8"))
    assert backtest.verify_headlines(spec, backtest.load_archive()) == []


def test_price_headline_regex_examples():
    is_price = backtest.PRICE_HEADLINE.search
    assert is_price("Oil surges 6%, Brent and US crude both surpass $100 on more tanker attacks")
    assert is_price("Oil prices fall after G7 agrees to reserve release")
    assert is_price("Brent tops $108 as Saudi pipeline shutdown deepens supply fears")
    assert not is_price("Saudi cancels some oil cargoes after pipeline hit, top buyer chasing alternatives")
    assert not is_price("Saudi Arabia shut down East-West crude oil pipeline after multiple attacks by drones")


def test_case_headlines_are_not_price_reports():
    spec = json.loads((PROJECT_DIR / "arastirma/backtest/vakalar.json").read_text(encoding="utf-8"))
    for case in spec["cases"]:
        for h in case["headlines"]:
            assert not backtest.PRICE_HEADLINE.search(h["title"]), h["title"]


def test_case_prompt_trend_stops_before_case_day():
    """H4 (23 Eylul): egilim 22 Eylul kapanisinda biter; 23 Eylul'un kendi hareketi istemde olmamali."""
    spec = json.loads((PROJECT_DIR / "arastirma/backtest/vakalar.json").read_text(encoding="utf-8"))
    case = next(c for c in spec["cases"] if c["id"] == "H4")
    prompt, recent = backtest.case_prompt(case, spec["cases"], backtest.load_archive())
    trend = next(line for line in prompt.splitlines() if line.startswith("RECENT TREND:"))
    assert "09-22" in trend and "09-23" not in trend
    assert recent in prompt
