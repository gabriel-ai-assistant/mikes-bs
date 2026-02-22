"""Economic gate for subdivision candidates."""

from __future__ import annotations

import json
import os

ECON_MARGIN_THIN_THRESHOLD = float(os.getenv("ECON_MARGIN_THIN_THRESHOLD", "0.20"))
BUILD_SIZE_SF = int(os.getenv("BUILD_SIZE_SF", "2200"))
BUILD_COST_PER_SF = float(os.getenv("BUILD_COST_PER_SF", "250"))
ENTITLEMENT_PER_LOT = float(os.getenv("ENTITLEMENT_PER_LOT", "130000"))
CARRY_FACTOR = float(os.getenv("CARRY_FACTOR", "0.08"))
SELL_COST_FACTOR = float(os.getenv("SELL_COST_FACTOR", "0.06"))

ZONE_ARV_MULTIPLIER_DEFAULT = {
    "ULDR": 1.6,
    "UMDR": 1.5,
    "UHDR": 1.4,
    "R-8400": 1.5,
    "R-7200": 1.5,
    "R-9600": 1.55,
    "R-4": 1.7,
    "R-6": 1.65,
    "R-1": 2.0,
    "R-5": 2.5,
    "RD": 2.2,
    "F&R": 2.3,
    "_default": 1.8,
}


def _parse_zone_multiplier() -> dict[str, float]:
    raw = os.getenv("ZONE_ARV_MULTIPLIER")
    if not raw:
        return ZONE_ARV_MULTIPLIER_DEFAULT
    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            return ZONE_ARV_MULTIPLIER_DEFAULT
        out: dict[str, float] = {}
        for k, v in parsed.items():
            out[str(k)] = float(v)
        if "_default" not in out:
            out["_default"] = ZONE_ARV_MULTIPLIER_DEFAULT["_default"]
        return out
    except Exception:
        return ZONE_ARV_MULTIPLIER_DEFAULT


ZONE_ARV_MULTIPLIER = _parse_zone_multiplier()


def compute_economic_margin(candidate: dict, splits: int, zone_code: str) -> tuple[float, list[str], list[str]]:
    """Return margin ratio (0.15 = 15%), tags, reason codes."""
    tags: list[str] = []
    reasons: list[str] = []

    if splits <= 0:
        tags.append("RISK_ECON_LOSS_AT_ASK")
        reasons.append("ECON_SPLITS_INVALID_0")
        reasons.append("EFFECT_RISK_ECON_LOSS_AT_ASK_-20")
        return -1.0, tags, reasons

    assessed_value = float(candidate.get("assessed_value") or 0)
    last_sale_price = float(candidate.get("last_sale_price") or 0)

    if last_sale_price > assessed_value and last_sale_price > 0:
        land_cost = last_sale_price
        land_cost_source = "LAST_SALE"
    else:
        land_cost = assessed_value
        land_cost_source = "ASSESSED"

    build_cost_per_lot = BUILD_SIZE_SF * BUILD_COST_PER_SF
    build_cost = build_cost_per_lot * splits
    entitlement_cost = ENTITLEMENT_PER_LOT * splits
    carry_cost = land_cost * CARRY_FACTOR

    zone_mult = float(ZONE_ARV_MULTIPLIER.get(zone_code, ZONE_ARV_MULTIPLIER.get("_default", 1.8)))
    assessed_per_lot = assessed_value / max(splits, 1)
    arv_per_lot = assessed_per_lot * zone_mult + build_cost_per_lot
    revenue = arv_per_lot * splits
    sell_cost = revenue * SELL_COST_FACTOR

    total_cost = land_cost + build_cost + entitlement_cost + carry_cost + sell_cost
    margin = ((revenue - total_cost) / revenue) if revenue > 0 else -1.0

    reasons.extend([
        f"ECON_LAND_COST_SOURCE_{land_cost_source}",
        f"ECON_LAND_COST_{int(land_cost)}",
        f"ECON_BUILD_COST_{int(build_cost)}",
        f"ECON_ENTITLEMENT_COST_{int(entitlement_cost)}",
        f"ECON_CARRY_COST_{int(carry_cost)}",
        f"ECON_SELL_COST_{int(sell_cost)}",
        f"ECON_REVENUE_{int(revenue)}",
        f"ECON_MARGIN_{margin:.4f}",
    ])

    if margin < 0:
        tags.append("RISK_ECON_LOSS_AT_ASK")
        reasons.append("EFFECT_RISK_ECON_LOSS_AT_ASK_-20")
    if margin < ECON_MARGIN_THIN_THRESHOLD:
        tags.append("RISK_ARV_MARGIN_THIN")
        reasons.append("EFFECT_RISK_ARV_MARGIN_THIN_-10")

    return margin, tags, reasons
