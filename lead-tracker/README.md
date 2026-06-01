# Lead Tracker

A CRM-lite for working web-design leads: a fast, filterable table over a whole
region's businesses, with a per-lead status pipeline, notes, favorites, and CSV
export. Built as a drop-in **Next.js (App Router)** module backed by a local
**SQLite** file. Single-user, runs entirely on your machine — no cloud, no accounts.

The dataset is **region-parameterized** — build any area you want (default:
**Sonoma County**, the primary target area: ~20K cleaned leads, ~3.7K Tier-A,
644 niches, all of it). SQLite stays snappy into the low millions of rows;
queries return in milliseconds, so you can scale up to the whole state or coast
anytime with one command.

| Region (`build-db <key>`) | Businesses | Cleaned leads | ~Tier-A | SQLite |
|---|---|---|---|---|
| `sonoma` (Sonoma County) *(default)* | 33K | 20K | 3.7K | ~11 MB |
| `bayarea` (Bay Area + Wine Country) | 417K | 267K | 51K | ~140 MB |
| `california` | 1.94M | 1.23M | 309K | ~635 MB |
| `westcoast` (CA/OR/WA) | 2.66M | ~1.7M | ~325K | ~0.9 GB |
| `us` (whole country) | ~60M+ | ~38M | ~7M+ | ~20 GB † |

† At US scale a single SQLite file gets unwieldy — switch the backend to
DuckDB-over-Parquet (the `lib/db.js` layer is the only file that changes).

## Data source
Business records come from [Overture Maps](https://overturemaps.org) (the open
Meta/Microsoft/Amazon places dataset, CC-BY 4.0). No website scraping. The build
script pulls a region straight from Overture's public S3 bucket, drops chains and
non-business POIs, and tiers each lead:

- **Tier A** — no website, or only a social/listing page (your hottest prospects)
- **Tier B** — a DIY builder site (Wix/Weebly/GoDaddy/Square/…) — upsell to custom
- **Tier C** — has a real custom website (audit before pitching)

## Enrichment
Every build is automatically enriched (offline — no network needed) by
`scripts/enrich_leads.py`, which adds per-lead:

- **tier** A/B/C (incl. DIY-builder detection) + **builder** name
- **score** 0–100 lead priority (need + reachability + Overture confidence)
- **phone_fmt** `(707) 555-1234` + **area_code**
- **social_platforms** present, **email_owned** (email domain == site domain)
- **completeness** 0–100, **best_contact** (phone/email/social), and a
  **personalized pitch** line tailored to the lead's tier, niche, and city

**Live website audit (run locally — needs outbound internet):**
```bash
npm run audit              # = python3 scripts/audit_websites.py
python3 scripts/audit_websites.py --tier C --limit 500 --workers 12
```
This fetches each Tier B/C site and records real HTTPS / HTTP-status /
mobile-viewport / load-time / builder-from-HTML signals into an `audit` table
(preserved across rebuilds, like `crm`). It surfaces "has a *bad* website"
warm leads — a `weak`/`broken` Tier-C site is a real prospect. The tracker
shows audit badges and the CSV export includes every audit column. Re-run
`npm run enrich` anytime to recompute the offline fields.

## Run it standalone (fastest way to see it)
```bash
cd lead-tracker
npm install
npm run build-db        # builds Sonoma County into data/leads.sqlite (~1-2 min; needs python3)
                        # other regions: python3 scripts/build_leads_db.py bayarea|california|westcoast|us
npm run dev             # http://localhost:3030  → redirects to /leads
```
If you already have `data/leads.sqlite` (e.g. it was handed to you), skip
`build-db` and just `npm install && npm run dev`.

## Drop it into your existing Next.js app
Your site is App Router (`app/`). Copy these in:

| From `lead-tracker/` | Into your app |
|---|---|
| `lib/db.js` | `lib/db.js` |
| `components/LeadTracker.jsx` | `components/LeadTracker.jsx` |
| `app/leads/page.jsx` | `app/leads/page.jsx` (the tracker lives at `/leads`) |
| `app/api/leads/`, `app/api/facets/`, `app/api/stats/`, `app/api/export/` | same paths under your `app/api/` |
| `data/leads.sqlite` | anywhere; point `LEADS_DB` at it |
| CSS in `app/globals.css` (the `.lt-*` rules) | merge into your global stylesheet |

Then:
1. `npm install better-sqlite3`
2. Add to your `next.config.js`: `experimental.serverComponentsExternalPackages: ["better-sqlite3"]` (Next 15: top-level `serverExternalPackages`).
3. Set `LEADS_DB=/abs/path/to/leads.sqlite` (defaults to `<cwd>/data/leads.sqlite`).
4. Visit `/leads`.

> **Hosting note:** this writes to the SQLite file, so run it where the filesystem
> is writable (your own server, a VM, `next start` locally). Serverless platforms
> with read-only/ephemeral disk (e.g. Vercel) won't persist edits — use a host with
> a real disk, or swap the `crm` table for a hosted DB later.

## The database
`data/leads.sqlite` has two tables:

- **`leads`** — the dataset. Rebuilt from scratch every time you run `build-db`.
- **`crm`** — your tracking state (status, notes, last-contacted, favorite).
  **Preserved across rebuilds**, so refreshing the Overture data never wipes your
  progress. (Rows whose lead disappears in a refresh are pruned.)

Status pipeline: `New → Contacted → Quoted → Won → Lost`.

## API (all local, JSON)
- `GET /api/leads?q=&city=&category=&tier=&status=&hasWebsite=&hasPhone=&favorite=&sort=&order=&page=&pageSize=`
  → `{ rows, total, page, pageSize, pages }`
- `PATCH /api/leads/:id` body `{ status?, notes?, last_contacted?, favorite? }`
- `GET /api/facets` → city/category lists for the dropdowns
- `GET /api/stats` → totals + pipeline counts
- `GET /api/export?<same filters>` → CSV download of the current view

## Refresh / re-target
- **New Overture release:** re-run `npm run build-db` (it auto-detects the newest release).
- **Different region:** pass a built-in key, or a custom bounding box — no file edits:
  ```bash
  python3 scripts/build_leads_db.py california       # built-in: sonoma | bayarea | california | westcoast | us
  REGION=california python3 scripts/build_leads_db.py # or via env var
  REGION_NAME="North Bay" REGION_BBOX="38.0,-123.6,38.9,-122.3" \
    python3 scripts/build_leads_db.py              # custom box (south,west,north,east)
  ```
  Grab custom coordinates from https://bboxfinder.com. Your **`crm` tracking
  table is preserved** across rebuilds — switching/expanding regions keeps the
  status/notes for any lead that still exists (matched by stable Overture ID).

Credit "Overture Maps Foundation" if you publish anything derived from this data.
