"""
Data sources — collect the raw business universe for a bbox.

Two free, no-key sources, both already proven in this repo:
  - overture_collect(): Overture Maps Places via DuckDuckDB+S3 (national, CC-BY)
  - osm_collect():      OpenStreetMap via Overpass (live, ODbL)

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


def _overture_release(con) -> str:
    try:
        pat = ("s3://overturemaps-us-west-2/release/202[0-9]-*"
               "/theme=places/type=place/part-00000-*")
        rows = con.execute(
            "SELECT DISTINCT regexp_extract(file, 'release/([^/]+)/', 1) AS rel "
            f"FROM glob('{pat}') WHERE rel <> '' ORDER BY rel DESC LIMIT 1"
        ).fetchall()
        if rows and rows[0][0]:
            return rows[0][0]
    except Exception:
        pass
    return FALLBACK_RELEASE


def _cat_match(primary: str | None, categories: list[str] | None) -> bool:
    """True if no filter, or a category substring matches the primary category —
    mirrors the DuckDB `lower(categories.primary) LIKE '%c%'` clause exactly."""
    if not categories:
        return True
    p = (primary or "").lower()
    return any(c.lower() in p for c in categories)


def _overture_norm(row: dict) -> dict:
    """Flatten one Overture place row (nested structs) to a lead dict. Pure: shared by
    the pyarrow fallback and unit-tested without network. Matches the DuckDB columns."""
    def first(x):
        return x[0] if isinstance(x, list) and x else None
    cats = row.get("categories") or {}
    addrs = row.get("addresses") or []
    a = (addrs[0] if addrs else None) or {}
    bb = row.get("bbox") or {}
    brand = row.get("brand")
    bname = ((brand.get("names") or {}).get("primary")) if isinstance(brand, dict) else None
    return {
        "name": (row.get("names") or {}).get("primary"),
        "category": cats.get("primary") or "",
        "website": first(row.get("websites")),
        "phone": first(row.get("phones")),
        "email": first(row.get("emails")),
        "address": a.get("freeform"),
        "city": a.get("locality"),
        "state": a.get("region"),
        "zip": a.get("postcode"),
        "brand": bname,
        "lon": bb.get("xmin"),
        "lat": bb.get("ymin"),
        "source": "overture",
        "source_url": "",
    }


def _overture_latest_release_s3(s3, pafs) -> str:
    """Newest release folder name by listing the bucket (no httpfs needed)."""
    try:
        sel = pafs.FileSelector(f"{OVERTURE_BUCKET}/release", recursive=False)
        dirs = [i.base_name for i in s3.get_file_info(sel)
                if i.type == pafs.FileType.Directory and i.base_name[:4].isdigit()]
        if dirs:
            return sorted(dirs)[-1]
    except Exception:
        pass
    return FALLBACK_RELEASE


def _overture_pyarrow(bbox, categories, limit, log) -> list[dict]:
    """Fallback collector: read Overture Places parquet straight from S3 with pyarrow.
    Used when DuckDB's httpfs extension can't be installed (locked-down networks, CI,
    the web sandbox). S3 needs only plain HTTPS — no extension download — and pyarrow
    pushes the bbox filter into the parquet row-group statistics, so it reads only the
    handful of row groups covering the market."""
    try:
        import pyarrow.dataset as pads
        import pyarrow.fs as pafs
    except ImportError:
        raise RuntimeError("Overture pyarrow fallback needs pyarrow: pip install pyarrow")
    south, west, north, east = bbox
    s3 = pafs.S3FileSystem(anonymous=True, region="us-west-2")
    release = _overture_latest_release_s3(s3, pafs)
    base = f"{OVERTURE_BUCKET}/release/{release}/theme=places/type=place"
    files = [i.path for i in s3.get_file_info(pafs.FileSelector(base))
             if i.type == pafs.FileType.File]
    if not files:
        raise RuntimeError(f"no Overture place files under s3://{base}")
    log(f"  Overture release {release} via pyarrow/S3 (httpfs unavailable); streaming bbox…")
    dset = pads.dataset(files, filesystem=s3, format="parquet")
    flt = ((pads.field("bbox", "xmin") >= west) & (pads.field("bbox", "xmin") <= east) &
           (pads.field("bbox", "ymin") >= south) & (pads.field("bbox", "ymin") <= north))
    cols = ["names", "categories", "websites", "phones", "emails",
            "addresses", "brand", "bbox"]
    out = []
    for row in dset.to_table(filter=flt, columns=cols).to_pylist():
        if not _cat_match((row.get("categories") or {}).get("primary"), categories):
            continue
        rec = _overture_norm(row)
        if not rec["name"]:
            continue
        out.append(rec)
        if limit and len(out) >= limit:
            break
    log(f"  Overture: {len(out)} businesses")
    return out


def overture_collect(bbox, categories: list[str] | None = None,
                     limit: int | None = None, log=print) -> list[dict]:
    """Stream Overture Places for a bbox, optionally filtered to category substrings.

    Prefers DuckDB+httpfs (fast, predicate pushdown). If DuckDB is missing or its
    httpfs extension can't be downloaded, transparently falls back to a pyarrow read
    straight from S3 so the same command still works on locked-down networks."""
    try:
        import duckdb
    except ImportError:
        log("  duckdb not installed; using pyarrow/S3 fallback…")
        return _overture_pyarrow(bbox, categories, limit, log)
    try:
        con = duckdb.connect()
        con.execute("INSTALL httpfs; LOAD httpfs; SET s3_region='us-west-2';")
    except Exception as e:
        log(f"  DuckDB httpfs unavailable ({type(e).__name__}); using pyarrow/S3 fallback…")
        return _overture_pyarrow(bbox, categories, limit, log)

    south, west, north, east = bbox
    release = _overture_release(con)
    log(f"  Overture release {release}; streaming bbox…")
    s3 = (f"s3://overturemaps-us-west-2/release/{release}"
          f"/theme=places/type=place/*")

    cat_clause = ""
    if categories:
        ors = " OR ".join("lower(categories.primary) LIKE ?" for _ in categories)
        cat_clause = f"AND ({ors})"
    params = [f"%{c.lower()}%" for c in (categories or [])]

    sql = f"""
      SELECT names.primary AS name,
             categories.primary AS category,
             CASE WHEN length(websites)>0 THEN websites[1] END AS website,
             CASE WHEN length(phones)>0   THEN phones[1]   END AS phone,
             CASE WHEN length(emails)>0   THEN emails[1]   END AS email,
             addresses[1].freeform AS address,
             addresses[1].locality AS city,
             addresses[1].region   AS state,
             addresses[1].postcode AS zip,
             brand.names.primary AS brand,
             bbox.xmin AS lon, bbox.ymin AS lat
      FROM read_parquet('{s3}', hive_partitioning=1)
      WHERE bbox.xmin BETWEEN {west} AND {east}
        AND bbox.ymin BETWEEN {south} AND {north}
        AND names.primary IS NOT NULL
        {cat_clause}
      {f'LIMIT {int(limit)}' if limit else ''}
    """
    cols = ["name", "category", "website", "phone", "email", "address",
            "city", "state", "zip", "brand", "lon", "lat"]
    rows = con.execute(sql, params).fetchall()
    out = []
    for r in rows:
        rec = dict(zip(cols, r))
        rec["source"] = "overture"
        rec["source_url"] = ""
        out.append(rec)
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
