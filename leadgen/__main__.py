"""
CLI for the universal lead engine.

    python -m leadgen --list
    python -m leadgen --vertical simply_tc --market sonoma_county_ca --out sonoma_tc
    python -m leadgen --vertical simply_tc --market "Austin, Texas" --sources overture osm
    python -m leadgen --vertical web_design --market sonoma_county_ca --no-enrich --limit 200

Agent-to-agent use (structured stdout, logs on stderr, stable schema):
    python -m leadgen --schema                                                              # describe the record schema
    python -m leadgen --vertical web_design --market sonoma_county_ca --category plumbing \\
                      --no-enrich --format jsonl                                            # one JSON object per line
    python -m leadgen --vertical web_design --demo --format json                            # fully offline sample
"""
from __future__ import annotations

import argparse
import csv
import json
import sys

from . import get_vertical, all_verticals, run_pipeline

# Stable, self-describing schema for one emitted lead record, so a consuming agent
# can parse the output without guessing. Collector fields are always present; the
# scoring fields (tier/score/why/opener) are added by every vertical. A null or
# absent value means "unknown", never "zero". Printed by `--schema`.
RECORD_SCHEMA = {
    "record": "one business lead",
    "encoding": {
        "json": "a single JSON array of record objects on stdout",
        "jsonl": "one JSON record object per line on stdout (newline-delimited)",
        "csv": "CSV with the vertical's columns on stdout (header row first)",
    },
    "stdout_is_data": True,
    "logs_on": "stderr",
    "exit_codes": {"0": "success", "2": "bad arguments / unknown vertical"},
    "fields": {
        "name": "string — business name",
        "category": "string — Overture primary category, e.g. 'plumbing'",
        "website": "string|null — homepage URL if known",
        "phone": "string|null — primary phone",
        "email": "string|null — primary email",
        "socials": "array[string] — social profile URLs (may be empty)",
        "address": "string|null — street line",
        "city": "string|null",
        "state": "string|null — region/state code",
        "zip": "string|null — postal code",
        "brand": "string|null — franchise/brand name when the business is a chain",
        "confidence": "number|null — Overture data confidence, 0..1",
        "lat": "number|null — latitude",
        "lon": "number|null — longitude",
        "source": "string — provenance: 'overture' | 'osm' | 'demo'",
        "source_url": "string — provenance URL when available, else ''",
        "tier": "string — lead grade 'A' | 'B' | 'C' (A = best). Added by scoring.",
        "score": "integer — numeric lead score, higher = stronger. Added by scoring.",
        "why": "string — semicolon-separated reasons this is a lead. Added by scoring.",
        "opener": "string — suggested first outreach line. Added by scoring.",
    },
}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="leadgen", description="Universal lead-gen engine")
    ap.add_argument("--list", action="store_true", help="list available verticals and exit")
    ap.add_argument("--vertical", help="vertical key (see --list)")
    ap.add_argument("--market", help="named market key or a geocodable place name")
    ap.add_argument("--sources", nargs="+", default=["overture"],
                    choices=["overture", "osm"], help="data sources to collect from")
    ap.add_argument("--limit", type=int, help="cap businesses collected")
    ap.add_argument("--category", nargs="+", metavar="SUBSTR",
                    help="filter Overture to these category substrings (e.g. plumbing "
                         "electrician); overrides the vertical's default categories")
    ap.add_argument("--enrich-cap", type=int, default=150,
                    help="enrich only the top-N businesses (cost control)")
    ap.add_argument("--no-enrich", action="store_true", help="skip per-site enrichment")
    ap.add_argument("--keep-chains", action="store_true",
                    help="keep branded records (use for sectors like wineries where the "
                         "Overture brand is the business's own label, not a franchise)")
    ap.add_argument("--demo", action="store_true",
                    help="run fully offline on bundled sample data (no network) — for testing / agents")
    ap.add_argument("--format", choices=["json", "jsonl", "csv"],
                    help="emit scored leads to stdout in this format (logs go to stderr). "
                         "jsonl = one JSON record per line, ideal for agent parsing")
    ap.add_argument("--json", action="store_true",
                    help="alias for --format json (kept for back-compat)")
    ap.add_argument("--schema", action="store_true",
                    help="print the output record schema as JSON and exit (for consuming agents)")
    ap.add_argument("--out", help="output filename stem (writes <stem>_crm.csv + <stem>.xlsx)")
    args = ap.parse_args(argv)

    if args.schema:
        json.dump(RECORD_SCHEMA, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return 0

    if args.list:
        for k, v in sorted(all_verticals().items()):
            print(f"  {k:14s} {v.label}")
        return 0

    # Resolve the stdout data format: --format wins, --json is a back-compat alias.
    fmt = args.format or ("json" if args.json else None)

    if not args.vertical or (not args.market and not args.demo):
        ap.error("--vertical and --market are required (or use --list, or --demo)")

    try:
        vertical = get_vertical(args.vertical)
    except KeyError as e:
        print(e, file=sys.stderr)
        return 2

    # When emitting data to stdout, stdout is reserved for the payload — logs go to stderr.
    log = (lambda *a, **k: print(*a, file=sys.stderr)) if fmt else print
    # A stdout-format run is for an agent that just wants the data — don't write
    # CSV/XLSX files unless an explicit --out was given.
    out_stem = args.out
    if not out_stem and not fmt:
        out_stem = f"{args.vertical}_{args.market or 'demo'}"

    leads = run_pipeline(
        vertical, args.market or "demo",
        sources=tuple(args.sources), limit=args.limit,
        enrich=not args.no_enrich, enrich_cap=args.enrich_cap,
        out_stem=out_stem, demo=args.demo,
        overture_categories=args.category,
        keep_chains=(True if args.keep_chains else None), log=log,
    )

    if fmt == "json":
        json.dump(leads, sys.stdout, ensure_ascii=False, indent=2, default=str)
        sys.stdout.write("\n")
    elif fmt == "jsonl":
        for r in leads:
            sys.stdout.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    elif fmt == "csv":
        w = csv.writer(sys.stdout)
        w.writerow([h for h, _ in vertical.columns])
        for r in leads:
            w.writerow([r.get(k, "") for _, k in vertical.columns])
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BrokenPipeError:
        # A downstream consumer (head/jq/an agent) closed the pipe early. Silence the
        # default flush-on-exit error and leave with the conventional SIGPIPE code.
        import os
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        raise SystemExit(141)
