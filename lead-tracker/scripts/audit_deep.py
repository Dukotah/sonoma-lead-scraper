"""
Deep, one-time website enrichment for the lead tracker.

This is the slow-but-thorough cousin of audit_ci.py. The weekly audit_ci.py is
tuned to chip away fast (15s timeout, single try, homepage only, tiers B/C). This
script is built for a single exhaustive pass where runtime does not matter and the
goal is the richest possible record per lead. It is CSV-in / CSV-out and resumable
(already-done lead ids are skipped), so it commits cleanly back to the repo and a
killed runner just resumes where it left off.

Five enrichment upgrades over audit_ci.py:

  1. Tier-A web discovery. "No website" only means Overture had none. For leads
     with no site we web-search (DuckDuckGo HTML) to find a real owned site Overture
     missed; if found we reclassify and audit it, and if not found we mark the lead
     `no_site` with confidence — your hottest web-design prospects.

  2. Robust fetching. 30s timeout, retries with backoff, a browser-UA retry on
     403/401 (many sites block bot agents), an http->https fallback, and a DNS
     pre-check so a dead domain (NXDOMAIN) is recorded distinctly from a transient
     blip.

  3. Contact-page crawl. Beyond the homepage we fetch /contact, /about, /team, etc.
     and harvest emails, extra phone numbers, and a likely decision-maker name+title.

  4. Neglected-site signals. <meta name="generator"> (catches builders hiding on a
     custom domain), footer copyright year (stale = neglected = prime pitch), and a
     coarse analytics check. A working-but-old site is a lead, not a dead end.

  5. A 0-100 site_quality score (higher = better site = colder lead) plus a richer
     audit_grade: good / weak / neglected / broken / no_site.

Usage (one county):
  python scripts/audit_deep.py --in data/export/sonoma/sonoma_leads_full.csv \
                               --out data/export/audit/sonoma_deep.csv

Tune with --tiers (default A,B,C), --workers (site audits), --discover-workers
(kept low; DuckDuckGo throttles bursts), --limit (0 = no cap), --no-discover, --all.
"""
import os, re, csv, sys, time, socket, argparse
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse, unquote
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import requests
except ImportError:
    sys.exit("needs requests:  python -m pip install requests")

BOT_UA = ("Mozilla/5.0 (compatible; LeadTrackerAudit/2.0; "
          "+https://github.com/Dukotah/sonoma-lead-scraper)")
BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

FETCH_TIMEOUT = 30
RETRIES = 3                      # total attempts = RETRIES (with backoff between)
CONTACT_PATHS = ["contact", "contact-us", "about", "about-us",
                 "team", "our-team", "staff", "meet-the-team"]
MAX_CONTACT_PAGES = 4

# Builder fingerprints (HTML body + response headers).
FINGERPRINTS = [
    ("Wix", ["wix.com", "_wixCssStates", "X-Wix-", "wixstatic"]),
    ("Squarespace", ["squarespace.com", "static1.squarespace", "Squarespace"]),
    ("Weebly", ["weebly.com", "weeblycloud"]),
    ("GoDaddy", ["godaddy", "Website Builder by GoDaddy", "img1.wsimg.com"]),
    ("Shopify", ["cdn.shopify.com", "Shopify", "myshopify"]),
    ("Squarespace", ["squarespace"]),
    ("Duda", ["dudamobile", "dudaone", "irp.cdn-website.com"]),
    ("Site123", ["site123", "us-east-1.linodeobjects"]),
    ("Jimdo", ["jimdo"]),
    ("WordPress", ["wp-content", "wp-includes", "WordPress"]),
    ("Webflow", ["webflow.com", "wf-", "data-wf-"]),
    ("Joomla", ["/media/jui/", "Joomla"]),
    ("Drupal", ["Drupal.settings", "sites/all/"]),
]
# Builders we treat as "DIY / upsell" for grading purposes.
DIY_BUILDERS = {"Wix", "Weebly", "GoDaddy", "Site123", "Jimdo", "Duda"}

