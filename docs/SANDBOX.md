# Scraping from inside an agent sandbox

This project started as an **offline tool you run locally**. It is now also a
**lead scraper an agent can drive from inside a restricted sandbox** (e.g.
Claude Code on the web), with no local machine and no open internet.

The sandbox does not have general outbound internet — an allowlist proxy lets a
few hosts through and blocks the rest. The job here was to find a real scrape
path that lives entirely inside those limits and wire the engine to use it.

## What the sandbox can and can't reach

Measured from this environment (a `200`/`404` means the host is reachable; `403`
means the proxy blocked it):

| Capability | Host | In-sandbox | Used for |
|---|---|---|---|
| **Overture Maps Places** | `overturemaps-us-west-2.s3.amazonaws.com` | ✅ reachable | **the business universe — primary in-sandbox source** |
| Python packages | `pypi.org`, `files.pythonhosted.org` | ✅ reachable | `pip install pyarrow s3fs` etc. |
| GitHub raw | `raw.githubusercontent.com` | ✅ reachable | reading committed data/config |
| Google Places API | `places.googleapis.com` | ✅ reachable (needs key) | optional enrichment |
| OpenStreetMap live | Overpass / Nominatim / openstreetmap.org | ❌ blocked | OSM source, place-name geocoding |
| DuckDB extensions | `extensions.duckdb.org` | ❌ blocked | (why we don't use duckdb httpfs) |
| Web search / arbitrary sites | DuckDuckGo, Google, business homepages | ❌ blocked | website audit/enrichment, missing-site lookup |

**Takeaway:** the *collection* step works fully in-sandbox via Overture; the
steps that hit arbitrary third-party sites (live website audit, per-business
enrichment, place-name geocoding, web search) do not, and stay on an open
connection or a GitHub Actions runner.

## How in-sandbox scraping works

`leadgen/sources.py::overture_collect()` reads Overture's GeoParquet directly
with **`pyarrow` + `s3fs`** — no DuckDB, no `httpfs` extension (its download host
is blocked). It applies a **bbox predicate pushdown**, so parquet skips
non-overlapping row groups and S3 serves only the relevant byte ranges via range
GETs. Pulling Sonoma County (~33k places out of a ~10 GB global file) takes a
few seconds, not a full download.

```bash
pip install -r leadgen/requirements.txt   # pyarrow + s3fs + openpyxl + requests

# Real scrape, entirely inside the sandbox (Overture only, skip the steps that
# need open internet):
python -m leadgen --vertical web_design --market sonoma_county_ca \
    --sources overture --no-enrich --out sonoma_leads

python -m leadgen --vertical simply_tc  --market sonoma_county_ca \
    --sources overture --no-enrich --out sonoma_tc
```

Outputs the usual CRM CSV + tiered XLSX. Both verticals were run this way and
produced real, scored leads in-sandbox.

### Markets

Free-text markets (`--market "Austin, Texas"`) need Nominatim geocoding, which
the sandbox blocks. **Use a named market** from `leadgen/geo.py::MARKETS`
(`sonoma_county_ca`, `phoenix_az`, `tampa_fl`, `austin_tx`) — those carry a
hard-coded bbox and need no network. Add more by dropping a bbox into that dict
(grab coordinates from https://bboxfinder.com).

### What to leave off in-sandbox

- `--no-enrich` — per-business website fetches are blocked; enabling it just
  logs per-lead errors and slows the run.
- Competitor **suppression** (simply_tc) scrapes rival sites; in-sandbox it
  finds 0 names and degrades gracefully — the run still completes.
- **Live website audit** (`good/weak/broken` grading) belongs on the GitHub
  Actions workflows (`.github/workflows/website-audit.yml`,
  `deep-audit.yml`), which run where outbound internet works and commit results
  back into `lead-tracker/data/export/`.

## Checking the environment yourself

`leadgen.diagnostics.check_connectivity()` probes every source and reports, in
plain English, what's reachable right now — it correctly shows Overture green
and OSM/geocoding/web-search blocked inside the sandbox.
