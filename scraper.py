"""
Sonoma County Web Design Lead Scraper
──────────────────────────────────────
Zero API keys required. Runs on your local machine.

Sources:  Yelp + Yellow Pages (no key needed)
Audits:   Google PageSpeed Insights (free, no key needed)
Email:    Scrapes contact pages directly + optional Hunter.io

Install:
    pip install requests beautifulsoup4 pandas tqdm

Run:
    python scraper.py
    python scraper.py --categories "restaurants,contractors" --limit 15
    python scraper.py --hunter-key YOUR_KEY
"""

import argparse, json, os, re, sys, time, urllib.parse
from datetime import datetime

import requests
from bs4 import BeautifulSoup
import pandas as pd
from tqdm import tqdm

# ── CONFIG ────────────────────────────────────────────────────────────────────

SCORE_THRESHOLD = 70   # Only keep sites scoring below this
LOCATION_YELP   = "Sonoma County, CA"
LOCATION_YP     = "sonoma-county-ca"   # Yellow Pages URL slug

DEFAULT_CATEGORIES = [
    "contractors", "auto-repair", "restaurants",
    "hair-salons", "plumbers", "dentists", "gyms", "lawyers",
]

# Yellow Pages uses different slug format for some categories
YP_CATEGORY_MAP = {
    "contractors":  "general-contractors",
    "auto-repair":  "auto-repair-service",
    "restaurants":  "restaurants",
    "hair-salons":  "beauty-salons",
    "plumbers":     "plumbers",
    "dentists":     "dentists",
    "gyms":         "health-clubs",
    "lawyers":      "attorneys",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
}

CONTACT_PATHS = [
    "", "/contact", "/contact-us", "/contact_us",
    "/about", "/about-us", "/team", "/reach-us",
]

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")

JUNK_PREFIXES = [
    "noreply","no-reply","donotreply","bounce","postmaster",
    "webmaster","example","privacy@","legal@","press@","abuse@",
]
JUNK_DOMAINS = [
    "sentry.io","example.com","wixpress.com","squarespace.com",
    "godaddy.com","wpengine.com","shopify.com","amazonaws.com",
    "cloudflare.com","google.com","facebook.com","instagram.com",
    "twitter.com","yelp.com","yellowpages.com",
]


# ── YELP SCRAPER ──────────────────────────────────────────────────────────────

def scrape_yelp(category: str, limit: int) -> list[dict]:
    """Scrape Yelp search results. Works great on your local IP."""
    results, seen = [], set()
    yelp_cat = category.replace("-", " ")

    for offset in range(0, min(limit * 3, 240), 10):
        if len(results) >= limit:
            break

        params = {
            "find_desc": yelp_cat,
            "find_loc":  LOCATION_YELP,
            "start":     offset,
        }
        url = "https://www.yelp.com/search?" + urllib.parse.urlencode(params)

        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
        except Exception as e:
            print(f"   ⚠️  Yelp request failed: {e}")
            break

        if resp.status_code == 429:
            print("   ⚠️  Yelp rate-limited — waiting 30s then retrying...")
            time.sleep(30)
            continue
        if resp.status_code != 200:
            print(f"   ⚠️  Yelp returned HTTP {resp.status_code} — skipping")
            break

        businesses = _parse_yelp_json(resp.text)
        if not businesses:
            businesses = _parse_yelp_html(resp.text)

        added = 0
        for biz in businesses:
            if len(results) >= limit:
                break
            name = biz.get("name", "").strip()
            if not name or name.lower() in seen:
                continue
            seen.add(name.lower())
            results.append({
                "business_name": name,
                "yelp_url":      biz.get("url", ""),
                "phone":         biz.get("phone", ""),
                "address":       biz.get("address", ""),
                "website":       "",
                "source":        "yelp",
                "category":      category,
            })
            added += 1

        if added == 0:
            break
        time.sleep(2)

    return results


def _parse_yelp_json(html: str) -> list[dict]:
    """Pull businesses out of Yelp's embedded JSON data."""
    results = []
    soup    = BeautifulSoup(html, "html.parser")

    for script in soup.find_all("script", type="application/json"):
        try:
            data = json.loads(script.string or "")
            _walk(data, results, depth=0)
        except Exception:
            pass

    for script in soup.find_all("script"):
        text = script.string or ""
        if '"name"' not in text or "yelp" not in text.lower():
            continue
        for match in re.finditer(r'\{(?:[^{}]|\{[^{}]*\}){10,}\}', text):
            try:
                obj = json.loads(match.group())
                if obj.get("name") and (obj.get("phone") or obj.get("businessUrl") or obj.get("url")):
                    results.append(_normalize_biz(obj))
            except Exception:
                pass

    return [r for r in results if r.get("name")]


