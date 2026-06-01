# Lead Schema — Scraper → CRM Ingest Contract

This is the contract a scraper (or any lead source) should emit so its output
drops straight into the CRM pipeline. Match these field names and formats and
the existing tooling — tiering, scoring, pitch generation, website audit, the
Next.js UI — works on your data with no changes.

**The golden rule:** a source should emit the **raw facts** (left column below).
The pipeline *derives* tier, score, pitch, audit, formatting. Don't compute those
in the scraper — just give clean raw fields and let `enrich_leads.py` /
`audit_ci.py` do the rest. That keeps every source consistent.

---

## 1. Output format

One row per business. Either:

- **CSV** with a header row (UTF-8), or
- **NDJSON** (one JSON object per line).

File naming the pipeline expects: `data/export/<county>/<county>_leads_full.csv`
(or feed a raw file to the loader — see §5).

---

## 2. Fields

### Required (the pipeline rejects rows missing these)

| Field | Type | Format / notes |
|---|---|---|
| `id` | string | **Stable, globally-unique, deterministic.** Never reused, never reassigned. Prefix by source to avoid collisions, e.g. `gmaps:0x808...`, `yelp:abc-123`, `ovt:<overture_id>`. This is the join key for CRM state and audit results — if it changes, a business's notes/status/audit history are orphaned. |
| `name` | string | Business display name. Trimmed. No trailing location noise (`"Joe's Plumbing"` not `"Joe's Plumbing - Santa Rosa, CA"`). |

### Strongly recommended (drive tiering, scoring, outreach)

| Field | Type | Format / notes |
|---|---|---|
| `category` | string | Single primary niche, **snake_case**, controlled vocab where possible: `plumber`, `beauty_salon`, `auto_repair`, `restaurant`, `winery`, `dentist`, … Used for the niche facet and industry-fit scoring. |
| `phone` | string | Primary phone, digits + separators. E.164 (`+17075551234`) preferred; `707-555-1234` accepted. The pipeline derives `phone_fmt` and `area_code`. |
| `website` | string | Primary site URL, or **empty/null if none** — emptiness is the signal for Tier A (the hottest leads). Do **not** put social/listing URLs here; put those in `socials`. |
| `address` | string | Street address, no city/state/zip baked in. |
| `city` | string | City name, Title Case (`Santa Rosa`). Powers the city facet + market-gap analysis. |
| `state` | string | 2-letter (`CA`). |
| `zip` | string | 5-digit. |
| `lat` / `lon` | number | WGS84 decimal degrees. Enables map/geo features. |

### Optional (used when present, never required)

| Field | Type | Format / notes |
|---|---|---|
| `email` | string | Public business email. The pipeline flags owned-domain emails (`info@joesplumbing.com`) higher than free ones. |
| `socials` | string | Pipe-separated social/listing URLs: `https://facebook.com/x|https://instagram.com/x`. |
| `alt_categories` | string | Pipe-separated secondary niches. |
| `brand` | string | Franchise/brand if part of a chain. **Presence implies chain** → the pipeline drops it (see §4). Leave empty for independents. |
| `confidence` | number | 0–1 source confidence in the record. |
| `websites_all` / `phones_all` | string | Pipe-separated, if the source found several. |
| `source_dataset` | string | Where this came from: `gmaps`, `yelp`, `overture`, `yellowpages`, … |
| `source_id` | string | The source's own native id (for re-fetch/debug). |

---

## 3. Fields the pipeline DERIVES — do not emit these from a scraper

Emitting them is harmless (they'll be overwritten) but pointless:

| Derived field | Produced by | What it is |
|---|---|---|
| `tier` (`A`/`B`/`C`) | build/enrich | A = no/weak site (hot), B = DIY builder (upsell), C = real site |
| `tier_reason` | build/enrich | Human-readable why |
| `score` | `enrich_leads.py` | 0–100 outreach priority |
| `builder` | `enrich_leads.py` | DIY platform guessed from URL (Wix/Squarespace/…) |
| `phone_fmt`, `area_code` | `enrich_leads.py` | Normalized phone display |
| `best_contact`, `completeness`, `email_owned`, `social_platforms` | `enrich_leads.py` | Contactability signals |
| `pitch` | `enrich_leads.py` | Suggested outreach line |
| `audit_grade`, `audit_https`, `audit_mobile`, `load_ms`, `builder_live`, … | `audit_ci.py` | Live website audit (good/weak/broken) |

---

## 4. Quality rules the pipeline enforces (mirror them in the scraper)

- **No chains.** Rows with a non-empty `brand`, or whose `name` repeats ≥ a
  threshold across the dataset, are dropped. A scraper targeting *independent*
  businesses should pre-filter franchises.
- **No non-businesses.** Categories like `atm`, `park`, `bus_stop` are excluded.
- **De-duplicate by `id`.** Same business from two crawls = same `id` → one row.
  If two sources disagree, keep the richer record (more fields populated).
- **Trim everything.** No leading/trailing whitespace; empty string and null are
  treated the same (= "missing").

---

## 5. How a new source gets ingested

1. Scraper writes `data/export/<county>/<county>_leads_full.csv` with §2 fields.
2. `npm run build-db` (or a thin loader) rebuilds the `leads` table + FTS index.
   Existing `crm` (status/notes) and `audit` rows are **preserved** across
   rebuilds, joined back by `id` — so stable ids are everything.
3. `npm run enrich` computes tier/score/pitch.
4. The **Website Audit** GitHub Action grades the Tier B/C sites; `npm run
   load-audit` pulls the results into the `audit` table.
5. The UI/API pick everything up automatically (they `LEFT JOIN crm` and `audit`
   onto `leads` by `id`).

---

## 6. Minimal valid examples

**CSV**
```csv
id,name,category,phone,website,address,city,state,zip,lat,lon,email,socials,source_dataset
gmaps:0x1a2b,Joe's Plumbing,plumber,+17075551234,joesplumbing.com,12 A St,Santa Rosa,CA,95401,38.44,-122.71,info@joesplumbing.com,,gmaps
gmaps:0x3c4d,Ace Hair Studio,beauty_salon,+17075555678,,440 B Ave,Napa,CA,94559,38.30,-122.29,,https://instagram.com/acehair,gmaps
```

The second row has **no `website`** → the pipeline tiers it **A** (hottest), with
its Instagram captured in `socials`. That's exactly the lead this CRM is built to
surface.
