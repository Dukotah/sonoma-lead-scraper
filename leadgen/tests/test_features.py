"""
Tests for the mom-proofing features: demo mode, CRM dedupe, friendly errors.
Run:  python leadgen/tests/test_features.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from leadgen import get_vertical, run_pipeline
from leadgen.pipeline import load_crm_names
from leadgen.diagnostics import friendly_error, explain_empty_result


def test_demo_mode_runs_offline_and_tiers():
    v = get_vertical("simply_tc")
    leads = run_pipeline(v, market="(demo)", demo=True, enrich=True, log=lambda *_: None)
    assert len(leads) == 5, f"expected 5 demo leads, got {len(leads)}"
    # every lead got scored + an opener
    assert all("tier" in r and "opener" in r for r in leads)
    # the hiring brokerage should be the top lead
    assert leads[0]["name"] == "Vanguard Properties", [l["name"] for l in leads]
    assert leads[0]["tc_gap"] == "hiring"
    # the software brokerage detected SkySlope
    coastal = next(r for r in leads if r["name"] == "Coastal Realty Group")
    assert coastal["tc_gap"] == "software" and coastal["tc_software"] == "SkySlope"
    # the in-house one is low priority
    summit = next(r for r in leads if r["name"] == "Summit Brokerage")
    assert summit["tc_gap"] == "in_house"
    # decision-maker pulled for the small open brokerage
    harbor = next(r for r in leads if r["name"] == "Harbor Real Estate")
    assert harbor["decision_maker"] == "Susan Park"


def test_crm_dedupe_removes_existing():
    csv_text = "Company name,Phone\nHarbor Real Estate,555\n\"Coastal Realty Group, LLC\",555\n"
    names = load_crm_names(csv_text, is_text=True)
    assert names, "no names parsed"
    v = get_vertical("simply_tc")
    leads = run_pipeline(v, market="(demo)", demo=True, enrich=True,
                         exclude_names=names, log=lambda *_: None)
    got = {l["name"] for l in leads}
    assert "Harbor Real Estate" not in got, "CRM dedupe failed to remove Harbor"
    assert "Coastal Realty Group" not in got, "normalized CRM match failed"
    assert "Vanguard Properties" in got, "wrongly removed a non-CRM lead"


def test_load_crm_names_various_headers():
    assert load_crm_names("Business,City\nAcme Realty,Reno\n", is_text=True) == {"acme"}
    assert load_crm_names("name\nThe Smith Team\n", is_text=True) == {"smith"}
    # no header match → falls back to first column
    assert load_crm_names("foo,bar\nWidget Co,x\n", is_text=True) == {"widget"}
    assert load_crm_names("", is_text=True) == set()


def test_friendly_error_translates():
    assert "place name" in friendly_error("could not resolve market 'Xyz'").lower()
    assert "openstreetmap" in friendly_error("All Overpass mirrors failed (HTTP 403)").lower()
    assert "network" in friendly_error("Host not in allowlist").lower()
    # unknown errors pass through unchanged
    assert friendly_error("some weird thing") == "some weird thing"


def test_explain_empty_result():
    msg = explain_empty_result("Tiny Town, MT", ("overture",), "TC leads")
    assert "Tiny Town" in msg and "larger" in msg.lower()


def _run_all():
    fns = [g for n, g in sorted(globals().items()) if n.startswith("test_")]
    failed = 0
    for fn in fns:
        try:
            fn(); print(f"  PASS {fn.__name__}")
        except AssertionError as e:
            failed += 1; print(f"  FAIL {fn.__name__}: {e}")
        except Exception as e:
            import traceback
            failed += 1; print(f"  ERROR {fn.__name__}: {type(e).__name__}: {e}")
            traceback.print_exc()
    print(f"\n{len(fns)-failed}/{len(fns)} passed")
    return failed


if __name__ == "__main__":
    raise SystemExit(_run_all())
