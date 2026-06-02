"""
HTTP + website auditing — shared, vertical-agnostic. Consolidated from the proven
logic in data-kit/lead_tools.py and legacy/scraper-gui/app.py (polite UA, timeout,
retry, builder/SSL/mobile checks) so every vertical fetches the same safe way.
"""
from __future__ import annotations

import re
import time
from typing import Optional
from urllib.parse import urlparse, unquote

import requests

UA = "LeadGen/1.0 (+contact: dukotah@gmail.com)"
AUDIT_TIMEOUT = 6

# Domains that mean "no real website" — a social/listing page, not an owned site.
WEAK_DOMAINS = (
    "yelp.com", "yelp.to", "facebook.com", "fb.com", "instagram.com",
    "yellowpages.com", "localsearch.com", "google.com", "youtube.com",
    "linkedin.com", "twitter.com", "x.com", "tiktok.com", "pinterest.com",
    "groupon.com", "nextdoor.com", "linktr.ee", "linktree.com",
    "business.site", "wixsite.com", "mapquest.com", "tripadvisor.com",
)

# Hosts that appear in search results but are never a business's own site.
DIRECTORY_HOSTS = WEAK_DOMAINS + (
    "wikipedia.org", "bbb.org", "manta.com", "chamberofcommerce.com",
    "indeed.com", "glassdoor.com", "apple.com", "bing.com", "duckduckgo.com",
    "amazon.com", "doordash.com", "ubereats.com", "grubhub.com", "opentable.com",
    "zillow.com", "realtor.com", "redfin.com", "trulia.com", "homes.com",
)


def hostname(url: str) -> str:
    if not url:
        return ""
    u = url if "://" in url else "http://" + url
    try:
        return (urlparse(u).hostname or "").lower()
    except Exception:
        return ""


def is_weak_url(url: str) -> tuple[bool, str]:
    """(is_weak, matched_domain). Matches on host boundary, not substring, so
    "x.com" won't flag "fedex.com"."""
    if not url:
        return True, "no website"
    host = hostname(url)
    for d in WEAK_DOMAINS:
        if host == d or host.endswith("." + d):
            return True, d
    return False, ""


def fetch(url: str, timeout: int = AUDIT_TIMEOUT) -> Optional["requests.Response"]:
    """GET a URL politely; return the Response or None on any failure."""
    if not url:
        return None
    if not url.startswith("http"):
        url = "http://" + url
    try:
        return requests.get(url, headers={"User-Agent": UA},
                            timeout=timeout, allow_redirects=True)
    except Exception:
        return None


def audit_website(url: str) -> dict:
    """Fetch a homepage and report basic quality signals (HTTPS/mobile/load/builder)."""
    out = {"reachable": False, "https": False, "load_ms": None,
           "mobile_viewport": False, "builder": "", "title": "",
           "size_kb": None, "html": "", "audit_notes": []}
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
        out["html"] = r.text  # kept so verticals can fingerprint without re-fetching
        _audit_from_html(out, r.text)
    except requests.exceptions.SSLError:
        out["audit_notes"].append("SSL / broken cert")
    except requests.exceptions.Timeout:
        out["audit_notes"].append(f"Timeout (>{AUDIT_TIMEOUT}s)")
    except Exception as e:
        out["audit_notes"].append(f"Unreachable: {type(e).__name__}")
    return out


# DIY site builders that signal a low-investment site a designer could rebuild.
DIY_BUILDERS = ("Wix", "Weebly", "GoDaddy Sites", "Site123", "Jimdo")


def _audit_from_html(out: dict, html_text: str) -> dict:
    """Derive viewport / title / builder signals + notes from page HTML into `out`.
    Shared by the live fetch (audit_website) and the offline demo path (audit_html),
    so both report identical signals. Assumes `out` already has https/load_ms set."""
    html = (html_text or "")[:50000].lower()
    if 'name="viewport"' in html:
        out["mobile_viewport"] = True
    tm = re.search(r"<title>([^<]+)</title>", html_text or "", re.IGNORECASE)
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
    if (out.get("load_ms") or 0) > 4000:
        out["audit_notes"].append(f"Slow load ({out['load_ms']}ms)")
    if not out["mobile_viewport"]:
        out["audit_notes"].append("No mobile viewport")
    if not out["https"]:
        out["audit_notes"].append("No HTTPS")
    if out["builder"] in DIY_BUILDERS:
        out["audit_notes"].append(f"DIY-builder ({out['builder']})")
    return out


def audit_html(url: str, html: str, load_ms: int = 800) -> dict:
    """Audit a page from already-fetched HTML — no network. Used by demo mode and
    tests so the web-design vertical can grade fixture pages exactly as it would a
    live fetch. `https` is inferred from the URL scheme; the page is assumed reachable."""
    out = {"reachable": True, "https": (url or "").startswith("https://"),
           "load_ms": load_ms, "mobile_viewport": False, "builder": "", "title": "",
           "size_kb": round(len(html or "") / 1024, 1), "html": html or "",
           "audit_notes": []}
    return _audit_from_html(out, html or "")


def _name_tokens(name: str) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9]+", (name or "").lower()) if len(t) > 2]


def web_verify(name: str, city: str = "", state: str = "", retries: int = 2) -> dict:
    """Web-search a business to find its real (owned) website.

    Returns {searched, likely_site, directory_hits, verdict}, where verdict is
    'has_site' | 'no_site_found' | 'throttled' | 'unknown'. DuckDuckGo's HTML
    endpoint soft-throttles bursts (HTTP 202); we back off and return 'throttled'
    rather than falsely reporting 'no site'.
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
            time.sleep(2.5 * (attempt + 1))
            continue
        break
    if html is None:
        out["verdict"] = "throttled"
        return out
    out["searched"] = True

    hrefs = re.findall(r'class="result__a"[^>]*href="([^"]+)"', html)
    tokens = set(_name_tokens(name))
    for raw in hrefs[:10]:
        m = re.search(r"uddg=([^&]+)", raw)
        target = unquote(m.group(1)) if m else raw
        host = hostname(target)
        if not host:
            continue
        if any(host == d or host.endswith("." + d) for d in DIRECTORY_HOSTS):
            out["directory_hits"].append(host)
            continue
        host_core = host.replace("www.", "").split(".")[0]
        if tokens and any(t in host_core or host_core in t for t in tokens):
            out["likely_site"] = target
            break
        if out["likely_site"] is None:
            out["likely_site"] = target

    if out["likely_site"]:
        out["verdict"] = "has_site"
    elif out["searched"]:
        out["verdict"] = "no_site_found"
    return out
