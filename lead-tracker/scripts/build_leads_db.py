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
# Region config. Pick a region with `python build_leads_db.py <region>` or the
# REGION env var (default: sonoma). Add your own to REGIONS, or pass a custom
# box without editing this file:
#     REGION_NAME="North Bay" REGION_BBOX="38.0,-123.6,38.9,-122.3" python build_leads_db.py
# (bbox order is south,west,north,east -- grab numbers from https://bboxfinder.com)
# Counts scale roughly with area; see the table in lead-tracker/README.md.
# ---------------------------------------------------------------------------
REGIONS = {
    "sonoma":     ("Sonoma County",          {"south": 38.05, "west": -123.55, "north": 38.85, "east": -122.35}),
    # Counties bordering Sonoma (clockwise from north): build each into its own DB.
    "mendocino":  ("Mendocino County",       {"south": 38.75, "west": -123.95, "north": 40.00, "east": -122.82}),
    "lake":       ("Lake County",            {"south": 38.65, "west": -123.10, "north": 39.60, "east": -122.32}),
    "napa":       ("Napa County",            {"south": 38.15, "west": -122.65, "north": 38.87, "east": -122.06}),
    "solano":     ("Solano County",          {"south": 38.03, "west": -122.41, "north": 38.54, "east": -121.59}),
    "marin":      ("Marin County",           {"south": 37.80, "west": -122.92, "north": 38.32, "east": -122.43}),
    "bayarea":    ("Bay Area + Wine Country", {"south": 36.85, "west": -124.05, "north": 40.05, "east": -121.45}),
    "california": ("California",              {"south": 32.50, "west": -124.50, "north": 42.05, "east": -114.10}),
    "westcoast":  ("West Coast (CA/OR/WA)",  {"south": 32.50, "west": -124.90, "north": 49.05, "east": -114.00}),
    "us":         ("United States",          {"south": 24.40, "west": -125.00, "north": 49.50, "east": -66.90}),
}


def select_region():
    """Resolve the target region from CLI arg, REGION env, or custom bbox env."""
    if os.environ.get("REGION_BBOX"):
        s, w, n, e = (float(x) for x in os.environ["REGION_BBOX"].split(","))
        return (os.environ.get("REGION_NAME", "Custom region"),
                {"south": s, "west": w, "north": n, "east": e})
    key = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("REGION", "sonoma")).lower()
    if key not in REGIONS:
        sys.exit(f"Unknown region '{key}'. Choices: {', '.join(REGIONS)} "
                 f"(or set REGION_BBOX='south,west,north,east').")
    return REGIONS[key]


REGION_NAME, BBOX = select_region()

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
# Output DB defaults to data/leads.sqlite, but set LEADS_DB to build a region
# into its own file (e.g. LEADS_DB=data/napa.sqlite) without touching others.
DB_PATH = os.environ.get("LEADS_DB", os.path.join(DATA_DIR, "leads.sqlite"))
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

# 2) Flatten + tag chains, compute tier into a clean DuckDB table. Materializing
#    to a table (instead of fetching into Python) keeps memory flat for big
#    regions like California (~1.2M leads) -- we stream it into SQLite below.
print("Cleaning, de-chaining, and tiering...")
weak_sql = " OR ".join(f"lower(website) LIKE '%{w}%'" for w in WEAK_DOMAINS)
nonbiz_sql = ", ".join(f"'{c}'" for c in NON_BUSINESS_CATEGORIES)
con.execute("DROP TABLE IF EXISTS leads_clean")
con.execute(f"""
CREATE TABLE leads_clean AS
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
""")
cols = [d[0] for d in con.execute("SELECT * FROM leads_clean LIMIT 0").description]
n_clean = con.execute("SELECT COUNT(*) FROM leads_clean").fetchone()[0]
n_a_clean = con.execute("SELECT COUNT(*) FROM leads_clean WHERE tier='A'").fetchone()[0]
print(f"  -> {n_clean:,} clean leads (Tier A: {n_a_clean:,})")

# 3) Write the flat CSV straight from DuckDB (no Python-side buffering).
con.execute(f"COPY leads_clean TO '{CSV_PATH}' (HEADER, DELIMITER ',')")
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
# Live website-audit results (filled by scripts/audit_websites.py, run locally).
# Preserved across rebuilds, like crm.
db.execute("""
CREATE TABLE IF NOT EXISTS audit (
  lead_id      TEXT PRIMARY KEY,
  http_status  INTEGER, https INTEGER, mobile INTEGER, load_ms INTEGER,
  builder_live TEXT, title TEXT, audit_grade TEXT, error TEXT, checked_at TEXT
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
insert_sql = f"INSERT OR REPLACE INTO leads ({', '.join(cols)}) VALUES ({placeholders})"
cur = con.execute("SELECT * FROM leads_clean")
inserted = 0
db.execute("BEGIN")
while True:
    batch = cur.fetchmany(50000)
    if not batch:
        break
    db.executemany(insert_sql, batch)
    inserted += len(batch)
    print(f"    inserted {inserted:,}/{n_clean:,}", end="\r", flush=True)
db.commit()
print(f"    inserted {inserted:,} rows" + " " * 24)

# Indexes for the filters the app exposes.
for col in ("city", "category", "tier"):
    db.execute(f"CREATE INDEX IF NOT EXISTS idx_leads_{col} ON leads({col})")

# Full-text search over the fields a user would type into the search box.
db.execute("DROP TABLE IF EXISTS leads_fts")
db.execute("CREATE VIRTUAL TABLE leads_fts USING fts5("
           "name, category, city, address, content='leads', content_rowid='rowid')")
db.execute("INSERT INTO leads_fts(rowid, name, category, city, address) "
           "SELECT rowid, name, category, city, address FROM leads")

# Drop any crm/audit rows whose lead no longer exists after a refresh.
db.execute("DELETE FROM crm WHERE lead_id NOT IN (SELECT id FROM leads)")
db.execute("DELETE FROM audit WHERE lead_id NOT IN (SELECT id FROM leads)")
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

# Offline enrichment: re-tier (A/B/C incl. DIY builders), score, format phones,
# build pitches, etc. Runs automatically so a fresh build is fully enriched.
print("\nEnriching (offline: tiers, scores, pitches, normalized contacts)...")
try:
    import enrich_leads
    enrich_leads.DB_PATH = DB_PATH
    enrich_leads.main()
except Exception as e:
    print(f"  (enrichment step skipped: {type(e).__name__}: {e})")
    print("  Run it manually with:  python scripts/enrich_leads.py")
