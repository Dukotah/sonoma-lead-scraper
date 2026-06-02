# DEMO — running the lead engine live (offline-safe)

A 3-minute demo you can run in any chat/terminal window. It uses **`--demo` mode**,
which runs the **full pipeline with zero network**, so it can't fail on a flaky
connection in front of an audience. Same code path as a real run — just bundled
sample data instead of a live scrape.

## The 30-second pitch
> "This engine finds businesses that need a service, scores them by how good a lead
> they are, and hands your salesperson a ranked call list — each row with the
> contact, *why* they're a lead, and a *ready-to-say opening line*. Watch."

## The one command (transaction-coordinator leads — the SimplyTC use case)
```bash
python -m leadgen --vertical simply_tc --demo --out demo_tc
```
You'll see it collect → de-dupe → enrich → score, then write **`demo_tc_crm.csv`**
(open in Excel/Sheets) and a color-tiered **`demo_tc.xlsx`** (Tier A/B/C shaded).

### What to point at in the output (this is the value)
| Column | The pitch |
|---|---|
| **Tier / Score** | Leads are ranked — your rep calls Tier A first, not a random list. |
| **TC gap** (`hiring` / `open` / `software` / `in_house`) | The engine *reads each brokerage's site* and figures out whether they already have a coordinator. A brokerage **actively hiring** one is the hottest possible lead. |
| **Decision-maker / Title** | It pulled the broker/owner's name off the site — no guessing who to ask for. |
| **Why a lead** | Plain-English reason, so the rep trusts the ranking. |
| **Suggested opener** | A tailored first line per lead — *"actively hiring a TC — instead of hiring salary+benefits, outsource per-file to SimplyTC today."* |
| **Already has TC?** | Competitor suppression: it can scrape rival firms' client lists and drop brokerages already taken — you never waste a call. |

## Variations
```bash
# Same thing, structured JSON output (for a technical audience / integration)
python -m leadgen --vertical simply_tc --demo --json | head -40

# A different vertical, same engine — proves it generalizes
python -m leadgen --list
```

## Going live on real data (if the demo machine has internet)
Demo mode is the safe choice in front of people. To show **real, current** leads for
any area, drop `--demo`, add a market, and skip the slow per-site step with
`--no-enrich`:
```bash
python -m leadgen --vertical simply_tc --market "Sonoma County, CA" --no-enrich --out sonoma_live
```
(`--no-enrich` keeps it fast and robust — it does the single bulk directory query but
skips the hundreds of per-site fetches. Re-run without it later to deep-grade the top
leads.)

## If asked "how does it scale / where's the data?"
- Business records come from **Overture Maps** (the open Meta/Microsoft/Amazon
  dataset) — free, no API keys, refreshed monthly.
- The companion **Lead Tracker** CRM (`lead-tracker/`) holds a whole region
  (Sonoma County → all of California → the US) in a local database for working the list.
- The whole thing also ships as a **double-click Windows app** (`LeadEngine.exe`) for
  a non-technical user — no command line.

## Pre-flight (run once before the meeting)
```bash
pip install -r leadgen/requirements.txt
python -m leadgen --vertical simply_tc --demo --out /tmp/preflight   # should print "Scored 5 — A=1 B=3 C=1"
```
