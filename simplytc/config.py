"""
SimplyTC lead-engine configuration.

This is the one file you edit to tune who gets called. Everything here is data,
not logic — the pipeline reads it. See DESIGN.md for the full plan.

NOTHING in COMPETITOR_TC_SEEDS or the fingerprint lists should be trusted blindly:
they ship as *starting points to verify and expand*. Your mom knows the real
competitor names in her market — adding them here is the single highest-leverage
edit you can make.
"""

# ─────────────────────────────────────────────────────────────────────────────
# 1. IDEAL CUSTOMER PROFILE
# ─────────────────────────────────────────────────────────────────────────────
ICP = {
    # Overture category substrings that mean "real-estate brokerage / agent".
    "overture_categories": ["real_estate"],
    # OSM tags for the same (used by the Overpass collector).
    "osm_tags": ["office=estate_agent", "shop=estate_agent"],

    # Volume gate: brokerages below this agent count are de-prioritized, not dropped
    # (a fast-growing 3-agent team can still need a TC — it just scores lower).
    "min_agents_preferred": 5,
    "sweet_spot_agents": (5, 50),

    # Franchise handling: keep but flag. A franchised *office* is often an
    # independently owned brokerage that still needs an outside TC.
    "suppress_franchise_corporate": True,   # drop obvious corporate HQ offices
    "keep_franchised_local_offices": True,  # but keep local franchise offices, flagged
}

# ─────────────────────────────────────────────────────────────────────────────
# 2. TARGET MARKETS  (national = swept metro-by-metro, not one giant query)
# Each entry is a bbox: (south, west, north, east). Get coords from bboxfinder.com.
# Start small, validate, then add metros. Sonoma is kept as a familiar test market.
# ─────────────────────────────────────────────────────────────────────────────
TARGET_MARKETS = {
    "sonoma_county_ca": (38.05, -123.55, 38.85, -122.35),   # test market (known data)
    # "phoenix_az":     (33.20, -112.40, 33.85, -111.80),
    # "tampa_fl":       (27.80, -82.65,  28.20, -82.30),
    # "austin_tx":      (30.10, -97.95,  30.52, -97.55),
    # … add the metros your mom wants to work, one validated batch at a time.
}

# ─────────────────────────────────────────────────────────────────────────────
# 3. COMPETITOR SUPPRESSION  (§5.1)
# Outsourced-TC companies whose public testimonial / "agents we serve" pages we
# scrape to build a suppression set of brokerages that ALREADY have a TC.
# ⚠️  PLACEHOLDERS — replace with the real competitors in your mom's markets.
# Format: "label": "https://their-site.com/testimonials"
# ─────────────────────────────────────────────────────────────────────────────
COMPETITOR_TC_SEEDS = {
    # "example_tc_co": "https://example-tc.com/testimonials",
    # "regional_tc":   "https://regional-tc.com/our-clients",
}

# ─────────────────────────────────────────────────────────────────────────────
# 4. TC-PRESENCE FINGERPRINTS  (§5.2)
# When we audit a brokerage's own website, these substrings (lowercased) in the
# page HTML/links suggest they already handle coordination.
# ─────────────────────────────────────────────────────────────────────────────

# Transaction-management SOFTWARE — uses tooling, may still lack a human TC.
TC_SOFTWARE_FINGERPRINTS = {
    "skyslope": "SkySlope",
    "dotloop": "Dotloop",
    "paperlesspipeline": "Paperless Pipeline",
    "brokermint": "Brokermint",
    "transactiondesk": "TransactionDesk",
    "open to close": "Open To Close",
    "transactly": "Transactly",
}

# Phrases that suggest an IN-HOUSE or already-contracted TC (a stronger "taken" tell).
IN_HOUSE_TC_PHRASES = [
    "transaction coordinator",
    "transaction coordination",
    "our transaction team",
    "in-house tc",
    "closing coordinator",
    "transaction management department",
]

# ─────────────────────────────────────────────────────────────────────────────
# 5. ENRICHMENT — pages we try per brokerage to estimate volume + find people.
# ─────────────────────────────────────────────────────────────────────────────
ROSTER_PAGE_PATHS = ["/agents", "/our-agents", "/team", "/our-team", "/agent-roster", "/about/team"]
LISTING_PAGE_PATHS = ["/listings", "/properties", "/our-listings", "/homes-for-sale"]
ABOUT_PAGE_PATHS = ["/about", "/about-us", "/our-story", "/contact"]

# Decision-maker titles to look for on About/Team pages.
DECISION_MAKER_TITLES = [
    "broker", "broker/owner", "owner", "designated broker",
    "managing broker", "office manager", "team lead", "principal",
]

# ─────────────────────────────────────────────────────────────────────────────
# 6. SCORING WEIGHTS  (§6) — tune to taste.
# ─────────────────────────────────────────────────────────────────────────────
SCORE_WEIGHTS = {
    "per_agent": 1.0,        # × agent count, capped
    "volume_cap": 50,
    "gap_open": 40,
    "gap_software": 20,
    "gap_in_house": 5,
    "gap_confirmed": 0,
    "has_phone": 5,
    "has_decision_maker": 5,
    "suppression_penalty": -100,
}

# Tier thresholds on the final tc_fit_score.
TIER_A_MIN = 55
TIER_B_MIN = 30