# Hosts that are never a business's own site (for discovery filtering).
DIRECTORY_HOSTS = (
    "yelp.com", "yelp.to", "facebook.com", "fb.com", "instagram.com",
    "yellowpages.com", "localsearch.com", "google.com", "youtube.com",
    "linkedin.com", "twitter.com", "x.com", "tiktok.com", "pinterest.com",
    "groupon.com", "nextdoor.com", "linktr.ee", "linktree.com",
    "mapquest.com", "tripadvisor.com", "wikipedia.org", "bbb.org", "manta.com",
    "chamberofcommerce.com", "indeed.com", "glassdoor.com", "apple.com",
    "bing.com", "duckduckgo.com", "amazon.com", "doordash.com", "ubereats.com",
    "grubhub.com", "opentable.com", "zillow.com", "realtor.com", "redfin.com",
    "trulia.com", "homes.com",
)

# Decision-maker titles, most senior first (seniority = match priority).
TITLES = ["owner", "founder", "co-founder", "president", "principal", "proprietor",
          "ceo", "broker", "partner", "managing director", "general manager",
          "director", "manager"]

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?:\+?1[\s.\-]?)?\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4}")
YEAR_RE = re.compile(r"(?:©|&copy;|copyright)\s*(?:[\d,\s\-]*?)(20[0-2]\d)", re.I)
GENERATOR_RE = re.compile(r'<meta[^>]+name=["\']generator["\'][^>]+content=["\']([^"\']+)', re.I)
NAME_RE = r"[A-Z][a-zA-Z'’\-]+(?:\s+[A-Z][a-zA-Z'’\-]+){1,2}"

# Junk we never want to surface as a contact email.
EMAIL_JUNK_DOMAINS = ("example.com", "sentry.io", "wix.com", "wixpress.com",
                      "godaddy.com", "squarespace.com", "schema.org", "w3.org",
                      "domain.com", "email.com", "yourdomain.com")
EMAIL_JUNK_EXT = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".css", ".js")

OUT_FIELDS = ["id", "input_url", "final_url", "dns_ok", "http_status", "https",
              "mobile", "load_ms", "size_kb", "builder_live", "generator", "title",
              "emails", "phones_found", "decision_maker", "decision_title",
              "copyright_year", "stale", "has_analytics", "pages_crawled",
              "discovered_site", "discovery_verdict", "site_quality",
              "audit_grade", "error", "checked_at"]

THIS_YEAR = datetime.now(timezone.utc).year


def norm_url(u):
    u = (u or "").strip()
    if not u:
        return None
    if not re.match(r"^https?://", u, re.I):
        u = "http://" + u
    return u


def hostname(url):
    if not url:
        return ""
    u = url if "://" in url else "http://" + url
    try:
        return (urlparse(u).hostname or "").lower()
    except Exception:
        return ""


def dns_resolves(host):
    if not host:
        return False
    try:
        socket.getaddrinfo(host, None)
        return True
    except Exception:
        return False


def robust_get(url, timeout=FETCH_TIMEOUT, retries=RETRIES):
    """GET with retries/backoff, a browser-UA retry on bot-block, and an
    http->https fallback. Returns (response_or_None, error_str)."""
    if not url:
        return None, "no url"
    if not url.startswith("http"):
        url = "http://" + url
    ua = BOT_UA
    last_err = None
    tried_https = False
    for attempt in range(retries):
        try:
            r = requests.get(url, headers={"User-Agent": ua,
                                           "Accept-Language": "en-US,en;q=0.9"},
                             timeout=timeout, allow_redirects=True)
            # Bot-blocked? retry once as a browser.
            if r.status_code in (401, 403) and ua == BOT_UA:
                ua = BROWSER_UA
                continue
            return r, None
        except requests.exceptions.SSLError as e:
            last_err = f"ssl: {str(e)[:80]}"
        except requests.exceptions.Timeout:
            last_err = "timeout"
        except requests.exceptions.ConnectionError as e:
            last_err = "connection failed"
            # If we only tried http, a single https retry is cheap and often works.
            if url.startswith("http://") and not tried_https:
                url = "https://" + url[len("http://"):]
                tried_https = True
                continue
        except Exception as e:
            last_err = f"{type(e).__name__}: {str(e)[:80]}"
        time.sleep(1.5 * (attempt + 1))
    return None, last_err


def detect_builder(html, headers, generator):
    blob = (html or "")[:300000]
    hdr = " ".join(f"{k}:{v}" for k, v in (headers or {}).items())
    gen = (generator or "").lower()
    for name, needles in FINGERPRINTS:
        if name.lower() in gen:
            return name
        if any(n in blob or n in hdr for n in needles):
            return name
    return None


