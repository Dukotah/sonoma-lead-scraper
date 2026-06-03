# Agent contract — generating and consuming leads

This tool is built so **one agent can generate a lead file and another agent can parse
it** with no human in the loop. The contract below is stable; build against it.

## Invocation
```bash
python -m leadgen --vertical <key> --market <market> [--category <substr>...] \
                  --no-enrich --format <json|jsonl|csv>
```
- **stdout = data only.** All progress/diagnostics go to **stderr**. Redirect stderr
  (`2>/dev/null`) or read it separately; never parse it.
- **Exit codes:** `0` success · `2` bad arguments / unknown vertical.
- Runs **offline-capable**: if DuckDB's `httpfs` extension can't be downloaded (CI,
  sandboxes, locked-down networks), it automatically falls back to reading Overture
  Places straight from S3 via pyarrow. Same command, same output.
- Add `--demo` for a fully offline, deterministic 5-record sample (no network) — use
  this for self-tests.

## Discover the schema (so a consumer never guesses)
```bash
python -m leadgen --schema        # prints the record schema as JSON, exits 0
```
Every emitted record has these keys (null/absent = unknown, never zero):

| field | type | meaning |
|---|---|---|
| `name` | string | business name |
| `category` | string | Overture primary category, e.g. `plumbing` |
| `website` | string\|null | homepage URL |
| `phone` / `email` | string\|null | primary contact |
| `socials` | array[string] | social profile URLs (may be empty) |
| `address` / `city` / `state` / `zip` | string\|null | postal address parts |
| `brand` | string\|null | franchise name if the business is a chain |
| `confidence` | number\|null | Overture data confidence, 0..1 |
| `lat` / `lon` | number\|null | coordinates |
| `source` / `source_url` | string | provenance (`overture`/`osm`/`demo`) |
| `tier` | string | lead grade `A`>`B`>`C` (added by scoring) |
| `score` | integer | numeric lead strength, higher = better |
| `why` | string | semicolon-separated reasons it's a lead |
| `opener` | string | suggested first outreach line |

## Formats
- `--format jsonl` — **preferred for agents.** One JSON object per line; parse with a
  streaming reader; robust to truncation; safe to pipe into `head`/`jq`.
- `--format json` — a single JSON array (load whole).
- `--format csv` — header row + one row per record, using the vertical's columns.
- `--out <stem>` — instead of stdout, write `<stem>_crm.csv` + a color-tiered
  `<stem>.xlsx` (for when a human needs the file too).

## Worked example — generate, then consume
Generating agent:
```bash
python -m leadgen --vertical web_design --market sonoma_county_ca \
                  --category plumbing --no-enrich --format jsonl \
                  > plumbers.jsonl 2> run.log
```
Consuming agent (Python):
```python
import json
leads = [json.loads(line) for line in open("plumbers.jsonl")]
hot = [l for l in leads if l["tier"] == "A"]          # no-website / best leads first
for l in sorted(hot, key=lambda x: -x["score"]):
    print(l["name"], l["phone"], "→", l["opener"])
```
Consuming agent (shell):
```bash
jq -r 'select(.tier=="A") | [.name, .phone, .opener] | @tsv' plumbers.jsonl
```

## Notes for the consumer
- Order: records are sorted best-first (`tier` then `score`), so "take the top N" works.
- `--category` matches a **substring of the Overture primary category** (e.g. `plumb`
  matches `plumbing`). Pass multiple to union them: `--category electrician hvac`.
- With `--no-enrich`, businesses that *have* a website land in tier `C`
  (`why` = "has a site — not audited"); drop `--no-enrich` on an open network to fetch
  and grade those sites into real A/B/C. No-website/social-only leads are accurate
  either way.
