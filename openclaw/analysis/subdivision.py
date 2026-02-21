"""Subdivision feasibility assessment for candidate parcels."""

from dataclasses import dataclass

ZONE_MIN_LOT_SF = {
    "R-5": 217800,
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

SEPTIC_MIN_LOT_SF = 12000
WETLAND_USABLE_PCT = 0.70
AG_USABLE_PCT = 0.90
CLEAN_USABLE_PCT = 0.95

SUBDIVISION_SCORE_EFFECTS = {
    "EDGE_SUBDIVIDABLE": +15,
    "EDGE_SHORT_PLAT_ELIGIBLE": +20,
    "EDGE_SEWER_AVAILABLE": +10,
    "RISK_SEPTIC_REQUIRED": -15,
    "RISK_ACCESS_UNKNOWN": -20,
    "RISK_BUILDABLE_AREA_LIMITED": -10,
    "RISK_LONG_PLAT_REQUIRED": -5,
}


@dataclass
class SubdivisionResult:
    feasible_splits: int
    buildable_sf: int
    min_lot_sf: int
    plat_type: str
    sewer_available: bool
    access_confirmed: bool
    feasibility: str
    score: int
    flags: list[str]
    reasons: list[str]


def _unknown_result(min_lot_sf: int, reason: str, lot_sf: int = 0) -> SubdivisionResult:
    reasons = [
        f"SUBDIV_LOT_SF_{lot_sf}",
        "SUBDIV_BUILDABLE_SF_0",
        f"SUBDIV_MIN_LOT_SF_{min_lot_sf}",
        "SUBDIV_FEASIBLE_SPLITS_0",
        "SUBDIV_PLAT_TYPE_NOT_FEASIBLE",
        "SEPTIC_REQUIRED",
        "ACCESS_UNKNOWN",
        reason,
    ]
    return SubdivisionResult(
        feasible_splits=0,
        buildable_sf=0,
        min_lot_sf=min_lot_sf,
        plat_type="NOT_FEASIBLE",
        sewer_available=False,
        access_confirmed=False,
        feasibility="UNLIKELY",
        score=0,
        flags=[],
        reasons=reasons,
    )


def assess_subdivision(candidate: dict, parcel: dict) -> SubdivisionResult:
    zone_code = (parcel.get("zone_code") or "").strip()
    min_lot_sf = ZONE_MIN_LOT_SF.get(zone_code, 43560)

    if min_lot_sf == 0:
        result = _unknown_result(min_lot_sf=0, reason="COMMERCIAL_ZONE", lot_sf=int(parcel.get("lot_sf") or candidate.get("lot_sf") or 0))
        result.feasibility = "UNLIKELY"
        return result

    lot_sf = int(parcel.get("lot_sf") or candidate.get("lot_sf") or 0)
    if lot_sf == 0:
        return _unknown_result(min_lot_sf=min_lot_sf, reason="LOT_SF_UNKNOWN", lot_sf=0)

    usable_pct = CLEAN_USABLE_PCT
    if candidate.get("has_critical_area_overlap"):
        usable_pct *= WETLAND_USABLE_PCT
    if candidate.get("flagged_for_review"):
        usable_pct *= AG_USABLE_PCT

    buildable_sf = int(lot_sf * usable_pct)

    sewer_available = not candidate.get("uga_outside", True)
    effective_min = SEPTIC_MIN_LOT_SF if not sewer_available else min_lot_sf
    effective_min = max(effective_min, min_lot_sf)

    feasible_splits = buildable_sf // effective_min if effective_min > 0 else 0

    address = (parcel.get("address") or "")
    address_upper = address.upper().strip()
    access_confirmed = bool(address and address_upper not in ("", "UNKNOWN", "UNKNOWN UNKNOWN", "UNKNOWN,"))

    flags: list[str] = []
    if feasible_splits >= 2 and access_confirmed:
        flags.append("EDGE_SUBDIVIDABLE")
    if feasible_splits >= 2 and feasible_splits <= 4 and access_confirmed:
        flags.append("EDGE_SHORT_PLAT_ELIGIBLE")
    if sewer_available:
        flags.append("EDGE_SEWER_AVAILABLE")
    if not sewer_available:
        flags.append("RISK_SEPTIC_REQUIRED")
    if not access_confirmed:
        flags.append("RISK_ACCESS_UNKNOWN")
    unusable_ratio = (lot_sf - buildable_sf) / lot_sf if lot_sf > 0 else 0
    if unusable_ratio > 0.25:
        flags.append("RISK_BUILDABLE_AREA_LIMITED")
    if feasible_splits >= 5:
        flags.append("RISK_LONG_PLAT_REQUIRED")

    if feasible_splits <= 0 or feasible_splits < 2:
        plat_type = "NOT_FEASIBLE"
    elif feasible_splits <= 4:
        plat_type = "SHORT_PLAT"
    else:
        plat_type = "LONG_PLAT"

    if feasible_splits >= 2 and access_confirmed and not candidate.get("has_critical_area_overlap"):
        feasibility = "LIKELY"
    elif feasible_splits >= 2 and (not access_confirmed or candidate.get("has_critical_area_overlap")):
        feasibility = "POSSIBLE"
    else:
        feasibility = "UNLIKELY"

    base = min(feasible_splits * 15, 60)
    if "EDGE_SHORT_PLAT_ELIGIBLE" in flags:
        base += 20
    if "EDGE_SEWER_AVAILABLE" in flags:
        base += 10
    if "RISK_ACCESS_UNKNOWN" in flags:
        base -= 20
    if "RISK_SEPTIC_REQUIRED" in flags:
        base -= 15
    if "RISK_BUILDABLE_AREA_LIMITED" in flags:
        base -= 10
    score = max(0, min(100, base))

    reasons = [
        f"SUBDIV_LOT_SF_{lot_sf}",
        f"SUBDIV_BUILDABLE_SF_{buildable_sf}",
        f"SUBDIV_MIN_LOT_SF_{effective_min}",
        f"SUBDIV_FEASIBLE_SPLITS_{feasible_splits}",
        f"SUBDIV_PLAT_TYPE_{plat_type}",
        "SEWER_AVAILABLE" if sewer_available else "SEPTIC_REQUIRED",
        "ACCESS_CONFIRMED" if access_confirmed else "ACCESS_UNKNOWN",
    ]

    return SubdivisionResult(
        feasible_splits=feasible_splits,
        buildable_sf=buildable_sf,
        min_lot_sf=effective_min,
        plat_type=plat_type,
        sewer_available=sewer_available,
        access_confirmed=access_confirmed,
        feasibility=feasibility,
        score=score,
        flags=flags,
        reasons=reasons,
    )
