"""
CLI for the universal lead engine.

    python -m leadgen --list
    python -m leadgen --vertical simply_tc --market sonoma_county_ca --out sonoma_tc
    python -m leadgen --vertical simply_tc --market "Austin, Texas" --sources overture osm
    python -m leadgen --vertical web_design --market sonoma_county_ca --no-enrich --limit 200
    python -m leadgen --vertical web_design --market sonoma_county_ca --no-enrich --json   # agent: structured stdout
    python -m leadgen --vertical web_design --demo --json                                  # fully offline sample
"""
from __future__ import annotations

import argparse
import json
import sys

from . import get_vertical, all_verticals, run_pipeline


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
    ap.add_argument("--demo", action="store_true",
                    help="run fully offline on bundled sample data (no network) — for testing / agents")
    ap.add_argument("--json", action="store_true",
                    help="emit scored leads as a JSON array on stdout (progress logs go to stderr)")
    ap.add_argument("--out", help="output filename stem (writes <stem>_crm.csv + <stem>.xlsx)")
    args = ap.parse_args(argv)

    if args.list:
        for k, v in sorted(all_verticals().items()):
            print(f"  {k:14s} {v.label}")
        return 0

    if not args.vertical or (not args.market and not args.demo):
        ap.error("--vertical and --market are required (or use --list, or --demo)")

    try:
        vertical = get_vertical(args.vertical)
    except KeyError as e:
        print(e, file=sys.stderr)
        return 2

    # With --json, stdout is reserved for the JSON payload, so progress goes to stderr.
    log = (lambda *a, **k: print(*a, file=sys.stderr)) if args.json else print
    # A bare --json run is for an agent that just wants the data on stdout — don't
    # write CSV/XLSX unless an explicit --out was given.
    out_stem = args.out
    if not out_stem and not args.json:
        out_stem = f"{args.vertical}_{args.market or 'demo'}"

    leads = run_pipeline(
        vertical, args.market or "demo",
        sources=tuple(args.sources), limit=args.limit,
        enrich=not args.no_enrich, enrich_cap=args.enrich_cap,
        out_stem=out_stem, demo=args.demo,
        overture_categories=args.category, log=log,
    )

    if args.json:
        json.dump(leads, sys.stdout, ensure_ascii=False, indent=2, default=str)
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
