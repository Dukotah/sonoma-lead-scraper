# DEMO — running the lead engine live (offline-safe)

A 3-minute demo you can run in any chat/terminal window. It uses **`--demo` mode**,
which runs the **full pipeline with zero network**, so it can't fail on a flaky
connection in front of an audience. Same code path as a real run — just bundled
sample data instead of a live scrape. **Both verticals demo fully offline.**

## The 30-second pitch
> "This engine finds local businesses that need a service, scores them by how good
> a lead they are, and hands your salesperson a ranked call list — each row with the
> contact, *why* they're a lead, and a *ready-to-say opening line*. Watch."

## Demo A — transaction-coordinator leads (the SimplyTC use case)
```bash
python -m leadgen --vertical simply_tc --demo --out demo_tc
```
Expect: `Scored 5 — A=1 B=3 C=1`, plus `demo_tc_crm.csv` and a color-tiered
`demo_tc.xlsx`. Point at these columns — this is the value:

| Column | The pitch |
|---|---|
| **Tier / Score** | Leads are ranked — your rep calls Tier A first, not a random list. |
| **TC gap** (`hiring`/`open`/`software`/`in_house`) | The engine *reads each brokerage's site* and figures out whether they already have a coordinator. One **actively hiring** is the hottest possible lead. |
| **Decision-maker / Title** | It pulled the broker/owner's name off the site — no guessing who to ask for. |
| **Suggested opener** | A tailored first line per lead — *"actively hiring a TC — instead of salary+benefits, outsource per-file to SimplyTC today."* |
| **Already has TC?** | Competitor suppression: scrape rival firms' client lists and drop brokerages already taken — never waste a call. |

## Demo B — web-design leads (proves the engine generalizes)
```bash
python -m leadgen --vertical web_design --demo --out demo_web
```
Expect: `Scored 5 — A=2 B=2 C=1`. Same engine, totally different scoring:

| Lead | What the engine found | Tier |
|---|---|---|
| Redwood Plumbing | **No website at all** | A |
| Bella Hair Salon | Facebook page only, no real site | A |
| Joe's Auto Repair | `http://` only — **not secure**, not mobile-friendly | B |
| Sonoma Family Law | Built on **Wix** — DIY, slow, hard to rank | B |
| Green Valley Cafe | Clean modern site — **correctly flagged low-priority** | C |

The Tier-C result is the trust-builder: *it doesn't flag everyone* — it tells your
rep which businesses to skip.

## Variations
```bash
python -m leadgen --vertical simply_tc --demo --json | head -40   # structured output
python -m leadgen --list                                          # show all verticals
```

## Going live on real data (if the demo machine has internet)
Demo mode is the safe choice in front of people. For real, current leads, drop
`--demo`, add a market, and skip the slow per-site step with `--no-enrich`:
```bash
python -m leadgen --vertical simply_tc --market "Sonoma County, CA" --no-enrich --out sonoma_live
```

## If asked "where's the data / how does it scale?"
- Records come from **Overture Maps** (the open Meta/Microsoft/Amazon dataset) — free,
  no API keys, refreshed monthly.
- A companion **Lead Tracker** CRM (`lead-tracker/`) holds a whole region for working
  the list; it also ships as a double-click **Windows app** for a non-technical user.

## Pre-flight (run once before the meeting)
```bash
pip install -r leadgen/requirements.txt
python -m leadgen --vertical simply_tc  --demo --out /tmp/pre   # -> Scored 5 — A=1 B=3 C=1
python -m leadgen --vertical web_design --demo --out /tmp/pre   # -> Scored 5 — A=2 B=2 C=1
```

---

# Driving the demo from an AI agent chat

If you're demoing inside an AI assistant chat (Claude Code, etc.), paste the block
below as your first message. The agent will run the demo and narrate it for the room.

> **You are demoing a lead-generation engine to a business audience. Do exactly this,
> narrating each step in plain English a non-technical person understands.**
>
> 1. Say one line: this tool finds local businesses that need a service, ranks them as
>    sales leads, and writes a call list with a ready-to-say opener for each.
> 2. Run: `python -m leadgen --vertical simply_tc --demo --out /tmp/demo_tc`
>    Then show the contents of `/tmp/demo_tc_crm.csv` as a clean table. Walk through the
>    top lead and read its "Suggested opener" out loud. Explain that "TC gap = hiring"
>    means the brokerage is actively trying to hire a coordinator — the hottest lead.
> 3. Run: `python -m leadgen --vertical web_design --demo --out /tmp/demo_web`
>    Show `/tmp/demo_web_crm.csv` as a table. Point out it found a business with no
>    website at all (Tier A) and also correctly marked a business with a good site as
>    low-priority (Tier C) — it tells you who to skip, not just who to call.
> 4. Close: same engine, two different businesses — point it at any market and it
>    produces a ranked, ready-to-work call list. Everything ran offline, no setup.
>
> Keep it tight and benefit-focused. Don't show raw JSON or stack traces; if a command
> prints logs, summarize them. The `--demo` runs need no network.
