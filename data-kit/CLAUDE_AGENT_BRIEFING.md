# Briefing for a Claude agent — Sonoma County lead-gen project

## Goal
Build a lead-generation pipeline for a web-design business targeting Sonoma County, CA.
The user finds businesses with no website (or a bad one) and pitches them a new site.

## The data
Run `download_sonoma.py` first. It produces three files:

### `sonoma_places.parquet` — primary data
Full Overture Maps Places dataset for Sonoma County bounding box (lat 38.05–38.85, lon -123.55 to -122.35).
Schema (columns):
- `id` — stable Overture ID
- `name` — business name (may be null for unnamed amenities)
- `category_primary` — Overture category, e.g. "restaurant", "plumber", "beauty_salon"
- `category_alt` — array of alternate categories
- `confidence` — float 0-1, Overture's confidence in this record
- `websites` — array of URLs (may be empty)
- `phones` — array of phone strings (may be empty)
- `emails` — array
- `socials` — array of social media URLs
- `brand` — name of parent brand (for chains like McDonald's; null for indie)
- `address_line`, `city`, `state`, `zip`, `country`
- `lon`, `lat` — coordinates
- `source_dataset`, `source_id` — provenance (meta, msft, tomtom, etc.)

### `sonoma_places.csv` — flattened version
Same data with arrays joined by `|`. Excel-readable.

### `sonoma_businesses.xlsx` — quick-look ranked list
Pre-filtered to named businesses, with a Tier column (A = no website, C = has website).

## Suggested project structure
```
sonoma_leads/
├── data/
│   ├── sonoma_places.parquet      ← raw
│   ├── sonoma_places.csv          ← flat
│   └── sonoma_businesses.xlsx     ← summary
├── enrich/
│   ├── audit_websites.py          ← live-fetch each URL; check HTTPS/mobile/load/builder
│   ├── verify_no_website.py       ← Google search each "no website" business to confirm
│   └── cross_check_business_licenses.py ← merge with county business licenses
├── score/
│   └── score_leads.py             ← rank by lead quality
├── outreach/
│   ├── generate_pitches.py        ← LLM-generated tailored pitch per lead
│   └── crm_export.py              ← export to HubSpot/Pipedrive format
└── README.md
```

## Lead-scoring heuristics
**Tier A (hottest):**
- No website + valid phone + name + Sonoma County address
- Website = facebook.com / yelp.com / instagram.com / linktr.ee (social-only)
- Website returns 404, 5xx, or SSL error

**Tier B (warm):**
- Website exists but: HTTP only (no SSL), no mobile viewport, load time > 4s,
  built on Wix/Weebly/GoDaddy/Site123, hosted on yellowpages.com/localsearch.com

**Tier C (cold):**
- Real domain, HTTPS, mobile-friendly, fast — verify manually before pitching

**Exclude:**
- `brand` is populated AND brand is a known national chain (McDonald's, Starbucks, CVS, etc.)
  → these have corporate marketing teams and won't buy from a local web designer

## Tasks the user wants done
1. **Triage:** Tier every business by lead quality
2. **Audit:** Live-fetch each website, score quality
3. **Enrich:** For "no website" leads, Google to confirm; flag false positives
4. **Pitch:** Generate a personalized 1-paragraph cold-call opener per Tier-A lead
5. **Export:** Excel/CSV grouped by niche + city, sorted by score, with phone & pitch

## Stretch goals
- Cross-reference with Sonoma County business license rolls (https://data-sonomacounty.opendata.arcgis.com/)
  to find businesses that exist but aren't in Overture
- Build a simple Flask dashboard to filter/sort leads by tier, niche, city
- Set up a quarterly refresh: rerun download_sonoma.py with newest Overture release

## Don't
- Don't redistribute the raw Overture data publicly — it's CC-BY licensed, you must attribute
- Don't hammer business websites during audits — pace requests (1 per second per domain)
- Don't include national chains in outreach lists (waste of time, kills your conversion rate)

## Releases & freshness
Overture publishes a new release roughly monthly. To get fresh data, edit `RELEASE` in
download_sonoma.py to the newest version from https://docs.overturemaps.org/release/latest/
