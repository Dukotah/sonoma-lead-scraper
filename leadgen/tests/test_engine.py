"""
Tests for the pure (non-network) logic: scoring, fingerprinting, suppression
parsing, dedupe, and export. Run:  python -m pytest leadgen/tests -q
or simply:  python leadgen/tests/test_engine.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import leadgen
from leadgen import get_vertical
from leadgen.suppression import norm, _candidates_from_html, build_suppression_set
from leadgen.verticals.simply_tc import _fingerprint_tc, CONFIG
from leadgen.export import write_csv
from leadgen.pipeline import _dedupe


def test_verticals_registered():
    keys = set(leadgen.all_verticals())
    assert {"simply_tc", "web_design"} <= keys


def test_norm_strips_legal_suffixes():
    assert norm("Acme Realty, LLC") == norm("Acme Real Estate Group")
    assert norm("The Smith Team") == norm("Smith")
    assert norm("") == ""


def test_tc_fingerprint_priority():
    # in-house phrase beats software fingerprint
    html = "We have an in-house transaction coordinator. Powered by SkySlope."
    fp = _fingerprint_tc(html, CONFIG)
    assert fp["tc_gap"] == "in_house"
    # software only
    fp = _fingerprint_tc("Listings managed in Dotloop.", CONFIG)
    assert fp["tc_gap"] == "software" and fp["tc_software"] == "Dotloop"
    # nothing → open (the good leads)
    fp = _fingerprint_tc("Welcome to our brokerage. Buy and sell homes.", CONFIG)
    assert fp["tc_gap"] == "open"


def test_tc_scoring_tiers():
    v = get_vertical("simply_tc")
    hot = {"name": "Open Brokerage", "agent_count": 25, "tc_gap": "open",
           "phone": "555", "decision_maker": "Jane Broker"}
    score, tier, _ = v.score(hot)
    assert tier == "A" and score >= 55
    # suppressed competitor client sinks to the bottom regardless of volume
    taken = {"name": "Taken Realty", "agent_count": 40, "tc_gap": "open",
             "suppressed": True, "suppressed_by": "RivalTC", "phone": "555"}
    s2, t2, why = v.score(taken)
    assert t2 == "C" and s2 < 0 and "SUPPRESSED" in why


def test_suppression_parsing_and_build():
    html = '''
      <blockquote>Great service! — Jane Doe, Coastal Realty Group</blockquote>
      <img alt="Summit Properties" src="logo.png">
      <cite>Harbor Real Estate</cite>
    '''
    names = _candidates_from_html(html)
    assert any("coastal" in n.lower() for n in names)
    assert any("summit" in n.lower() for n in names)


def test_dedupe_merges_and_fills():
    leads = [
        {"name": "Acme Realty LLC", "website": "", "phone": "111"},
        {"name": "Acme Real Estate Group", "website": "http://acme.com", "phone": ""},
    ]
    out = _dedupe(leads)
    assert len(out) == 1
    assert out[0]["website"] == "http://acme.com"  # filled from the duplicate
    assert out[0]["phone"] == "111"


def test_export_csv_uses_vertical_columns():
    v = get_vertical("simply_tc")
    rows = [{"name": "X Brokerage", "tier": "A", "score": 70, "city": "Reno"}]
    with tempfile.TemporaryDirectory() as d:
        p = write_csv(rows, v.columns, os.path.join(d, "out.csv"))
        content = open(p, encoding="utf-8").read()
    assert "Brokerage" in content and "X Brokerage" in content and "Tier" in content


def _run_all():
    fns = [g for n, g in sorted(globals().items()) if n.startswith("test_")]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"  PASS {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL {fn.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"  ERROR {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(fns)-failed}/{len(fns)} passed")
    return failed


if __name__ == "__main__":
    raise SystemExit(_run_all())
