# Lead Scraper Toolkit

> **Picking this up fresh (human or AI agent)?** Read [`START_HERE.md`](START_HERE.md)
> first — it's the operational handoff: current state, how to run/ship each piece, and
> the one sandbox gotcha (live scraping needs internet → runs on GitHub Actions).

Two tools, one job: **fill a pipeline with web-design (and other) leads, then work
them until they're customers.** Everything runs on your own machine off free public
data — no accounts, no API keys.

1. **🔍 Find new leads** — scrape the web for fresh prospects, audit their sites, score them, export.
2. **📇 Work your leads** — browse everything you've collected in a fast local CRM: filter, take notes, track status, call through the list.

The easiest way to use both is the **`LeadEngine` desktop app** (`gui/`, shippable as a
single Windows `.exe`) — it has a tab for each. Power users can drive each tool directly.

---

## Tool 1 — Find new leads  (`leadgen/`)

A **universal lead-generation engine**: one pipeline (collect → dedupe → enrich →
suppress → score → export) driven by swappable **verticals**, where a vertical
defines *what* you're prospecting for and *how* to score it. Ships with two —
transaction-coordinator leads (for [simplytc.com](https://simplytc.com)) and the
original web-design leads.

```bash
pip install -r leadgen/requirements.txt

python -m leadgen --list                     # show available verticals
# Web-design leads in Sonoma County:
python -m leadgen --vertical web_design --market sonoma_county_ca --out sonoma_web
# Transaction-coordinator leads for SimplyTC; any geocodable place is a market:
python -m leadgen --vertical simply_tc --market "Austin, Texas" --sources overture osm
```

Outputs a CRM-ready `<stem>_crm.csv` and a color-tiered `<stem>.xlsx`. Tests:
`python leadgen/tests/test_engine.py`.

**Add a use case** = one file in `leadgen/verticals/` calling `register(Vertical(...))`
with a `score_fn` (and optional `enrich_fn`, `opener_fn`, `suppression_fn`). The
`simply_tc` vertical shows the full pattern, including **competitor suppression** —
scraping a rival's published client list to drop prospects who already use them. See
`leadgen/verticals/simply_tc.py` and `simplytc/DESIGN.md`.

## Tool 2 — Work your leads  (`lead-tracker/`)

A **CRM-lite** for actually working the list: a fast, filterable table over a whole
region's businesses, with a per-lead status pipeline, notes, favorites, and CSV
export. A Next.js (App Router) app backed by a local **SQLite** file — single-user,
runs entirely on your machine.

```bash
cd lead-tracker
npm install
npm run build-db sonoma     # build the region dataset (default: Sonoma County)
npm run dev                 # open http://localhost:3030
```

The dataset is **region-parameterized** (`sonoma` → `bayarea` → `california` →
`us`); SQLite stays snappy into the low millions of rows. Business records come from
[Overture Maps](https://overturemaps.org) (open Meta/Microsoft/Amazon dataset,
CC-BY 4.0). See [`lead-tracker/README.md`](lead-tracker/README.md).

## The desktop app — both tools, no setup  (`gui/`)

`LeadEngine` wraps both tools in one point-and-click window built for a
non-technical user: a **📇 Browse all leads** tab (Tool 2, over the bundled dataset)
and a **🔍 Find new leads** tab (Tool 1). No command line, friendly errors, a no-internet
demo run, and a connection checker.

```bash
cd gui && ./run.sh          # browser mode (run.bat on Windows)
python gui/desktop_app.py   # or a native desktop window
```

Ship it as a single double-click **`LeadEngine.exe`** (no Python needed): build on
GitHub (Actions → **Build Windows EXE**, or push a `v*` tag for a Release) or locally
via `gui\build.bat`. See [`gui/README.md`](gui/README.md) and
[`gui/BUILD_EXE.md`](gui/BUILD_EXE.md). End-to-end test: `python gui/test_gui.py`.

---

## Supporting pieces

### `data-kit/` — bulk dataset + Claude-agent briefing
Downloads a county-sized chunk of the [Overture Maps](https://overturemaps.org)
Places dataset, plus a `CLAUDE_AGENT_BRIEFING.md` you hand to a Claude agent along
with the data files. **Use when:** you want to hand the whole project to a Claude
agent for deeper enrichment, or work with the raw data programmatically.

```bash
cd data-kit
python -m pip install duckdb openpyxl
python download_sonoma.py   # ~5 min, ~30 MB
```
Different region? Edit the `BBOX` dict at the top of `data-kit/download_sonoma.py`
(grab coordinates from https://bboxfinder.com).

### `legacy/` — first-generation scrapers
The original standalone `scraper.py` and `scraper-gui/` desktop app, **superseded** by
the engine + GUI above. Kept for reference. See [`legacy/README.md`](legacy/README.md).

## Repo layout
```
lead-scraper-toolkit/
├── README.md            ← you are here
├── LICENSE              ← MIT
├── leadgen/             ← Tool 1: universal scraping engine (verticals, CLI)
├── lead-tracker/        ← Tool 2: local CRM (Next.js + SQLite)
├── gui/                 ← LeadEngine desktop app / .exe — both tools, no setup
├── data-kit/            ← Overture bulk downloader + Claude-agent briefing
├── simplytc/            ← design notes for the simply_tc vertical
└── legacy/              ← archived first-gen scrapers (scraper.py, scraper-gui/)
```

## License
MIT (see `LICENSE`). Overture data is CC-BY 4.0 — credit "Overture Maps Foundation"
if you publish derived work.

## Built with
[Claude](https://claude.com).
