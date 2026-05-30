# Sonoma County Data Kit

A three-step pipeline: **download** the county's businesses, **enrich** the niche you're
about to pitch, and hand the whole thing to a **Claude agent** if you want to go further.

## 1. `download_sonoma.py` — get the data
Downloads ~all businesses in Sonoma County from Overture Maps (Meta + Microsoft + Amazon's open dataset).
- **Run once:** `python download_sonoma.py` (2–5 min, ~10–30 MB)
- Outputs three files in the same folder: `.parquet`, `.csv`, `.xlsx`
- No API key, no signup, no auth
- **Auto-detects the newest Overture release** each run, so the data never goes stale.
- The `.xlsx` summary already excludes national chains/franchises and non-business POIs
  (parks, beaches, monuments, post offices) and tiers every lead A/C by website status.

```bash
pip install duckdb openpyxl
python download_sonoma.py
```

## 2. `enrich_leads.py` — audit, verify, and export a niche
Takes the downloaded data, filters to the niche/city you care about, then:
- **live-audits** each existing website (HTTPS, mobile-friendly, load time, DIY builder)
- **web-verifies** each "no website" lead (DuckDuckGo) to catch false positives —
  businesses Overture *thinks* have no site but actually do
- **scores + tiers** every lead and writes a ranked `.xlsx` + a CRM-ready `.csv`

```bash
pip install requests        # in addition to duckdb + openpyxl

# wineries with no real website, verify the no-site ones
python enrich_leads.py --category winery --verify 30

# salons in Santa Rosa, audit their sites, cap at 100
python enrich_leads.py --category salon --city "Santa Rosa" --limit 100

# combine with an OSM scrape exported from the desktop GUI (../scraper-gui)
python enrich_leads.py --category restaurant --merge-osm leads_santa_rosa.xlsx
```
Outputs `sonoma_leads_enriched.xlsx` and `sonoma_leads_crm.csv`.

**Note on verification:** the DuckDuckGo endpoint rate-limits bursts (HTTP 202). The script
retries with backoff and honestly reports "search throttled — verify manually" rather than
guessing. Keep `--verify` batches modest (the default is 25); re-run later if throttled.

`lead_tools.py` holds the shared audit / verify / scoring helpers used by `enrich_leads.py`.

## 3. `CLAUDE_AGENT_BRIEFING.md` — hand off to a Claude agent
Hand this to any Claude agent (Claude Code, Claude in chat, the Claude API) along with the data files.
It explains the schema, scoring rules, suggested project structure, and what to build next.

## Want a different region?
Edit `BBOX` at the top of `download_sonoma.py`:
```python
BBOX = {"south": 30.10, "west": -97.95, "north": 30.52, "east": -97.55}  # Austin, TX
```
Use bboxfinder.com to draw a box on a map and grab the coordinates. The chain/non-business
filters (`CHAIN_NAME_THRESHOLD`, `NON_BUSINESS_CATEGORIES`) are tunable constants near the top too.

## Attribution
Overture data is CC BY 4.0. If you publish anything derived from this, credit "Overture Maps Foundation".
