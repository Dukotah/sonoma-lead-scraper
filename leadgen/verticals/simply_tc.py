"""
Vertical: SimplyTC — transaction-coordinator leads.

Target: real-estate brokerages / teams / producing agents who likely need a TC
and AREN'T already using a competing TC company (simplytc.com's business).

This wires three things into the engine:
  1. competitor suppression  — scrape rival TC companies' client/testimonial pages
                               and sink any brokerage already on one (DESIGN.md §5.1)
  2. TC-presence fingerprint — inspect each brokerage site for in-house/software TC
  3. volume estimate         — agent-roster size as a "needs a TC" proxy

Everything tunable lives in CONFIG. The single highest-value edit is filling in
COMPETITOR_TC_SEEDS with the real rival TC firms in your mom's markets.
"""
from __future__ import annotations

from .. import register, Vertical
from ..enrich import fetch_pages, count_matches, find_decision_maker
from ..suppression import build_suppression_set

# ─────────────────────────────── CONFIG ──────────────────────────────────────
CONFIG = {
    # Rival TC companies whose published client/testimonial pages we scrape to find
    # brokerages that ALREADY have a TC. ⚠️ PLACEHOLDERS — add the real ones.
    "competitor_tc_seeds": {
        # "transactly":        "https://transactly.com/testimonials",
        # "my_tc_company":     "https://example-tc.com/our-clients",
    },

    # TM SOFTWARE fingerprints (uses tooling — may still lack a human TC → pitchable).
    "tc_software": {
        "skyslope": "SkySlope", "dotloop": "Dotloop",
        "paperlesspipeline": "Paperless Pipeline", "brokermint": "Brokermint",
        "transactiondesk": "TransactionDesk", "transactly": "Transactly",
        "open to close": "Open To Close",
    },
    # Phrases suggesting an IN-HOUSE / already-contracted TC (stronger "taken" tell).
    "in_house_tc_phrases": [
        "transaction coordinator", "transaction coordination", "our transaction team",
        "in-house tc", "closing coordinator", "transaction management department",
    ],

    # Enrichment: pages we try, and what counts as an "agent card" (volume proxy).
    "roster_paths": ["/agents", "/our-agents", "/team", "/our-team",
                     "/agent-roster", "/about/team", "/meet-the-team"],
    "agent_card_patterns": [r'href="[^"]*/agent[s]?/', r"dre\s*#|license\s*#|lic\s*#",
                            r'class="[^"]*agent[-_ ]?card'],
    "decision_maker_titles": ["broker/owner", "designated broker", "managing broker",
                              "broker", "owner", "office manager", "team lead", "principal"],

    # Scoring weights / tiers.
    "weights": {"per_agent": 1.0, "volume_cap": 50, "gap_open": 40, "gap_software": 20,
                "gap_in_house": 5, "has_phone": 5, "has_contact": 5,
                "suppression_penalty": -100},
    "tier_a_min": 55, "tier_b_min": 30,
}


# ─────────────────────────── suppression hook ────────────────────────────────
def _suppression(config: dict) -> dict:
    seeds = config.get("competitor_tc_seeds") or {}
    if not seeds:
        return {}
    return build_suppression_set(seeds)


# ──────────────────────────── enrichment hook ────────────────────────────────
def _fingerprint_tc(html_blob: str, config: dict) -> dict:
    h = (html_blob or "").lower()
    for phrase in config["in_house_tc_phrases"]:
        if phrase in h:
            return {"tc_gap": "in_house", "tc_software": "", "evidence": phrase}
    for sig, label in config["tc_software"].items():
        if sig in h:
            return {"tc_gap": "software", "tc_software": label, "evidence": label}
    return {"tc_gap": "open", "tc_software": "", "evidence": ""}


