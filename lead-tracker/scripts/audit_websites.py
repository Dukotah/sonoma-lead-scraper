"""
Live website audit — RUN THIS ON YOUR OWN MACHINE (it needs outbound internet;
the build sandbox blocks it). Fetches each lead's website and records real signals
you can't get from the dataset alone, writing them into an `audit` table that the
tracker joins onto every lead (and that survives data rebuilds, like `crm`).

Per site it records:
  http_status   - final HTTP status (200, 404, 500, 0=unreachable)
  https         - 1 if the site loads over https
  mobile        - 1 if the HTML has a mobile <meta name=viewport>
  load_ms       - homepage fetch time in milliseconds
  builder_live  - platform detected from the HTML/headers (Wix, Squarespace, ...)
  title         - <title> text
  audit_grade   - good | weak | broken  (a quick triage of site quality)
  error         - failure reason, if any
  checked_at    - ISO timestamp

By default it audits Tier B/C leads (the ones that *have* a site worth checking)
that haven't been audited yet. Flags:
  --all          re-audit everything (ignore prior results)
  --tier A,B,C   which tiers to audit (default: B,C)
  --limit N      cap how many to do this run
  --workers N    concurrent fetches (default 8)

Run:  python scripts/audit_websites.py
      python scripts/audit_websites.py --tier C --limit 500 --workers 12
"""
import os, re, sys, time, sqlite3, argparse
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import requests
except ImportError:
    sys.exit("This script needs `requests`:  python -m pip install requests")

HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get(
    "LEADS_DB", os.path.normpath(os.path.join(HERE, "..", "data", "leads.sqlite"))
)
UA = ("Mozilla/5.0 (compatible; LeadTrackerAudit/1.0; "
      "+https://github.com/Dukotah/sonoma-lead-scraper)")

# Builder fingerprints found in live HTML/headers (catches builders on custom
# domains, which the URL-only check in enrich_leads.py can't see).
FINGERPRINTS = [
    ("Wix", ["wix.com", "_wixCssStates", "X-Wix-"]),
    ("Squarespace", ["squarespace.com", "static1.squarespace", "Squarespace"]),
    ("Weebly", ["weebly.com", "weeblycloud"]),
    ("GoDaddy", ["godaddy", "Website Builder by GoDaddy"]),
    ("Shopify", ["cdn.shopify.com", "Shopify", "myshopify"]),
    ("WordPress", ["wp-content", "wp-includes", "WordPress"]),
    ("Webflow", ["webflow.com", "wf-", "data-wf-"]),
    ("Squarespace Commerce", ["sqs-block"]),
    ("Joomla", ["/media/jui/", "Joomla"]),
    ("Drupal", ["Drupal.settings", "sites/all/"]),
]


def norm_url(u):
    u = (u or "").strip()
    if not u:
        return None
    if not re.match(r"^https?://", u, re.I):
        u = "http://" + u
    return u


def detect_builder(html, headers):
    blob = (html or "")[:200000]
    hdr = " ".join(f"{k}:{v}" for k, v in (headers or {}).items())
    for name, needles in FINGERPRINTS:
        for n in needles:
            if n in blob or n in hdr:
                return name
    return None


