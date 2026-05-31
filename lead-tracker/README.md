# Lead Tracker

A CRM-lite for working web-design leads: a fast, filterable table over the whole
**Bay Area + Wine Country** business set (Sonoma, Napa, Marin, Mendocino, Lake,
Solano + greater Bay Area — ~267K cleaned leads), with a per-lead status pipeline,
notes, favorites, and CSV export. Built as a drop-in **Next.js (App Router)** module
backed by a local **SQLite** file. Single-user, runs entirely on your machine — no
cloud, no accounts.

## Data source
Business records come from [Overture Maps](https://overturemaps.org) (the open
Meta/Microsoft/Amazon places dataset, CC-BY 4.0). No website scraping. The build
script pulls a region straight from Overture's public S3 bucket, drops chains and
non-business POIs, and tiers each lead:

- **Tier A** — no website, or only a social/listing page (your hottest prospects)
- **Tier C** — has a real website (audit before pitching)

## Run it standalone (fastest way to see it)
```bash
cd lead-tracker
npm install
npm run build-db        # pulls Overture, builds data/leads.sqlite (~1-3 min, needs python3 + duckdb)
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
- **Different region:** edit `BBOX` at the top of `scripts/build_leads_db.py`
  (grab coordinates from https://bboxfinder.com), then rebuild.

Credit "Overture Maps Foundation" if you publish anything derived from this data.
