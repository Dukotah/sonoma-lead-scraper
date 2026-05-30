# Lead Scraper Toolkit

Two tools for finding local businesses that need a website — built for web-design lead generation.

## What's in this repo

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
