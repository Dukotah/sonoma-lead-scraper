"""
Generic enrichment helpers verticals call from their enrich_fn.

These add depth to a raw lead by visiting the business's own website:
  - fetch_pages():         homepage + a few candidate sub-pages that resolve
  - estimate_roster():     distinct-agent count (a volume proxy), de-duplicated
  - find_decision_maker(): a likely owner/manager name + title
  - find_phrases():        which of a phrase list appear (TC signals, hiring, …)

Nothing here is vertical-specific; the vertical supplies the paths/markers/titles.
The estimators are written to resist the two common traps: roster links counted
twice (image + name) and the same roster echoed in nav/footer across pages.
"""
from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

from .audit import fetch, hostname

# Anchor text / hrefs on the homepage that point at the pages worth reading for
# a brokerage: the roster, the team/about, and the contact page (for email/phone).
_LINK_KEYWORDS = ("agent", "team", "roster", "associate", "about", "contact",
                  "staff", "our-people", "meet", "join", "career")


def _discover_links(home_html: str, base_url: str, cap: int = 8) -> list[str]:
    """Pull same-site links from the homepage whose href or text suggests a
    roster/about/contact page. Catches sites whose pages don't match our static
    path guesses (e.g. /our-realtors, /the-team-2)."""
    base_host = hostname(base_url)
    found: list[str] = []
    seen: set[str] = set()
    for m in re.finditer(r'<a\b[^>]*href="([^"#]+)"[^>]*>(.*?)</a>',
                         home_html, re.IGNORECASE | re.DOTALL):
        href, text = m.group(1), re.sub(r"<[^>]+>", " ", m.group(2)).lower()
        hay = (href + " " + text).lower()
        if not any(k in hay for k in _LINK_KEYWORDS):
            continue
        url = urljoin(base_url, href)
        host = hostname(url)
        if host and host != base_host:   # stay on the business's own site
            continue
        key = url.rstrip("/").lower()
        if key in seen:
            continue
        seen.add(key)
        found.append(url)
        if len(found) >= cap:
            break
    return found


def fetch_pages(base_url: str, paths: list[str], cap: int = 4,
                discover: bool = True) -> dict[str, str]:
    """Return {url: html} for the homepage plus up to `cap` candidate sub-pages
    that actually resolve. Tries links discovered on the homepage first (most
    likely to be the real team/contact pages), then the static path guesses.
    Stops early once cap pages succeed."""
    out: dict[str, str] = {}
    if not base_url:
        return out
    home = fetch(base_url)
    base = base_url if base_url.startswith("http") else "http://" + base_url
    candidates: list[str] = []
    if home is not None and home.status_code < 400:
        out[base_url] = home.text
        if discover:
            candidates += _discover_links(home.text, base)
    candidates += [urljoin(base, p) for p in paths]

    seen = {u.rstrip("/").lower() for u in out}
    for url in candidates:
        if len(out) >= cap + 1:
            break
        if url.rstrip("/").lower() in seen:
            continue
        seen.add(url.rstrip("/").lower())
        r = fetch(url)
        if r is not None and r.status_code < 400 and len(r.text) > 500:
            out[url] = r.text
    return out


# ─────────────────────── contact extraction (fill CRM gaps) ───────────────────
_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
_PHONE_RE = re.compile(r"(?:\+?1[\s.\-]?)?\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4}")
_EMAIL_NOISE = ("noreply", "no-reply", "donotreply", "postmaster", "sentry",
                "wixpress", "example.", "@2x", ".png", ".jpg", ".gif", ".webp")


def extract_emails(pages: dict[str, str], prefer_host: str = "") -> list[str]:
    """Plausible contact emails found across the pages, best-first: an address on
    the business's own domain ranks above a gmail/yahoo; noise/system mailboxes
    are dropped. De-duplicated, lowercased."""
    prefer = (prefer_host or "").lower().lstrip("www.")
    owned, other = [], []
    seen: set[str] = set()
    for html in pages.values():
        for raw in _EMAIL_RE.findall(html):
            e = raw.lower()
            if e in seen or any(bad in e for bad in _EMAIL_NOISE):
                continue
            seen.add(e)
            dom = e.rsplit("@", 1)[1]
            (owned if prefer and (dom == prefer or dom.endswith("." + prefer)) else other).append(e)
    return owned + other


def extract_phones(pages: dict[str, str]) -> list[str]:
    """Distinct US-style phone numbers found across the pages (raw text form)."""
    seen: set[str] = set()
    out: list[str] = []
    for html in pages.values():
        text = re.sub(r"<[^>]+>", " ", html)
        for m in _PHONE_RE.findall(text):
            digits = re.sub(r"\D", "", m)
            if len(digits) == 11 and digits[0] == "1":
                digits = digits[1:]
            if len(digits) != 10 or digits in seen:
                continue
            seen.add(digits)
            out.append(m.strip())
    return out


# Agent-profile link patterns: /agent/slug, /agents/slug, /team/slug, /our-team/slug
_AGENT_HREF = re.compile(r'href="[^"]*/(?:agent|agents|team|our-team|associates?)/'
                         r'([a-z0-9][a-z0-9\-_]{1,60})/?["#?]', re.IGNORECASE)
