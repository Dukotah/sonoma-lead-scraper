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
from ..enrich import fetch_pages, estimate_roster, find_decision_maker, find_phrases
from ..suppression import build_suppression_set

# ─────────────────────────────── CONFIG ──────────────────────────────────────
CONFIG = {
    # Rival TC companies whose published client/testimonial pages we scrape to find
    # brokerages that ALREADY have a TC. Seeded from web research (June 2026) —
    # VERIFY each URL resolves and review the scraped names before relying on them.
    # Put your mom's known local rivals at the top; "Real Estate Paper Pushers"
    # is the most direct competitor (it operates in Sonoma County too).
    "competitor_tc_seeds": {
        # — Direct / regional (California & Sonoma County) —
        "real_estate_paper_pushers": "https://realestatepaperpushers.com/",
        "real_estate_paper_pushers_sonoma": "https://realestatepaperpushers.com/California/Sonoma-County",
        "california_tc": "https://www.californiatc.net/",
        # — National players (publish agent/brokerage testimonials) —
        "coordinator_team": "https://coordinatorteam.com/",
        "premier_tc_services": "https://www.premiertcsvc.com/",
        "transactly": "https://transactly.com/",
        "xact_tc": "https://www.xact-tc.com/",
        "be_happy_tc": "https://www.behappytc.com/",
        "agentup": "https://www.agentup.com/",
        "myoutdesk": "https://www.myoutdesk.com/services/transaction-coordinator/",
        "freedom_res": "https://www.freedom-res.com/transaction-coordinator-for-brokers/",
        "tctor": "https://tctor.com/",
        "taylor_tc": "https://www.taylortcexpert.com/",
        # Add more rivals you know of — one "label": "URL" per line.
    },

    # TM SOFTWARE fingerprints (uses tooling — may still lack a human TC → pitchable).
    "tc_software": {
        "skyslope": "SkySlope", "dotloop": "Dotloop",
        "paperlesspipeline": "Paperless Pipeline", "brokermint": "Brokermint",
        "transactiondesk": "TransactionDesk", "transactly": "Transactly",
        "open to close": "Open To Close", "brokerwolf": "BrokerWOLF",
    },
    # Phrases that say they're HIRING a TC → they need help NOW (a hot lead, not taken).
    # Checked BEFORE in-house phrases, because "hiring a transaction coordinator"
    # also contains "transaction coordinator".
    "hiring_tc_phrases": [
        "hiring a transaction coordinator", "we are hiring a transaction coordinator",
        "seeking a transaction coordinator", "transaction coordinator wanted",
        "now hiring transaction coordinator", "transaction coordinator position",
        "join our team as a transaction coordinator",
    ],
    # Phrases suggesting an IN-HOUSE / already-contracted TC (a "taken" tell).
    "in_house_tc_phrases": [
        "our transaction coordinator", "in-house transaction coordinator",
        "our in-house tc", "transaction coordination team", "our transaction team",
        "closing coordinator", "transaction management department",
        "our tc handles", "dedicated transaction coordinator",
    ],

    # Enrichment: pages we try, and a fallback "agent card" container pattern.
    "roster_paths": ["/agents", "/our-agents", "/team", "/our-team", "/agent-roster",
                     "/about/team", "/meet-the-team", "/associates", "/realtors",
                     "/careers", "/join", "/about", "/contact"],
    "agent_card_patterns": [r'class="[^"]*agent[-_ ]?card', r'class="[^"]*team[-_ ]?member',
                            r'class="[^"]*roster[-_ ]?item'],
    "decision_maker_titles": ["broker/owner", "broker / owner", "designated broker",
                              "managing broker", "principal broker", "owner/broker",
                              "broker associate", "office manager", "team lead",
                              "principal", "broker", "owner"],

    # Scoring weights / tiers.
    "weights": {"per_agent": 1.2, "volume_cap": 50, "gap_open": 35, "gap_hiring": 50,
                "gap_software": 20, "gap_in_house": 5, "has_phone": 5, "has_contact": 8,
                "suppression_penalty": -100},
    "tier_a_min": 55, "tier_b_min": 30,
}


