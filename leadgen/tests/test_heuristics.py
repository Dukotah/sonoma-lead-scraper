"""
Tests for the enrichment heuristics against realistic brokerage-HTML fixtures.
Run:  python leadgen/tests/test_heuristics.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from leadgen.enrich import estimate_roster, find_decision_maker, find_phrases
from leadgen.verticals.simply_tc import fingerprint_tc, CONFIG, _score, _opener
from leadgen.tests import fixtures as F


def _pages(html):
    return {"http://x.test/": html}


def test_roster_count_distinct():
    # BIG_SOFTWARE has 5 distinct agents (each linked twice + a license each)
    assert estimate_roster(_pages(F.BIG_SOFTWARE)) == 5
    # DUP_LINKS: 3 agents each linked twice → must be 3, not 6
    assert estimate_roster(_pages(F.DUP_LINKS)) == 3
    # SMALL_OPEN: 3 team links
    assert estimate_roster(_pages(F.SMALL_OPEN)) == 3
    # SOLO_AGENT: one license, no roster → 1
    assert estimate_roster(_pages(F.SOLO_AGENT)) in (0, 1)


def test_tc_gap_hiring_beats_in_house_phrase():
    # HIRING_TC contains "transaction coordinator" but they're HIRING → 'hiring'
    fp = fingerprint_tc(_pages(F.HIRING_TC), CONFIG)
    assert fp["tc_gap"] == "hiring", fp


def test_tc_gap_in_house():
    fp = fingerprint_tc(_pages(F.IN_HOUSE_TC), CONFIG)
    assert fp["tc_gap"] == "in_house", fp


def test_tc_gap_software():
    fp = fingerprint_tc(_pages(F.BIG_SOFTWARE), CONFIG)
    assert fp["tc_gap"] == "software" and fp["tc_software"] == "SkySlope", fp


def test_tc_gap_open():
    fp = fingerprint_tc(_pages(F.SMALL_OPEN), CONFIG)
    assert fp["tc_gap"] == "open", fp


def test_decision_maker_prefers_senior_title():
    # SMALL_OPEN has Susan Park (Broker/Owner) and others (Realtor) → pick the owner
    name, title = find_decision_maker(_pages(F.SMALL_OPEN), CONFIG["decision_maker_titles"])
    assert name == "Susan Park", (name, title)
    assert "broker" in title.lower() or "owner" in title.lower()


def test_decision_maker_managing_broker():
    name, title = find_decision_maker(_pages(F.IN_HOUSE_TC), CONFIG["decision_maker_titles"])
    assert name == "Greg Hall", (name, title)


def test_decision_maker_none_when_absent():
    name, title = find_decision_maker(_pages(F.DUP_LINKS), CONFIG["decision_maker_titles"])
    assert name == "" and title == ""


def test_end_to_end_scoring_hiring_is_hot():
    # A hiring brokerage with volume + contact should land Tier A and score high.
    rec = {"name": "Vanguard Properties", "website": "http://v.test",
           "agent_count": estimate_roster(_pages(F.HIRING_TC)), "phone": "555"}
    rec.update(fingerprint_tc(_pages(F.HIRING_TC), CONFIG))
    score, tier, why = _score(rec)
    assert tier == "A", (score, tier, why)
    assert "HIRING" in why
    assert "hiring a TC" in _opener(rec)


def test_end_to_end_scoring_open_small():
    rec = {"name": "Harbor Real Estate", "website": "http://h.test",
           "agent_count": estimate_roster(_pages(F.SMALL_OPEN)), "phone": "555",
           "decision_maker": "Susan Park"}
    rec.update(fingerprint_tc(_pages(F.SMALL_OPEN), CONFIG))
    score, tier, why = _score(rec)
    assert tier in ("A", "B"), (score, tier, why)
    assert "OPEN" in why


def test_in_house_scores_low():
    rec = {"name": "Summit", "website": "http://s.test",
           "agent_count": 3}
    rec.update(fingerprint_tc(_pages(F.IN_HOUSE_TC), CONFIG))
    score, tier, why = _score(rec)
    assert tier in ("B", "C")  # in-house = low priority


def _run_all():
    fns = [g for n, g in sorted(globals().items()) if n.startswith("test_")]
    failed = 0
    for fn in fns:
        try:
            fn(); print(f"  PASS {fn.__name__}")
        except AssertionError as e:
            failed += 1; print(f"  FAIL {fn.__name__}: {e}")
        except Exception as e:
            failed += 1; print(f"  ERROR {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(fns)-failed}/{len(fns)} passed")
    return failed


if __name__ == "__main__":
    raise SystemExit(_run_all())
