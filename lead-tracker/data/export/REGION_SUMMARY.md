# Sonoma + Bordering Counties — Lead Dataset Summary

**71,102 businesses total** across Sonoma County and its five bordering counties.

All built from Overture Maps (CC-BY 4.0), cleaned, de-chained, enriched, and scored — same pipeline and columns as the Sonoma set.

| County | Businesses | Tier A (no website) | With phone |
|---|---|---|---|
| Sonoma | 21,662 | 3,838 | 20,401 |
| Napa | 11,343 | 2,031 | 10,568 |
| Marin | 14,868 | 2,203 | 14,069 |
| Mendocino | 4,779 | 1,210 | 4,485 |
| Lake | 2,737 | 749 | 2,543 |
| Solano | 15,713 | 3,357 | 14,660 |
| **TOTAL** | **71,102** | | |

## Files

- `ALL_COUNTIES_leads_full.csv` — every business from all six counties in one file, with a `county` column. Import this for the combined CRM.
- `<county>/` — per-county folder: full CSV + JSONL, call sheet (xlsx), warm-leads CSV, niches/cities, and a data dictionary.
- Field meanings are identical across all counties — see any county's `DATA_DICTIONARY.md`.

**Primary key:** `id` is globally unique (Overture IDs), so the combined file upserts cleanly.

## Deduplicated combined file (recommended)

County bounding boxes are rectangles around irregular county lines, so they overlap — a business near a border can appear in two counties' raw pulls. `ALL_COUNTIES_leads_full.csv` keeps every row (with duplicates); **`ALL_COUNTIES_dedup.csv` keeps each business once** (51,271 unique), assigning border businesses to their primary county (Sonoma is preserved in full).

| County | Unique businesses | Tier A | With phone |
|---|---|---|---|
| Sonoma | 21,662 | 3,838 | 20,401 |
| Napa | 5,607 | 994 | 5,243 |
| Marin | 8,660 | 1,212 | 8,177 |
| Solano | 10,084 | 2,335 | 9,427 |
| Mendocino | 4,416 | 1,122 | 4,146 |
| Lake | 842 | 237 | 777 |
| **TOTAL** | **51,271** | **9,738** | **48,171** |
