"""
Generic enrichment helpers verticals can call from their enrich_fn.

These add depth to a raw lead by visiting the business's own website:
  - fetch_pages():        grab homepage + a few candidate sub-pages
  - count_matches():      count a marker across pages (e.g. agent cards) → volume
  - find_decision_maker(): pull a likely owner/manager name + title
Nothing here is vertical-specific; the vertical decides which paths/titles matter.
"""
from __future__ import annotations

import re
from urllib.parse import urljoin

from .audit import fetch, hostname


def fetch_pages(base_url: str, paths: list[str], cap: int = 4) -> dict[str, str]:
    """Return {url: html} for the homepage plus up to `cap` candidate sub-pages
    that actually resolve. Stops early once cap pages succeed."""
    out: dict[str, str] = {}
    if not base_url:
        return out
    home = fetch(base_url)
    if home is not None and home.status_code < 400:
        out[base_url] = home.text
    for p in paths:
        if len(out) >= cap + 1:
            break
        url = urljoin(base_url if base_url.startswith("http") else "http://" + base_url, p)
        r = fetch(url)
        if r is not None and r.status_code < 400 and len(r.text) > 500:
            out[url] = r.text
    return out


def count_matches(pages: dict[str, str], patterns: list[str], cap: int = 500) -> int:
    """Max count of any regex pattern across all fetched pages — a volume proxy.
    Using max (not sum) avoids double-counting the same roster echoed in nav."""
    best = 0
    for html in pages.values():
        h = html.lower()
        for pat in patterns:
            best = max(best, len(re.findall(pat, h)))
    return min(best, cap)


def find_decision_maker(pages: dict[str, str], titles: list[str]) -> tuple[str, str]:
    """Look for 'Name, Title' or 'Title: Name' near one of the target titles.
    Returns (name, title) or ('', '')."""
    title_alt = "|".join(re.escape(t) for t in titles)
    # "Jane Doe, Managing Broker"  /  "Managing Broker: Jane Doe"  / "Jane Doe – Broker/Owner"
    pats = [
        re.compile(r"([A-Z][a-z]+(?:\s+[A-Z][a-z.'-]+){1,2})\s*[,–—-]\s*(" + title_alt + r")",
                   re.IGNORECASE),
        re.compile(r"(" + title_alt + r")\s*[:–—-]\s*([A-Z][a-z]+(?:\s+[A-Z][a-z.'-]+){1,2})",
                   re.IGNORECASE),
    ]
    for html in pages.values():
        text = re.sub(r"<[^>]+>", " ", html)
        for i, pat in enumerate(pats):
            m = pat.search(text)
            if m:
                a, b = m.group(1).strip(), m.group(2).strip()
                # pattern 0 = (name, title); pattern 1 = (title, name)
                return (a, b) if i == 0 else (b, a)
    return "", ""


def primary_domain(url: str) -> str:
    return hostname(url)
