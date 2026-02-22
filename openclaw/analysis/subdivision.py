"""Subdivision feasibility assessment for candidate parcels."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass


ZONE_MIN_LOT_SF = {
    "R-5": 43560,
    "RD": 108900,
    "F&R": 217800,
    "R-1": 43560,
    "R-4": 10890,
    "R-6": 7260,
    "R-8": 5445,
    "R-9600": 9600,
    "R-8400": 8400,
    "R-7200": 7200,
    "ULDR": 6000,
    "UMDR": 4000,
    "UHDR": 2000,
    "MUC": 0,
    "MUN": 0,
    "B": 0,
    "I": 0,
}

ZONE_FRONTAGE_PER_LOT_FT_DEFAULT = {
    "R-5": 200,
    "RD": 150,
    "F&R": 200,
    "R-1": 100,
    "R-4": 60,
    "R-6": 50,
    "R-8": 40,
    "R-9600": 60,
    "R-8400": 60,
    "R-7200": 50,
    "ULDR": 40,
    "UMDR": 30,
    "UHDR": 25,
    "_default": 60,
}

ZONE_MIN_LOT_WIDTH_FT_DEFAULT = {
    "R-5": 150,
    "RD": 100,
    "F&R": 150,
    "R-1": 75,
    "R-4": 50,
    "R-6": 40,
    "R-8": 30,
    "R-9600": 50,
    "R-8400": 50,
    "R-7200": 40,
    "ULDR": 30,
    "UMDR": 25,
    "UHDR": 20,
    "_default": 40,
}

SEPTIC_MIN_LOT_SF = int(os.getenv("SEPTIC_MIN_LOT_SF", "12000"))
WETLAND_USABLE_PCT = float(os.getenv("WETLAND_USABLE_PCT", "0.70"))
STORMWATER_DEDUCTION_SF = int(os.getenv("STORMWATER_DEDUCTION_SF", "1500"))
ACCESS_TRACT_SF = int(os.getenv("ACCESS_TRACT_SF", "2750"))
ROW_DEDICATION_PCT = float(os.getenv("ROW_DEDICATION_PCT", "0.03"))
UTILITY_EASEMENT_PCT = float(os.getenv("UTILITY_EASEMENT_PCT", "0.02"))
FRONTAGE_UNKNOWN_PENALTY = int(os.getenv("FRONTAGE_UNKNOWN_PENALTY", "1"))
ECON_MARGIN_THIN_THRESHOLD = float(os.getenv("ECON_MARGIN_THIN_THRESHOLD", "0.20"))


def _json_map_env(name: str, default_map: dict[str, float]) -> dict[str, float]:
    raw = os.getenv(name)
    if not raw:
        return default_map
    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            return default_map
        out: dict[str, float] = {}
        for k, v in parsed.items():
            out[str(k)] = float(v)
        if "_default" not in out:
            out["_default"] = float(default_map.get("_default", 0))
        return out
    except Exception:
        return default_map


ZONE_FRONTAGE_PER_LOT_FT = _json_map_env("ZONE_FRONTAGE_PER_LOT_FT", ZONE_FRONTAGE_PER_LOT_FT_DEFAULT)
ZONE_MIN_LOT_WIDTH_FT = _json_map_env("ZONE_MIN_LOT_WIDTH_FT", ZONE_MIN_LOT_WIDTH_FT_DEFAULT)

SUBDIVISION_SCORE_EFFECTS = {
    "EDGE_SUBDIVIDABLE": +15,
    "EDGE_SHORT_PLAT_ELIGIBLE": +20,
    "EDGE_SEWER_AVAILABLE": +10,
    "EDGE_ARBITRAGE_DEPTH_HIGH": +10,
    "RISK_SEPTIC_REQUIRED": -15,
    "RISK_ACCESS_UNKNOWN": -20,
    "RISK_BUILDABLE_AREA_LIMITED": -10,
    "RISK_LONG_PLAT_REQUIRED": -5,
    "RISK_ACCESS_TRACT_REQUIRED": -8,
    "RISK_WIDTH_CONSTRAINED": -5,
    "RISK_ARV_MARGIN_THIN": -10,
    "RISK_ECON_LOSS_AT_ASK": -20,
    "RISK_INFILL_PRICED_IN": -8,
}


@dataclass
class SubdivisionResult:
    feasible_splits: int
    potential_splits: int
    buildable_sf: int
    min_lot_sf: int
    plat_type: str
    sewer_available: bool
    access_confirmed: bool
    feasibility: str
    score: int
    flags: list[str]
    reasons: list[str]
    splits_min: int
    splits_max: int
    splits_most_likely: int
    splits_confidence: str
    access_mode: str
    frontage_cap: int | None
    width_cap: int | None
    economic_margin_pct: float | None
    arbitrage_depth_score: int | None
    net_buildable_sf: int


def _zone_number(zone_map: dict[str, float], zone_code: str) -> float:
    return float(zone_map.get(zone_code, zone_map.get("_default", 0.0)))


def _unknown_result(min_lot_sf: int, reason: str, lot_sf: int = 0) -> SubdivisionResult:
    reasons = [
        f"SUBDIV_LOT_SF_{lot_sf}",
        "SUBDIV_BUILDABLE_SF_0",
        "SUBDIV_NET_BUILDABLE_SF_0",
        f"SUBDIV_MIN_LOT_SF_{min_lot_sf}",
        "SUBDIV_FEASIBLE_SPLITS_0",
        "SUBDIV_SPLITS_RANGE_0_0",
        "SUBDIV_SPLITS_MOST_LIKELY_0",
        "SUBDIV_CONFIDENCE_LOW",
        "SUBDIV_ACCESS_MODE_UNKNOWN",
        "SUBDIV_PLAT_TYPE_NOT_FEASIBLE",
        "SEPTIC_REQUIRED",
        "ACCESS_UNKNOWN",
        reason,
    ]
    return SubdivisionResult(
        feasible_splits=0,
        potential_splits=0,
        buildable_sf=0,
        min_lot_sf=min_lot_sf,
        plat_type="NOT_FEASIBLE",
        sewer_available=False,
        access_confirmed=False,
        feasibility="UNLIKELY",
        score=0,
        flags=["RISK_ACCESS_UNKNOWN"],
        reasons=reasons,
        splits_min=0,
        splits_max=0,
        splits_most_likely=0,
        splits_confidence="LOW",
        access_mode="UNKNOWN",
        frontage_cap=None,
        width_cap=None,
        economic_margin_pct=None,
        arbitrage_depth_score=None,
        net_buildable_sf=0,
    )


def assess_subdivision(candidate: dict, parcel: dict) -> SubdivisionResult:
    zone_code = (parcel.get("zone_code") or "").strip()
    min_lot_sf = int(ZONE_MIN_LOT_SF.get(zone_code, 43560))

    if min_lot_sf == 0:
        result = _unknown_result(
            min_lot_sf=0,
            reason="COMMERCIAL_ZONE",
            lot_sf=int(parcel.get("lot_sf") or candidate.get("lot_sf") or 0),
        )
        result.feasibility = "UNLIKELY"
        return result

    lot_sf = int(parcel.get("lot_sf") or candidate.get("lot_sf") or 0)
    if lot_sf <= 0:
        return _unknown_result(min_lot_sf=min_lot_sf, reason="LOT_SF_UNKNOWN", lot_sf=0)

    frontage_raw = parcel.get("frontage_ft")
    frontage_ft = float(frontage_raw) if frontage_raw not in (None, "") else None
    if frontage_ft is not None and frontage_ft <= 0:
        frontage_ft = None

    parcel_width_raw = parcel.get("parcel_width_ft")
    parcel_width_ft = float(parcel_width_raw) if parcel_width_raw not in (None, "") else None
    if parcel_width_ft is not None and parcel_width_ft <= 0:
        parcel_width_ft = None

    sewer_available = not candidate.get("uga_outside", True)
    effective_min = SEPTIC_MIN_LOT_SF if not sewer_available else min_lot_sf
    effective_min = max(effective_min, min_lot_sf)

    gross_sf = float(lot_sf)
    has_critical = bool(candidate.get("has_critical_area_overlap"))
    critical_deduction = gross_sf * (1.0 - WETLAND_USABLE_PCT) if has_critical else 0.0
    after_critical = max(0.0, gross_sf - critical_deduction)

    row_deduction = gross_sf * ROW_DEDICATION_PCT
    after_row = max(0.0, after_critical - row_deduction)

    splits_plausible = (after_row / max(effective_min, 1)) >= 2.0
    stormwater_deduction = STORMWATER_DEDUCTION_SF if splits_plausible else 0
    after_stormwater = max(0.0, after_row - stormwater_deduction)

    utility_deduction = after_stormwater * UTILITY_EASEMENT_PCT
    net_before_access = max(0.0, after_stormwater - utility_deduction)

    area_cap_pre = int(net_before_access // effective_min) if effective_min > 0 else 0

    min_frontage_per_lot = _zone_number(ZONE_FRONTAGE_PER_LOT_FT, zone_code)
    frontage_cap = None
    if frontage_ft is not None and min_frontage_per_lot > 0:
        frontage_cap = int(frontage_ft // min_frontage_per_lot)

    min_lot_width = _zone_number(ZONE_MIN_LOT_WIDTH_FT, zone_code)
    width_basis = parcel_width_ft if parcel_width_ft is not None else frontage_ft
    width_cap = None
    if width_basis is not None and min_lot_width > 0:
        width_cap = int(width_basis // min_lot_width)

    if frontage_cap is None:
        access_mode = "UNKNOWN"
    elif area_cap_pre >= 3 and frontage_cap < area_cap_pre:
        access_mode = "SHARED_TRACT"
    else:
        access_mode = "INDIVIDUAL"

    net_final = net_before_access
    if access_mode == "SHARED_TRACT":
        net_final = max(0.0, net_final - ACCESS_TRACT_SF)

    net_buildable_sf = int(max(0.0, net_final))
    area_cap = int(net_buildable_sf // effective_min) if effective_min > 0 else 0

    caps: list[int] = [area_cap]
    if frontage_cap is not None and access_mode != "SHARED_TRACT":
        caps.append(frontage_cap)
    if width_cap is not None:
        caps.append(width_cap)

    splits_max = max(0, min(caps) if caps else 0)
    penalty = FRONTAGE_UNKNOWN_PENALTY if frontage_cap is None else 0
    splits_min = max(0, splits_max - penalty)

    all_known = frontage_cap is not None and width_cap is not None
    if all_known:
        splits_most_likely = splits_max
    else:
        splits_most_likely = max(splits_min, splits_max - 1)

    spread = max(0, splits_max - splits_min)
    unknown_caps = (1 if frontage_cap is None else 0) + (1 if width_cap is None else 0)
    if frontage_cap is None:
        splits_confidence = "LOW"
    elif all_known and spread <= 1:
        splits_confidence = "HIGH"
    elif unknown_caps == 1 or spread <= 2:
        splits_confidence = "MEDIUM"
    else:
        splits_confidence = "LOW"
    if (
        access_mode == "SHARED_TRACT"
        and (width_cap is None or width_cap < area_cap)
        and splits_confidence == "HIGH"
    ):
        splits_confidence = "MEDIUM"

    address = (parcel.get("address") or "")
    address_upper = address.upper().strip()
    access_confirmed = bool(address and address_upper not in ("", "UNKNOWN", "UNKNOWN UNKNOWN", "UNKNOWN,"))

    flags: list[str] = []
    if splits_most_likely >= 2 and access_confirmed:
        flags.append("EDGE_SUBDIVIDABLE")
    if 2 <= splits_most_likely <= 4 and access_confirmed:
        flags.append("EDGE_SHORT_PLAT_ELIGIBLE")
    if sewer_available:
        flags.append("EDGE_SEWER_AVAILABLE")
    if not sewer_available:
        flags.append("RISK_SEPTIC_REQUIRED")
    if not access_confirmed:
        flags.append("RISK_ACCESS_UNKNOWN")
    if access_mode == "SHARED_TRACT":
        flags.append("RISK_ACCESS_TRACT_REQUIRED")
    if width_cap is not None and width_cap < area_cap:
        flags.append("RISK_WIDTH_CONSTRAINED")

    unusable_ratio = (lot_sf - net_buildable_sf) / lot_sf if lot_sf > 0 else 0
    if unusable_ratio > 0.25:
        flags.append("RISK_BUILDABLE_AREA_LIMITED")
    if splits_most_likely >= 5:
        flags.append("RISK_LONG_PLAT_REQUIRED")

    if splits_most_likely < 2:
        plat_type = "NOT_FEASIBLE"
    elif splits_most_likely <= 4:
        plat_type = "SHORT_PLAT"
    else:
        plat_type = "LONG_PLAT"

    if splits_most_likely >= 2 and access_confirmed and not has_critical:
        feasibility = "LIKELY"
    elif splits_most_likely >= 2:
        feasibility = "POSSIBLE"
    else:
        feasibility = "UNLIKELY"

    score = min(splits_most_likely * 15, 60)
    for flag in flags:
        score += SUBDIVISION_SCORE_EFFECTS.get(flag, 0)
    score = max(0, min(100, score))

    reasons = [
        f"SUBDIV_LOT_SF_{lot_sf}",
        f"SUBDIV_BUILDABLE_SF_{int(after_critical)}",
        f"SUBDIV_NET_BUILDABLE_SF_{net_buildable_sf}",
        f"SUBDIV_MIN_LOT_SF_{effective_min}",
        f"SUBDIV_AREA_CAP_{area_cap}",
        f"SUBDIV_FRONTAGE_CAP_{frontage_cap if frontage_cap is not None else 'UNKNOWN'}",
        f"SUBDIV_WIDTH_CAP_{width_cap if width_cap is not None else 'UNKNOWN'}",
        f"SUBDIV_FEASIBLE_SPLITS_{splits_most_likely}",
        f"SUBDIV_SPLITS_RANGE_{splits_min}_{splits_max}",
        f"SUBDIV_SPLITS_MOST_LIKELY_{splits_most_likely}",
        f"SUBDIV_CONFIDENCE_{splits_confidence}",
        f"SUBDIV_ACCESS_MODE_{access_mode}",
        f"SUBDIV_PLAT_TYPE_{plat_type}",
        "SEWER_AVAILABLE" if sewer_available else "SEPTIC_REQUIRED",
        "ACCESS_CONFIRMED" if access_confirmed else "ACCESS_UNKNOWN",
    ]

    if frontage_cap is None:
        reasons.append("FRONTAGE_UNKNOWN")
        reasons.append(f"FRONTAGE_UNKNOWN_PENALTY_{penalty}")

    for flag in flags:
        reasons.append(f"EFFECT_{flag}_{SUBDIVISION_SCORE_EFFECTS.get(flag, 0)}")

    return SubdivisionResult(
        feasible_splits=splits_most_likely,
        potential_splits=splits_most_likely,
        buildable_sf=int(after_critical),
        min_lot_sf=effective_min,
        plat_type=plat_type,
        sewer_available=sewer_available,
        access_confirmed=access_confirmed,
        feasibility=feasibility,
        score=score,
        flags=flags,
        reasons=reasons,
        splits_min=splits_min,
        splits_max=splits_max,
        splits_most_likely=splits_most_likely,
        splits_confidence=splits_confidence,
        access_mode=access_mode,
        frontage_cap=frontage_cap,
        width_cap=width_cap,
        economic_margin_pct=None,
        arbitrage_depth_score=None,
        net_buildable_sf=net_buildable_sf,
    )
