from datetime import datetime
from recorder.titles import gen_suffix, make_title, extract_suffix, title_contains_suffix, pick_match

def test_suffix_6_hex():
    s = gen_suffix(); assert len(s) == 6 and all(c in "0123456789abcdef" for c in s)

def test_make_title_ascii():
    t = make_title("Office discussion", datetime(2026,6,26,14,30,7), "a1b2c3")
    assert t == "Office discussion 2026-06-26 14:30:07 a1b2c3" and t.isascii()

def test_extract_suffix():
    assert extract_suffix("Office discussion 2026-06-26 14:30:07 a1b2c3") == "a1b2c3"
    assert extract_suffix("nope") is None

def test_contains_suffix():
    assert title_contains_suffix("a1b2c3", "Meeting a1b2c3") is True
    assert title_contains_suffix("a1b2c3", "Meeting zzz") is False

def test_pick_match_single_ignores_duration():
    # item 600s; transcript says 10 (minutes) -> still matches on suffix alone
    ts = [{"id": "T1", "title": "x a1b2c3", "duration": 10}]
    assert pick_match("a1b2c3", 600.0, ts)["id"] == "T1"

def test_pick_match_disambiguates_by_duration_minutes():
    ts = [{"id": "T1", "title": "a a1b2c3", "duration": 5},    # 300s
          {"id": "T2", "title": "b a1b2c3", "duration": 10}]   # 600s -> closer to 590s item
    assert pick_match("a1b2c3", 590.0, ts)["id"] == "T2"

def test_pick_match_none_when_absent():
    assert pick_match("a1b2c3", 600.0, [{"id":"T","title":"none","duration":10}]) is None
