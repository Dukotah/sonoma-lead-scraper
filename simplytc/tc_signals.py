"""
TC-presence signals — the genuinely new logic for SimplyTC (DESIGN.md §5).

This module answers "do they already have a TC?" two ways:
  - build_suppression_set()  : scrape competitor testimonial pages → names to drop
  - fingerprint_tc(html)     : inspect a brokerage's own site for TC tells
  - estimate_agent_count(html): volume proxy from a roster page (DESIGN.md §4)

It deliberately reuses the audit/fetch plumbing already proven in
`data-kit/lead_tools.py` (polite UA, timeout, builder-fingerprint pattern) rather
than reinventing HTTP handling. These are STUBS with finished signatures and the
intended behavior documented — fill the bodies in Phase 1.
"""
from __future__ import annotations

import re

import config  # simplytc/config.py


def fingerprint_tc(html: str) -> dict:
    """Inspect a brokerage homepage's HTML for signs they already coordinate deals.

    Returns:
        {
          "tc_gap":      "open" | "software" | "in_house",
          "software":    str | None,   # detected TM software name, if any
          "evidence":    list[str],    # matched phrases/software, for the call notes
        }

    Logic (mirrors lead_tools.audit_website's builder fingerprinting):
      1. lowercase html
      2. if any IN_HOUSE_TC_PHRASES present     -> "in_house"
      3. elif any TC_SOFTWARE_FINGERPRINTS hit  -> "software" (+ which)
      4. else                                   -> "open"   (best leads)
    """
    h = (html or "").lower()
    evidence: list[str] = []

    for phrase in config.IN_HOUSE_TC_PHRASES:
        if phrase in h:
            evidence.append(phrase)
    if evidence:
        return {"tc_gap": "in_house", "software": None, "evidence": evidence}

    for sig, label in config.TC_SOFTWARE_FINGERPRINTS.items():
        if sig in h:
            return {"tc_gap": "software", "software": label, "evidence": [label]}

    return {"tc_gap": "open", "software": None, "evidence": []}


def estimate_agent_count(roster_html: str) -> int:
    """Rough agent count from a roster/team page — a volume proxy (DESIGN.md §4).

    STUB. Intended approach (cheap and good-enough):
      - count repeated agent-card markers: links to /agent/, /agents/, mailto:,
        'DRE #', 'License #', or repeated profile-image blocks.
      - take the max of a few heuristics, cap at a sane ceiling.
    Returns 0 when unknown (caller treats 0 as "volume unknown", not "no volume").
    """
    if not roster_html:
        return 0
    h = roster_html.lower()
    candidates = [
        len(re.findall(r'href="[^"]*/agent[s]?/', h)),
        len(re.findall(r"dre\s*#|license\s*#|lic\s*#", h)),
        len(re.findall(r"mailto:", h)),
    ]
    return min(max(candidates), 500)  # cap guards against nav/footer noise


def build_suppression_set(competitor_seeds: dict | None = None) -> set[str]:
    """Scrape competitor TC testimonial/client pages → normalized brokerage names
    that ALREADY have a TC (DESIGN.md §5.1).

    STUB. Intended approach:
      - for each url in config.COMPETITOR_TC_SEEDS:
          fetch politely (reuse lead_tools fetch pattern), extract candidate
          brokerage/agent names from testimonial blocks (quoted author lines,
          'agents we serve' lists, client logos' alt text).
      - normalize each name (see norm()) and add to the set.
    Returns a set of normalized names; the scorer applies suppression_penalty to
    any lead whose normalized name is in this set.
    """
    seeds = competitor_seeds if competitor_seeds is not None else config.COMPETITOR_TC_SEEDS
    suppressed: set[str] = set()
    # TODO(phase1): fetch + parse each seed page; add norm(name) for each client.
    _ = seeds
    return suppressed


def norm(name: str) -> str:
    """Normalized key for matching names across sources (same convention as
    enrich_leads.norm)."""
    return re.sub(r"[^a-z0-9]+", "", (name or "").lower())
