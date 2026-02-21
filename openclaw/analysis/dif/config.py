"""DIFConfig — Developer Identity Fingerprint configuration.

All parameters sourced from environment variables with safe defaults.
Follows the same pattern as openclaw/analysis/edge_config.py.
"""

import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Tuple


def _parse_recency_weights(raw: str) -> List[Tuple[int, int, float]]:
    """Parse ALS_RECENCY_WEIGHTS from JSON env var.

    Expected format: [[0,180,1.0],[181,365,0.5],[366,730,0.25]]
    Returns list of (lo, hi, weight) tuples.
    """
    try:
        parsed = json.loads(raw)
        return [(int(lo), int(hi), float(w)) for lo, hi, w in parsed]
    except Exception:
        return [(0, 180, 1.0), (181, 365, 0.5), (366, 730, 0.25)]


def _parse_json_dict(raw: str, default: dict) -> dict:
    """Parse a JSON string from env var, returning default on failure."""
    try:
        return json.loads(raw)
    except Exception:
        return default


@dataclass
class DIFConfig:
    # ── Composite weights ──────────────────────────────────────────────────
    DIF_WEIGHT_YMS: int = field(default_factory=lambda: int(os.getenv("DIF_WEIGHT_YMS", "3")))
    DIF_WEIGHT_ALS: int = field(default_factory=lambda: int(os.getenv("DIF_WEIGHT_ALS", "2")))
    DIF_WEIGHT_CMS: int = field(default_factory=lambda: int(os.getenv("DIF_WEIGHT_CMS", "3")))
    DIF_WEIGHT_SFI: int = field(default_factory=lambda: int(os.getenv("DIF_WEIGHT_SFI", "2")))
    DIF_WEIGHT_EFI: int = field(default_factory=lambda: int(os.getenv("DIF_WEIGHT_EFI", "2")))

    # ── YMS — Yield Multiplier Score ───────────────────────────────────────
    YMS_MAX_EFFECTIVE_LOTS: int = field(default_factory=lambda: int(os.getenv("YMS_MAX_EFFECTIVE_LOTS", "20")))
    YMS_MAX_YIELD: int = field(default_factory=lambda: int(os.getenv("YMS_MAX_YIELD", "20")))
    YMS_CRITICAL_AREA_PENALTY: int = field(default_factory=lambda: int(os.getenv("YMS_CRITICAL_AREA_PENALTY", "1")))

    # ── EFI — Entitlement Friction Index (asymmetric two-slope) ───────────
    EFI_MILD_THRESHOLD: float = field(default_factory=lambda: float(os.getenv("EFI_MILD_THRESHOLD", "3.0")))
    EFI_MILD_PENALTY: float = field(default_factory=lambda: float(os.getenv("EFI_MILD_PENALTY", "0.5")))
    EFI_STEEP_PENALTY: float = field(default_factory=lambda: float(os.getenv("EFI_STEEP_PENALTY", "2.0")))

    # ── ALS — Absorption Liquidity Score ──────────────────────────────────
    ALS_TARGET_LOW: int = field(default_factory=lambda: int(os.getenv("ALS_TARGET_LOW", "900000")))
    ALS_TARGET_HIGH: int = field(default_factory=lambda: int(os.getenv("ALS_TARGET_HIGH", "1500000")))
    ALS_SATURATION_COUNT: int = field(default_factory=lambda: int(os.getenv("ALS_SATURATION_COUNT", "6")))
    ALS_COMP_RADIUS_METERS: int = field(default_factory=lambda: int(os.getenv("ALS_COMP_RADIUS_METERS", "804")))
    ALS_RECENCY_WEIGHTS: List[Tuple[int, int, float]] = field(
        default_factory=lambda: _parse_recency_weights(
            os.getenv("ALS_RECENCY_WEIGHTS", "[[0,180,1.0],[181,365,0.5],[366,730,0.25]]")
        )
    )

    # ── CMS — Construction Margin Spread ──────────────────────────────────
    CMS_MAX_MARGIN_PCT: float = field(default_factory=lambda: float(os.getenv("CMS_MAX_MARGIN_PCT", "0.30")))
    CMS_CARRY_MONTHS: int = field(default_factory=lambda: int(os.getenv("CMS_CARRY_MONTHS", "12")))
    CMS_BUILD_MONTHS: int = field(default_factory=lambda: int(os.getenv("CMS_BUILD_MONTHS", "8")))
    CMS_FINANCING_LTV: float = field(default_factory=lambda: float(os.getenv("CMS_FINANCING_LTV", "0.65")))
    CMS_FINANCING_RATE_PCT: float = field(default_factory=lambda: float(os.getenv("CMS_FINANCING_RATE_PCT", "7.5")))
    CMS_ASSESSED_VALUE_MULTIPLIER: Dict[str, float] = field(
        default_factory=lambda: _parse_json_dict(
            os.getenv("CMS_ASSESSED_VALUE_MULTIPLIER", '{"default": 1.0}'),
            {"default": 1.0},
        )
    )
    CMS_LAND_COST_PRIORITY: List[str] = field(
        default_factory=lambda: (
            os.getenv("CMS_LAND_COST_PRIORITY", "LIST_PRICE,LAST_SALE,ASSESSED").split(",")
        )
    )

    # ── SFI — Seller Fatigue Index ─────────────────────────────────────────
    SFI_MIN_YEARS: int = field(default_factory=lambda: int(os.getenv("SFI_MIN_YEARS", "10")))
    SFI_MAX_YEARS: int = field(default_factory=lambda: int(os.getenv("SFI_MAX_YEARS", "30")))
    SFI_TRUST_BONUS: float = field(default_factory=lambda: float(os.getenv("SFI_TRUST_BONUS", "2.0")))
    SFI_LOW_IMP_BONUS: float = field(default_factory=lambda: float(os.getenv("SFI_LOW_IMP_BONUS", "2.0")))
    SFI_LOW_IMP_RATIO: float = field(default_factory=lambda: float(os.getenv("SFI_LOW_IMP_RATIO", "0.15")))
    SFI_NO_SALE_DATE_DEFAULT: float = field(default_factory=lambda: float(os.getenv("SFI_NO_SALE_DATE_DEFAULT", "0.5")))

    # ── DIF delta clamp ────────────────────────────────────────────────────
    DIF_MAX_DELTA: float = field(default_factory=lambda: float(os.getenv("DIF_MAX_DELTA", "25.0")))

    # ── Tier thresholds ────────────────────────────────────────────────────
    TIER_THRESHOLDS: Dict[str, int] = field(
        default_factory=lambda: _parse_json_dict(
            os.getenv("TIER_THRESHOLDS", '{"A":85,"B":70,"C":50,"D":35,"E":20,"F":0}'),
            {"A": 85, "B": 70, "C": 50, "D": 35, "E": 20, "F": 0},
        )
    )


# Module-level singleton — callers can import this directly
dif_config = DIFConfig()
