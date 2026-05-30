"""
Shared lead-enrichment helpers for the Sonoma data kit.

- audit_website(url)        : live-fetch a site, report HTTPS / mobile / load / builder
- web_verify(name, city)    : web-search a business to confirm whether it has a real site
- is_weak_url(url)          : True if a URL is a social/listing page, not an owned site
- score_lead(rec, audit)    : assign tier (A/B/C), numeric score, and human reasons

No third-party deps beyond `requests`. Safe to import from any script.
"""
import re
import time
from urllib.parse import urlparse, unquote

UA = "SonomaLeadKit/1.0 (contact: dukotah@gmail.com)"
AUDIT_TIMEOUT = 6

import requests

# Domains that mean "no real website" — a social/listing page, not an owned site.
WEAK_DOMAINS = (
    "yelp.com", "yelp.to", "facebook.com", "fb.com", "instagram.com",
    "yellowpages.com", "localsearch.com", "google.com", "youtube.com",
    "linkedin.com", "twitter.com", "x.com", "tiktok.com", "pinterest.com",
    "groupon.com", "nextdoor.com", "linktr.ee", "linktree.com",
    "business.site", "wixsite.com", "mapquest.com", "tripadvisor.com",
)

# Hosts that show up in search results but are never a business's own site.
DIRECTORY_HOSTS = WEAK_DOMAINS + (
    "wikipedia.org", "bbb.org", "manta.com", "chamberofcommerce.com",
    "indeed.com", "glassdoor.com", "apple.com", "bing.com", "duckduckgo.com",
    "amazon.com", "doordash.com", "ubereats.com", "grubhub.com", "opentable.com",
)


def _hostname(url: str) -> str:
    if not url:
        return ""
    u = url if "://" in url else "http://" + url
    try:
        return (urlparse(u).hostname or "").lower()
    except Exception:
        return ""


def is_weak_url(url: str):
    """Return (is_weak, matched_domain). Matches on host boundary, not substring,
    so "x.com" won't flag "fedex.com"."""
    if not url:
        return True, "no website"
    host = _hostname(url)
    for d in WEAK_DOMAINS:
        if host == d or host.endswith("." + d):
            return True, d
    return False, ""


def audit_website(url: str) -> dict:
    """Fetch a homepage and report basic quality signals."""
    out = {"reachable": False, "https": False, "load_ms": None,
           "mobile_viewport": False, "builder": "", "title": "",
           "size_kb": None, "audit_notes": []}
    if not url:
        return out
    if not url.startswith("http"):
        url = "http://" + url
    out["https"] = url.startswith("https://")
    try:
        t0 = time.time()
        r = requests.get(url, headers={"User-Agent": UA},
                         timeout=AUDIT_TIMEOUT, allow_redirects=True)
        ms = int((time.time() - t0) * 1000)
        out["load_ms"] = ms
        out["reachable"] = r.status_code < 400
        out["https"] = r.url.startswith("https://")
        out["size_kb"] = round(len(r.content) / 1024, 1)
        html = r.text[:50000].lower()
        if 'name="viewport"' in html:
            out["mobile_viewport"] = True
        tm = re.search(r"<title>([^<]+)</title>", r.text, re.IGNORECASE)
        if tm:
            out["title"] = tm.group(1).strip()[:100]
        for sig, b in [("wix.com", "Wix"), ("squarespace", "Squarespace"),
                       ("weebly", "Weebly"), ("godaddy", "GoDaddy Sites"),
                       ("wordpress", "WordPress"), ("shopify", "Shopify"),
                       ("webflow", "Webflow"), ("duda", "Duda"),
                       ("site123", "Site123"), ("jimdo", "Jimdo")]:
            if sig in html:
                out["builder"] = b
                break
        if ms > 4000:
            out["audit_notes"].append(f"Slow load ({ms}ms)")
        if not out["mobile_viewport"]:
            out["audit_notes"].append("No mobile viewport")
        if not out["https"]:
            out["audit_notes"].append("No HTTPS")
        if out["builder"] in ("Wix", "Weebly", "GoDaddy Sites", "Site123", "Jimdo"):
            out["audit_notes"].append(f"DIY-builder ({out['builder']})")
    except requests.exceptions.SSLError:
        out["audit_notes"].append("SSL / broken cert")
    except requests.exceptions.Timeout:
        out["audit_notes"].append(f"Timeout (>{AUDIT_TIMEOUT}s)")
    except Exception as e:
        out["audit_notes"].append(f"Unreachable: {type(e).__name__}")
    return out


def _name_tokens(name: str):
    return [t for t in re.split(r"[^a-z0-9]+", (name or "").lower()) if len(t) > 2]