def audit_one(url):
    out = {"http_status": 0, "https": 0, "mobile": 0, "load_ms": None,
           "builder_live": None, "title": None, "audit_grade": "broken", "error": None}
    target = norm_url(url)
    if not target:
        out["error"] = "no url"
        return out
    t0 = time.time()
    try:
        r = requests.get(target, headers={"User-Agent": UA}, timeout=15,
                         allow_redirects=True)
        out["load_ms"] = int((time.time() - t0) * 1000)
        out["http_status"] = r.status_code
        out["https"] = 1 if r.url.lower().startswith("https://") else 0
        html = r.text or ""
        out["mobile"] = 1 if re.search(
            r'<meta[^>]+name=["\']viewport["\']', html, re.I) else 0
        m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
        if m:
            out["title"] = re.sub(r"\s+", " ", m.group(1)).strip()[:200]
        out["builder_live"] = detect_builder(html, r.headers)
        # quick quality triage
        if r.status_code >= 400 or r.status_code == 0:
            out["audit_grade"] = "broken"
        elif out["https"] and out["mobile"] and (out["load_ms"] or 9999) < 4000:
            out["audit_grade"] = "good"
        else:
            out["audit_grade"] = "weak"  # http-only, no viewport, or slow
    except requests.exceptions.SSLError as e:
        out["error"] = f"ssl: {str(e)[:120]}"
    except requests.exceptions.ConnectionError:
        out["error"] = "connection failed"
    except requests.exceptions.Timeout:
        out["error"] = "timeout"
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {str(e)[:120]}"
    if out["load_ms"] is None:
        out["load_ms"] = int((time.time() - t0) * 1000)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="re-audit even already-checked leads")
    ap.add_argument("--tier", default="B,C", help="comma tiers to audit (default B,C)")
    ap.add_argument("--limit", type=int, default=0, help="max sites this run (0=all)")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()
    tiers = [t.strip().upper() for t in args.tier.split(",") if t.strip()]

    db = sqlite3.connect(DB_PATH)
    db.execute("""CREATE TABLE IF NOT EXISTS audit (
      lead_id TEXT PRIMARY KEY, http_status INTEGER, https INTEGER, mobile INTEGER,
      load_ms INTEGER, builder_live TEXT, title TEXT, audit_grade TEXT,
      error TEXT, checked_at TEXT)""")

    placeholders = ",".join("?" * len(tiers))
    sql = (f"SELECT l.id, l.website FROM leads l "
           f"WHERE l.tier IN ({placeholders}) "
           f"AND l.website IS NOT NULL AND l.website <> '' ")
    if not args.all:
        sql += "AND l.id NOT IN (SELECT lead_id FROM audit) "
    sql += "ORDER BY l.score DESC"
    if args.limit:
        sql += f" LIMIT {args.limit}"
    targets = db.execute(sql, tiers).fetchall()

    n = len(targets)
    if not n:
        print("Nothing to audit (all caught up). Use --all to re-audit.")
        return
    print(f"Auditing {n:,} sites (tiers {','.join(tiers)}, {args.workers} workers)…")
    print("Pacing requests; be patient and don't hammer — ~1-3 sites/sec.")

    done = 0
    now = lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(audit_one, w): lid for (lid, w) in targets}
        batch = []
        for fut in as_completed(futs):
            lid = futs[fut]
            r = fut.result()
            batch.append((lid, r["http_status"], r["https"], r["mobile"],
                          r["load_ms"], r["builder_live"], r["title"],
                          r["audit_grade"], r["error"], now()))
            done += 1
            if len(batch) >= 50:
                db.executemany(
                    "INSERT OR REPLACE INTO audit (lead_id,http_status,https,mobile,"
                    "load_ms,builder_live,title,audit_grade,error,checked_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)", batch)
                db.commit()
                batch.clear()
                print(f"  {done:,}/{n:,}", end="\r", flush=True)
        if batch:
            db.executemany(
                "INSERT OR REPLACE INTO audit (lead_id,http_status,https,mobile,"
                "load_ms,builder_live,title,audit_grade,error,checked_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)", batch)
            db.commit()

    g = dict(db.execute(
        "SELECT audit_grade, COUNT(*) FROM audit GROUP BY audit_grade").fetchall())
    print(f"\nDone. Audited {done:,}. "
          f"good={g.get('good',0):,}  weak={g.get('weak',0):,}  broken={g.get('broken',0):,}")
    print("Tip: in the tracker, 'weak'/'broken' Tier-C sites are now real warm leads.")
    db.close()


if __name__ == "__main__":
    main()
