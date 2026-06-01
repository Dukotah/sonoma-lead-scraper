"""
The Vertical spec + registry.

A Vertical is a plain dataclass describing one prospecting use case. The engine
reads it; you never subclass anything. Two are shipped (web_design, simply_tc);
add a third by writing one file in verticals/ and calling register().

Hook functions all take/return plain dicts so verticals stay simple and testable:

    enrich_fn(rec, ctx)  -> mutates/returns rec with extra fields  (optional)
    score_fn(rec)        -> (score:int, tier:str, reasons:str)     (required)
    opener_fn(rec)       -> str  call/email opener                 (optional)
    suppression_fn(cfg)  -> set[str] normalized names to sink      (optional)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass
class Vertical:
    key: str                      # cli id, e.g. "simply_tc"
    label: str                    # human name, e.g. "Transaction-coordinator leads"

    # --- targeting: which businesses to collect ---
    overture_categories: list[str] = field(default_factory=list)  # substring match
    osm_tags: list[str] = field(default_factory=list)             # "k=v"
    keep_chains: bool = False     # web_design drops chains; tc keeps+flags them

    # --- behavior hooks ---
    score_fn: Optional[Callable[[dict], tuple[int, str, str]]] = None
    enrich_fn: Optional[Callable[[dict, dict], dict]] = None
    opener_fn: Optional[Callable[[dict], str]] = None
    suppression_fn: Optional[Callable[[dict], set]] = None

    # --- config blob passed to hooks (fingerprints, competitor seeds, weights…) ---
    config: dict = field(default_factory=dict)

    # --- output: (header, record_key) in column order ---
    columns: list[tuple[str, str]] = field(default_factory=list)

    def score(self, rec: dict) -> tuple[int, str, str]:
        if not self.score_fn:
            raise ValueError(f"vertical '{self.key}' has no score_fn")
        return self.score_fn(rec)


# ---- registry ----
_REGISTRY: dict[str, Vertical] = {}


def register(v: Vertical) -> Vertical:
    _REGISTRY[v.key] = v
    return v


def get_vertical(key: str) -> Vertical:
    if key not in _REGISTRY:
        raise KeyError(f"unknown vertical '{key}'. Available: {sorted(_REGISTRY)}")
    return _REGISTRY[key]


def all_verticals() -> dict[str, Vertical]:
    return dict(_REGISTRY)
