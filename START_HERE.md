# START HERE — handoff briefing for the next agent

Read this first. It tells you **what this repo is, what's already built, and exactly
how to run and ship each piece** so you don't start from zero. For the user-facing
overview see [`README.md`](README.md); this file is the operational handoff.

---

## What this repo is

A lead-generation toolkit for selling web-design (and other) services off **free
public data** — no accounts, no paid APIs. It's organized as **two tools**:

1. **🔍 Find new leads** — `leadgen/` — scrape the web, audit sites, score, export.
2. **📇 Work your leads** — `lead-tracker/` — a local CRM to filter, note, and call through everything you've collected.

The **`LeadEngine` desktop app** (`gui/`, shippable as a Windows `.exe`) wraps both
in a point-and-click window with a tab for each. Supporting: `data-kit/` (bulk
Overture downloader + agent briefing); `legacy/` (archived first-gen scrapers).

## Current state (what's built & working)

- ✅ **`leadgen/` engine** — universal pipeline (collect → dedupe → enrich → suppress
  → score → export) with swappable **verticals**. Two ship today: `web_design` and
  `simply_tc`. Tested (`leadgen/tests/`). Verify: `python -m leadgen --list`.
- ✅ **`gui/` LeadEngine** — Flask/pywebview app, both tabs (Browse + Find), no-internet
  demo, connection checker. Builds to a single `LeadEngine.exe` via GitHub Actions.
- ✅ **`lead-tracker/` CRM** — Next.js + SQLite, region-parameterized dataset
  (`sonoma` default → up to `us`), status pipeline, notes, favorites, daily call list.
- ✅ **Datasets + audits** — Sonoma + 5 bordering counties committed; live website
  audit + deep one-time enrichment run on GitHub Actions and commit results back.
- ✅ **Repo restructured** (latest commit) into the two-tool layout; first-gen
  `scraper.py` / `scraper-gui/` archived under `legacy/`.

There is **no open work item blocking deploy** — the pieces above all run today.

## ⚠️ The one gotcha that will strand you

**This build sandbox has no outbound internet.** Anything that scrapes or fetches a
live site (`leadgen` collect/audit, the website-audit pass) **cannot run here** — it
will hang or fail on network calls. That's deliberate: the live audits run on
**GitHub Actions runners** (which do have internet) and commit results back. So:

- Develop/test logic locally against fixtures (`leadgen/tests/` use canned data).
- Run anything that hits the network via the **Actions tab**, not in this sandbox.
- The `.exe` is also built on a real Windows runner in Actions, not here.

## How to run / deploy each piece

### Tool 1 — leadgen (CLI)
```bash
pip install -r leadgen/requirements.txt        # requests + openpyxl (+ duckdb for Overture)
python -m leadgen --list                        # offline, safe here
python -m leadgen --vertical web_design --market sonoma_county_ca --out sonoma_web   # NEEDS INTERNET
python leadgen/tests/test_engine.py             # offline tests
```
Outputs `<stem>_crm.csv` + color-tiered `<stem>.xlsx`.

### Tool 2 — lead-tracker (local CRM)
```bash
cd lead-tracker
npm install
npm run build-db sonoma     # build SQLite dataset (needs python3; ~1-2 min)
npm run dev                 # http://localhost:3030
```
Single-user, all local. To deploy as a hosted app it's a standard Next.js build
(`npm run build && npm start`), but it's designed to run on the user's machine.

### The desktop app + `.exe` (main shippable artifact)
```bash
cd gui && ./run.sh                  # run from source (browser); run.bat on Windows
python gui/desktop_app.py           # native window
```
**Ship the .exe — do this in GitHub Actions, not here:**
- Actions tab → **Build Windows EXE** → Run workflow. Set `release_tag` (e.g. `v1.1.0`)
  to also publish a public Release with the exe attached; leave blank for an
  artifact-only build. Or push a `v*` tag to trigger the same.
- Workflow: `.github/workflows/build-exe.yml` (installs `gui/requirements.txt` + pyinstaller, builds `gui/LeadEngine.spec`).

### Live website audits (need internet → Actions only)
- **Website Audit** (`.github/workflows/website-audit.yml`) — weekly + manual; grades
  each lead's site, commits results CSV the CRM joins on.
- **Deep Audit** (`.github/workflows/deep-audit.yml`) — manual, exhaustive one-time
  enrichment; resumable, commits per county.

## Git / branch

- Active branch: **`claude/lead-scraping-tool-status-16Wd9`** (push here; it has been
  merged to `main` before via PR).
- Push with `git push -u origin claude/lead-scraping-tool-status-16Wd9`.
- Don't push to other branches without the user's say-so. Don't open a PR unless asked.

## Where to look
| Need | Path |
|---|---|
| Add a new prospecting use case | `leadgen/verticals/` (copy `simply_tc.py`), `simplytc/DESIGN.md` |
| Engine internals | `leadgen/pipeline.py`, `sources.py`, `audit.py`, `enrich.py`, `score`/`export.py` |
| CRM schema / data | `lead-tracker/SCHEMA.md`, `lead-tracker/scripts/`, `lead-tracker/data/` |
| Exe packaging | `gui/BUILD_EXE.md`, `gui/LeadEngine.spec` |
| Hand the data to a Claude agent | `data-kit/CLAUDE_AGENT_BRIEFING.md` |