def clean_emails(text):
    found = []
    for e in EMAIL_RE.findall(text or ""):
        el = e.lower()
        if el.endswith(EMAIL_JUNK_EXT):
            continue
        dom = el.split("@")[-1]
        if any(dom == j or dom.endswith("." + j) for j in EMAIL_JUNK_DOMAINS):
            continue
        if len(el) > 60 or el.count("@") != 1:
            continue
        if el not in found:
            found.append(el)
    return found[:5]


def clean_phones(text):
    out = []
    for m in PHONE_RE.findall(text or ""):
        d = re.sub(r"\D", "", m)
        if len(d) == 11 and d.startswith("1"):
            d = d[1:]
        if len(d) != 10 or d[0] in "01":
            continue
        fmt = f"({d[0:3]}) {d[3:6]}-{d[6:10]}"
        if fmt not in out:
            out.append(fmt)
    return out[:5]


def copyright_year(text):
    yrs = [int(y) for y in YEAR_RE.findall(text or "") if 2000 <= int(y) <= THIS_YEAR]
    return max(yrs) if yrs else None


def has_analytics(html):
    h = (html or "").lower()
    return any(s in h for s in ("google-analytics.com", "googletagmanager.com",
                                "gtag(", "ga('create", "plausible.io",
                                "fbevents.js", "clarity.ms"))


_NON_NAME = {"our", "the", "meet", "team", "about", "contact", "owner", "founder",
             "president", "ceo", "broker", "manager", "director", "principal",
             "home", "welcome", "us", "staff", "agent", "partner"}


def _clean_name(raw):
    parts = [p for p in raw.split() if p]
    while parts and parts[0].lower() in _NON_NAME:
        parts.pop(0)
    if len(parts) > 3:
        parts = parts[-3:]
    if not (2 <= len(parts) <= 3):
        return ""
    if any(p.lower() in _NON_NAME for p in parts):
        return ""
    if not all(p[:1].isupper() for p in parts):
        return ""
    return " ".join(parts)


def find_decision_maker(text):
    """Best 'Name, Title' / 'Title: Name' match; more-senior title wins."""
    title_alt = "|".join(re.escape(t) for t in sorted(TITLES, key=len, reverse=True))
    sep = r"\s*[,–—\-:|]\s*"
    pat_nt = re.compile(rf"({NAME_RE}){sep}({title_alt})\b", re.I)
    pat_tn = re.compile(rf"\b({title_alt}){sep}({NAME_RE})", re.I)
    best, best_rank = ("", ""), 10 ** 9
    flat = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text or ""))
    for name_first, pat in ((True, pat_nt), (False, pat_tn)):
        for m in pat.finditer(flat):
            raw = m.group(1) if name_first else m.group(2)
            title = (m.group(2) if name_first else m.group(1)).strip(" .,-—–").lower()
            name = _clean_name(raw)
            if not name:
                continue
            rank = next((i for i, t in enumerate(TITLES) if t == title), len(TITLES))
            if rank < best_rank:
                best, best_rank = (name, title), rank
    return best


