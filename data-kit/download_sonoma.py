"""
Downloads Overture Maps Places data for Sonoma County, CA.
Outputs three files:
  - sonoma_places.parquet  (raw Overture data, ~50 columns, all types)
  - sonoma_places.csv      (same data, flattened, Excel-friendly)
  - sonoma_businesses.xlsx (Excel summary with key columns)

Run:  python download_sonoma.py
First run takes 2-5 minutes (downloads ~10-30 MB of partitioned parquet from S3).
"""
import sys, subprocess

def pip_install(*pkgs):
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet", *pkgs])

try:
    import duckdb
except ImportError:
    print("Installing duckdb...")
    pip_install("duckdb")
    import duckdb

try:
    import openpyxl  # noqa
except ImportError:
    print("Installing openpyxl...")
    pip_install("openpyxl")

import json

# Sonoma County bounding box
BBOX = {"south": 38.05, "west": -123.55, "north": 38.85, "east": -122.35}

# Latest Overture release as of mid-2026 — bump this string when you want fresher data.
# See: https://docs.overturemaps.org/release/latest/
RELEASE = "2025-04-23.0"  # change to newest release if older when you run this

print("Connecting to DuckDB + Overture S3...")
con = duckdb.connect()
con.execute("INSTALL httpfs; LOAD httpfs;")
con.execute("INSTALL spatial; LOAD spatial;")
con.execute("SET s3_region='us-west-2';")

S3_URL = (
    f"s3://overturemaps-us-west-2/release/{RELEASE}"
    f"/theme=places/type=place/*"
)

print(f"Querying Overture release {RELEASE} for Sonoma County...")
print("(2-5 min: streaming partitioned parquet from S3)")

# Pull a clean set of useful columns
query = f"""
COPY (
  SELECT
    id,
    names.primary AS name,
    categories.primary AS category_primary,
    categories.alternate AS category_alt,
    confidence,
    websites,
    socials,
    emails,
    phones,
    brand.names.primary AS brand,
    addresses[1].freeform AS address_line,
    addresses[1].locality AS city,
    addresses[1].region   AS state,
    addresses[1].postcode AS zip,
    addresses[1].country  AS country,
    bbox.xmin AS lon,
    bbox.ymin AS lat,
    sources[1].dataset AS source_dataset,
    sources[1].record_id AS source_id
  FROM read_parquet('{S3_URL}', hive_partitioning=1)
  WHERE bbox.xmin BETWEEN {BBOX["west"]} AND {BBOX["east"]}
    AND bbox.ymin BETWEEN {BBOX["south"]} AND {BBOX["north"]}
) TO 'sonoma_places.parquet' (FORMAT PARQUET);
"""
con.execute(query)
n = con.execute("SELECT COUNT(*) FROM 'sonoma_places.parquet'").fetchone()[0]
print(f"  → wrote sonoma_places.parquet ({n:,} records)")

# Flatten arrays for CSV/xlsx readability
print("Flattening for CSV/xlsx...")
con.execute("""
CREATE TABLE flat AS
SELECT
  id, name, category_primary,
  array_to_string(category_alt, '|') AS category_alt,
  confidence,
  CASE WHEN length(websites) > 0 THEN websites[1] ELSE NULL END AS website,
  array_to_string(websites, '|') AS websites_all,
  CASE WHEN length(phones) > 0 THEN phones[1] ELSE NULL END AS phone,
  array_to_string(phones, '|') AS phones_all,
  CASE WHEN length(emails) > 0 THEN emails[1] ELSE NULL END AS email,
  array_to_string(socials, '|') AS socials,
  brand, address_line, city, state, zip, country, lon, lat,
  source_dataset, source_id
FROM 'sonoma_places.parquet'
""")
con.execute("COPY flat TO 'sonoma_places.csv' (HEADER, DELIMITER ',')")
print(f"  → wrote sonoma_places.csv")

# Excel summary — businesses with a name, prioritizing those without websites
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

print("Building Excel summary...")
rows = con.execute("""
SELECT
  CASE WHEN website IS NULL OR website = '' THEN 'A' ELSE 'C' END AS tier,
  name, category_primary, city, phone, website, address_line,
  lon, lat, source_dataset, id
FROM flat
WHERE name IS NOT NULL
ORDER BY tier ASC, name ASC
""").fetchall()

wb = openpyxl.Workbook()
ws = wb.active
ws.title = "Sonoma Businesses"
headers = ["Tier", "Business", "Category", "City", "Phone", "Website",
           "Address", "Lon", "Lat", "Source", "Overture ID"]
for i, h in enumerate(headers, 1):
    c = ws.cell(row=1, column=i, value=h)
    c.font = Font(name="Arial", bold=True, color="FFFFFF", size=11)
    c.fill = PatternFill("solid", start_color="1F4E78")
    c.alignment = Alignment(horizontal="center")
widths = [6, 30, 26, 16, 16, 36, 40, 12, 12, 14, 28]
for i, w in enumerate(widths, 1):
    ws.column_dimensions[get_column_letter(i)].width = w

TIER_A = PatternFill("solid", start_color="C6EFCE")
for r in rows:
    ws.append(r)
    if r[0] == "A":
        ws.cell(row=ws.max_row, column=1).fill = TIER_A
        ws.cell(row=ws.max_row, column=1).font = Font(name="Arial", bold=True)

ws.freeze_panes = "A2"
ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{len(rows)+1}"
wb.save("sonoma_businesses.xlsx")
print(f"  → wrote sonoma_businesses.xlsx ({len(rows):,} named businesses)")

print("\n=========================================")
print("  DONE")
print("=========================================")
print(f"Files written to current folder:")
print(f"  sonoma_places.parquet  - raw Overture data ({n:,} records)")
print(f"  sonoma_places.csv      - flattened CSV")
print(f"  sonoma_businesses.xlsx - Excel summary ({len(rows):,} named)")
