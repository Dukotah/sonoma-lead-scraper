"""
Full data handoff export — EVERY lead, EVERY sector, CRM-ready.

Unlike make_call_sheet.py (which ranks/filters to warm leads), this dumps the
complete enriched dataset in clean, documented formats for importing into a CRM
or handing to another tool/model:

  data/export/sonoma_leads_full.csv    - all rows, all useful columns, UTF-8
  data/export/sonoma_leads_full.jsonl  - one JSON object per line (same data)
  data/export/DATA_DICTIONARY.md       - what every field means + value ranges
  data/export/niches.csv               - every niche with counts
  data/export/cities.csv               - every city with counts

Run:  python scripts/export_full.py
"""
import os, csv, json, sqlite3

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.normpath(os.path.join(HERE, "..", "data"))
OUT = os.path.join(DATA, "export")
DB_PATH = os.environ.get("LEADS_DB", os.path.join(DATA, "leads.sqlite"))

# Output columns in a sensible CRM order. (brand is always empty -> dropped.)
COLUMNS = [
    # identity
    "id", "name", "category", "alt_categories",
    # contact
    "phone", "phone_fmt", "area_code", "phones_all",
    "email", "email_owned",
    "website", "websites_all", "socials", "social_platforms", "best_contact",
    # location
    "address", "city", "state", "zip", "country", "lat", "lon",
    # classification / scoring
    "tier", "tier_reason", "builder",
    "industry_fit", "outreach_score", "score", "completeness", "confidence",
    "is_chain",
    # ready-to-use
    "pitch",
    # provenance
    "source_dataset", "source_id",
]

# Field documentation for the data dictionary.
DOCS = {
    "id": "Stable unique ID (from Overture Maps). Use as the CRM primary key.",
    "name": "Business name.",
    "category": "Primary niche/sector (Overture taxonomy, e.g. beauty_salon, restaurant).",
    "alt_categories": "Other categories that also apply, pipe-separated.",
    "phone": "Primary phone, raw.",
    "phone_fmt": "Primary phone, formatted (XXX) XXX-XXXX when it's a valid 10-digit US number.",
    "area_code": "3-digit area code of the primary phone.",
    "phones_all": "All listed phone numbers, pipe-separated.",
    "email": "Primary email (only ~41% of leads have one).",
    "email_owned": "1 if the email's domain matches the website domain (owned, not a gmail/yahoo).",
    "website": "Primary website URL (empty for ~17% = Tier A 'no site' leads).",
    "websites_all": "All listed website URLs, pipe-separated.",
    "socials": "All social profile URLs, pipe-separated.",
    "social_platforms": "Which platforms are present, pipe-separated (facebook|instagram|...).",
    "best_contact": "Suggested channel: phone | email | social | none.",
    "address": "Street address (freeform).",
    "city": "City.",
    "state": "State (CA).",
    "zip": "Postal code.",
    "country": "Country code.",
    "lat": "Latitude.",
    "lon": "Longitude.",
    "tier": "Website-need tier: A=no/social-only site, B=DIY builder site, C=real custom site.",
    "tier_reason": "Human-readable explanation of the tier.",
    "builder": "Detected DIY builder (Wix/Weebly/etc.) for Tier B; empty otherwise.",
    "industry_fit": "How likely the niche buys web design: high | medium | low.",
    "outreach_score": "0-100 cold-outreach priority (need + reachability + fit). Best ranking field for a call queue.",
    "score": "0-100 raw lead-priority (need + reachability + confidence), ignores industry fit.",
    "completeness": "0-100 how filled-in this record is.",
    "confidence": "Overture's 0-1 confidence that this place exists/is accurate.",
    "is_chain": "1 if flagged as a chain/franchise (these were mostly already excluded).",
    "pitch": "A personalized one-line cold-open, tailored to tier/niche/city.",
    "source_dataset": "Which Overture source this record came from.",
    "source_id": "Record ID within that source.",
}


