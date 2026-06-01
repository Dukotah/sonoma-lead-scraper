# Lead Scraper

A desktop app that finds local businesses that need a website — for web-design lead generation.

**Source:** OpenStreetMap (Overpass API). Free, unlimited, never breaks, no API keys.

## What it does
1. You type a city (e.g. "Santa Rosa, California") and pick which kinds of businesses to scan.
2. App geocodes the city and queries OpenStreetMap for matching businesses.
3. For each business, fetches their website and audits it — load time, HTTPS, mobile-friendly, what builder they use.
4. Scores every business by how badly they need a new site.
5. You download a ranked .xlsx with a tailored pitch line per lead.

## OSM coverage — set expectations
- Coverage of small businesses depends on local volunteer mappers.
- For Sonoma County, expect ~50–200 businesses per niche (compared to ~30/niche YP would give per page).
- Businesses **without a website tag** in OSM are real leads worth verifying.
- Phone numbers and addresses are present for ~60% of entries.
- It's not exhaustive, but every result is real and the tool works every time.

## How to use it

### Path 1: standalone .exe (no Python visible)
Follow `BUILD_INSTRUCTIONS.md` once → `LeadScraper.exe` you can double-click forever.

### Path 2: Python native window
Install Python 3.10+ (check "Add to PATH"). Double-click `desktop_app.py`.

### Path 3: browser
Double-click `run.bat` (Windows) or `run.sh` (Mac). Opens at http://localhost:5000.

## Using the app
1. Type a real city name: "Santa Rosa, California", "Petaluma, CA", "Austin, Texas", etc.
2. Tick the niches you want.
3. Leave "Live-fetch each lead's website" checked for real quality scores.
4. Click **Scrape**. Watch the live log.
5. When done, click **Download**.

## Output columns
- **Tier**: A (no/fake website), B (real but weak), C (real, no obvious issues)
- **Score**: higher = stronger lead
- **HTTPS / Mobile / Load / Builder**: live audit results
- **Audit notes**: e.g., "Slow load (5200ms); Not mobile-friendly; DIY-builder (Wix)"
- **Why a lead**: human-readable scoring reason
- **Pitch**: a tailored opening line for that specific lead
- **OSM link**: lets you verify or correct the data on openstreetmap.org

## Files
| File | Purpose |
|---|---|
| `LeadScraper.exe` | Compiled app — double-click to run |
| `desktop_app.py` | Native window entry point |
| `app.py` | Flask backend (OSM scraper + audit + xlsx) |
| `run.bat` / `run.sh` | Browser-mode launcher |
| `build.bat` / `build.sh` | Compile .exe (one-time setup) |
| `BUILD_INSTRUCTIONS.md` | Step-by-step build |
| `requirements.txt` | Python deps |

## Etiquette
The app paces requests to Overpass (~1s between niches). Don't run 30 niches against a giant city at once — split it up. OSM is a free volunteer project; treat their servers nicely.
