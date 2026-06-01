"""
Offline enrichment for the lead tracker.

Runs against data/leads.sqlite AFTER build_leads_db.py. Adds derived columns to
the `leads` table using only data already present (no network needed), so it works
even in locked-down environments:

  tier / tier_reason  - recomputed A/B/C from the website URL:
                          A = no website, or social/listing-only page
                          B = DIY builder site (Wix/Weebly/GoDaddy/etc.) - upsell
                          C = real custom domain (audit live before pitching)
  builder             - detected DIY platform (or NULL)
  score               - 0-100 lead-priority (need + reachability + confidence)
  phone_fmt           - normalized "(707) 555-1234"
  area_code           - 3-digit area code
  social_platforms    - "facebook|instagram|..." present for this lead
  email_owned         - 1 if the email's domain matches the website's domain
  completeness        - 0-100 how complete this record is
  best_contact        - "phone" | "email" | "social" | "none"
  pitch               - a personalized one-line cold-open

Idempotent: safe to re-run. Run:  python scripts/enrich_leads.py
"""
import os, re, sqlite3
from urllib.parse import urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("LEADS_DB", os.path.normpath(os.path.join(HERE, "..", "data", "leads.sqlite")))

# Social / listing pages = "no real owned site" -> Tier A.
SOCIAL_LISTING = (
    "facebook.com", "instagram.com", "yelp.com", "linktr.ee", "linktree.com",
    "tiktok.com", "linkedin.com", "twitter.com", "x.com", "nextdoor.com",
    "yellowpages.com", "google.com", "g.page", "business.google.com",
)
# DIY builder *sub*domains we can detect from the URL alone -> Tier B (upsell).
# (Builders on a custom domain are invisible from the URL; the live audit catches those.)
BUILDERS = {
    "wixsite.com": "Wix", "wix.com": "Wix",
    "weebly.com": "Weebly",
    "godaddysites.com": "GoDaddy", "godaddy.com": "GoDaddy",
    "square.site": "Square", "squareup.com": "Square",
    "business.site": "Google Business",  # google's free one-pager
    "wordpress.com": "WordPress.com", "blogspot.com": "Blogger",
    "myshopify.com": "Shopify", "bigcartel.com": "Big Cartel",
    "webflow.io": "Webflow", "netlify.app": "Netlify", "wordpress.org": "WordPress",
    "ecwid.com": "Ecwid", "square.online": "Square",
}

SOCIAL_HOSTS = {
    "facebook.com": "facebook", "instagram.com": "instagram", "tiktok.com": "tiktok",
    "linkedin.com": "linkedin", "twitter.com": "twitter", "x.com": "twitter",
    "youtube.com": "youtube", "yelp.com": "yelp", "nextdoor.com": "nextdoor",
    "pinterest.com": "pinterest",
}

ADD_COLUMNS = [
    ("builder", "TEXT"), ("score", "INTEGER"), ("phone_fmt", "TEXT"),
    ("area_code", "TEXT"), ("social_platforms", "TEXT"), ("email_owned", "INTEGER"),
    ("completeness", "INTEGER"), ("best_contact", "TEXT"), ("pitch", "TEXT"),
]


def host_of(url):
    if not url:
        return ""
    u = url.strip()
    if not re.match(r"^https?://", u, re.I):
        u = "http://" + u
    try:
        h = urlparse(u).netloc.lower()
    except Exception:
        return ""
    return h[4:] if h.startswith("www.") else h


def registrable(host):
    """Crude eTLD+1 (good enough for builder/social matching and owned-email check)."""
    parts = host.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def classify(website):
    """-> (tier, reason, builder)."""
    if not website or not website.strip():
        return "A", "No website", None
    host = host_of(website)
    reg = registrable(host)
    # full-host check first (handles multi-label like business.google.com)
    for s in SOCIAL_LISTING:
        if host == s or host.endswith("." + s) or reg == s:
            return "A", "Social/listing only - no owned site", None
    for dom, name in BUILDERS.items():
        if host == dom or host.endswith("." + dom) or reg == dom:
            return "B", f"DIY builder site ({name}) - upsell to custom", name
    return "C", "Has a real website - audit quality before pitching", None


def fmt_phone(phone):
    if not phone:
        return None, None
    d = re.sub(r"\D", "", phone)
    if len(d) == 11 and d.startswith("1"):
        d = d[1:]
    if len(d) != 10:
        return phone, (d[:3] if len(d) >= 3 else None)
    return f"({d[0:3]}) {d[3:6]}-{d[6:10]}", d[0:3]


