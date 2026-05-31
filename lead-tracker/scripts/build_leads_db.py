"""
Build the lead-tracker SQLite database from Overture Maps Places.

Pulls a whole region (default: Bay Area + Wine Country) straight from the public
Overture S3 bucket, cleans it (drops chains/franchises and non-business POIs),
tiers each lead by how much it looks like it needs a website, and writes:

  lead-tracker/data/leads.sqlite   <- the DB the Next.js app reads
  lead-tracker/data/region_places.parquet  <- raw pull, every record in the bbox
  lead-tracker/data/region_leads.csv        <- flat cleaned leads, Excel-friendly

The SQLite file has two tables:
  leads  - rebuilt from scratch on every run (the dataset)
  crm    - your tracking state (status/notes/favorites). PRESERVED across rebuilds,
           so re-pulling fresh Overture data never wipes your progress.

Run:  python lead-tracker/scripts/build_leads_db.py
First run streams partitioned parquet from S3 and filters to the bbox (~1-3 min).
"""
import os, sys, time, sqlite3, subprocess

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def pip_install(*pkgs):
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet", *pkgs])


try:
    import duckdb
except ImportError:
    print("Installing duckdb...")
    pip_install("duckdb")
    import duckdb

# ---------------------------------------------------------------------------
# Region config. Swap the bbox to target a different area (draw a box at
# https://bboxfinder.com and paste the numbers). Counts scale roughly with area.
# ---------------------------------------------------------------------------
REGION_NAME = "Bay Area + Wine Country"
BBOX = {"south": 36.85, "west": -124.05, "north": 40.05, "east": -121.45}

FALLBACK_RELEASE = "2026-05-20.0"

# A name appearing at least this many times across the whole region is almost
# always a chain/franchise or a non-business POI, not a web-design lead.
CHAIN_NAME_THRESHOLD = 5

# Overture's "places" theme mixes in natural features and civic POIs nobody buys
# a website for. Dropped from the leads table (they stay in the raw parquet).
NON_BUSINESS_CATEGORIES = {
    "park", "beach", "river", "mountain", "mountain_peak", "hiking_trail", "trail",
    "lake", "forest", "island", "dam", "waterfall", "canyon", "valley", "cliff",
    "plateau", "natural_feature", "structure_and_geography", "body_of_water",
    "landmark_and_historical_building", "monument", "bridge", "cemetery",
    "post_office", "fire_station", "police_department",
}

# Domains that mean "no real owned site" -- a social/listing page. These bump a
# lead to Tier A even though a URL is present.
WEAK_DOMAINS = [
    "facebook.com", "instagram.com", "yelp.com", "linktr.ee", "linktree.com",
    "yellowpages.com", "business.site", "wixsite.com", "tiktok.com",
    "linkedin.com", "twitter.com", "nextdoor.com", "google.com/maps",
]

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.normpath(os.path.join(HERE, "..", "data"))
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "leads.sqlite")
PARQUET_PATH = os.path.join(DATA_DIR, "region_places.parquet")
CSV_PATH = os.path.join(DATA_DIR, "region_leads.csv")

# ---------------------------------------------------------------------------
# Connect DuckDB to Overture S3. Prefer the httpfs extension; fall back to
# fsspec/s3fs when the extension host is blocked (locked-down networks).
# ---------------------------------------------------------------------------
print("Connecting to DuckDB + Overture S3...")
con = duckdb.connect()
S3FS = None
try:
    con.execute("INSTALL httpfs; LOAD httpfs;")
    con.execute("SET s3_region='us-west-2';")
    print("  connection: DuckDB httpfs extension")
except Exception as e:
    print(f"  httpfs unavailable ({type(e).__name__}); falling back to fsspec/s3fs")
    try:
        import fsspec
    except ImportError:
        print("Installing s3fs...")
        pip_install("s3fs")
        import fsspec
    S3FS = fsspec.filesystem("s3", anon=True, client_kwargs={"region_name": "us-west-2"})
    con.register_filesystem(S3FS)
    print("  connection: fsspec/s3fs (anonymous)")


