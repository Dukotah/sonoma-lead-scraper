"""
Scrape the whole multi-county lead dataset, end to end, in one command.

This is the workflow that produces the committed deliverables under
`data/export/`: the per-county folders AND the combined `ALL_COUNTIES_*`
files + `REGION_SUMMARY.md` — ~71k businesses across Sonoma and its five
bordering counties, pulled live from Overture Maps.

It runs entirely from the data side (no web scraping of individual sites), so
it works inside a restricted agent sandbox: the only network it touches is the
public Overture S3 bucket, read via DuckDB's anonymous fsspec/s3fs fallback when
the httpfs extension host is blocked (see build_leads_db.py). See
`docs/SANDBOX.md` for the capability map.

For each county it runs the existing three-step pipeline into a private SQLite
DB, then relocates the outputs into `data/export/<county>/`:
    build_leads_db.py   pull Overture -> clean/de-chain/tier -> enrich
    make_call_sheet.py  add outreach_score/industry_fit -> warm CSV + xlsx
    export_full.py      full CSV + JSONL + niches/cities + data dictionary
Finally it assembles:
    ALL_COUNTIES_leads_full.csv   every county's rows + a `county` column
    ALL_COUNTIES_dedup.csv        each business once (counties' bboxes overlap)
    REGION_SUMMARY.md             the counts table

Run (all counties, into the tracked export dir):
    python lead-tracker/scripts/build_all_counties.py
A subset / scratch location (e.g. to validate without touching committed data):
    python lead-tracker/scripts/build_all_counties.py --counties lake mendocino \
        --export-root /tmp/export_check
"""
import argparse
import csv
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.normpath(os.path.join(HERE, "..", "data"))
DEFAULT_EXPORT = os.path.join(DATA, "export")

# The six counties this dataset covers. Each key must exist in build_leads_db's
# REGIONS table (that script owns the bboxes); here we only need the human label
# for the export folder + summary. The county key is passed through as REGION.
COUNTY_LABELS = {
    "sonoma": "Sonoma County", "napa": "Napa County", "marin": "Marin County",
    "mendocino": "Mendocino County", "lake": "Lake County", "solano": "Solano County",
}

# Order the per-county rows are concatenated into ALL_COUNTIES_leads_full.csv
# (the order the counties were originally added).
FULL_ORDER = ["sonoma", "napa", "marin", "mendocino", "lake", "solano"]
# Dedup processing order: a business in two counties' boxes is attributed to the
# FIRST county here that contains it. Sonoma is kept in full, then the rest only
# keep ids not already seen — matching REGION_SUMMARY's unique-per-county counts.
DEDUP_ORDER = ["sonoma", "napa", "marin", "solano", "mendocino", "lake"]


def run(script, env_extra, label):
    """Run a pipeline script in a clean subprocess with the given env overlay."""
    env = dict(os.environ, **env_extra)
    t0 = time.time()
    r = subprocess.run([sys.executable, os.path.join(HERE, script)],
                       env=env, cwd=os.path.join(HERE, ".."))
    if r.returncode != 0:
        sys.exit(f"  !! {label} failed (exit {r.returncode})")
    print(f"  {label} done ({round(time.time() - t0)}s)")


def build_county(county, export_root):
    name = COUNTY_LABELS[county]
    out_dir = os.path.join(export_root, county)
    os.makedirs(out_dir, exist_ok=True)
    db_path = os.path.join(DATA, f"{county}.sqlite")  # gitignored scratch DB
    print(f"\n=== {name} ({county}) ===")

    # 1) pull + clean + tier + enrich (build_leads_db auto-runs enrich_leads)
    run("build_leads_db.py", {"REGION": county, "LEADS_DB": db_path},
        "build_leads_db")
    # 2) outreach scoring + warm CSV + call-sheet xlsx, straight into the folder
    run("make_call_sheet.py",
        {"LEADS_DB": db_path, "CALL_SHEET_DIR": out_dir, "CALL_SHEET_PREFIX": county},
        "make_call_sheet")
    # 3) full export (CSV/JSONL/niches/cities/dictionary) into the folder
    run("export_full.py",
        {"LEADS_DB": db_path, "EXPORT_DIR": out_dir, "EXPORT_PREFIX": county,
         "REGION_LABEL": name},
        "export_full")

    full_csv = os.path.join(out_dir, f"{county}_leads_full.csv")
    with open(full_csv, newline="", encoding="utf-8") as fh:
        n = sum(1 for _ in fh) - 1
    print(f"  -> {full_csv} ({n:,} leads)")
    return full_csv


