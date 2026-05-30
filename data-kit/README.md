# Sonoma County Data Kit

Two files, two purposes:

## `download_sonoma.py`
Downloads ~all businesses in Sonoma County from Overture Maps (Meta + Microsoft + Amazon's open dataset).
- **Run once:** `python download_sonoma.py` (2–5 min, ~10–30 MB)
- Outputs three files in same folder: `.parquet`, `.csv`, `.xlsx`
- No API key, no signup, no auth

## `CLAUDE_AGENT_BRIEFING.md`
Hand this to any Claude agent (Claude Code, Claude in chat, the Claude API) along with the data files.
It explains the schema, scoring rules, suggested project structure, and what to build.

## Quick start
```bash
# 1. Get the data
pip install duckdb openpyxl
python download_sonoma.py

# 2. Hand off to a Claude agent
claude
> Read CLAUDE_AGENT_BRIEFING.md and the three data files. Build me the lead-gen
> pipeline described, starting with the audit + scoring step.
```

## Want a different region?
Edit `BBOX` at the top of `download_sonoma.py`:
```python
BBOX = {"south": 30.10, "west": -97.95, "north": 30.52, "east": -97.55}  # Austin, TX
```
Use bboxfinder.com to draw a box on a map and grab the coordinates.

## Overture release version
Check https://docs.overturemaps.org/release/latest/ for the newest release. If `2025-04-23.0` is old
when you run this, update the `RELEASE` constant at the top of the script.

## Attribution
Overture data is CC BY 4.0. If you publish anything derived from this, credit "Overture Maps Foundation".
