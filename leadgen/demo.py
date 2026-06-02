"""
Demo mode — a fully offline sample run so a new user sees exactly what the tool
produces before their first real scrape. No network required.

Each vertical has its own bundled dataset (raw record + the fixture HTML used to
"enrich" it offline), so scoring/tiering/openers all populate from realistic pages
without a single network call. demo_records() and demo_html_lookup() are
vertical-aware; the pipeline passes the active vertical's key.
"""
from __future__ import annotations

from .tests import fixtures as F

# ── simply_tc: transaction-coordinator leads ─────────────────────────────────
# Raw records as a collector would return them, paired with the roster/TC fixture
# HTML used to "enrich" them offline. Mix of gaps so the output shows every tier.
_SIMPLY_TC = [
    (dict(name="Vanguard Properties", category="real_estate",
          website="http://demo/vanguard", phone="415-555-0144", email="",
          address="2501 Mission St", city="San Francisco", state="CA", zip="94110",
          brand="", lat=37.75, lon=-122.41, source="demo", source_url=""),
     F.HIRING_TC),
    (dict(name="Harbor Real Estate", category="real_estate",
          website="http://demo/harbor", phone="707-555-0102", email="info@harborre.com",
          address="120 Kentucky St", city="Petaluma", state="CA", zip="94952",
          brand="", lat=38.23, lon=-122.63, source="demo", source_url=""),
     F.SMALL_OPEN),
    (dict(name="Coastal Realty Group", category="real_estate",
          website="http://demo/coastal", phone="707-555-0101", email="",
          address="1 Main St", city="Santa Rosa", state="CA", zip="95401",
          brand="", lat=38.44, lon=-122.71, source="demo", source_url=""),
     F.BIG_SOFTWARE),
    (dict(name="Summit Brokerage", category="real_estate",
          website="http://demo/summit", phone="707-555-0103", email="",
          address="55 Oak Ave", city="Sebastopol", state="CA", zip="95472",
          brand="", lat=38.40, lon=-122.82, source="demo", source_url=""),
     F.IN_HOUSE_TC),
    (dict(name="John Realtor", category="real_estate",
          website="http://demo/john", phone="707-555-0104", email="",
          address="7 Pine Rd", city="Santa Rosa", state="CA", zip="95403",
          brand="", lat=38.46, lon=-122.70, source="demo", source_url=""),
     F.SOLO_AGENT),
]

# ── web_design: local businesses that need website work ──────────────────────
# Fixture HTML for the sites that DO exist, so the audit (HTTPS/mobile/builder)
# runs offline. The no-website and social-only records need no page at all — they
# score on the absence of a real site.
_HTML_NO_SSL = (
    "<html><head><title>Joe's Auto Repair</title></head>"
    "<body><h1>Joe's Auto Repair</h1><p>Brake & tire service. Call us.</p></body></html>"
)  # http:// + no viewport  -> "No HTTPS" + "not mobile-friendly"
_HTML_WIX = (
    "<html><head><title>Sonoma Family Law</title>"
    '<meta name="viewport" content="width=device-width, initial-scale=1">'
    '<script src="https://static.parastorage.com/services/wix.com/x.js"></script>'
    "</head><body><h1>Sonoma Family Law</h1></body></html>"
)  # https + mobile, but built on Wix -> "DIY (Wix)"
_HTML_CLEAN = (
    "<html><head><title>Green Valley Cafe — Healdsburg</title>"
    '<meta name="viewport" content="width=device-width, initial-scale=1"></head>'
    "<body><h1>Green Valley Cafe</h1><p>Farm-to-table breakfast & lunch.</p></body></html>"
)  # https + mobile + custom -> "real site, no obvious issues" (a low-priority lead)

_WEB_DESIGN = [
    (dict(name="Redwood Plumbing", category="plumber",
          website="", phone="707-555-0210", email="",
          address="14 Industrial Dr", city="Santa Rosa", state="CA", zip="95403",
          brand="", lat=38.46, lon=-122.71, source="demo", source_url=""),
     None),                                              # NO WEBSITE -> Tier A
    (dict(name="Bella Hair Salon", category="hairdresser",
          website="https://facebook.com/bellahairsalon", phone="707-555-0211", email="",
          address="88 4th St", city="Santa Rosa", state="CA", zip="95404",
          brand="", lat=38.44, lon=-122.71, source="demo", source_url=""),
     None),                                              # social-only -> Tier A
    (dict(name="Joe's Auto Repair", category="car_repair",
          website="http://joesautorepair.com", phone="707-555-0212", email="",
          address="320 Sebastopol Rd", city="Santa Rosa", state="CA", zip="95407",
          brand="", lat=38.43, lon=-122.74, source="demo", source_url=""),
     _HTML_NO_SSL),                                      # no SSL + not mobile -> Tier B
    (dict(name="Sonoma Family Law", category="lawyer",
          website="https://sonomafamilylaw.com", phone="707-555-0213",
          email="intake@sonomafamilylaw.com",
          address="200 Matheson St", city="Healdsburg", state="CA", zip="95448",
          brand="", lat=38.61, lon=-122.87, source="demo", source_url=""),
     _HTML_WIX),                                         # DIY builder -> Tier B
    (dict(name="Green Valley Cafe", category="restaurant",
          website="https://greenvalleycafe.com", phone="707-555-0214", email="",
          address="5 Plaza St", city="Healdsburg", state="CA", zip="95448",
          brand="", lat=38.61, lon=-122.86, source="demo", source_url=""),
     _HTML_CLEAN),                                       # solid site -> Tier C (skip)
]

_DATASETS = {"simply_tc": _SIMPLY_TC, "web_design": _WEB_DESIGN}


def _dataset(vertical_key: str) -> list:
    """The demo dataset for a vertical, falling back to simply_tc."""
    return _DATASETS.get(vertical_key, _SIMPLY_TC)


def demo_records(vertical_key: str = "simply_tc") -> list[dict]:
    """Raw lead dicts for the demo (deep-copied so callers can mutate freely)."""
    return [dict(rec) for rec, _ in _dataset(vertical_key)]


def demo_html_lookup(vertical_key: str = "simply_tc"):
    """Return a `lookup(website) -> html` for this vertical's bundled pages, so the
    vertical's enrich hook can 'fetch' a fixture page offline (empty string if none)."""
    data = _dataset(vertical_key)

    def lookup(website: str) -> str:
        for rec, html in data:
            if rec["website"] == website:
                return html or ""
        return ""

    return lookup
