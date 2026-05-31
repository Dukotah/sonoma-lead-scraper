# SimplyTC Lead Engine

Finds **real-estate brokerages & high-volume agents** who likely need a
transaction coordinator and **aren't already locked in with a competitor** —
enriched, scored, and CRM-ready for [simplytc.com](https://simplytc.com).

This is a **vertical built on the existing toolkit in this repo**, not a rewrite.
It reuses the Overture/OSM collectors, website auditing, web-verify, and exporters
from `../data-kit/` and `../scraper-gui/`; it replaces *what we look for* and
*how we score*.

## Start here
- **[`DESIGN.md`](./DESIGN.md)** — the full approach, architecture, and phased plan. Read this first.
- **[`config.py`](./config.py)** — the one file you tune: ICP, target markets, competitor list, TC fingerprints.

## What's built vs. planned
| Piece | Status | Where |
|-------|--------|-------|
| Approach & architecture | ✅ done | `DESIGN.md` |
| Tunable ICP / markets / signals | ✅ done (data) | `config.py` |
| TC-presence fingerprint + suppression | 🟡 stubs w/ finished signatures | `tc_signals.py` |
| TC-fit scoring + call openers | ✅ logic done | `score.py` |
| Collect (brokerages) | ♻️ reuse | `../data-kit/download_sonoma.py`, `../scraper-gui/app.py` |
| Enrich (website audit / web-verify) | ♻️ reuse | `../data-kit/lead_tools.py` |
| Export (xlsx + CRM csv) | ♻️ reuse + remap columns | `../data-kit/enrich_leads.py` |
| `pipeline.py` orchestration | ⬜ Phase 1 | — |

## Phase 1 (next)
1. Pick 1–2 target metros in `config.TARGET_MARKETS`.
2. Add the real competitor TC companies your mom knows to `config.COMPETITOR_TC_SEEDS`.
3. Wire `pipeline.py`: collect brokerages → enrich (roster size + `fingerprint_tc`)
   → `score_lead_tc` → export CRM CSV.
4. Validate on ~50 real calls before scaling to more markets.

## The honest caveat
Proving a brokerage *doesn't* use a TC is impossible from public data. This engine
**confirms** the obvious "already taken" cases (removes them) and **scores the
likelihood** of a gap for everyone else. Final qualification happens on the call —
the data just makes every call start from a much better place.