def audit_site(input_url):
    """Full per-site audit: homepage + contact pages, builder/quality/contacts."""
    out = {k: None for k in OUT_FIELDS}
    out.update({"input_url": input_url, "dns_ok": 0, "http_status": 0, "https": 0,
                "mobile": 0, "stale": 0, "has_analytics": 0, "pages_crawled": 0,
                "emails": "", "phones_found": "", "site_quality": 0,
                "audit_grade": "broken"})
    target = norm_url(input_url)
    if not target:
        out["error"] = "no url"
        return out
    host = hostname(target)
    out["dns_ok"] = 1 if dns_resolves(host) else 0
    if not out["dns_ok"]:
        out["error"] = "dns: domain does not resolve"
        out["audit_grade"] = "broken"
        return out

    t0 = time.time()
    r, err = robust_get(target)
    out["load_ms"] = int((time.time() - t0) * 1000)
    if r is None:
        out["error"] = err
        return out

    html = r.text or ""
    out["final_url"] = r.url
    out["http_status"] = r.status_code
    out["https"] = 1 if r.url.lower().startswith("https://") else 0
    out["size_kb"] = round(len(r.content) / 1024, 1)
    out["mobile"] = 1 if re.search(r'<meta[^>]+name=["\']viewport["\']', html, re.I) else 0
    gm = GENERATOR_RE.search(html)
    out["generator"] = gm.group(1)[:80] if gm else None
    tm = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    if tm:
        out["title"] = re.sub(r"\s+", " ", tm.group(1)).strip()[:200]
    out["builder_live"] = detect_builder(html, r.headers, out["generator"])
    out["has_analytics"] = 1 if has_analytics(html) else 0
    yr = copyright_year(html)
    out["copyright_year"] = yr
    out["stale"] = 1 if (yr and yr <= THIS_YEAR - 3) else 0

    # Crawl a few contact pages for emails / phones / decision-maker.
    pages = [html]
    base = r.url if r.url.startswith("http") else target
    for p in CONTACT_PATHS:
        if len(pages) > MAX_CONTACT_PAGES:
            break
        sub, _ = robust_get(urljoin(base, p), timeout=20, retries=2)
        if sub is not None and sub.status_code < 400 and len(sub.text) > 400:
            pages.append(sub.text)
    out["pages_crawled"] = len(pages)
    blob = "\n".join(pages)
    # Prefer mailto: targets, then scan visible text.
    mailtos = re.findall(r"mailto:([^\"'?>\s]+)", blob, re.I)
    emails = clean_emails(" ".join(mailtos) + " " + blob)
    out["emails"] = "|".join(emails)
    out["phones_found"] = "|".join(clean_phones(blob))
    dm, dt = find_decision_maker(blob)
    out["decision_maker"], out["decision_title"] = dm, dt

    out["site_quality"], out["audit_grade"] = grade_site(out)
    return out


def grade_site(o):
    """0-100 site_quality (higher = better site = colder lead) + a label.
    broken: unreachable. neglected: works but old/DIY/insecure (prime upsell).
    weak: middling. good: fast, secure, mobile, fresh."""
    if not o["http_status"] or o["http_status"] >= 400:
        return 0, "broken"
    q = 100
    if not o["https"]:
        q -= 25
    if not o["mobile"]:
        q -= 20
    lm = o["load_ms"] or 0
    if lm > 8000:
        q -= 25
    elif lm > 4000:
        q -= 12
    if o["builder_live"] in DIY_BUILDERS:
        q -= 15
    if o["stale"]:
        q -= 15
    if not o["has_analytics"]:
        q -= 5
    q = max(0, min(100, q))
    grade = "good" if q >= 75 else ("weak" if q >= 45 else "neglected")
    return q, grade


def web_discover(name, city, state, retries=3):
    """Search for a business's real owned site (DuckDuckGo HTML endpoint).
    Returns (likely_site_or_None, verdict). DDG soft-throttles bursts (202/403);
    we back off and report 'throttled' rather than a false 'no site'."""
    q = " ".join(p for p in [name, city, state] if p).strip()
    if not q:
        return None, "unknown"
    headers = {"User-Agent": BROWSER_UA}
    html = None
    for attempt in range(retries + 1):
        try:
            r = requests.post("https://html.duckduckgo.com/html/", data={"q": q},
                              headers=headers, timeout=15)
        except Exception:
            time.sleep(2.5 * (attempt + 1))
            continue
        if r.status_code == 200:
            html = r.text
            break
        if r.status_code in (202, 429, 403) and attempt < retries:
            time.sleep(3.0 * (attempt + 1))
            continue
        break
    if html is None:
        return None, "throttled"

    tokens = [t for t in re.split(r"[^a-z0-9]+", (name or "").lower()) if len(t) > 2]
    likely = None
    for raw in re.findall(r'class="result__a"[^>]*href="([^"]+)"', html)[:10]:
        m = re.search(r"uddg=([^&]+)", raw)
        target = unquote(m.group(1)) if m else raw
        host = hostname(target)
        if not host or any(host == d or host.endswith("." + d) for d in DIRECTORY_HOSTS):
            continue
        core = host.replace("www.", "").split(".")[0]
        if tokens and any(t in core or core in t for t in tokens):
            return target, "has_site"
        if likely is None:
            likely = target
    if likely:
        return likely, "has_site"
    return None, "no_site_found"


