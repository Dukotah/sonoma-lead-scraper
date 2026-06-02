"""
Data sources — collect the raw business universe for a bbox.

Two free, no-key sources, both already proven in this repo:
  - overture_collect(): Overture Maps Places via pyarrow+s3fs (national, CC-BY)
  - osm_collect():      OpenStreetMap via Overpass (live, ODbL)

Sandbox note: overture_collect talks ONLY to the public Overture S3 bucket
(overturemaps-us-west-2), which is reachable from the restricted agent sandbox,
and uses bbox predicate pushdown so it streams just the relevant byte ranges
instead of the multi-GB global files. osm_collect needs Overpass, which the
sandbox proxy blocks — use Overture in-sandbox, OSM on an open connection.

Both return a list of normalized lead dicts with the same shape so the rest of
the pipeline is source-agnostic:
  {name, category, website, phone, email, address, city, state, zip,
   lat, lon, brand, source, source_url}
"""
from __future__ import annotations

import time

import requests

from .audit import UA

# ───────────────────────── Overture (bulk, national) ─────────────────────────
FALLBACK_RELEASE = "2026-05-20.0"
OVERTURE_BUCKET = "overturemaps-us-west-2"


def _overture_fs():
    """Anonymous read-only handle to the public Overture S3 bucket."""
    import s3fs
    return s3fs.S3FileSystem(anon=True, client_kwargs={"region_name": "us-west-2"})


def _overture_release(fs=None) -> str:
    """Newest release folder under the bucket (e.g. '2026-05-20.0'); FALLBACK on error."""
    try:
        fs = fs or _overture_fs()
        rels = sorted(p.rsplit("/", 1)[-1] for p in fs.ls(f"{OVERTURE_BUCKET}/release"))
        rels = [r for r in rels if r[:1].isdigit()]
        if rels:
            return rels[-1]
    except Exception:
        pass
    return FALLBACK_RELEASE


def _first(v):
    """First element of an Overture list-valued field (websites/phones/emails), or None."""
    return v[0] if isinstance(v, list) and v else None


def overture_collect(bbox, categories: list[str] | None = None,
                     limit: int | None = None, log=print) -> list[dict]:
    """Stream Overture Places for a bbox, optionally filtered to category substrings.

    Backend: pyarrow.dataset over s3fs. Reads directly from the public Overture
    S3 bucket using bbox predicate pushdown (range GETs), so it runs inside the
    restricted agent sandbox with no DuckDB/httpfs and no full-file downloads.
    """
    try:
        import pyarrow.dataset as ds
        import pyarrow.compute as pc
    except ImportError as e:
        raise RuntimeError(
            "overture_collect needs pyarrow + s3fs: pip install pyarrow s3fs"
        ) from e

    south, west, north, east = bbox
    fs = _overture_fs()
    release = _overture_release(fs)
    log(f"  Overture release {release}; streaming bbox via S3…")
    base = f"{OVERTURE_BUCKET}/release/{release}/theme=places/type=place"
    dataset = ds.dataset(base, filesystem=fs, format="parquet")

    # bbox pushdown — points have xmin==xmax, ymin==ymax, so this keeps everything
    # inside the requested box and lets parquet skip non-overlapping row groups.
    flt = ((pc.field("bbox", "xmin") >= west) & (pc.field("bbox", "xmax") <= east)
           & (pc.field("bbox", "ymin") >= south) & (pc.field("bbox", "ymax") <= north))
    if categories:
        cat = pc.field("categories", "primary")
        cat_or = None
        for c in categories:
            m = pc.match_substring(cat, c, ignore_case=True)
            cat_or = m if cat_or is None else (cat_or | m)
        flt = flt & cat_or

    cols = ["id", "names", "categories", "phones", "websites", "emails",
            "addresses", "brand", "bbox"]
    rows = dataset.to_table(columns=cols, filter=flt).to_pylist()
    if limit:
        rows = rows[:int(limit)]

    out = []
    for r in rows:
        name = (r.get("names") or {}).get("primary")
        if not name:
            continue
        addrs = r.get("addresses") or []
        addr = addrs[0] if addrs else {}
        brand = ((r.get("brand") or {}).get("names") or {}).get("primary")
        bb = r.get("bbox") or {}
        out.append({
            "id": r.get("id"),
            "name": name,
            "category": (r.get("categories") or {}).get("primary"),
            "website": _first(r.get("websites")),
            "phone": _first(r.get("phones")),
            "email": _first(r.get("emails")),
            "address": addr.get("freeform"),
            "city": addr.get("locality"),
            "state": addr.get("region"),
            "zip": addr.get("postcode"),
            "brand": brand,
            "lon": bb.get("xmin"),
            "lat": bb.get("ymin"),
            "source": "overture",
            "source_url": "",
        })
    log(f"  Overture: {len(out)} businesses")
    return out


# ───────────────────────── OSM / Overpass (live) ─────────────────────────────
OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]
RETRY_STATUS = {429, 502, 503, 504}


def _overpass_query(bbox, tag_filters: list[str], timeout: int = 60) -> list[dict]:
    south, west, north, east = bbox
    parts = []
    for tf in tag_filters:
        if "=" not in tf:
            continue
        k, v = tf.split("=", 1)
        parts.append(f'nwr["{k}"="{v}"]({south},{west},{north},{east});')
    if not parts:
        return []
    body = (f"[out:json][timeout:{timeout}];\n(\n  " + "\n  ".join(parts)
            + "\n);\nout center tags;")
    errors = []
    for endpoint in OVERPASS_ENDPOINTS:
        for attempt in range(2):
            try:
                r = requests.post(endpoint, data=body, headers={"User-Agent": UA},
                                  timeout=timeout + 10)
                if r.status_code == 200:
                    return r.json().get("elements", [])
                errors.append(f"HTTP {r.status_code}")
                if r.status_code in RETRY_STATUS and attempt == 0:
                    time.sleep(2); continue
                break
            except requests.exceptions.RequestException as e:
                errors.append(type(e).__name__)
                if attempt == 0:
                    time.sleep(2); continue
                break
    raise RuntimeError("All Overpass mirrors failed (" + "; ".join(errors) + ")")


def osm_collect(bbox, osm_tags: list[str], log=print) -> list[dict]:
    """Query Overpass for the given OSM tags within bbox; normalize to lead dicts."""
    els = _overpass_query(bbox, osm_tags)
    out = []
    for el in els:
        tags = el.get("tags", {})
        name = tags.get("name") or tags.get("operator")
        if not name:
            continue
        line1 = " ".join(tags.get(k, "") for k in ("addr:housenumber", "addr:street")).strip()
        out.append({
            "name": name.strip(),
            "category": next((t for t in osm_tags if "=" in t), ""),
            "website": (tags.get("website") or tags.get("contact:website") or "").strip(),
            "phone": (tags.get("phone") or tags.get("contact:phone") or "").strip(),
            "email": (tags.get("email") or tags.get("contact:email") or "").strip(),
            "address": ", ".join(p for p in [line1, tags.get("addr:city", "")] if p),
            "city": tags.get("addr:city", ""),
            "state": tags.get("addr:state", ""),
            "zip": tags.get("addr:postcode", ""),
            "brand": tags.get("brand", ""),
            "lat": el.get("lat") or (el.get("center") or {}).get("lat"),
            "lon": el.get("lon") or (el.get("center") or {}).get("lon"),
            "source": "osm",
            "source_url": f"https://www.openstreetmap.org/{el['type']}/{el['id']}",
        })
    log(f"  OSM: {len(out)} named businesses")
    return out