def _parse_yelp_html(html: str) -> list[dict]:
    """Fallback: scrape business names directly from visible HTML."""
    soup    = BeautifulSoup(html, "html.parser")
    results = []

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/biz/" in href and not href.startswith("http"):
            name = a.get_text(strip=True)
            if name and len(name) > 2 and len(name) < 80:
                full_url = "https://www.yelp.com" + href.split("?")[0]
                results.append({
                    "name": name,
                    "url":  full_url,
                    "phone": "",
                    "address": "",
                })
    return results


def _walk(data, out: list, depth: int):
    if depth > 12:
        return
    if isinstance(data, dict):
        if data.get("name") and isinstance(data["name"], str) and len(data["name"]) > 2:
            url = data.get("businessUrl") or data.get("url") or ""
            if "/biz/" in url or data.get("phone") or data.get("telephone"):
                out.append(_normalize_biz(data))
        for v in data.values():
            _walk(v, out, depth + 1)
    elif isinstance(data, list):
        for item in data:
            _walk(item, out, depth + 1)


def _normalize_biz(obj: dict) -> dict:
    addr = obj.get("address") or obj.get("location") or {}
    if isinstance(addr, dict):
        parts = [
            addr.get("streetAddress",""),
            addr.get("addressLocality",""),
            addr.get("addressRegion",""),
        ]
        addr_str = ", ".join(p for p in parts if p)
    else:
        addr_str = str(addr) if addr else ""

    url = obj.get("businessUrl") or obj.get("url") or ""
    if url and not url.startswith("http"):
        url = "https://www.yelp.com" + url

    return {
        "name":    obj.get("name","").strip(),
        "url":     url,
        "phone":   str(obj.get("phone") or obj.get("telephone") or ""),
        "address": addr_str,
    }


# ── YELLOW PAGES SCRAPER ──────────────────────────────────────────────────────