def process_no_site(lead):
    """Tier-A path: discover a real site; audit it if found, else confirm no_site."""
    site, verdict = web_discover(lead.get("name", ""), lead.get("city", ""),
                                 lead.get("state", ""))
    if site:
        out = audit_site(site)
        out["discovered_site"] = site
        out["discovery_verdict"] = verdict
        return out
    out = {k: None for k in OUT_FIELDS}
    out.update({"input_url": "", "discovery_verdict": verdict,
                "site_quality": 0, "pages_crawled": 0,
                "audit_grade": "no_site" if verdict == "no_site_found" else "unknown",
                "error": None if verdict == "no_site_found" else verdict})
    return out


def load_done(path, force):
    if not os.path.exists(path) or force:
        return set()
    with open(path, encoding="utf-8") as f:
        return {r["id"] for r in csv.DictReader(f)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="infile", required=True)
    ap.add_argument("--out", dest="outfile", required=True)
    ap.add_argument("--tiers", default="A,B,C")
    ap.add_argument("--workers", type=int, default=8, help="site-audit threads")
    ap.add_argument("--discover-workers", type=int, default=2,
                    help="DDG discovery threads (keep low; it throttles)")
    ap.add_argument("--limit", type=int, default=0, help="max leads this run (0=all)")
    ap.add_argument("--no-discover", action="store_true",
                    help="skip Tier-A web discovery")
    ap.add_argument("--all", action="store_true", help="re-audit even if already done")
    args = ap.parse_args()
    tiers = {t.strip().upper() for t in args.tiers.split(",") if t.strip()}

    with open(args.infile, encoding="utf-8") as f:
        leads = list(csv.DictReader(f))
    os.makedirs(os.path.dirname(args.outfile) or ".", exist_ok=True)
    done = load_done(args.outfile, args.all)

    site_leads, nosite_leads = [], []
    for l in leads:
        if (l.get("tier") or "").upper() not in tiers or l["id"] in done:
            continue
        if (l.get("website") or "").strip():
            site_leads.append(l)
        elif not args.no_discover:
            nosite_leads.append(l)
    if args.limit:
        # Spend the budget on sites first, then discovery.
        site_leads = site_leads[:args.limit]
        rem = max(0, args.limit - len(site_leads))
        nosite_leads = nosite_leads[:rem]

    total = len(site_leads) + len(nosite_leads)
    if not total:
        print(f"Nothing to do in {os.path.basename(args.infile)} (all caught up).")
        return
    print(f"Deep audit: {len(site_leads):,} sites + {len(nosite_leads):,} discovery "
          f"from {os.path.basename(args.infile)} (tiers {','.join(sorted(tiers))})…",
          flush=True)

    write_header = not (os.path.exists(args.outfile) and not args.all)
    mode = "w" if (args.all or write_header) else "a"
    fh = open(args.outfile, mode, newline="", encoding="utf-8")
    w = csv.DictWriter(fh, fieldnames=OUT_FIELDS, extrasaction="ignore")
    if mode == "w":
        w.writeheader()
    now = lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")

    n = 0

    def emit(lid, res):
        nonlocal n
        res["id"] = lid
        res["checked_at"] = now()
        w.writerow(res)
        n += 1
        if n % 50 == 0:
            fh.flush()
            print(f"  {n:,}/{total:,}", flush=True)

    # Phase 1: parallel site audits.
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(audit_site, l["website"]): l["id"] for l in site_leads}
        for fut in as_completed(futs):
            emit(futs[fut], fut.result())
    fh.flush()

    # Phase 2: low-concurrency Tier-A discovery (DDG-friendly).
    if nosite_leads:
        with ThreadPoolExecutor(max_workers=args.discover_workers) as ex:
            futs = {ex.submit(process_no_site, l): l["id"] for l in nosite_leads}
            for fut in as_completed(futs):
                emit(futs[fut], fut.result())
    fh.close()

    grades = {}
    with open(args.outfile, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            grades[r["audit_grade"]] = grades.get(r["audit_grade"], 0) + 1
    print("Done. " + os.path.basename(args.outfile) + " grades: "
          + "  ".join(f"{k}={v:,}" for k, v in sorted(grades.items())), flush=True)


if __name__ == "__main__":
    main()
