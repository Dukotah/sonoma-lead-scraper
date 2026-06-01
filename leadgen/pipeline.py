"""
The pipeline: collect → dedupe → enrich → suppress → score → export.
Vertical-agnostic; all use-case specifics come from the Vertical object.
"""
from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from .geo import resolve_market
from .sources import overture_collect, osm_collect
from .suppression import norm, build_suppression_set
from .export import write_outputs
from .vertical import Vertical


def _dedupe(leads: list[dict]) -> list[dict]:
    """Collapse same-name duplicates (across sources) within one market."""
    seen: dict[str, dict] = {}
    for r in leads:
        key = norm(r.get("name", ""))
        if not key:
            continue
        if key in seen:
            # prefer the record that already has a website / more fields
            cur = seen[key]
            if not cur.get("website") and r.get("website"):
                cur["website"] = r["website"]
            if not cur.get("phone") and r.get("phone"):
                cur["phone"] = r["phone"]
        else:
            seen[key] = r
    return list(seen.values())


def run_pipeline(vertical: Vertical, market: str, *,
                 sources=("overture",), limit: int | None = None,
                 enrich: bool = True, enrich_cap: int | None = 150,
                 out_stem: str | None = None, config_override: dict | None = None,
                 log=print) -> list[dict]:
    """Run the full pipeline for one vertical in one market.

    sources: any of ("overture", "osm").
    enrich:  run the vertical's enrich_fn (fetches each business's site).
    enrich_cap: only enrich the top-N by collection order (cost control); None = all.
    out_stem: if set, also writes <stem>_crm.csv and <stem>.xlsx.
    config_override: shallow-merged over the vertical's config for THIS run only
                     (e.g. competitor seed URLs typed into the GUI). The shared
                     vertical object is never mutated.
    Returns the scored, sorted list of lead dicts. Output file paths, when written,
    are attached as run_pipeline.last_outputs = (csv_path, xlsx_path).
    """
    run_pipeline.last_outputs = None
    # Per-run config: copy so concurrent runs / the registry stay clean.
    cfg = dict(vertical.config)
    if config_override:
        cfg.update(config_override)

    bbox, label = resolve_market(market)
    log(f"Market: {label}  bbox={tuple(round(x,3) for x in bbox)}")

    # 1. COLLECT
    leads: list[dict] = []
    if "overture" in sources:
        try:
            leads += overture_collect(bbox, vertical.overture_categories, limit, log)
        except Exception as e:
            log(f"  Overture failed: {e}")
    if "osm" in sources and vertical.osm_tags:
        try:
            leads += osm_collect(bbox, vertical.osm_tags, log)
        except Exception as e:
            log(f"  OSM failed: {e}")
    log(f"Collected {len(leads)} raw; deduping…")
    leads = _dedupe(leads)
    log(f"  {len(leads)} after dedupe")

    # 1b. chain handling — verticals that don't keep chains drop branded records
    if not vertical.keep_chains:
        before = len(leads)
        leads = [r for r in leads if not (r.get("brand"))]
        log(f"  dropped {before - len(leads)} chain/branded records")

    # 2. SUPPRESSION (competitor clients) — build once, applied during scoring
    suppressed: dict[str, str] = {}
    if vertical.suppression_fn:
        log("Building competitor-suppression set…")
        suppressed = vertical.suppression_fn(cfg) or {}

    # 3. ENRICH (per-business website visit) — parallel, capped
    if enrich and vertical.enrich_fn:
        targets = leads if enrich_cap is None else leads[:enrich_cap]
        log(f"Enriching {len(targets)} businesses (parallel)…")
        ctx = {"config": cfg}
        with ThreadPoolExecutor(max_workers=8) as ex:
            futs = {ex.submit(vertical.enrich_fn, r, ctx): r for r in targets}
            done = 0
            for f in as_completed(futs):
                try:
                    f.result()
                except Exception as e:
                    futs[f]["enrich_error"] = str(e)
                done += 1
                if done % 25 == 0:
                    log(f"  enriched {done}/{len(targets)}")

    # 4. SCORE (+ apply suppression flag) + opener
    for r in leads:
        key = norm(r.get("name", ""))
        if key in suppressed:
            r["suppressed"] = True
            r["suppressed_by"] = suppressed[key]
        s, tier, reasons = vertical.score(r)
        r["score"], r["tier"], r["why"] = s, tier, reasons
        if vertical.opener_fn:
            r["opener"] = vertical.opener_fn(r)
    leads.sort(key=lambda x: -x.get("score", 0))

    n = {"A": 0, "B": 0, "C": 0}
    for r in leads:
        n[r.get("tier", "C")] = n.get(r.get("tier", "C"), 0) + 1
    log(f"Scored {len(leads)} — A={n['A']} B={n['B']} C={n['C']}")

    # 5. EXPORT
    if out_stem:
        # Slugify only the filename; keep any directory the caller supplied intact.
        import os
        d, base = os.path.split(out_stem)
        stem = os.path.join(d, re.sub(r"[^a-z0-9]+", "_", base.lower()).strip("_"))
        run_pipeline.last_outputs = write_outputs(leads, vertical.columns, stem, log)

    return leads