def main():
    os.makedirs(OUT, exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    cols_sql = ", ".join(COLUMNS)
    rows = db.execute(
        f"SELECT {cols_sql} FROM leads "
        f"ORDER BY outreach_score DESC, category, name"
    ).fetchall()
    n = len(rows)

    # CSV
    csv_path = os.path.join(OUT, "sonoma_leads_full.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(COLUMNS)
        for r in rows:
            w.writerow([r[c] for c in COLUMNS])

    # JSONL
    jsonl_path = os.path.join(OUT, "sonoma_leads_full.jsonl")
    with open(jsonl_path, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps({c: r[c] for c in COLUMNS}, ensure_ascii=False) + "\n")

    # niches.csv
    niches = db.execute(
        "SELECT category, COUNT(*) n FROM leads WHERE category IS NOT NULL AND category<>'' "
        "GROUP BY category ORDER BY n DESC").fetchall()
    with open(os.path.join(OUT, "niches.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh); w.writerow(["niche", "count"])
        for x in niches:
            w.writerow([x["category"], x["n"]])

    # cities.csv
    cities = db.execute(
        "SELECT city, COUNT(*) n FROM leads WHERE city IS NOT NULL AND city<>'' "
        "GROUP BY city ORDER BY n DESC").fetchall()
    with open(os.path.join(OUT, "cities.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh); w.writerow(["city", "count"])
        for x in cities:
            w.writerow([x["city"], x["n"]])

    # fill rates for the dictionary
    def fill(col):
        c = db.execute(
            f"SELECT COUNT(*) FROM leads WHERE {col} IS NOT NULL AND {col}<>''").fetchone()[0]
        return round(100 * c / n)

    tiers = dict(db.execute("SELECT tier, COUNT(*) FROM leads GROUP BY tier").fetchall())
    fits = dict(db.execute("SELECT industry_fit, COUNT(*) FROM leads GROUP BY industry_fit").fetchall())

    # DATA_DICTIONARY.md
    md = []
    md.append("# Sonoma County Business Leads — Data Dictionary\n")
    md.append(f"**{n:,} businesses** across **{len(niches):,} niches** and "
              f"**{len(cities):,} cities** in Sonoma County, CA.\n")
    md.append("Source: [Overture Maps](https://overturemaps.org) (CC-BY 4.0), "
              "cleaned, de-chained, and enriched. No web scraping.\n")
    md.append("## Files\n")
    md.append("| File | What |")
    md.append("|---|---|")
    md.append("| `sonoma_leads_full.csv` | All leads, all columns (import this into the CRM). |")
    md.append("| `sonoma_leads_full.jsonl` | Same data, one JSON object per line. |")
    md.append("| `niches.csv` | Every niche with its count. |")
    md.append("| `cities.csv` | Every city with its count. |")
    md.append("| `DATA_DICTIONARY.md` | This file. |\n")
    md.append("## Suggested CRM schema\n")
    md.append("`id` is a stable unique key — use it as the primary key so re-imports "
              "upsert cleanly. All fields are text unless noted.\n")
    md.append("| Column | Fill % | Description |")
    md.append("|---|---|---|")
    for c in COLUMNS:
        md.append(f"| `{c}` | {fill(c)}% | {DOCS.get(c, '')} |")
    md.append("\n## Key value distributions\n")
    md.append("**tier** (website need):")
    md.append(f"- A (no real website — hottest): {tiers.get('A',0):,}")
    md.append(f"- B (DIY builder site — upsell): {tiers.get('B',0):,}")
    md.append(f"- C (has a real website): {tiers.get('C',0):,}\n")
    md.append("**industry_fit** (likelihood the niche buys web design):")
    md.append(f"- high: {fits.get('high',0):,}  ·  medium: {fits.get('medium',0):,}  ·  low: {fits.get('low',0):,}\n")
    md.append("**Ranking tip:** sort by `outreach_score` (desc) for a cold-call queue. "
              "`tier='A'` + `industry_fit='high'` + a phone = your warmest segment.\n")
    md.append("## Top 25 niches\n")
    md.append("| Niche | Count |")
    md.append("|---|---|")
    for x in niches[:25]:
        md.append(f"| {x['category']} | {x['n']:,} |")
    with open(os.path.join(OUT, "DATA_DICTIONARY.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")

    db.close()
    print(f"Exported {n:,} leads (all sectors) to {OUT}/")
    for f in ("sonoma_leads_full.csv", "sonoma_leads_full.jsonl",
              "niches.csv", "cities.csv", "DATA_DICTIONARY.md"):
        p = os.path.join(OUT, f)
        print(f"  {f:28} {os.path.getsize(p):>10,} bytes")


if __name__ == "__main__":
    main()
