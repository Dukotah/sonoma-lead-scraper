"""
TC-fit scoring (DESIGN.md §6) — adapts data-kit/lead_tools.py::score_lead(), which
scored *website quality*, into scoring *transaction-coordinator fit*.

score_lead_tc(rec) expects an enriched record with (any may be missing):
    name, phone, website, city, state, address,
    agent_count   : int   (0 = unknown)
    tc_gap        : "open" | "software" | "in_house" | "confirmed"
    decision_maker: str | None
    suppressed    : bool  (True if name matched competitor suppression set)

Returns (score:int, tier:str, reasons:str).
"""
from __future__ import annotations

import config


def _volume_score(agent_count: int) -> tuple[int, str]:
    w = config.SCORE_WEIGHTS
    if not agent_count:
        return 0, "volume unknown"
    raw = min(int(agent_count * w["per_agent"]), w["volume_cap"])
    return raw, f"{agent_count} agents (vol {raw})"


def _gap_score(tc_gap: str) -> tuple[int, str]:
    w = config.SCORE_WEIGHTS
    return {
        "open":      (w["gap_open"],      "no TC detected — OPEN"),
        "software":  (w["gap_software"],  "uses TM software, maybe no human TC"),
        "in_house":  (w["gap_in_house"],  "in-house TC signals"),
        "confirmed": (w["gap_confirmed"], "confirmed competitor client"),
    }.get(tc_gap, (0, "TC status unknown"))


def score_lead_tc(rec: dict) -> tuple[int, str, str]:
    w = config.SCORE_WEIGHTS
    score = 0
    reasons: list[str] = []

    v, vr = _volume_score(rec.get("agent_count", 0))
    score += v
    reasons.append(vr)

    g, gr = _gap_score(rec.get("tc_gap", "unknown"))
    score += g
    reasons.append(gr)

    if rec.get("phone"):
        score += w["has_phone"]
        reasons.append("phone listed")
    if rec.get("decision_maker"):
        score += w["has_decision_maker"]
        reasons.append(f"contact: {rec['decision_maker']}")

    if rec.get("suppressed"):
        score += w["suppression_penalty"]
        reasons.append("SUPPRESSED — already has a TC")

    if score >= config.TIER_A_MIN:
        tier = "A"
    elif score >= config.TIER_B_MIN:
        tier = "B"
    else:
        tier = "C"
    return score, tier, "; ".join(reasons)


def suggested_opener(rec: dict) -> str:
    """SimplyTC analog of lead_tools.pitch_for() — a one-line call opener."""
    n = rec.get("agent_count") or 0
    size = f"{n}-agent " if n else ""
    gap = rec.get("tc_gap")
    if gap == "open":
        return (f"{size}brokerage, no TC software detected — open: do your agents "
                f"still handle their own contract-to-close paperwork?")
    if gap == "software":
        sw = rec.get("tc_software") or "TM software"
        return (f"{size}brokerage on {sw} — the software still needs a human to run "
                f"it; is a person actually coordinating each file?")
    if gap == "in_house":
        return f"{size}brokerage with in-house coordination — pitch overflow/coverage when their TC is slammed."
    return f"{size}brokerage — verify TC status on the call."
