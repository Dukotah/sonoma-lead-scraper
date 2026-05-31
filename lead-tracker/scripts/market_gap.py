"""
Market-gap analysis — purely offline. Answers "where is the opportunity densest?"
by crossing niche x city and counting website-less / warm businesses, so outreach
can be aimed at the segments with the most prospects.

Reads the committed per-county full CSVs (no DB needed) and writes:
  data/export/analysis/market_gap_by_niche.csv  - per niche: totals, no-site %, warm count, avg score
  data/export/analysis/market_gap_by_city.csv   - per city: same
  data/export/analysis/opportunity_matrix.csv   - niche x city: no-website counts (the hot cells)
  data/export/analysis/MARKET_GAP.md            - readable top-opportunities summary

Run:  python scripts/market_gap.py
"""
import os, csv, glob
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.normpath(os.path.join(HERE, "..", "data"))
EXPORT = os.path.join(DATA, "export")
OUT = os.path.join(EXPORT, "analysis")


def load_rows():
    """All leads across every per-county full CSV, deduped by id."""
    seen = {}
    for path in sorted(glob.glob(os.path.join(EXPORT, "*", "*_leads_full.csv"))):
        with open(path, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                seen[r["id"]] = r  # later wins; fine, fields are identical
    return list(seen.values())


def num(v, d=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def is_no_site(r):
    return (r.get("tier") or "").upper() == "A"


def is_warm(r):
    # callable + a real need + a niche that buys
    return (r.get("phone") or "").strip() and (r.get("tier") or "").upper() in ("A", "B") \
        and (r.get("industry_fit") or "") in ("high", "medium")


def main():
    os.makedirs(OUT, exist_ok=True)
    rows = load_rows()
    n = len(rows)

    by_niche = defaultdict(lambda: {"n": 0, "nosite": 0, "warm": 0, "score": 0.0, "phone": 0})
    by_city = defaultdict(lambda: {"n": 0, "nosite": 0, "warm": 0, "score": 0.0, "phone": 0})
    matrix = defaultdict(int)  # (niche, city) -> no-site count

    for r in rows:
        niche = (r.get("category") or "(uncategorized)").strip() or "(uncategorized)"
        city = (r.get("city") or "(unknown)").strip() or "(unknown)"
        sc = num(r.get("outreach_score"))
        for agg, key in ((by_niche, niche), (by_city, city)):
            a = agg[key]
            a["n"] += 1
            a["score"] += sc
            if is_no_site(r):
                a["nosite"] += 1
            if is_warm(r):
                a["warm"] += 1
            if (r.get("phone") or "").strip():
                a["phone"] += 1
        if is_no_site(r):
            matrix[(niche, city)] += 1

    def write_agg(path, agg, label):
        rowsout = []
        for k, a in agg.items():
            rowsout.append((k, a["n"], a["nosite"],
                            round(100 * a["nosite"] / a["n"], 1) if a["n"] else 0,
                            a["warm"], a["phone"],
                            round(a["score"] / a["n"], 1) if a["n"] else 0))
        rowsout.sort(key=lambda x: -x[4])  # by warm count desc
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow([label, "total", "no_website", "no_website_pct",
                        "warm_leads", "with_phone", "avg_outreach_score"])
            w.writerows(rowsout)
        return rowsout

    niche_rows = write_agg(os.path.join(OUT, "market_gap_by_niche.csv"), by_niche, "niche")
    city_rows = write_agg(os.path.join(OUT, "market_gap_by_city.csv"), by_city, "city")

    # opportunity matrix: top no-site cells
    cells = sorted(matrix.items(), key=lambda kv: -kv[1])
    with open(os.path.join(OUT, "opportunity_matrix.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["niche", "city", "businesses_with_no_website"])
        for (niche, city), c in cells:
            if c >= 2:  # skip singletons to keep it actionable
                w.writerow([niche, city, c])

    # readable summary
    md = [f"# Market-Gap Analysis — Sonoma + Bordering Counties\n",
          f"Crossing **{n:,} businesses** by niche and city to show where website-less "
          f"and warm prospects cluster. Offline analysis of the committed datasets.\n",
          "## Top 25 niches by warm-lead count\n",
          "| Niche | Warm leads | No website | No-site % | Avg score |",
          "|---|---|---|---|---|"]
    for k, tot, nosite, pct, warm, phone, avg in niche_rows[:25]:
        md.append(f"| {k} | {warm:,} | {nosite:,} | {pct}% | {avg} |")
    md.append("\n## Top 20 cities by warm-lead count\n")
    md.append("| City | Warm leads | No website | Total businesses |")
    md.append("|---|---|---|---|")
    for k, tot, nosite, pct, warm, phone, avg in city_rows[:20]:
        md.append(f"| {k} | {warm:,} | {nosite:,} | {tot:,} |")
    md.append("\n## 30 hottest niche×city cells (most no-website businesses in one place)\n")
    md.append("These are the densest pockets — pick a cell and you can call a dozen "
              "same-niche, same-town prospects in a row.\n")
    md.append("| Niche | City | No-website businesses |")
    md.append("|---|---|---|")
    for (niche, city), c in cells[:30]:
        md.append(f"| {niche} | {city} | {c} |")
    with open(os.path.join(OUT, "MARKET_GAP.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")

    print(f"Market-gap analysis over {n:,} businesses -> {OUT}/")
    print(f"  niches: {len(by_niche):,} | cities: {len(by_city):,} | "
          f"hot cells (>=2 no-site): {sum(1 for _,c in cells if c>=2):,}")
    print("  top niche by warm leads:", niche_rows[0][0], f"({niche_rows[0][4]:,} warm)")
    print("  hottest cell:", cells[0][0][0], "in", cells[0][0][1], f"({cells[0][1]} no-site)")


if __name__ == "__main__":
    main()
