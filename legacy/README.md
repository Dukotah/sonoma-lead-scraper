# Legacy / archived tools

These were the **first-generation** scrapers for this project. They still run, but
they've been **superseded** by the universal engine (`../leadgen/`) and the polished
GUI/exe (`../gui/`). They're kept here for reference and so nothing is lost — not for
day-to-day use.

| Archived | What it was | Use this instead |
|---|---|---|
| `scraper.py` | Standalone CLI scraper for Sonoma web-design leads (Yelp + Yellow Pages, Google PageSpeed audit, contact-page email scraping). | `python -m leadgen --vertical web_design --market <area>` |
| `scraper-gui/` | Earlier desktop GUI (Flask + pywebview) over an OpenStreetMap scrape + website audit + xlsx export. | The **🔍 Find new leads** tab in `../gui/` (the `LeadEngine` app/exe). |

Both did the same job — collect businesses, audit their sites, score, export — that
`leadgen` now does in one consolidated, tested pipeline with swappable verticals.
See the top-level [`README.md`](../README.md) for the current two-tool layout.
