"""
EDGE/RISK Zoning Arbitrage Tagger for Mike's Building System.

TAG SYSTEM INVENTORY:
---------------------
Storage: candidates.tags (TEXT[]) and candidates.reason_codes (TEXT[])
Pipeline position: called after scorer.py spatial flags, before/during rule_engine evaluation
Previous "tags": boolean columns only (has_critical_area_overlap, flagged_for_review, has_shoreline_overlap)
Scoring consumer: rule_engine.py - reads tags from candidate dict and applies weight boosts

EDGE TAGS (positive signals):
  EDGE_SNOCO_LSA_R5_RD_FR       - Lot Size Averaging eligible (R-5/RD/F&R, >=10 acres, SCC 30.23.215)
  EDGE_SNOCO_RURAL_CLUSTER_BONUS - Rural cluster density bonus eligible (>=5 acres)
  EDGE_SNOCO_RUTA_ARBITRAGE      - Inside RUTA boundary (improves yield; data stub pending)
  EDGE_WA_HB1110_MIDDLE_HOUSING  - HB 1110 middle housing preemption (zone in admin-configured set)
  EDGE_WA_UNIT_LOT_SUBDIVISION   - Unit lot subdivision supported (zone in admin-configured set)

INFORMATIONAL TAGS:
  EDGE_UGA_STATUS_UNKNOWN        - UGA boundary data unavailable; review manually

RISK TAGS (negative signals / constraints):
  RISK_ACCESS_UNKNOWN            - No address + tiny lot + near-zero value -> access unclear
  RISK_CRITICAL_AREAS            - Critical area overlap detected
  RISK_LOT_TOO_SMALL             - Lot below rural cluster minimum; LSA not applicable
  RISK_SEPTIC_UNKNOWN            - Rural parcel, no existing structure -> septic feasibility unknown
  RISK_WATER_UNKNOWN             - Rural parcel, no existing structure -> water source unknown
  RISK_RUTA_DATA_UNAVAILABLE     - RUTA boundary data not loaded; cannot confirm RUTA status
  RISK_HB1110_DATA_UNAVAILABLE   - HB1110 urban zones not configured; cannot confirm eligibility
  RISK_UNIT_LOT_DATA_UNAVAILABLE - Unit lot zones not configured; cannot confirm eligibility
"""

SQFT_PER_ACRE = 43560.0


def compute_tags(
    candidate: dict,
    config=None,
    ruta_confirmed: bool = False,
) -> tuple[list[str], list[str]]:
    """
    Compute EDGE/RISK tags for a candidate parcel.

    Args:
        candidate: dict with keys: county, zone_code, lot_sf, has_critical_area_overlap,
                   improvement_value, total_value, address, owner_name, potential_splits
        config: EdgeConfig instance (defaults to module-level edge_config)
        ruta_confirmed: True only when caller has confirmed parcel is inside RUTA boundary

    Returns:
        (tags, reason_codes) — both are lists of strings
    """
    if config is None:
        from openclaw.analysis.edge_config import edge_config
        config = edge_config

    tags: list[str] = []
    reasons: list[str] = []

    county = (candidate.get("county") or "").lower()
    zone = (candidate.get("zone_code") or "").strip()
    lot_sf = float(candidate.get("lot_sf") or 0)
    lot_acres = lot_sf / SQFT_PER_ACRE
    has_critical = bool(candidate.get("has_critical_area_overlap", False))
    improvement_value = float(candidate.get("improvement_value") or 0)
    total_value = float(candidate.get("total_value") or 0)
    address = candidate.get("address")
    is_snohomish = county == "snohomish"
    is_rural_zone = zone in config.lsa_zones

    # --- CONSTRAINTS GATE ---
    lsa_suppressed = False

    # 1. Access unknown (suppress LSA)
    if address is None and lot_sf < 1000 and total_value < 5000:
        tags.append("RISK_ACCESS_UNKNOWN")
        lsa_suppressed = True

    # 2. Critical area overlap (add risk, do NOT suppress EDGE)
    if has_critical:
        tags.append("RISK_CRITICAL_AREAS")

    # 3. Lot too small for LSA (suppress LSA but not rural cluster)
    rural_cluster_min_sf = config.rural_cluster_min_acres * SQFT_PER_ACRE
    lsa_min_sf = config.lsa_min_acres * SQFT_PER_ACRE
    if is_snohomish and is_rural_zone and lot_sf < rural_cluster_min_sf:
        tags.append("RISK_LOT_TOO_SMALL")
        lsa_suppressed = True

    # 4. Septic/water unknown (rural, no existing structure)
    if is_snohomish and is_rural_zone and improvement_value == 0:
        tags.append("RISK_SEPTIC_UNKNOWN")
        tags.append("RISK_WATER_UNKNOWN")

    # --- EDGE TAGS ---

    # A. EDGE_SNOCO_LSA_R5_RD_FR
    if is_snohomish and is_rural_zone and lot_sf >= lsa_min_sf and not lsa_suppressed:
        tags.append("EDGE_SNOCO_LSA_R5_RD_FR")
        tags.append("EDGE_UGA_STATUS_UNKNOWN")  # No UGA data available
        reasons.append(
            f"EDGE_SNOCO_LSA_R5_RD_FR triggered: zone={zone}, acres={lot_acres:.1f}, "
            f"UGA=unknown (no boundary data)"
        )

    # B. EDGE_SNOCO_RURAL_CLUSTER_BONUS
    if is_snohomish and is_rural_zone and lot_sf >= rural_cluster_min_sf:
        tags.append("EDGE_SNOCO_RURAL_CLUSTER_BONUS")
        reasons.append(
            f"EDGE_SNOCO_RURAL_CLUSTER_BONUS triggered: zone={zone}, acres={lot_acres:.1f}"
        )

    # C. EDGE_SNOCO_RUTA_ARBITRAGE (only if caller confirms RUTA membership)
    if ruta_confirmed:
        tags.append("EDGE_SNOCO_RUTA_ARBITRAGE")
        reasons.append("EDGE_SNOCO_RUTA_ARBITRAGE triggered: parcel confirmed inside RUTA boundary")
    else:
        if is_snohomish and is_rural_zone:
            tags.append("RISK_RUTA_DATA_UNAVAILABLE")

    # D. EDGE_WA_HB1110_MIDDLE_HOUSING
    if config.hb1110_urban_zones:
        if zone in config.hb1110_urban_zones:
            tags.append("EDGE_WA_HB1110_MIDDLE_HOUSING")
            reasons.append(f"EDGE_WA_HB1110_MIDDLE_HOUSING triggered: zone={zone}")
    else:
        # Only emit the unavailable risk if it's a non-rural zone (don't spam rural parcels)
        if not is_rural_zone:
            tags.append("RISK_HB1110_DATA_UNAVAILABLE")

    # E. EDGE_WA_UNIT_LOT_SUBDIVISION
    if config.unit_lot_zones:
        if zone in config.unit_lot_zones:
            tags.append("EDGE_WA_UNIT_LOT_SUBDIVISION")
            reasons.append(f"EDGE_WA_UNIT_LOT_SUBDIVISION triggered: zone={zone}")
    else:
        if not is_rural_zone:
            tags.append("RISK_UNIT_LOT_DATA_UNAVAILABLE")

    return tags, reasons
