"""
Tests for the production-hardening fixes: CSV/formula-injection sanitizing, the
SSRF guard on fetched URLs, the bbox area cap on geocoded markets, city-aware
dedupe, and enrich-budget prioritization. All offline (no network).

Run:  python leadgen/tests/test_hardening.py
"""
import csv
import io
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from leadgen import get_vertical
from leadgen.export import sanitize_cell, write_csv
from leadgen.audit import is_safe_url
from leadgen import geo
from leadgen.geo import bbox_area_sqkm, resolve_market, MARKETS
from leadgen.pipeline import _dedupe, _enrich_priority


# ───────────────────────── CSV / formula injection ───────────────────────────
def test_sanitize_neutralizes_formula_triggers():
    assert sanitize_cell("=cmd|'/c calc'!A1") == "'=cmd|'/c calc'!A1"
    assert sanitize_cell("+1-800-EVIL") == "'+1-800-EVIL"
    assert sanitize_cell("-2+3") == "'-2+3"
    assert sanitize_cell("@SUM(A1)") == "'@SUM(A1)"


def test_sanitize_leaves_safe_values_alone():
    assert sanitize_cell("Harbor Real Estate") == "Harbor Real Estate"
    assert sanitize_cell(70) == 70          # numeric score stays numeric
    assert sanitize_cell(None) is None
    assert sanitize_cell("") == ""


def test_write_csv_sanitizes_malicious_name():
    v = get_vertical("simply_tc")
    rows = [{"name": "=HYPERLINK(\"http://evil\")", "tier": "A", "score": 70}]
    with tempfile.TemporaryDirectory() as d:
        p = write_csv(rows, v.columns, os.path.join(d, "out.csv"))
        with open(p, encoding="utf-8") as f:
            parsed = list(csv.reader(f))
    name_col = [k for _, k in v.columns].index("name")
    assert parsed[1][name_col].startswith("'="), parsed[1][name_col]


# ───────────────────────────── SSRF guard ────────────────────────────────────
def test_is_safe_url_blocks_private_and_loopback():
    assert is_safe_url("http://127.0.0.1/") is False
    assert is_safe_url("http://localhost/") is False
    assert is_safe_url("http://10.0.0.1/") is False
    assert is_safe_url("http://192.168.1.5/") is False
    assert is_safe_url("http://169.254.169.254/") is False   # cloud metadata
    assert is_safe_url("http://[::1]/") is False
    assert is_safe_url("") is False


def test_is_safe_url_allows_public_literal():
    # A public literal IP resolves without DNS, keeping this test offline.
    assert is_safe_url("http://8.8.8.8/") is True


# ───────────────────────────── bbox area cap ─────────────────────────────────
def test_bbox_area_sane():
    sonoma = bbox_area_sqkm(MARKETS["sonoma_county_ca"])
    assert 5_000 < sonoma < 15_000, sonoma           # ~9,000 sq km
    huge = bbox_area_sqkm((32.5, -124.5, 42.0, -114.0))  # ~all of California
    assert huge > 300_000, huge


def test_resolve_named_market_skips_check():
    bbox, label = resolve_market("sonoma_county_ca")
    assert bbox == MARKETS["sonoma_county_ca"] and label == "sonoma_county_ca"


def test_resolve_market_refuses_huge_area(monkeypatch=None):
    # Stub geocoding to return a state-sized bbox; no network involved.
    orig = geo.geocode_city
    geo.geocode_city = lambda place: {
        "lat": 37.0, "lon": -119.0,
        "bbox": (32.5, -124.5, 42.0, -114.0), "display_name": "California"}
    try:
        raised = False
        try:
            resolve_market("California")
        except ValueError as e:
            raised = True
            assert "very large area" in str(e)
        assert raised, "expected ValueError for an oversized market"
    finally:
        geo.geocode_city = orig


# ───────────────────────────── city-aware dedupe ─────────────────────────────
def test_dedupe_keeps_distinct_cities():
    leads = [
        {"name": "Coldwell Banker", "city": "Santa Rosa", "phone": "111"},
        {"name": "Coldwell Banker", "city": "Petaluma", "phone": "222"},
    ]
    out = _dedupe(leads)
    assert len(out) == 2, "same-name offices in different cities must stay separate"


def test_dedupe_merges_same_city_and_blanks():
    leads = [
        {"name": "Harbor Realty LLC", "city": "Petaluma", "website": ""},
        {"name": "Harbor Real Estate", "city": "Petaluma", "website": "http://h.com"},
        {"name": "Harbor Realty", "city": "", "phone": "707"},
    ]
    out = _dedupe(leads)
    assert len(out) == 1, "same name + same/blank city should collapse"
    assert out[0]["website"] == "http://h.com"   # back-filled
    assert out[0]["phone"] == "707"              # back-filled from blank-city dupe


# ───────────────────────────── enrich priority ───────────────────────────────
def test_enrich_priority_prefers_real_website():
    real = {"website": "http://acme.com", "phone": "1"}
    social = {"website": "https://facebook.com/acme", "phone": "1"}
    nosite = {"website": "", "phone": "1"}
    ranked = sorted([nosite, social, real], key=_enrich_priority, reverse=True)
    assert ranked[0] is real, "a real website must be enriched first"
    assert ranked[-1] is nosite, "no-website leads should be enriched last"


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
