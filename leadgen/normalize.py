"""
Data-quality layer — clean and enrich the *values* on every lead so the engine's
live output matches the bar set by the bundled dataset (formatted phones, owned-
email detection, best-contact channel, completeness). Pure functions; no network.

Two entry points the pipeline calls:
  normalize_record(rec)  — clean name/website/email/phone in place (idempotent,
                           so it's safe to call again after enrichment adds fields)
  finalize_record(rec)   — derive email_owned / best_contact / completeness once
                           the contact fields are settled (i.e. after enrichment)
"""
from __future__ import annotations

import re

from .audit import hostname, is_weak_url


def _strip_www(host: str) -> str:
    h = (host or "").lower()
    return h[4:] if h.startswith("www.") else h

# ─────────────────────────────── names ───────────────────────────────────────
_ACRONYMS = {"llc", "inc", "re", "tc", "us", "usa", "ca", "kw", "bhhs", "exp",
             "c21", "era", "pllc", "pc"}


def clean_name(name: str) -> str:
    """Trim whitespace; convert SHOUTING names to Title Case while preserving
    short acronyms. 'JOHN REALTOR' → 'John Realtor'; 'RE/MAX GOLD' → 'RE/MAX Gold'."""
    n = re.sub(r"\s+", " ", (name or "").strip())
    if not n:
        return ""
    letters = re.sub(r"[^A-Za-z]", "", n)
    if letters and letters.isupper():  # all-caps → smart title case
        def fix(tok: str) -> str:
            core = re.sub(r"[^A-Za-z]", "", tok)
            if core.lower() in _ACRONYMS or len(core) <= 2:
                return tok
            return tok[:1].upper() + tok[1:].lower()
        n = " ".join(fix(t) for t in n.split(" "))
    return n


# ─────────────────────────────── phones ──────────────────────────────────────
def normalize_phone(raw: str) -> tuple[str, str]:
    """Return (formatted, area_code). US 10-digit → '(XXX) XXX-XXXX'; an 11-digit
    leading-1 is treated as US. Non-US / unparseable numbers pass through trimmed
    with an empty area code."""
    s = (raw or "").strip()
    if not s:
        return "", ""
    digits = re.sub(r"\D", "", s)
    if len(digits) == 11 and digits[0] == "1":
        digits = digits[1:]
    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}", digits[:3]
    return s, ""


# ─────────────────────────────── emails ──────────────────────────────────────
_EMAIL_RE = re.compile(r"[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}", re.IGNORECASE)
# Mailboxes that aren't a real human/sales contact.
_EMAIL_NOISE = ("noreply", "no-reply", "donotreply", "postmaster", "mailer-daemon",
                "sentry", "wixpress", "example.com", "domain.com", "email.com")


def clean_email(email: str) -> str:
    """Lowercase + validate. Returns '' if it isn't a plausible address or is a
    noreply/system mailbox (those aren't worth putting in front of a salesperson)."""
    e = (email or "").strip().lower()
    if not e or not _EMAIL_RE.fullmatch(e):
        return ""
    if any(bad in e for bad in _EMAIL_NOISE):
        return ""
    return e


def email_owned(email: str, website: str) -> int:
    """1 if the email's domain matches the business's own website domain (a real
    company mailbox, not a gmail/yahoo), else 0 — mirrors the bundled schema."""
    if not email or "@" not in email or not website:
        return 0
    dom = _strip_www(email.rsplit("@", 1)[1].lower())
    host = _strip_www(hostname(website))
    if not dom or not host:
        return 0
    return int(dom == host or host.endswith("." + dom) or dom.endswith("." + host))


# ─────────────────────────────── websites ────────────────────────────────────
_SOCIALS = {"facebook.com": "facebook", "fb.com": "facebook",
            "instagram.com": "instagram", "linkedin.com": "linkedin",
            "twitter.com": "twitter", "x.com": "twitter", "tiktok.com": "tiktok",
            "youtube.com": "youtube", "yelp.com": "yelp", "pinterest.com": "pinterest",
            "linktr.ee": "linktree", "nextdoor.com": "nextdoor"}


def normalize_website(url: str) -> str:
    """Canonicalize a URL for stable dedupe/display: ensure a scheme, lowercase the
    host, drop the fragment and a bare trailing slash. Leaves the path/query intact."""
    u = (url or "").strip()
    if not u:
        return ""
    u = u.split()[0]  # a stray "site.com (call first)" → just the URL
    if "://" not in u:
        u = "http://" + u
    from urllib.parse import urlsplit, urlunsplit
    try:
        p = urlsplit(u)
    except ValueError:
        return url.strip()
    host = (p.hostname or "").lower()
    if not host:
        return url.strip()
    netloc = host + (f":{p.port}" if p.port else "")
    path = p.path.rstrip("/") if p.path != "/" else ""
    return urlunsplit((p.scheme.lower(), netloc, path, p.query, ""))


def social_platform(url: str) -> str:
    host = hostname(url)
    for dom, plat in _SOCIALS.items():
        if host == dom or host.endswith("." + dom):
            return plat
    return ""


# ───────────────────────── record-level passes ───────────────────────────────
def normalize_record(rec: dict) -> dict:
    """Clean the contact fields in place. Idempotent — safe to call before dedupe
    and again after enrichment fills more fields."""
    rec["name"] = clean_name(rec.get("name", ""))
    rec["website"] = normalize_website(rec.get("website", ""))
    rec["email"] = clean_email(rec.get("email", ""))
    fmt, area = normalize_phone(rec.get("phone", ""))
    rec["phone"] = fmt
    rec["phone_fmt"] = fmt
    rec["area_code"] = area
    rec["social_platform"] = social_platform(rec.get("website", ""))
    return rec


# Weighted fields → a 0-100 "how callable/complete is this lead" score.
_COMPLETENESS_WEIGHTS = {"name": 10, "phone": 25, "email": 20, "website": 15,
                         "address": 10, "city": 5, "state": 5, "zip": 5, "lat": 5}


def completeness(rec: dict) -> int:
    return sum(w for f, w in _COMPLETENESS_WEIGHTS.items() if rec.get(f))


def best_contact(rec: dict) -> str:
    """Suggested outreach channel: phone | email | social | none — the field a
    salesperson should reach for first."""
    if rec.get("phone"):
        return "phone"
    if rec.get("email"):
        return "email"
    if rec.get("website") and is_weak_url(rec["website"])[0]:
        return "social"
    return "none"


def finalize_record(rec: dict) -> dict:
    """Derive the rollup quality fields once contact fields are settled (post-enrich)."""
    normalize_record(rec)  # re-clean anything enrichment added (email/phone)
    rec["email_owned"] = email_owned(rec.get("email", ""), rec.get("website", ""))
    rec["best_contact"] = best_contact(rec)
    rec["completeness"] = completeness(rec)
    return rec
