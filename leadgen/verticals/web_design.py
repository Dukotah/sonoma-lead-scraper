"""
Vertical: web-design leads — the repo's original use case, ported to the engine.

Target: local businesses with no website, a social-only presence, or a weak/slow
DIY site — i.e. good prospects for a web designer. Demonstrates that the engine
generalizes: same pipeline, totally different scoring.
"""
from __future__ import annotations

from .. import register, Vertical
from ..audit import audit_website, audit_html, is_weak_url, DIY_BUILDERS

CONFIG = {"diy_builders": DIY_BUILDERS}


def _enrich(rec: dict, ctx: dict) -> dict:
    site = rec.get("website") or ""
    if not site or is_weak_url(site)[0]:
        return rec                       # no real site to audit — scoring handles these
    # Demo mode: grade bundled fixture HTML offline, exactly as a live fetch would.
    demo_html = ctx.get("demo_html")
    if demo_html is not None:
        html = demo_html(site)
        rec["audit"] = audit_html(site, html) if html else None
    else:
        rec["audit"] = audit_website(site)
    return rec


def _score(rec: dict) -> tuple[int, str, str]:
    score, reasons = 0, []
    site = rec.get("website") or ""
    weak, why = is_weak_url(site)
    audit = rec.get("audit")           # None when enrichment was skipped (--no-enrich)
    if not site:
        score += 60; reasons.append("NO WEBSITE"); tier = "A"
    elif weak:
        score += 40; reasons.append(f"non-site link ({why})"); tier = "A"
    elif not audit:
        # Enrichment skipped (--no-enrich). We can't judge a live site without fetching
        # it — BUT one defect is provable from the URL string alone, no network: an
        # http:// URL has no SSL, which Chrome flags as "Not secure" in the address bar.
        # That's a real, sellable problem, so surface it as a Tier-B lead now. https
        # sites stay low-confidence until a full enrichment run can inspect them.
        if site.lower().startswith("http://"):
            score += 18; reasons.append("no HTTPS (http:// — Chrome flags 'Not secure')"); tier = "B"
        else:
            tier = "C"; reasons.append("has a site — not audited (run enrichment to grade)")
    else:
        tier = "C"
        if not audit.get("reachable"):
            score += 50; reasons.append("site unreachable"); tier = "A"
        else:
            if not audit.get("https"):
                score += 18; reasons.append("no HTTPS"); tier = "B"
            if not audit.get("mobile_viewport"):
                score += 14; reasons.append("not mobile-friendly"); tier = "B"
            if (audit.get("load_ms") or 0) > 4000:
                score += 10; reasons.append(f"slow ({audit['load_ms']}ms)"); tier = "B"
            if audit.get("builder") in CONFIG["diy_builders"]:
                score += 12; reasons.append(f"DIY ({audit['builder']})"); tier = "B"
            if not reasons:
                reasons.append("real site, no obvious issues")
    if rec.get("phone"):
        score += 4; reasons.append("phone listed")
    return score, tier, "; ".join(reasons)


def _opener(rec: dict) -> str:
    site = (rec.get("website") or "").lower()
    audit = rec.get("audit") or {}
    if not site:
        return f"No website — pitch a 1-page site ranking for '{rec.get('category','')} {rec.get('city','')}'."
    if "facebook" in site or "instagram" in site:
        return "Social-only — pitch a real site that ranks on Google."
    if site.startswith("http://"):
        return "HTTP only — Chrome flags it 'Not secure'. Quick rebuild + SSL."
    if audit.get("builder") in CONFIG["diy_builders"]:
        return f"DIY {audit['builder']} site — pitch a custom rebuild that loads faster and ranks better."
    return "Has a site — verify quality before pitching."


COLUMNS = [
    ("Tier", "tier"), ("Score", "score"), ("Business", "name"),
    ("Category", "category"), ("City", "city"), ("Phone", "phone"),
    ("Website", "website"), ("Why a lead", "why"), ("Pitch", "opener"),
    ("Address", "address"), ("Source", "source"), ("Source URL", "source_url"),
]

register(Vertical(
    key="web_design",
    label="Local businesses that need a website",
    description=("Finds local businesses with no website, a social-only page, or "
                 "a weak/outdated site — good prospects for web-design work."),
    overture_categories=[],          # all categories; broad by design
    osm_tags=["craft=plumber", "craft=electrician", "shop=car_repair",
              "shop=hairdresser", "amenity=restaurant", "office=lawyer"],
    keep_chains=False,               # chains don't buy from local web designers
    score_fn=_score,
    enrich_fn=_enrich,
    opener_fn=_opener,
    config=CONFIG,
    columns=COLUMNS,
))
