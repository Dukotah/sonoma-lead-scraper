# Lead Scraper Toolkit

A **universal lead-generation engine**: one pipeline (collect → dedupe → enrich →
suppress → score → export) driven by swappable **verticals**, where a vertical
defines *what* you're prospecting for and *how* to score it. Ships with two
verticals — transaction-coordinator leads (for [simplytc.com](https://simplytc.com))
and the original web-design leads — plus the GUI and bulk-data tools below.

## The engine — `leadgen/`

```bash
pip install -r leadgen/requirements.txt

python -m leadgen --list                     # show available verticals
# Transaction-coordinator leads for SimplyTC:
python -m leadgen --vertical simply_tc --market sonoma_county_ca --out sonoma_tc
# Any geocodable place works as a market:
python -m leadgen --vertical simply_tc --market "Austin, Texas" --sources overture osm
# Original web-design use case, same engine:
python -m leadgen --vertical web_design --market sonoma_county_ca --no-enrich
```

Outputs a CRM-ready `<stem>_crm.csv` and a color-tiered `<stem>.xlsx`.

> **Run it from an agent sandbox (no local machine, no open internet).** The
> Overture source reads parquet straight from public S3 via `pyarrow` + `s3fs`
> (no DuckDB/`httpfs`), so an agent can scrape live business data from inside a
> restricted sandbox like Claude Code on the web. Use `--sources overture
> --no-enrich` with a named `--market`. What's reachable, what isn't, and why:
> [`docs/SANDBOX.md`](docs/SANDBOX.md).

### Point-and-click GUI — `gui/`

No command line needed: pick a vertical + market, paste competitor pages to skip,
upload your CRM to de-dupe, hit Run, watch live progress, download the CSV/XLSX.
Built for a non-technical user:

- **Try a demo** — a full sample run with **no internet**, so you see real output first.
- **Check my connection** — tests each data source and says, in plain English,
  what works before you waste a run.
- **Skip people already in your CRM** — upload a CSV; matches are removed, never duplicated.
- **Friendly errors** — guidance instead of tracebacks.

```bash
cd gui && ./run.sh          # browser mode (run.bat on Windows)
# or a native desktop window:
python gui/desktop_app.py
```

See [`gui/README.md`](gui/README.md). End-to-end test: `python gui/test_gui.py`.

### Ship it as a Windows .exe — `gui/`

A single double-click `LeadEngine.exe`, no Python needed. Build it on GitHub
(Actions → **Build Windows EXE**, or push a `v*` tag for a Release) or locally on
Windows via `gui\build.bat`. Details: [`gui/BUILD_EXE.md`](gui/BUILD_EXE.md).

**Add a new use case** = one file in `leadgen/verticals/` that calls
`register(Vertical(...))` with a `score_fn` (and optional `enrich_fn`,
`opener_fn`, `suppression_fn`). The `simply_tc` vertical shows the full pattern,
including **competitor suppression** — scraping a rival's published client list to
drop prospects who already use them. See `leadgen/verticals/simply_tc.py` and
`simplytc/DESIGN.md` for the approach. Tests: `python leadgen/tests/test_engine.py`.

## Legacy / companion tools

### `scraper-gui/` — desktop app
A clickable desktop app (Flask + pywebview, optionally compiled to a single .exe).
Pick a city, pick niches, hit Scrape. It queries OpenStreetMap, audits each business's website
(load time, HTTPS, mobile-friendly, what builder they use), scores the leads, and exports a ranked .xlsx.

**Use when:** you want a quick interactive scrape and a clean spreadsheet to call from.

### `data-kit/` — bulk dataset + Claude-agent briefing
A script that downloads a county-sized chunk of the [Overture Maps](https://overturemaps.org)
Places dataset (Meta + Microsoft + Amazon's open business database). Plus a `CLAUDE_AGENT_BRIEFING.md`
you hand to a Claude agent (Claude Code or otherwise) along with the data files.

**Use when:** you want to hand the whole project off to a Claude agent for deeper enrichment,
build a CRM pipeline, or work with the data programmatically.

## Quick start

### Just want the GUI scraper?
```powershell
cd scraper-gui
python -m pip install -r requirements.txt
python desktop_app.py
```
Or to make a standalone .exe: see `scraper-gui/BUILD_INSTRUCTIONS.md`.

### Want the bulk dataset + agent project?
```powershell
cd data-kit
python -m pip install duckdb openpyxl
python download_sonoma.py   # ~5 min, ~30 MB
# then hand off to Claude Code:
claude
> Read CLAUDE_AGENT_BRIEFING.md and the three data files. Build me the lead-gen pipeline described.
```

### Want a different region than Sonoma County?
Edit the `BBOX` dict at the top of `data-kit/download_sonoma.py`. Get coordinates
from https://bboxfinder.com (draw a box, copy the numbers).

## Repo layout
```
lead-scraper-toolkit/
├── README.md                  ← you are here
├── LICENSE                    ← MIT
├── .gitignore
├── scraper-gui/
│   ├── app.py                 ← Flask backend (OSM scraper + audit + xlsx)
│   ├── desktop_app.py         ← native-window entry point
│   ├── requirements.txt
│   ├── run.bat / run.sh       ← browser-mode launcher
│   ├── build.bat / build.sh   ← compile standalone .exe
│   ├── BUILD_INSTRUCTIONS.md
│   └── README.md
├── data-kit/
│   ├── download_sonoma.py     ← Overture downloader
│   ├── CLAUDE_AGENT_BRIEFING.md  ← hand this to a Claude agent
│   └── README.md
└── docs/
    └── (room for future docs)
```

## Tech notes
- **Source: OpenStreetMap** for the GUI app (Overpass API, live queries).
- **Source: Overture Maps** for the bulk data kit (Meta/MSFT/Amazon open dataset, monthly releases).
- **Audit**: Python `requests` against each business's homepage. Checks status, HTTPS, mobile viewport, load time, builder fingerprint (Wix/Squarespace/Weebly/etc.).
- **Output**: `.xlsx` with Tier A/B/C, score, pitch angle per lead.

## License
MIT (see `LICENSE`). Overture data is CC-BY 4.0 — credit "Overture Maps Foundation" if you publish derived work.

## Built with
[Claude](https://claude.com) on a Saturday afternoon in May 2026.
