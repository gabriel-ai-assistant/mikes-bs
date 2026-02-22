"""Arbitrage depth scoring for subdivision candidates."""

from __future__ import annotations

import os
from typing import Any

from sqlalchemy import text

from openclaw.analysis.subdivision import ZONE_MIN_LOT_SF

_ZONE_MEDIAN_PSF_CACHE: dict[str, float] = {}

RURAL_ZONES = {"R-5", "RD", "F&R", "R-1"}
URBAN_ZONES = {"ULDR", "UMDR", "UHDR", "MUC", "MUN"}

ARBITRAGE_WEIGHT_LOT_RATIO = float(os.getenv("ARBITRAGE_WEIGHT_LOT_RATIO", "30"))
ARBITRAGE_WEIGHT_RURALITY = float(os.getenv("ARBITRAGE_WEIGHT_RURALITY", "20"))
ARBITRAGE_WEIGHT_UGA_OUTSIDE = float(os.getenv("ARBITRAGE_WEIGHT_UGA_OUTSIDE", "20"))
ARBITRAGE_WEIGHT_RUTA = float(os.getenv("ARBITRAGE_WEIGHT_RUTA", "15"))
ARBITRAGE_WEIGHT_UNDERPRICING = float(os.getenv("ARBITRAGE_WEIGHT_UNDERPRICING", "15"))
ARBITRAGE_DEPTH_HIGH_THRESHOLD = float(os.getenv("ARBITRAGE_DEPTH_HIGH_THRESHOLD", "60"))


def compute_zone_medians(session: Any) -> dict[str, float]:
    """Populate and return zone median assessed $/sf."""
    rows = session.execute(text("""
        SELECT
            zone_code,
            percentile_cont(0.5) WITHIN GROUP (
                ORDER BY (assessed_value::double precision / NULLIF(lot_sf::double precision, 0))
            ) AS median_psf
        FROM parcels
        WHERE zone_code IS NOT NULL
          AND assessed_value IS NOT NULL
          AND assessed_value > 0
          AND lot_sf IS NOT NULL
          AND lot_sf > 0
        GROUP BY zone_code
    """)).fetchall()

    _ZONE_MEDIAN_PSF_CACHE.clear()
    for zone_code, median_psf in rows:
        if zone_code and median_psf is not None:
            _ZONE_MEDIAN_PSF_CACHE[str(zone_code)] = float(median_psf)
    return dict(_ZONE_MEDIAN_PSF_CACHE)


def compute_arbitrage_depth(candidate: dict, tags: list[str] | None = None) -> tuple[int, list[str], list[str]]:
    tags = tags or []
    out_tags: list[str] = []
    reasons: list[str] = []

    zone = (candidate.get("zone_code") or "").strip()
    lot_sf = float(candidate.get("lot_sf") or 0)
    min_lot_sf = float(ZONE_MIN_LOT_SF.get(zone, 43560) or 0)
    assessed_value = float(candidate.get("assessed_value") or 0)

    lot_ratio_raw = (lot_sf / min_lot_sf) if min_lot_sf > 0 else 0.0
    lot_ratio_capped = min(max(lot_ratio_raw, 1.0), 10.0)
    lot_ratio_score = ((lot_ratio_capped - 1.0) / 9.0) * ARBITRAGE_WEIGHT_LOT_RATIO

    if zone in RURAL_ZONES:
        rurality_score = ARBITRAGE_WEIGHT_RURALITY
    elif zone in URBAN_ZONES:
        rurality_score = 0.0
    else:
        rurality_score = ARBITRAGE_WEIGHT_RURALITY * 0.4

    uga_outside = candidate.get("uga_outside")
    if uga_outside is True:
        uga_score = ARBITRAGE_WEIGHT_UGA_OUTSIDE
    elif uga_outside is False:
        uga_score = 0.0
    else:
        uga_score = ARBITRAGE_WEIGHT_UGA_OUTSIDE * 0.2

    ruta_score = ARBITRAGE_WEIGHT_RUTA if "EDGE_SNOCO_RUTA_ARBITRAGE" in tags else 0.0

    parcel_psf = (assessed_value / lot_sf) if lot_sf > 0 else 0.0
    zone_median_psf = _ZONE_MEDIAN_PSF_CACHE.get(zone)
    if zone_median_psf and zone_median_psf > 0 and parcel_psf < zone_median_psf:
        underpricing_score = ((zone_median_psf - parcel_psf) / zone_median_psf) * ARBITRAGE_WEIGHT_UNDERPRICING
        underpricing_score = min(ARBITRAGE_WEIGHT_UNDERPRICING, max(0.0, underpricing_score))
    else:
        underpricing_score = 0.0

    score = int(round(max(0.0, min(100.0, lot_ratio_score + rurality_score + uga_score + ruta_score + underpricing_score))))

    reasons.extend([
        f"ARB_LOT_RATIO_{lot_ratio_raw:.3f}",
        f"ARB_LOT_RATIO_SCORE_{lot_ratio_score:.2f}",
        f"ARB_RURALITY_SCORE_{rurality_score:.2f}",
        f"ARB_UGA_SCORE_{uga_score:.2f}",
        f"ARB_RUTA_SCORE_{ruta_score:.2f}",
        f"ARB_UNDERPRICING_SCORE_{underpricing_score:.2f}",
        f"ARB_PARCEL_PSF_{parcel_psf:.3f}",
        f"ARB_ZONE_MEDIAN_PSF_{zone_median_psf:.3f}" if zone_median_psf is not None else "ARB_ZONE_MEDIAN_PSF_UNKNOWN",
        f"ARB_SCORE_{score}",
    ])

    if score >= ARBITRAGE_DEPTH_HIGH_THRESHOLD:
        out_tags.append("EDGE_ARBITRAGE_DEPTH_HIGH")
        reasons.append("EFFECT_EDGE_ARBITRAGE_DEPTH_HIGH_10")

    if zone in URBAN_ZONES and parcel_psf > 15 and lot_ratio_raw < 4:
        out_tags.append("RISK_INFILL_PRICED_IN")
        reasons.append("EFFECT_RISK_INFILL_PRICED_IN_-8")

    return score, out_tags, reasons