# License numbers are a near-unique per-agent fingerprint.
_LICENSE = re.compile(r'(?:dre|calbre|lic|license|bre)\s*#?\s*(\d{6,8})', re.IGNORECASE)


def estimate_roster(pages: dict[str, str], extra_card_patterns: list[str] | None = None,
                    cap: int = 1000) -> int:
    """Best estimate of how many agents a brokerage has, de-duplicated.

    Strategy — take the strongest of three DISTINCT-count signals (not raw
    counts), so duplicate links (image + name → same slug) don't inflate it:
      1. distinct agent-profile slugs   (e.g. /agents/jane-smith/)
      2. distinct license numbers       (DRE/CalBRE #…)
      3. distinct names inside agent-card containers (fallback)
    Returns 0 when nothing is found (caller treats 0 as "unknown", not "zero").
    """
    slugs: set[str] = set()
    licenses: set[str] = set()
    for html in pages.values():
        for m in _AGENT_HREF.findall(html):
            slugs.add(m.lower())
        for m in _LICENSE.findall(html):
            licenses.add(m)

    best = max(len(slugs), len(licenses))

    # Fallback: count agent-card-like containers if links/licenses were sparse.
    if best < 2 and extra_card_patterns:
        for html in pages.values():
            h = html.lower()
            for pat in extra_card_patterns:
                best = max(best, len(re.findall(pat, h)))

    return min(best, cap)


def find_phrases(pages: dict[str, str], phrases: list[str]) -> list[str]:
    """Return the subset of `phrases` (lowercased match) present across pages."""
    blob = "\n".join(pages.values()).lower()
    return [p for p in phrases if p.lower() in blob]


# Title list is injected; we match a Name adjacent to one of those titles.
# NAME excludes '.' and digits so it can't bleed across a sentence boundary
# ("…Petaluma. Susan Park" → only "Susan Park" matches).
_NAME_RE = r"[A-Z][a-zA-Z'’\-]+(?:\s+[A-Z][a-zA-Z'’\-]+){1,2}"


def find_decision_maker(pages: dict[str, str], titles: list[str]) -> tuple[str, str]:
    """Find a 'Name, Title' / 'Title: Name' / 'Name — Title' decision-maker.
    More-senior titles win (the titles list is treated as a seniority order).
    Returns (name, title) or ('', '')."""
    ordered = list(dict.fromkeys(titles))  # preserve caller's seniority order
    # match longest titles first so 'broker/owner' isn't shadowed by 'broker'
    title_alt = "|".join(re.escape(t) for t in sorted(ordered, key=len, reverse=True))
    SEP = r"\s*[,–—\-:|]\s*"
    pat_name_title = re.compile(rf"({_NAME_RE}){SEP}({title_alt})\b", re.IGNORECASE)
    pat_title_name = re.compile(rf"\b({title_alt}){SEP}({_NAME_RE})", re.IGNORECASE)

    best = ("", "")
    best_rank = 10**9
    for html in pages.values():
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"\s+", " ", text)
        for is_name_first, pat in ((True, pat_name_title), (False, pat_title_name)):
            for m in pat.finditer(text):
                raw_name = m.group(1) if is_name_first else m.group(2)
                title = (m.group(2) if is_name_first else m.group(1)).strip(" .,-—–")
                name = _clean_name(raw_name)
                if not name:
                    continue
                rank = next((i for i, t in enumerate(ordered)
                             if t.lower() == title.lower()), len(ordered))
                if rank < best_rank:
                    best, best_rank = (name, title), rank
    return best


_NON_NAME_WORDS = {"our", "the", "meet", "team", "about", "contact", "broker",
                   "owner", "agent", "agents", "realtor", "realtors", "transaction",
                   "coordinator", "join", "careers", "home", "welcome", "us"}


def _clean_name(raw: str) -> str:
    """Trim a captured phrase to a plausible trailing personal name, dropping
    leading stop-words ('Team Greg Hall' → 'Greg Hall'). Returns '' if implausible."""
    parts = [p for p in raw.split() if p]
    # strip leading stop-words / lowercase leftovers
    while parts and parts[0].lower() in _NON_NAME_WORDS:
        parts.pop(0)
    # keep the last 3 tokens at most
    if len(parts) > 3:
        parts = parts[-3:]
    if not (2 <= len(parts) <= 3):
        return ""
    if any(p.lower() in _NON_NAME_WORDS for p in parts):
        return ""
    if not all(p[:1].isupper() for p in parts):
        return ""
    return " ".join(parts)


def primary_domain(url: str) -> str:
    return hostname(url)


# Back-compat: keep the old name as a thin wrapper (some callers/tests use it).
def count_matches(pages: dict[str, str], patterns: list[str], cap: int = 500) -> int:
    best = 0
    for html in pages.values():
        h = html.lower()
        for pat in patterns:
            best = max(best, len(re.findall(pat, h)))
    return min(best, cap)
