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
from .normalize import normalize_record, finalize_record
from .audit import hostname, is_weak_url
from .export import write_outputs
from .vertical import Vertical


def load_crm_names(path_or_text: str, *, is_text: bool = False) -> set[str]:
    """Normalized company names from an existing CRM export (CSV) so the pipeline
    never hands back a brokerage the user already has.

    Reads the first column that looks like a company/business/name field; falls
    back to the first column. Accepts a file path or raw CSV text (is_text=True).
    """
    import csv
    import io
    if not path_or_text:
        return set()
    if is_text:
        f = io.StringIO(path_or_text)
    else:
        f = open(path_or_text, newline="", encoding="utf-8-sig", errors="replace")
    try:
        reader = csv.reader(f)
        rows = list(reader)
    finally:
        if not is_text:
            f.close()
    if not rows:
        return set()
    header = [h.strip().lower() for h in rows[0]]
    name_keys = ("company name", "company", "business", "business name", "brokerage",
                 "name", "account name", "organization")
    col = next((i for i, h in enumerate(header) if h in name_keys), 0)
    out: set[str] = set()
    for row in rows[1:]:
        if col < len(row):
            k = norm(row[col])
            if k:
                out.add(k)
    return out


def _merge_into(dst: dict, src: dict) -> None:
    """Back-fill blank contact/geo fields on the surviving record from a duplicate."""
    for fld in ("website", "phone", "phone_fmt", "area_code", "email",
                "address", "city", "state", "zip", "lat", "lon"):
        if not dst.get(fld) and src.get(fld):
            dst[fld] = src[fld]


def _own_host(rec: dict) -> str:
    """The record's own (non-social) website host, used as a strong dedupe key.
    Social/listing URLs are skipped so two unrelated shops that both list a
    facebook page don't get merged. 'www.' is dropped so the bare and www hosts
    of the same site collapse together."""
    site = rec.get("website") or ""
    if not site or is_weak_url(site)[0]:
        return ""
    h = hostname(site)
    return h[4:] if h.startswith("www.") else h


def _dedupe(leads: list[dict]) -> list[dict]:
    """Collapse duplicates within one market.

    Records merge when they share the same owned website host (a strong identity
    signal that catches cross-source dupes the name can't), OR when their
    normalized names match AND they're in the same city (or one city is blank).
    The same-city guard keeps genuinely distinct offices that share a name — common
    once chains are kept — from collapsing. The survivor back-fills blank fields.
    """
    groups: list[dict] = []
    by_name: dict[str, list[dict]] = {}
    by_host: dict[str, dict] = {}

    def _same_place(a: dict, b: dict) -> bool:
        ca = (a.get("city") or "").strip().lower()
        cb = (b.get("city") or "").strip().lower()
        return not ca or not cb or ca == cb

    for r in leads:
        key = norm(r.get("name", ""))
        if not key:
            continue
        host = _own_host(r)
        match = by_host.get(host) if host else None
        if match is None:
            match = next((g for g in by_name.get(key, []) if _same_place(g, r)), None)
        if match is None:
            groups.append(r)
            by_name.setdefault(key, []).append(r)
            if host:
                by_host[host] = r
        else:
            _merge_into(match, r)
            if host and host not in by_host:
                by_host[host] = match
    return groups


def _enrich_priority(r: dict) -> tuple:
    """Cheap pre-enrichment rank so a capped budget goes to leads we can learn
    from. A real (non-social) website is the big one — without it enrichment is a
    no-op; phone/email are minor tie-breakers."""
    site = r.get("website") or ""
    has_site = bool(site) and not is_weak_url(site)[0]
    return (has_site, bool(site), bool(r.get("phone")), bool(r.get("email")))


