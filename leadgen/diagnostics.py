"""
Diagnostics & friendly errors — make the tool safe for a non-technical user.

  check_connectivity()      probe every data source, return plain-English status
  friendly_error(exc)       turn an exception/log line into human guidance
  explain_empty_result()    why a run might have returned 0 leads

Nothing here raises; everything returns data the GUI/CLI can show as-is.
"""
from __future__ import annotations

import time

import requests

from .audit import UA

# Each probe: (key, label, how-to-test). Kept tiny + fast.
_PROBES = [
    ("nominatim", "Geocoding (place-name lookup)",
     lambda: requests.get("https://nominatim.openstreetmap.org/search",
                          params={"q": "Santa Rosa, California", "format": "json", "limit": 1},
                          headers={"User-Agent": UA}, timeout=10)),
    ("overpass", "OpenStreetMap (live businesses)",
     lambda: requests.post("https://overpass-api.de/api/interpreter",
                           data="[out:json][timeout:5];node(38.43,-122.73,38.44,-122.72);out 1;",
                           headers={"User-Agent": UA}, timeout=15)),
    ("overture_s3", "Overture Maps (bulk dataset)",
     lambda: requests.get("https://overturemaps-us-west-2.s3.us-west-2.amazonaws.com/"
                          "?list-type=2&prefix=release/&delimiter=/&max-keys=1", timeout=15)),
    ("duckduckgo", "Web search (find missing websites)",
     lambda: requests.post("https://html.duckduckgo.com/html/", data={"q": "real estate"},
                           headers={"User-Agent": "Mozilla/5.0"}, timeout=12)),
]

# Which sources each pipeline source actually needs.
_SOURCE_NEEDS = {
    "overture": ["overture_s3"],   # + pyarrow/s3fs reader (checked separately)
    "osm": ["overpass"],
}


def check_connectivity() -> dict:
    """Probe all data sources. Returns:
      {"results":[{key,label,ok,detail}], "can_overture":bool, "can_osm":bool,
       "summary":str}
    """
    results = []
    status = {}
    for key, label, fn in _PROBES:
        ok, detail = _probe(fn)
        status[key] = ok
        results.append({"key": key, "label": label, "ok": ok, "detail": detail})

    # Overture also needs the pyarrow+s3fs reader (no network beyond the S3 bucket).
    reader_ok, reader_detail = _check_overture_reader()
    results.append({"key": "overture_reader", "label": "Overture reader (pyarrow+s3fs)",
                    "ok": reader_ok, "detail": reader_detail})

    can_overture = status.get("overture_s3", False) and reader_ok
    can_osm = status.get("overpass", False)

    if can_overture and can_osm:
        summary = "All systems go — both data sources are reachable."
    elif can_overture:
        summary = "Overture (bulk) works. OpenStreetMap is blocked — uncheck it and use Overture."
    elif can_osm:
        summary = "OpenStreetMap works. Overture is blocked — uncheck it and use OpenStreetMap."
    else:
        summary = ("Both data sources are blocked on this network. Try a normal home/office "
                   "connection (some corporate/VPN/cloud networks block these). You can still "
                   "use Demo mode to see how the tool works.")
    return {"results": results, "can_overture": can_overture, "can_osm": can_osm,
            "summary": summary}


def _probe(fn) -> tuple[bool, str]:
    t = time.time()
    try:
        r = fn()
        ms = int((time.time() - t) * 1000)
        if r.status_code == 200:
            return True, f"reachable ({ms} ms)"
        if r.status_code in (403, 401):
            return False, f"blocked by your network (HTTP {r.status_code})"
        if r.status_code == 429:
            return False, "rate-limited right now — try again in a minute"
        return False, f"unexpected response (HTTP {r.status_code})"
    except requests.exceptions.Timeout:
        return False, "timed out — slow or blocked connection"
    except requests.exceptions.ConnectionError:
        return False, "could not connect (offline or blocked)"
    except Exception as e:
        return False, f"{type(e).__name__}"


def _check_overture_reader() -> tuple[bool, str]:
    try:
        import pyarrow.dataset  # noqa: F401
        import s3fs  # noqa: F401
        return True, "ready"
    except ImportError:
        return False, "reader not installed (pip install pyarrow s3fs)"
    except Exception as e:
        return False, f"{type(e).__name__}"


# ───────────────────────── friendly error translation ────────────────────────
_ERROR_HINTS = [
    ("could not resolve market",
     "That place name wasn't found. Try adding the state, e.g. \"Santa Rosa, California\", "
     "or pick a saved market from the list."),
    ("All Overpass mirrors failed",
     "OpenStreetMap couldn't be reached (often blocked on corporate/VPN/cloud networks). "
     "Try the Overture source instead, or run from a home connection."),
    ("Host not in allowlist",
     "This network is blocking the data sources. Try a normal home/office connection, "
     "or use Demo mode to preview the tool."),
    ("pyarrow + s3fs",
     "The Overture (bulk) source needs the 'pyarrow' and 's3fs' packages. Install them "
     "(pip install pyarrow s3fs), or use the OpenStreetMap source."),
    ("Failed to download",
     "A required component couldn't be downloaded on this network. Try another connection "
     "or use the OpenStreetMap source."),
    ("timed out", "The connection was too slow or blocked. Check your internet and retry."),
]


def friendly_error(message: str) -> str:
    """Map a raw exception string / log line to plain-English guidance.
    Returns the original message if no hint matches."""
    if not message:
        return "Something went wrong, but no details were given. Please try again."
    low = message.lower()
    for needle, hint in _ERROR_HINTS:
        if needle.lower() in low:
            return hint
    return message


def explain_empty_result(market: str, sources, vertical_label: str) -> str:
    """Guidance shown when a run completes with 0 leads."""
    return (f"No leads found for \"{market}\" with {vertical_label}. "
            "This usually means the area is small or the data source has sparse coverage "
            "there. Try a larger nearby market, enable both data sources, or widen the search.")