def scrape_yellowpages(category: str, limit: int) -> list[dict]:
    """Scrape Yellow Pages — good complementary source to Yelp."""
    results, seen = [], set()
    yp_cat = YP_CATEGORY_MAP.get(category, category)

    for page in range(1, (limit // 10) + 3):
        if len(results) >= limit:
            break

        url = f"https://www.yellowpages.com/{LOCATION_YP}/{yp_cat}"
        if page > 1:
            url += f"?page={page}"

        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
        except Exception as e:
            print(f"   ⚠️  Yellow Pages request failed: {e}")
            break

        if resp.status_code == 404:
            url = f"https://www.yellowpages.com/{LOCATION_YP}/{category}"
            try:
                resp = requests.get(url, headers=HEADERS, timeout=15)
            except Exception:
                break

        if resp.status_code != 200:
            print(f"   ⚠️  Yellow Pages returned HTTP {resp.status_code}")
            break

        soup  = BeautifulSoup(resp.text, "html.parser")
        cards = soup.select("div.result, article.listing, div.v-card")

        if not cards:
            cards = soup.select("[class*='result']")

        added = 0
        for card in cards:
            if len(results) >= limit:
                break

            name_el = card.select_one("a.business-name, h2.n, [class*='business-name']")
            if not name_el:
                continue
            name = name_el.get_text(strip=True)
            if not name or name.lower() in seen:
                continue
            seen.add(name.lower())

            phone_el = card.select_one(".phones, [class*='phone']")
            phone    = phone_el.get_text(strip=True) if phone_el else ""

            street = card.select_one(".street-address")
            city   = card.select_one(".locality")
            addr   = ""
            if street:
                addr = street.get_text(strip=True)
                if city:
                    addr += ", " + city.get_text(strip=True)

            web_el  = card.select_one("a[href*='trackclick'], a.track-visit-website")
            website = ""
            if web_el:
                href = web_el.get("href","")
                m    = re.search(r'url=([^&"]+)', href)
                if m:
                    website = urllib.parse.unquote(m.group(1))
                elif href.startswith("http") and "yellowpages.com" not in href:
                    website = href

            results.append({
                "business_name": name,
                "yelp_url":      "",
                "phone":         phone,
                "address":       addr,
                "website":       website,
                "source":        "yellowpages",
                "category":      category,
            })
            added += 1

        if added == 0:
            break
        time.sleep(2)

    return results


# ── RESOLVE YELP WEBSITE ─────────────────────────────────────────────────────

def resolve_yelp_website(yelp_url: str) -> str:
    """Visit the Yelp listing page and extract the real business website."""
    if not yelp_url:
        return ""
    try:
        if not yelp_url.startswith("http"):
            yelp_url = "https://www.yelp.com" + yelp_url
        resp = requests.get(yelp_url, headers=HEADERS, timeout=12, allow_redirects=True)
        soup = BeautifulSoup(resp.text, "html.parser")

        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "biz_redir" in href or "redirect_url" in href:
                m = re.search(r'url=([^&"]+)', href)
                if m:
                    decoded = urllib.parse.unquote(m.group(1))
                    if decoded.startswith("http") and "yelp.com" not in decoded:
                        return decoded.split("?")[0].rstrip("/")

        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
                url  = data.get("url") or data.get("sameAs")
                if isinstance(url, str) and url.startswith("http") and "yelp.com" not in url:
                    return url.rstrip("/")
                if isinstance(url, list):
                    for u in url:
                        if isinstance(u, str) and u.startswith("http") and "yelp.com" not in u:
                            return u.rstrip("/")
            except Exception:
                pass

        for a in soup.find_all("a", href=True):
            text = a.get_text(strip=True).lower()
            href = a["href"]
            if any(kw in text for kw in ["website", "visit site", "business site"]):
                if href.startswith("http") and "yelp.com" not in href:
                    return href.split("?")[0].rstrip("/")

    except Exception:
        pass
    return ""


# ── PAGESPEED AUDIT ───────────────────────────────────────────────────────────

def pagespeed_audit(url: str) -> dict:
    """Free PageSpeed Insights API — no key required."""
    empty = {
        "score": None, "opportunities": "",
        "lcp": "", "fcp": "", "tbt": "", "cls": "",
    }
    if not url:
        return empty
    try:
        resp = requests.get(
            "https://www.googleapis.com/pagespeedonline/v5/runPagespeed",
            params={"url": url, "strategy": "mobile"},
            timeout=35,
        )
        if resp.status_code != 200:
            return empty

        data   = resp.json()
        lhr    = data.get("lighthouseResult", {})
        score  = lhr.get("categories", {}).get("performance", {}).get("score")
        score  = int(score * 100) if score is not None else None
        audits = lhr.get("audits", {})
        items  = audits.get("metrics", {}).get("details", {}).get("items", [{}])
        m      = items[0] if items else {}

        def ms(k):
            v = m.get(k, 0)
            return f"{round(v/1000, 1)}s" if v else ""

        opps = []
        for _, audit in audits.items():
            s = audit.get("score")
            if s is not None and s < 0.9:
                title   = audit.get("title", "")
                details = audit.get("details", {})
                if title and details.get("type") == "opportunity":
                    savings = details.get("overallSavingsMs", 0)
                    opps.append((savings, title))
        opps.sort(reverse=True)

        return {
            "score":         score,
            "opportunities": " | ".join(t for _, t in opps[:4]),
            "lcp":           ms("largestContentfulPaint"),
            "fcp":           ms("firstContentfulPaint"),
            "tbt":           ms("totalBlockingTime"),
            "cls":           str(m.get("cumulativeLayoutShift", "")),
        }
    except Exception:
        return empty


# ── EMAIL FINDER ──────────────────────────────────────────────────────────────

def find_email(website: str, hunter_key: str = "") -> str:
    if not website:
        return ""
    email = _scrape_for_email(website)
    if not email and hunter_key:
        email = _hunter_lookup(_domain(website), hunter_key)
    return email or ""


def _scrape_for_email(base: str) -> str:
    found = set()
    base  = base.rstrip("/")
    for path in CONTACT_PATHS:
        try:
            resp = requests.get(
                base + path, headers=HEADERS,
                timeout=8, allow_redirects=True,
            )
            if resp.status_code != 200:
                continue
            soup = BeautifulSoup(resp.text, "html.parser")

            for a in soup.find_all("a", href=True):
                if a["href"].lower().startswith("mailto:"):
                    e = a["href"][7:].split("?")[0].strip().lower()
                    if _good_email(e):
                        found.add(e)

            for e in EMAIL_RE.findall(resp.text):
                if _good_email(e.lower()):
                    found.add(e.lower())

            if found:
                break
        except Exception:
            pass
        time.sleep(0.3)

    if found:
        return sorted(found, key=lambda e: (
            0 if e.split("@")[0] in ("info","hello","contact","hi","team") else 1,
            len(e)
        ))[0]
    return ""


def _hunter_lookup(domain: str, api_key: str) -> str:
    try:
        r = requests.get(
            "https://api.hunter.io/v2/domain-search",
            params={"domain": domain, "api_key": api_key, "limit": 1},
            timeout=10,
        )
        emails = r.json().get("data", {}).get("emails", [])
        return emails[0].get("value", "") if emails else ""
    except Exception:
        return ""


def _good_email(e: str) -> bool:
    if not EMAIL_RE.fullmatch(e):
        return False
    dom = e.split("@")[-1] if "@" in e else ""
    if "." not in dom:
        return False
    el = e.lower()
    if any(el.startswith(j) for j in JUNK_PREFIXES):
        return False
    if dom in JUNK_DOMAINS:
        return False
    return True


def _domain(url: str) -> str:
    try:
        if "://" not in url:
            url = "https://" + url
        return urllib.parse.urlparse(url).netloc.replace("www.", "")
    except Exception:
        return ""


# ── MAIN PIPELINE ─────────────────────────────────────────────────────────────

def run(categories: list, limit_per: int, hunter_key: str, output_file: str):
    print(f"\n{'━'*54}")
    print(f"  Sonoma County Web Design Lead Scraper 🍷")
    print(f"  Categories : {', '.join(categories)}")
    print(f"  Limit      : {limit_per} per category per source")
    print(f"  Threshold  : PageSpeed mobile score < {SCORE_THRESHOLD}")
    print(f"  Hunter.io  : {'✅ enabled' if hunter_key else '⬜ not set (site scrape only)'}")
    print(f"{'━'*54}\n")

    all_leads = []
    for cat in categories:
        print(f"📍 {cat}")
        yelp = scrape_yelp(cat, limit_per)
        print(f"   Yelp         → {len(yelp)}")
        yp   = scrape_yellowpages(cat, limit_per)
        print(f"   Yellow Pages → {len(yp)}")
        all_leads.extend(yelp)
        all_leads.extend(yp)

    seen, unique = set(), []
    for lead in all_leads:
        key = lead["business_name"].lower().strip()
        if key and key not in seen:
            seen.add(key)
            unique.append(lead)
    print(f"\n✅ Unique businesses : {len(unique)}")

    print(f"\n🔗 Resolving real websites...")
    for lead in tqdm(unique, desc="Websites"):
        if not lead.get("website") and lead.get("yelp_url"):
            lead["website"] = resolve_yelp_website(lead["yelp_url"])
        time.sleep(0.8)

    has_site = [l for l in unique if l.get("website")]
    print(f"✅ With websites : {len(has_site)}/{len(unique)}")

    print(f"\n⚡ Running PageSpeed audits (mobile)...")
    qualified = []
    for lead in tqdm(has_site, desc="Auditing"):
        audit = pagespeed_audit(lead["website"])
        lead.update(audit)
        score = lead.get("score")
        if score is None or score < SCORE_THRESHOLD:
            qualified.append(lead)
        time.sleep(0.5)

    print(f"✅ Qualified (score < {SCORE_THRESHOLD}) : {len(qualified)}/{len(has_site)}")

    print(f"\n📧 Finding contact emails...")
    for lead in tqdm(qualified, desc="Emails"):
        lead["email"] = find_email(lead.get("website", ""), hunter_key)
        time.sleep(0.4)

    with_email = sum(1 for l in qualified if l.get("email"))
    print(f"✅ Emails found : {with_email}/{len(qualified)}")

    columns = [
        "business_name", "email", "website", "phone", "address",
        "score", "opportunities", "lcp", "fcp", "tbt", "cls",
        "source", "category", "yelp_url",
    ]
    df = pd.DataFrame(qualified)
    for col in columns:
        if col not in df.columns:
            df[col] = ""
    df = df[columns].sort_values("score", ascending=True, na_position="last")
    df.to_csv(output_file, index=False)

    print(f"\n{'━'*54}")
    print(f"  ✅  {len(qualified)} leads exported → {output_file}")
    print(f"  📧  {with_email} emails found")
    print(f"  📊  Avg PageSpeed score: "
          f"{df['score'].dropna().astype(float).mean():.0f}"
          if not df['score'].dropna().empty else "  📊  No scores recorded")
    print(f"{'━'*54}\n")

    if not df.empty:
        print("Top 10 targets (worst sites first):")
        preview = df[["business_name","email","score","opportunities"]].head(10)
        print(preview.to_string(index=False, max_colwidth=50))
        print()


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    p = argparse.ArgumentParser(
        description="Sonoma County Web Design Lead Scraper — no API keys needed"
    )
    p.add_argument(
        "--categories",
        default=",".join(DEFAULT_CATEGORIES),
        help=f"Comma-separated business types (default: {', '.join(DEFAULT_CATEGORIES)})",
    )
    p.add_argument(
        "--limit", type=int, default=20,
        help="Max leads per category per source (default: 20)",
    )
    p.add_argument(
        "--hunter-key", default="",
        help="Hunter.io API key for extra email finding (optional)",
    )
    p.add_argument(
        "--output",
        default=f"sonoma_leads_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        help="Output CSV filename",
    )
    args = p.parse_args()

    run(
        categories  = [c.strip() for c in args.categories.split(",") if c.strip()],
        limit_per   = args.limit,
        hunter_key  = args.hunter_key,
        output_file = args.output,
    )
