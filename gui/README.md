# Lead Engine — GUI

A point-and-click front end over the [`leadgen`](../leadgen) engine. Pick a
**vertical** (what to prospect for), a **market** (where), optionally paste
competitor pages to skip their clients, hit **Run**, watch live progress, and
download a CRM-ready CSV + a color-tiered XLSX.

## Run it

**Browser mode (simplest):**
```bash
cd gui
./run.sh            # macOS/Linux  (run.bat on Windows)
# then open the URL it prints, e.g. http://127.0.0.1:5000
```

**Native desktop window:**
```bash
pip install -r gui/requirements.txt
python gui/desktop_app.py
```

## What each control does
- **Vertical** — `simply_tc` (transaction-coordinator leads) or `web_design`.
  The description and competitor box update to match.
- **Market** — a saved key (e.g. `sonoma_county_ca`) or any place name we geocode
  on the fly (e.g. `"Austin, Texas"`).
- **Data sources** — *Overture* (bulk national dataset, needs `duckdb`) and/or
  *OpenStreetMap* (live, no extra deps).
- **Skip competitors' clients** *(simply_tc only)* — paste each rival TC company's
  testimonial / "clients we serve" URL. We scrape them and drop brokerages already
  using a competitor.
- **Enrich** — visit each business's site to estimate volume (agent count) and
  detect TC/competitor signals. Richer data, slower. **Enrich cap** limits how many
  sites are visited; **Collect limit** caps how many businesses are pulled.

Output files are written to `gui/_output/` and offered as downloads.

## Network note
The collectors call out to Overture (AWS S3), Overpass (OSM), and DuckDuckGo.
Some locked-down/cloud IPs block these (you'll see `HTTP 403` or S3 errors in the
log). If that happens, run from a normal network connection.
