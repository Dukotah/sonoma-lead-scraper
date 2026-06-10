"""
Demo mode — a fully offline sample run so a new user sees exactly what the tool
produces before their first real scrape. No network required.

demo_leads() returns a realistic set of raw brokerage records (the same shape the
collectors produce). The pipeline's demo path enriches them from bundled HTML
fixtures instead of fetching live sites, so scoring/tiering/openers all populate.
"""
from __future__ import annotations

from .tests import fixtures as F

# Raw records as a collector would return them, paired with the fixture HTML used
# to "enrich" them offline. Mix of gaps so the output shows every tier.
_DEMO = [
    (dict(name="Vanguard Properties", category="real_estate",
          website="http://vanguardproperties.demo", phone="415-555-0144", email="",
          address="2501 Mission St", city="San Francisco", state="CA", zip="94110",
          brand="", lat=37.75, lon=-122.41, source="demo", source_url=""),
     F.HIRING_TC),
    (dict(name="Harbor Real Estate", category="real_estate",
          website="http://harborrealestate.demo", phone="707-555-0102", email="info@harborre.com",
          address="120 Kentucky St", city="Petaluma", state="CA", zip="94952",
          brand="", lat=38.23, lon=-122.63, source="demo", source_url=""),
     F.SMALL_OPEN),
    (dict(name="Coastal Realty Group", category="real_estate",
          website="http://coastalrealtygroup.demo", phone="707-555-0101", email="",
          address="1 Main St", city="Santa Rosa", state="CA", zip="95401",
          brand="", lat=38.44, lon=-122.71, source="demo", source_url=""),
     F.BIG_SOFTWARE),
    (dict(name="Summit Brokerage", category="real_estate",
          website="http://summitbrokerage.demo", phone="707-555-0103", email="",
          address="55 Oak Ave", city="Sebastopol", state="CA", zip="95472",
          brand="", lat=38.40, lon=-122.82, source="demo", source_url=""),
     F.IN_HOUSE_TC),
    (dict(name="John Realtor", category="real_estate",
          website="http://johnrealtor.demo", phone="707-555-0104", email="",
          address="7 Pine Rd", city="Santa Rosa", state="CA", zip="95403",
          brand="", lat=38.46, lon=-122.70, source="demo", source_url=""),
     F.SOLO_AGENT),
]


def demo_records() -> list[dict]:
    """Raw lead dicts for the demo (deep-copied so callers can mutate freely)."""
    return [dict(rec) for rec, _ in _DEMO]


def demo_html_for(website: str) -> str:
    """The fixture HTML to use when 'enriching' a demo record's website."""
    for rec, html in _DEMO:
        if rec["website"] == website:
            return html
    return ""