def assemble_combined(counties, export_root):
    """Concatenate per-county full CSVs into ALL_COUNTIES_* + REGION_SUMMARY."""
    # Read every county's full file once, keyed by county.
    by_county = {}
    header = None
    for county in counties:
        path = os.path.join(export_root, county, f"{county}_leads_full.csv")
        with open(path, newline="", encoding="utf-8") as fh:
            rows = list(csv.reader(fh))
        header = header or rows[0]
        by_county[county] = rows[1:]

    out_header = ["county"] + header

    # ALL_COUNTIES_leads_full.csv — every row, county prepended.
    full_path = os.path.join(export_root, "ALL_COUNTIES_leads_full.csv")
    total = 0
    with open(full_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(out_header)
        for county in [c for c in FULL_ORDER if c in by_county]:
            for row in by_county[county]:
                w.writerow([county] + row)
                total += 1

    # ALL_COUNTIES_dedup.csv — keep each id once, in DEDUP_ORDER.
    id_idx = header.index("id")
    tier_idx = header.index("tier")
    seen = set()
    dedup_path = os.path.join(export_root, "ALL_COUNTIES_dedup.csv")
    per_county_stats = {}  # county -> [unique, tierA, with_phone]
    phone_idx = header.index("phone")
    uniq_total = 0
    with open(dedup_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(out_header)
        for county in [c for c in DEDUP_ORDER if c in by_county]:
            u = a = p = 0
            for row in by_county[county]:
                lead_id = row[id_idx]
                if lead_id in seen:
                    continue
                seen.add(lead_id)
                w.writerow([county] + row)
                u += 1
                uniq_total += 1
                if row[tier_idx] == "A":
                    a += 1
                if row[phone_idx].strip():
                    p += 1
            per_county_stats[county] = [u, a, p]

    # full-file per-county stats for the summary table
    full_stats = {}
    for county in by_county:
        a = sum(1 for r in by_county[county] if r[tier_idx] == "A")
        p = sum(1 for r in by_county[county] if r[phone_idx].strip())
        full_stats[county] = [len(by_county[county]), a, p]

    write_summary(export_root, counties, full_stats, per_county_stats,
                  total, uniq_total)
    return total, uniq_total


def write_summary(export_root, counties, full_stats, dedup_stats, total, uniq_total):
    L = []
    L.append("# Sonoma + Bordering Counties — Lead Dataset Summary\n")
    L.append(f"**{total:,} businesses total** across Sonoma County and its five "
             "bordering counties.\n")
    L.append("All built from Overture Maps (CC-BY 4.0), cleaned, de-chained, "
             "enriched, and scored — same pipeline and columns as the Sonoma set. "
             "Regenerate with `python lead-tracker/scripts/build_all_counties.py`.\n")
    L.append("| County | Businesses | Tier A (no website) | With phone |")
    L.append("|---|---|---|---|")
    for c in [c for c in FULL_ORDER if c in full_stats]:
        n, a, p = full_stats[c]
        L.append(f"| {COUNTY_LABELS[c].replace(' County','')} | {n:,} | {a:,} | {p:,} |")
    L.append(f"| **TOTAL** | **{total:,}** | | |\n")
    L.append("## Files\n")
    L.append("- `ALL_COUNTIES_leads_full.csv` — every business from all six "
             "counties in one file, with a `county` column. Import this for the "
             "combined CRM.")
    L.append("- `<county>/` — per-county folder: full CSV + JSONL, call sheet "
             "(xlsx), warm-leads CSV, niches/cities, and a data dictionary.")
    L.append("- Field meanings are identical across all counties — see any "
             "county's `DATA_DICTIONARY.md`.\n")
    L.append("**Primary key:** `id` is globally unique (Overture IDs), so the "
             "combined file upserts cleanly.\n")
    L.append("## Deduplicated combined file (recommended)\n")
    L.append("County bounding boxes are rectangles around irregular county lines, "
             "so they overlap — a business near a border can appear in two "
             "counties' raw pulls. `ALL_COUNTIES_leads_full.csv` keeps every row "
             f"(with duplicates); **`ALL_COUNTIES_dedup.csv` keeps each business "
             f"once** ({uniq_total:,} unique), assigning border businesses to "
             "their primary county (Sonoma is preserved in full).\n")
    L.append("| County | Unique businesses | Tier A | With phone |")
    L.append("|---|---|---|---|")
    da = dp = 0
    for c in [c for c in DEDUP_ORDER if c in dedup_stats]:
        n, a, p = dedup_stats[c]
        da += a
        dp += p
        L.append(f"| {COUNTY_LABELS[c].replace(' County','')} | {n:,} | {a:,} | {p:,} |")
    L.append(f"| **TOTAL** | **{uniq_total:,}** | **{da:,}** | **{dp:,}** |")
    with open(os.path.join(export_root, "REGION_SUMMARY.md"), "w",
              encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")


def main():
    ap = argparse.ArgumentParser(description="Scrape the full multi-county dataset.")
    ap.add_argument("--counties", nargs="+", default=FULL_ORDER,
                    help=f"counties to build (default: all). Choices: {', '.join(COUNTY_LABELS)}")
    ap.add_argument("--export-root", default=DEFAULT_EXPORT,
                    help="where to write per-county folders + ALL_COUNTIES_* "
                         "(default: the tracked data/export/).")
    ap.add_argument("--no-combine", action="store_true",
                    help="build the per-county folders but skip ALL_COUNTIES_* assembly.")
    args = ap.parse_args()

    bad = [c for c in args.counties if c not in COUNTY_LABELS]
    if bad:
        sys.exit(f"Unknown county/counties: {', '.join(bad)}. Choices: {', '.join(COUNTY_LABELS)}")

    t0 = time.time()
    print(f"Scraping {len(args.counties)} counties -> {args.export_root}")
    for county in args.counties:
        build_county(county, args.export_root)

    if not args.no_combine:
        print("\n=== Assembling combined files ===")
        total, uniq = assemble_combined(args.counties, args.export_root)
        print(f"  ALL_COUNTIES_leads_full.csv : {total:,} rows")
        print(f"  ALL_COUNTIES_dedup.csv      : {uniq:,} unique")
        print("  REGION_SUMMARY.md")

    print(f"\nDone in {round(time.time() - t0)}s -> {args.export_root}")


if __name__ == "__main__":
    main()
