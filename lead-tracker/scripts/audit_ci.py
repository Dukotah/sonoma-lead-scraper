"""
CI website audit — reads a committed leads CSV, fetches each business website,
and writes an audit CSV. Designed to run on GitHub Actions runners (which have
outbound internet, unlike the build sandbox). CSV-in / CSV-out so it needs no
SQLite DB and commits cleanly back to the repo.

Per site it records: http_status, https, mobile (viewport), load_ms,
builder_live (platform from HTML), title, audit_grade (good/weak/broken), error.

Resumable: if the output CSV already has a row for a lead id, it's skipped
(unless --all). This lets a scheduled job chip away across runs.

Usage:
  python scripts/audit_ci.py --in data/export/sonoma/sonoma_leads_full.csv \
                             --out data/export/audit/sonoma_audit.csv \
                             --tiers B,C --workers 12 --limit 6000
"""
import os, re, csv, sys, time, argparse
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import requests
except ImportError:
    sys.exit("needs requests:  python -m pip install requests")

UA = ("Mozilla/5.0 (compatible; LeadTrackerAudit/1.0; "
      "+https://github.com/Dukotah/sonoma-lead-scraper)")

FINGERPRINTS = [
    ("Wix", ["wix.com", "_wixCssStates", "X-Wix-"]),
    ("Squarespace", ["squarespace.com", "static1.squarespace", "Squarespace"]),
    ("Weebly", ["weebly.com", "weeblycloud"]),
    ("GoDaddy", ["godaddy", "Website Builder by GoDaddy"]),
    ("Shopify", ["cdn.shopify.com", "Shopify", "myshopify"]),
    ("WordPress", ["wp-content", "wp-includes", "WordPress"]),
    ("Webflow", ["webflow.com", "wf-", "data-wf-"]),
    ("Joomla", ["/media/jui/", "Joomla"]),
    ("Drupal", ["Drupal.settings", "sites/all/"]),
]
OUT_FIELDS = ["id", "http_status", "https", "mobile", "load_ms",
              "builder_live", "title", "audit_grade", "error", "checked_at"]


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
        if any(n in blob or n in hdr for n in needles):
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
        r = requests.get(target, headers={"User-Agent": UA}, timeout=15, allow_redirects=True)
        out["load_ms"] = int((time.time() - t0) * 1000)
        out["http_status"] = r.status_code
        out["https"] = 1 if r.url.lower().startswith("https://") else 0
        html = r.text or ""
        out["mobile"] = 1 if re.search(r'<meta[^>]+name=["\']viewport["\']', html, re.I) else 0
        m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
        if m:
            out["title"] = re.sub(r"\s+", " ", m.group(1)).strip()[:200]
        out["builder_live"] = detect_builder(html, r.headers)
        if r.status_code >= 400:
            out["audit_grade"] = "broken"
        elif out["https"] and out["mobile"] and (out["load_ms"] or 9999) < 4000:
            out["audit_grade"] = "good"
        else:
            out["audit_grade"] = "weak"
    except requests.exceptions.SSLError as e:
        out["error"] = f"ssl: {str(e)[:100]}"
    except requests.exceptions.ConnectionError:
        out["error"] = "connection failed"
    except requests.exceptions.Timeout:
        out["error"] = "timeout"
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {str(e)[:100]}"
    if out["load_ms"] is None:
        out["load_ms"] = int((time.time() - t0) * 1000)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="infile", required=True)
    ap.add_argument("--out", dest="outfile", required=True)
    ap.add_argument("--tiers", default="B,C", help="which tiers to audit (default B,C)")
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--limit", type=int, default=0, help="max sites this run (0=all)")
    ap.add_argument("--all", action="store_true", help="re-audit even if already in output")
    args = ap.parse_args()
    tiers = {t.strip().upper() for t in args.tiers.split(",") if t.strip()}

    with open(args.infile, encoding="utf-8") as f:
        leads = list(csv.DictReader(f))

    os.makedirs(os.path.dirname(args.outfile) or ".", exist_ok=True)
    done_ids = set()
    if os.path.exists(args.outfile) and not args.all:
        with open(args.outfile, encoding="utf-8") as f:
            done_ids = {r["id"] for r in csv.DictReader(f)}

    targets = [(l["id"], l.get("website", "")) for l in leads
               if (l.get("tier") or "").upper() in tiers
               and (l.get("website") or "").strip()
               and l["id"] not in done_ids]
    if args.limit:
        targets = targets[:args.limit]

    n = len(targets)
    if not n:
        print(f"Nothing to audit in {args.infile} (all caught up).")
        return
    print(f"Auditing {n:,} sites from {os.path.basename(args.infile)} "
          f"(tiers {','.join(sorted(tiers))}, {args.workers} workers)…", flush=True)

    write_header = not (os.path.exists(args.outfile) and not args.all)
    mode = "w" if (args.all or write_header) else "a"
    fh = open(args.outfile, mode, newline="", encoding="utf-8")
    w = csv.DictWriter(fh, fieldnames=OUT_FIELDS)
    if mode == "w":
        w.writeheader()
    now = lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")

    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(audit_one, url): lid for (lid, url) in targets}
        for fut in as_completed(futs):
            lid = futs[fut]
            r = fut.result()
            r["id"] = lid
            r["checked_at"] = now()
            w.writerow(r)
            done += 1
            if done % 100 == 0:
                fh.flush()
                print(f"  {done:,}/{n:,}", flush=True)
    fh.close()

    # quick summary
    grades = {}
    with open(args.outfile, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            grades[r["audit_grade"]] = grades.get(r["audit_grade"], 0) + 1
    print(f"Done. Output {args.outfile}. Grades so far: "
          + "  ".join(f"{k}={v:,}" for k, v in sorted(grades.items())))


if __name__ == "__main__":
    main()