def detect_latest_release() -> str:
    try:
        if S3FS is not None:
            rels = [p.rstrip("/").split("/")[-1]
                    for p in S3FS.ls("overturemaps-us-west-2/release")]
            rels = [r for r in rels if r.startswith("202")]
            if rels:
                return sorted(rels)[-1]
        else:
            pat = ("s3://overturemaps-us-west-2/release/202[0-9]-*"
                   "/theme=places/type=place/part-00000-*")
            rows = con.execute(
                "SELECT DISTINCT regexp_extract(file, 'release/([^/]+)/', 1) AS rel "
                f"FROM glob('{pat}') WHERE rel <> '' ORDER BY rel DESC LIMIT 1"
            ).fetchall()
            if rows and rows[0][0]:
                return rows[0][0]
    except Exception as e:
        print(f"  (release auto-detect failed: {type(e).__name__}; using fallback)")
    return FALLBACK_RELEASE


RELEASE = detect_latest_release()
print(f"Using Overture release: {RELEASE}")
S3_URL = (f"s3://overturemaps-us-west-2/release/{RELEASE}"
          f"/theme=places/type=place/*")

bbox_where = (f"bbox.xmin BETWEEN {BBOX['west']} AND {BBOX['east']} "
              f"AND bbox.ymin BETWEEN {BBOX['south']} AND {BBOX['north']}")

# 1) Raw pull -> parquet (every record in the bbox, useful columns).
print(f"Pulling {REGION_NAME} from Overture (streaming partitioned parquet)...")
t0 = time.time()
con.execute(f"""
COPY (
  SELECT
    id,
    names.primary AS name,
    categories.primary AS category,
    categories.alternate AS category_alt,
    confidence,
    websites, socials, emails, phones,
    brand.names.primary AS brand,
    addresses[1].freeform AS address,
    addresses[1].locality AS city,
    addresses[1].region   AS state,
    addresses[1].postcode AS zip,
    addresses[1].country  AS country,
    bbox.xmin AS lon, bbox.ymin AS lat,
    sources[1].dataset   AS source_dataset,
    sources[1].record_id AS source_id
  FROM read_parquet('{S3_URL}', hive_partitioning=1)
  WHERE {bbox_where}
) TO '{PARQUET_PATH}' (FORMAT PARQUET);
""")
raw_n = con.execute(f"SELECT COUNT(*) FROM '{PARQUET_PATH}'").fetchone()[0]
print(f"  -> {PARQUET_PATH} ({raw_n:,} records, {round(time.time()-t0)}s)")

# 2) Flatten + tag chains, compute tier. Build a clean 'leads' result set.
print("Cleaning, de-chaining, and tiering...")
weak_sql = " OR ".join(f"lower(website) LIKE '%{w}%'" for w in WEAK_DOMAINS)
nonbiz_sql = ", ".join(f"'{c}'" for c in NON_BUSINESS_CATEGORIES)
rows = con.execute(f"""
WITH flat AS (
  SELECT
    id, name, category,
    array_to_string(category_alt, '|') AS alt_categories,
    confidence,
    CASE WHEN length(websites) > 0 THEN websites[1] END AS website,
    array_to_string(websites, '|') AS websites_all,
    CASE WHEN length(phones)   > 0 THEN phones[1]   END AS phone,
    array_to_string(phones, '|')   AS phones_all,
    CASE WHEN length(emails)   > 0 THEN emails[1]   END AS email,
    array_to_string(socials, '|')  AS socials,
    brand, address, city, state, zip, country, lon, lat,
    source_dataset, source_id
  FROM '{PARQUET_PATH}'
  WHERE name IS NOT NULL
),
name_counts AS (SELECT name, COUNT(*) AS n FROM flat GROUP BY name),
tagged AS (
  SELECT f.*,
    ((f.brand IS NOT NULL AND f.brand <> '') OR nc.n >= {CHAIN_NAME_THRESHOLD}) AS is_chain
  FROM flat f JOIN name_counts nc ON f.name = nc.name
)
SELECT
  id, name, category, alt_categories, confidence,
  website, websites_all, phone, phones_all, email, socials,
  brand, CAST(is_chain AS INTEGER) AS is_chain,
  address, city, state, zip, country, lon, lat, source_dataset, source_id,
  CASE
    WHEN website IS NULL OR website = '' THEN 'A'
    WHEN {weak_sql} THEN 'A'
    ELSE 'C'
  END AS tier,
  CASE
    WHEN website IS NULL OR website = '' THEN 'No website'
    WHEN {weak_sql} THEN 'Social/listing only - no owned site'
    ELSE 'Has a website - audit quality before pitching'
  END AS tier_reason
FROM tagged
WHERE NOT is_chain
  AND (category IS NULL OR category NOT IN ({nonbiz_sql}))
ORDER BY tier ASC, city ASC, name ASC
""").fetchall()
cols = [d[0] for d in con.description]
print(f"  -> {len(rows):,} clean leads "
      f"(Tier A: {sum(1 for r in rows if r[cols.index('tier')]=='A'):,})")