def run_pipeline(vertical: Vertical, market: str, *,
                 sources=("overture",), limit: int | None = None,
                 enrich: bool = True, enrich_cap: int | None = 150,
                 out_stem: str | None = None, config_override: dict | None = None,
                 exclude_names: set | None = None, demo: bool = False,
                 log=print) -> list[dict]:
    """Run the full pipeline for one vertical in one market.

    sources: any of ("overture", "osm").
    enrich:  run the vertical's enrich_fn (fetches each business's site).
    enrich_cap: only enrich the top-N by collection order (cost control); None = all.
    out_stem: if set, also writes <stem>_crm.csv and <stem>.xlsx.
    config_override: shallow-merged over the vertical's config for THIS run only
                     (e.g. competitor seed URLs typed into the GUI). The shared
                     vertical object is never mutated.
    exclude_names: normalized company names to drop (e.g. the user's existing CRM)
                   — see load_crm_names(). Matches are removed, not just flagged.
    demo: if True, use bundled offline sample data + fixture enrichment (no network).
    Returns the scored, sorted list of lead dicts. Output file paths, when written,
    are attached as run_pipeline.last_outputs = (csv_path, xlsx_path).
    """
    run_pipeline.last_outputs = None
    # Per-run config: copy so concurrent runs / the registry stay clean.
    cfg = dict(vertical.config)
    if config_override:
        cfg.update(config_override)

    # 1. COLLECT
    leads: list[dict] = []
    if demo:
        from .demo import demo_records
        leads = demo_records()
        log(f"DEMO MODE — using {len(leads)} bundled sample businesses (no network).")
    else:
        bbox, label = resolve_market(market)
        log(f"Market: {label}  bbox={tuple(round(x,3) for x in bbox)}")
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
    # 1a. NORMALIZE values before dedupe so cleaned names + website hosts make
    # the dedupe keys reliable (and the output is CRM-clean from the start).
    for r in leads:
        normalize_record(r)
    log(f"Collected {len(leads)} raw; deduping…")
    leads = _dedupe(leads)
    log(f"  {len(leads)} after dedupe")

    # 1b. drop businesses already in the user's CRM (never hand back a dupe)
    if exclude_names:
        before = len(leads)
        leads = [r for r in leads if norm(r.get("name", "")) not in exclude_names]
        log(f"  removed {before - len(leads)} already in your CRM ({len(exclude_names)} names)")

    # 1c. chain handling — verticals that don't keep chains drop branded records
    if not vertical.keep_chains:
        before = len(leads)
        leads = [r for r in leads if not (r.get("brand"))]
        log(f"  dropped {before - len(leads)} chain/branded records")

    # 2. SUPPRESSION (competitor clients) — build once, applied during scoring.
    # Skipped in demo mode: it fetches competitor sites, and demo must stay offline.
    suppressed: dict[str, str] = {}
    if vertical.suppression_fn and not demo:
        log("Building competitor-suppression set…")
        suppressed = vertical.suppression_fn(cfg) or {}

    # 3. ENRICH (per-business website visit) — parallel, capped
    if enrich and vertical.enrich_fn and demo:
        # Offline enrichment: feed bundled fixture HTML through the same hooks.
        from .demo import demo_html_for
        ctx = {"config": cfg, "demo_html": demo_html_for}
        log(f"Enriching {len(leads)} sample businesses from bundled pages…")
        for r in leads:
            try:
                vertical.enrich_fn(r, ctx)
            except Exception as e:
                r["enrich_error"] = str(e)
    elif enrich and vertical.enrich_fn:
        # Spend the (capped) enrich budget on the most promising leads, not on
        # arbitrary collection order: a record with no website can't be enriched
        # at all, so prioritize ones we can actually learn something from.
        if enrich_cap is None:
            targets = leads
        else:
            ranked = sorted(leads, key=_enrich_priority, reverse=True)
            targets = ranked[:enrich_cap]
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
                    futs[f].setdefault("enrich_note", f"enrich failed: {e}")
                done += 1
                if done % 25 == 0:
                    log(f"  enriched {done}/{len(targets)}")

    # 4. FINALIZE quality fields (after enrichment may have added email/phone),
    #    then SCORE (+ apply suppression flag) + opener.
    for r in leads:
        finalize_record(r)
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
