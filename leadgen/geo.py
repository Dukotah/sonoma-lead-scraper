"""
Geocoding + market resolution.

A "market" can be either a named entry in MARKETS (a bbox tuple) or a free-text
place name we geocode on the fly via Nominatim. bbox order is (south, west,
north, east) everywhere in this package.
"""
from __future__ import annotations

import math

import requests

from .audit import UA

NOMINATIM = "https://nominatim.openstreetmap.org/search"

# Largest market we'll scan without an explicit override. Sonoma County's bbox is
# ~9,000 sq km; a big metro ~5,000. A mistyped place that geocodes to a whole
# state/country (e.g. "California" ≈ 420,000 sq km) would otherwise trigger a huge,
# slow, costly Overture scan. Callers can raise this when they really mean it.
MAX_MARKET_SQKM = 60_000.0


def bbox_area_sqkm(bbox: tuple[float, float, float, float]) -> float:
    """Approximate area of a (south, west, north, east) bbox in square km."""
    south, west, north, east = bbox
    dlat = abs(north - south) * 111.0
    dlon = abs(east - west) * 111.0 * math.cos(math.radians((south + north) / 2))
    return dlat * dlon

# Reusable named markets (south, west, north, east). Grow this list as you expand.
MARKETS: dict[str, tuple[float, float, float, float]] = {
    "sonoma_county_ca": (38.05, -123.55, 38.85, -122.35),
    "phoenix_az":       (33.20, -112.40, 33.85, -111.80),
    "tampa_fl":         (27.80, -82.65, 28.20, -82.30),
    "austin_tx":        (30.10, -97.95, 30.52, -97.55),
}


def geocode_city(place: str) -> dict | None:
    """Return {lat, lon, bbox=(s,w,n,e), display_name} for a free-text place."""
    try:
        r = requests.get(NOMINATIM, params={"q": place, "format": "json", "limit": 1},
                         headers={"User-Agent": UA}, timeout=10)
        if r.status_code != 200 or not r.json():
            return None
        d = r.json()[0]
        bb = [float(x) for x in d["boundingbox"]]  # nominatim: [s, n, w, e]
        return {
            "lat": float(d["lat"]), "lon": float(d["lon"]),
            "bbox": (bb[0], bb[2], bb[1], bb[3]),
            "display_name": d["display_name"],
        }
    except Exception:
        return None


def resolve_market(market: str, *, max_area_sqkm: float = MAX_MARKET_SQKM
                   ) -> tuple[tuple[float, float, float, float], str]:
    """Accept a named market key OR a free-text place. Return (bbox, label).

    Free-text places are geocoded; if the result's bbox is larger than
    max_area_sqkm we refuse rather than launch a runaway scan. Named markets in
    MARKETS are trusted and skip the check. Pass max_area_sqkm=float('inf') to
    deliberately allow a very large area."""
    if market in MARKETS:
        return MARKETS[market], market
    geo = geocode_city(market)
    if not geo:
        raise ValueError(
            f"could not resolve market '{market}'. Use a key in MARKETS "
            f"({sorted(MARKETS)}) or a geocodable place like 'Austin, Texas'."
        )
    area = bbox_area_sqkm(geo["bbox"])
    if area > max_area_sqkm:
        raise ValueError(
            f"market '{market}' resolves to a very large area (~{area:,.0f} sq km, "
            f"limit {max_area_sqkm:,.0f}). Narrow it to a city/county "
            f"(e.g. 'Santa Rosa, California') to avoid a huge, slow scan."
        )
    return geo["bbox"], geo["display_name"]