# 3) Write the flat CSV (cleaned leads).
import csv
with open(CSV_PATH, "w", newline="", encoding="utf-8") as fh:
    w = csv.writer(fh)
    w.writerow(cols)
    w.writerows(rows)
print(f"  -> {CSV_PATH}")

# 4) Build SQLite. Rebuild 'leads' + FTS; PRESERVE existing 'crm' tracking state.
print("Writing SQLite (leads rebuilt; crm tracking preserved)...")
db = sqlite3.connect(DB_PATH)
db.execute("PRAGMA journal_mode=WAL")
db.execute("""
CREATE TABLE IF NOT EXISTS crm (
  lead_id        TEXT PRIMARY KEY,
  status         TEXT NOT NULL DEFAULT 'New',
  notes          TEXT,
  last_contacted TEXT,
  favorite       INTEGER NOT NULL DEFAULT 0,
  updated_at     TEXT
)
""")
db.execute("DROP TABLE IF EXISTS leads")
db.execute(f"""
CREATE TABLE leads (
  id TEXT PRIMARY KEY,
  name TEXT, category TEXT, alt_categories TEXT, confidence REAL,
  website TEXT, websites_all TEXT, phone TEXT, phones_all TEXT, email TEXT, socials TEXT,
  brand TEXT, is_chain INTEGER,
  address TEXT, city TEXT, state TEXT, zip TEXT, country TEXT,
  lon REAL, lat REAL, source_dataset TEXT, source_id TEXT,
  tier TEXT, tier_reason TEXT
)
""")
placeholders = ", ".join("?" * len(cols))
db.executemany(f"INSERT OR REPLACE INTO leads ({', '.join(cols)}) VALUES ({placeholders})", rows)

# Indexes for the filters the app exposes.
for col in ("city", "category", "tier"):
    db.execute(f"CREATE INDEX IF NOT EXISTS idx_leads_{col} ON leads({col})")

# Full-text search over the fields a user would type into the search box.
db.execute("DROP TABLE IF EXISTS leads_fts")
db.execute("CREATE VIRTUAL TABLE leads_fts USING fts5("
           "name, category, city, address, content='leads', content_rowid='rowid')")
db.execute("INSERT INTO leads_fts(rowid, name, category, city, address) "
           "SELECT rowid, name, category, city, address FROM leads")

# Drop any crm rows whose lead no longer exists after a refresh.
db.execute("DELETE FROM crm WHERE lead_id NOT IN (SELECT id FROM leads)")
db.commit()

n_leads = db.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
n_a = db.execute("SELECT COUNT(*) FROM leads WHERE tier='A'").fetchone()[0]
n_phone = db.execute("SELECT COUNT(*) FROM leads WHERE phone IS NOT NULL AND phone<>''").fetchone()[0]
n_crm = db.execute("SELECT COUNT(*) FROM crm").fetchone()[0]
db.close()

print("\n=========================================")
print("  DONE")
print("=========================================")
print(f"  Region : {REGION_NAME}")
print(f"  Release: {RELEASE}")
print(f"  {DB_PATH}")
print(f"    leads : {n_leads:,}  (Tier A: {n_a:,}, with phone: {n_phone:,})")
print(f"    crm   : {n_crm:,} tracking rows preserved")
print(f"  {PARQUET_PATH}  ({raw_n:,} raw records)")
print(f"  {CSV_PATH}")
