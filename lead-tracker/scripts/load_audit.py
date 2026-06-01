"""
Load website-audit results (CSVs produced by scripts/audit_ci.py on GitHub
Actions and committed under data/export/audit/) into the SQLite `audit` table
that the CRM reads. Run after pulling fresh CI audit results:

    python scripts/load_audit.py            # load every data/export/audit/*.csv
    python scripts/load_audit.py sonoma     # just one county

Upserts by lead_id, so re-running is safe and newer rows replace older ones.
"""
import os, csv, sys, glob, sqlite3

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.normpath(os.path.join(HERE, "..", "data"))
DB = os.environ.get("LEADS_DB", os.path.join(DATA, "leads.sqlite"))
AUDIT_DIR = os.path.join(DATA, "export", "audit")

COLS = ["http_status", "https", "mobile", "load_ms",
        "builder_live", "title", "audit_grade", "error", "checked_at"]
INTS = {"http_status", "https", "mobile", "load_ms"}


def coerce(col, val):
    val = (val or "").strip()
    if val == "":
        return None
    if col in INTS:
        try:
            return int(float(val))
        except ValueError:
            return None
    return val


def main():
    if not os.path.exists(DB):
        sys.exit(f"no DB at {DB} — build it first (npm run build-db).")
    which = sys.argv[1] if len(sys.argv) > 1 else "*"
    paths = sorted(glob.glob(os.path.join(AUDIT_DIR, f"{which}_audit.csv")))
    if not paths:
        sys.exit(f"no audit CSVs matching {which}_audit.csv in {AUDIT_DIR}")

    con = sqlite3.connect(DB)
    con.execute("""CREATE TABLE IF NOT EXISTS audit (
        lead_id TEXT PRIMARY KEY, http_status INTEGER, https INTEGER, mobile INTEGER,
        load_ms INTEGER, builder_live TEXT, title TEXT, audit_grade TEXT,
        error TEXT, checked_at TEXT)""")
    valid_ids = {r[0] for r in con.execute("SELECT id FROM leads").fetchall()}

    total, skipped = 0, 0
    sql = (f"INSERT INTO audit (lead_id, {', '.join(COLS)}) "
           f"VALUES (?, {', '.join('?' * len(COLS))}) "
           f"ON CONFLICT(lead_id) DO UPDATE SET "
           + ", ".join(f"{c}=excluded.{c}" for c in COLS))
    for path in paths:
        with open(path, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                lid = (r.get("id") or "").strip()
                if not lid or lid not in valid_ids:
                    skipped += 1
                    continue
                con.execute(sql, [lid] + [coerce(c, r.get(c)) for c in COLS])
                total += 1
        print(f"  {os.path.basename(path)}")
    con.commit()

    grades = dict(con.execute(
        "SELECT COALESCE(audit_grade,'(none)'), COUNT(*) FROM audit GROUP BY 1").fetchall())
    con.close()
    print(f"Loaded {total:,} audit rows ({skipped:,} skipped: no matching lead).")
    print("  grades in DB: " + "  ".join(f"{k}={v:,}" for k, v in sorted(grades.items())))


if __name__ == "__main__":
    main()