def web_verify(name: str, city: str = "", state: str = "CA", retries: int = 2) -> dict:
    """Web-search a business to confirm whether it has a real (owned) website.

    DuckDuckGo's HTML endpoint soft-throttles bursts with HTTP 202; we retry with
    backoff and, if still blocked, return verdict 'throttled' rather than falsely
    reporting 'no site' (which would waste a call on a business that has one).

    Returns dict:
      searched      : bool, did the search actually return results
      likely_site   : str|None, best-guess owned site found in results
      directory_hits: list[str], directory/social pages found (yelp, fb, etc.)
      verdict       : 'has_site' | 'no_site_found' | 'throttled' | 'unknown'
    """
    out = {"searched": False, "likely_site": None, "directory_hits": [],
           "verdict": "unknown"}
    q = " ".join(p for p in [name, city, state] if p).strip()
    if not q:
        return out
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    html = None
    for attempt in range(retries + 1):
        try:
            r = requests.post("https://html.duckduckgo.com/html/", data={"q": q},
                              headers=headers, timeout=12)
        except Exception:
            time.sleep(2.0 * (attempt + 1))
            continue
        if r.status_code == 200:
            html = r.text
            break
        if r.status_code in (202, 429, 403) and attempt < retries:
            time.sleep(2.5 * (attempt + 1))  # back off and retry the throttle
            continue
        break
    if html is None:
        out["verdict"] = "throttled"   # rate-limited/blocked — could not get results
        return out
    out["searched"] = True

    # DuckDuckGo HTML: each result is <a class="result__a" href="...">
    hrefs = re.findall(r'class="result__a"[^>]*href="([^"]+)"', html)
    tokens = set(_name_tokens(name))
    for raw in hrefs[:10]:
        # DDG sometimes wraps in a redirect with uddg= param
        m = re.search(r"uddg=([^&]+)", raw)
        target = unquote(m.group(1)) if m else raw
        host = _hostname(target)
        if not host:
            continue
        if any(host == d or host.endswith("." + d) for d in DIRECTORY_HOSTS):
            out["directory_hits"].append(host)
            continue
        # An owned site usually echoes part of the business name in its host.
        host_core = host.replace("www.", "").split(".")[0]
        if tokens and any(t in host_core or host_core in t for t in tokens):
            out["likely_site"] = target
            break
        # otherwise remember the first non-directory result as a weak candidate
        if out["likely_site"] is None:
            out["likely_site"] = target

    if out["likely_site"]:
        out["verdict"] = "has_site"
    elif out["searched"]:
        out["verdict"] = "no_site_found"
    return out


def score_lead(rec: dict, audit: dict):
    """rec needs at least: website, phone, name, city, niche/category.
    Returns (score:int, reasons:str, tier:str)."""
    score, reasons = 0, []
    website = rec.get("website") or ""
    is_weak, why = is_weak_url(website)
    if not website:
        score += 60
        reasons.append("NO WEBSITE")
        tier = "A"
    elif is_weak:
        score += 40
        reasons.append(f"non-site link ({why})")
        tier = "A"
    else:
        tier = "C"
        if not audit.get("reachable"):
            score += 50
            reasons.append("Site listed but unreachable")
            tier = "A"
        else:
            if not audit.get("https"):
                score += 18
                reasons.append("HTTP only (no SSL)")
                tier = "B"
            if not audit.get("mobile_viewport"):
                score += 14
                reasons.append("Not mobile-friendly")
                tier = "B"
            if audit.get("load_ms") and audit["load_ms"] > 4000:
                score += 10
                reasons.append(f"Slow ({audit['load_ms']}ms)")
                tier = "B"
            if audit.get("builder") in ("Wix", "Weebly", "GoDaddy Sites", "Site123", "Jimdo"):
                score += 12
                reasons.append(f"DIY-builder ({audit['builder']})")
                tier = "B"
            if not reasons:
                reasons.append("Real site, no obvious issues")
    if rec.get("phone"):
        score += 4
        reasons.append("phone listed")
    return score, "; ".join(reasons), tier


def pitch_for(rec: dict, tier: str) -> str:
    website = rec.get("website") or ""
    niche = (rec.get("niche") or rec.get("category") or "business").lower()
    city = rec.get("city") or ""
    if not website:
        return (f"No website found. Pitch: a 1-page site that ranks for "
                f"'{niche} {city}' + click-to-call so phone leads stop going to competitors.")
    u = website.lower()
    if "yelp" in u:
        return "Yelp-only. Pitch: own your domain, stop paying Yelp ad fees to reach your own customers."
    if "facebook" in u or "instagram" in u:
        return "Social-only. Pitch: a real site ranks on Google; social should complement it, not replace it."
    if u.startswith("http://"):
        return "HTTP only — Chrome flags it 'Not secure'. Quick rebuild + SSL."
    return "Has a real site — verify quality manually before pitching."