def _enrich(rec: dict, ctx: dict) -> dict:
    config = ctx["config"]
    website = rec.get("website") or ""
    if not website:
        rec["tc_gap"] = "unknown"
        rec["agent_count"] = 0
        return rec
    pages = fetch_pages(website, config["roster_paths"])
    blob = "\n".join(pages.values())
    rec["agent_count"] = count_matches(pages, config["agent_card_patterns"])
    fp = _fingerprint_tc(blob, config)
    rec.update(fp)
    name, title = find_decision_maker(pages, config["decision_maker_titles"])
    rec["decision_maker"] = name
    rec["dm_title"] = title
    return rec


# ─────────────────────────────── scoring ─────────────────────────────────────
def _score(rec: dict) -> tuple[int, str, str]:
    w = CONFIG["weights"]
    score, reasons = 0, []

    ac = rec.get("agent_count") or 0
    if ac:
        v = min(int(ac * w["per_agent"]), w["volume_cap"])
        score += v
        reasons.append(f"{ac} agents (vol {v})")
    else:
        reasons.append("volume unknown")

    gap = rec.get("tc_gap", "unknown")
    gscore = {"open": w["gap_open"], "software": w["gap_software"],
              "in_house": w["gap_in_house"]}.get(gap, 0)
    score += gscore
    reasons.append({"open": "no TC detected — OPEN",
                    "software": f"uses {rec.get('tc_software') or 'TM software'}",
                    "in_house": "in-house TC signals",
                    "unknown": "TC status unknown"}.get(gap, "TC status unknown"))

    if rec.get("phone"):
        score += w["has_phone"]; reasons.append("phone")
    if rec.get("decision_maker"):
        score += w["has_contact"]; reasons.append(f"contact: {rec['decision_maker']}")

    if rec.get("suppressed"):
        score += w["suppression_penalty"]
        reasons.append(f"SUPPRESSED — client of {rec.get('suppressed_by','competitor')}")

    if score >= CONFIG["tier_a_min"]:
        tier = "A"
    elif score >= CONFIG["tier_b_min"]:
        tier = "B"
    else:
        tier = "C"
    return score, tier, "; ".join(reasons)


def _opener(rec: dict) -> str:
    n = rec.get("agent_count") or 0
    size = f"{n}-agent " if n else ""
    gap = rec.get("tc_gap")
    if rec.get("suppressed"):
        return f"Already with {rec.get('suppressed_by','a competitor')} — revisit on contract churn."
    if gap == "open":
        return (f"{size}brokerage, no TC detected — opener: are your agents still "
                f"doing their own contract-to-close paperwork?")
    if gap == "software":
        return (f"{size}brokerage on {rec.get('tc_software','TM software')} — the software "
                f"still needs a human; is a person actually running each file?")
    if gap == "in_house":
        return f"{size}brokerage with in-house coordination — pitch overflow/coverage."
    return f"{size}brokerage — verify TC status on the call."


COLUMNS = [
    ("Tier", "tier"), ("Score", "score"), ("Brokerage", "name"),
    ("Decision-maker", "decision_maker"), ("Title", "dm_title"),
    ("Phone", "phone"), ("Email", "email"), ("Website", "website"),
    ("City", "city"), ("State", "state"), ("Address", "address"),
    ("# Agents (est.)", "agent_count"), ("TC gap", "tc_gap"),
    ("TC software", "tc_software"), ("Already has TC?", "suppressed_by"),
    ("Why a lead", "why"), ("Suggested opener", "opener"),
    ("Source", "source"), ("Source URL", "source_url"),
]

register(Vertical(
    key="simply_tc",
    label="Transaction-coordinator leads (SimplyTC)",
    overture_categories=["real_estate"],
    osm_tags=["office=estate_agent", "shop=estate_agent"],
    keep_chains=True,          # a franchised office can still be an independent brokerage
    score_fn=_score,
    enrich_fn=_enrich,
    opener_fn=_opener,
    suppression_fn=_suppression,
    config=CONFIG,
    columns=COLUMNS,
))