def social_list(socials):
    if not socials:
        return None
    found = []
    for part in socials.split("|"):
        h = host_of(part)
        reg = registrable(h)
        for dom, label in SOCIAL_HOSTS.items():
            if (reg == dom or h.endswith(dom)) and label not in found:
                found.append(label)
    return "|".join(found) if found else None


def human_cat(cat):
    if not cat:
        return "local business"
    return cat.replace("_", " ").strip()


def make_pitch(name, tier, builder, city, category):
    nm = (name or "your business").strip()
    where = f" in {city}" if city else ""
    cat = human_cat(category)
    if tier == "A":
        return (f"Hi, I came across {nm}{where} and noticed you don't have a website yet — "
                f"for a {cat}, that's a lot of locals searching Google and not finding you. "
                f"I build fast, modern sites for {city or 'local'} businesses and can send a free mockup.")
    if tier == "B":
        b = builder or "a DIY builder"
        return (f"Hi, I found {nm}{where} and saw the site is on {b}. I can give you a faster, "
                f"more professional custom site that ranks better on Google — worth a quick look at a free mockup?")
    return (f"Hi, I help {city or 'local'} {cat}s like {nm} get more customers from their website "
            f"(speed, mobile, Google ranking). Could I send a free audit of your current site?")


def score_lead(tier, has_phone, has_email, confidence):
    need = {"A": 50, "B": 35, "C": 10}.get(tier, 10)
    reach = (25 if has_phone else 0) + (15 if has_email else 0)
    conf = int(round((confidence or 0) * 10))  # 0-10
    return max(0, min(100, need + reach + conf))


def completeness(name, phone, email, website, socials, address, category):
    fields = [name, phone, email, (website or socials), address, category]
    have = sum(1 for f in fields if f and str(f).strip())
    return int(round(100 * have / len(fields)))


def main():
    db = sqlite3.connect(DB_PATH)
    have = {r[1] for r in db.execute("PRAGMA table_info(leads)")}
    for col, typ in ADD_COLUMNS:
        if col not in have:
            db.execute(f"ALTER TABLE leads ADD COLUMN {col} {typ}")

    rows = db.execute(
        "SELECT id, name, category, website, phone, email, socials, address, "
        "city, confidence FROM leads"
    ).fetchall()

    updates = []
    tier_counts = {"A": 0, "B": 0, "C": 0}
    for (lid, name, category, website, phone, email, socials, address, city, conf) in rows:
        tier, reason, builder = classify(website)
        tier_counts[tier] = tier_counts.get(tier, 0) + 1
        phone_fmt, area = fmt_phone(phone)
        plats = social_list(socials)
        has_phone = bool(phone and phone.strip())
        has_email = bool(email and email.strip())
        # owned-email: email domain == website registrable domain
        email_owned = 0
        if has_email and website:
            edom = registrable((email.split("@")[-1] or "").lower())
            email_owned = 1 if edom and edom == registrable(host_of(website)) else 0
        best = "phone" if has_phone else ("email" if has_email else ("social" if plats else "none"))
        score = score_lead(tier, has_phone, has_email, conf)
        comp = completeness(name, phone, email, website, socials, address, category)
        pitch = make_pitch(name, tier, builder, city, category)
        updates.append((tier, reason, builder, score, phone_fmt, area, plats,
                        email_owned, comp, best, pitch, lid))

    db.execute("BEGIN")
    db.executemany(
        "UPDATE leads SET tier=?, tier_reason=?, builder=?, score=?, phone_fmt=?, "
        "area_code=?, social_platforms=?, email_owned=?, completeness=?, "
        "best_contact=?, pitch=? WHERE id=?",
        updates,
    )
    db.commit()
    db.execute("CREATE INDEX IF NOT EXISTS idx_leads_score ON leads(score)")
    # FTS mirrors leads; tier text lives only in leads so no FTS rebuild needed.
    db.commit()

    n = len(rows)
    avg = db.execute("SELECT ROUND(AVG(score),1) FROM leads").fetchone()[0]
    n_builder = db.execute("SELECT COUNT(*) FROM leads WHERE builder IS NOT NULL").fetchone()[0]
    print(f"Enriched {n:,} leads.")
    print(f"  Tiers: A={tier_counts.get('A',0):,}  B={tier_counts.get('B',0):,}  C={tier_counts.get('C',0):,}")
    print(f"  Builders detected: {n_builder:,}")
    print(f"  Avg lead score: {avg}")
    print(f"  Added columns: {', '.join(c for c,_ in ADD_COLUMNS)}")
    db.close()


if __name__ == "__main__":
    main()