# ─────────────────────────── suppression hook ────────────────────────────────
def _suppression(config: dict) -> dict:
    seeds = config.get("competitor_tc_seeds") or {}
    # Accept either {label: url} (config file) or [url, url, ...] (GUI textarea).
    if isinstance(seeds, (list, tuple, set)):
        from urllib.parse import urlparse
        seeds = {(urlparse(u).hostname or f"competitor_{i}"): u
                 for i, u in enumerate(seeds) if u and u.strip()}
    if not seeds:
        return {}
    return build_suppression_set(seeds)


# ──────────────────────────── enrichment hook ────────────────────────────────
def fingerprint_tc(pages: dict, config: dict) -> dict:
    """Classify a brokerage's TC situation from its fetched pages.

    Priority order matters:
      1. HIRING a TC      → 'hiring'  (they need help now — the hottest gap)
      2. IN-HOUSE TC      → 'in_house'(already covered by a person)
      3. TM SOFTWARE      → 'software'(tooling, maybe no human — still pitchable)
      4. nothing          → 'open'    (no signal — strong lead)
    """
    hiring = find_phrases(pages, config["hiring_tc_phrases"])
    if hiring:
        return {"tc_gap": "hiring", "tc_software": "", "tc_evidence": hiring[0]}
    in_house = find_phrases(pages, config["in_house_tc_phrases"])
    if in_house:
        return {"tc_gap": "in_house", "tc_software": "", "tc_evidence": in_house[0]}
    blob = "\n".join(pages.values()).lower()
    for sig, label in config["tc_software"].items():
        if sig in blob:
            return {"tc_gap": "software", "tc_software": label, "tc_evidence": label}
    return {"tc_gap": "open", "tc_software": "", "tc_evidence": ""}


def _enrich(rec: dict, ctx: dict) -> dict:
    config = ctx["config"]
    website = rec.get("website") or ""
    if not website:
        rec["tc_gap"] = "unknown"
        rec["agent_count"] = 0
        rec["enrich_note"] = "no website to inspect"
        return rec
    # Demo mode: enrich from bundled fixture HTML instead of fetching the network.
    demo_html = ctx.get("demo_html")
    if demo_html is not None:
        pages = {website: demo_html(website)}
    else:
        pages = fetch_pages(website, config["roster_paths"])
    if not pages or not any(pages.values()):
        rec["tc_gap"] = "unknown"
        rec["agent_count"] = 0
        rec["enrich_note"] = "site unreachable"
        return rec
    rec["agent_count"] = estimate_roster(pages, config["agent_card_patterns"])
    rec.update(fingerprint_tc(pages, config))
    name, title = find_decision_maker(pages, config["decision_maker_titles"])
    rec["decision_maker"] = name
    rec["dm_title"] = title
    rec["enrich_note"] = f"read {len(pages)} page(s)"
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
    gscore = {"hiring": w["gap_hiring"], "open": w["gap_open"],
              "software": w["gap_software"], "in_house": w["gap_in_house"]}.get(gap, 0)
    score += gscore
    reasons.append({"hiring": "HIRING a TC — needs help now",
                    "open": "no TC detected — OPEN",
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
    if gap == "hiring":
        return (f"{size}brokerage actively hiring a TC — opener: instead of hiring, "
                f"salary + benefits, you can outsource per-file to SimplyTC today.")
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
    description=("Real-estate brokerages/teams that likely need a transaction "
                 "coordinator and aren't already using a competing TC company."),
    overture_categories=["real_estate"],
    osm_tags=["office=estate_agent", "shop=estate_agent"],
    keep_chains=True,          # a franchised office can still be an independent brokerage
    score_fn=_score,
    enrich_fn=_enrich,
    opener_fn=_opener,
    suppression_fn=_suppression,
    config=CONFIG,
    competitor_input={
        "config_key": "competitor_tc_seeds",
        "label": "Competitor TC company pages (one URL per line)",
        "help": ("Paste the testimonial / 'clients we serve' page URL for each rival "
                 "transaction-coordination company. We scrape them to skip brokerages "
                 "already using a competitor."),
    },
    columns=COLUMNS,
))
