"""Profit model for subdivision candidates.

Estimates costs, ARV, and profit margin per candidate.
ARV uses PostGIS comp query (ST_DWithin) — no Python spatial ops.
"""

import logging
from datetime import datetime, timedelta

from sqlalchemy import text

from openclaw.config import settings
from openclaw.db.session import SessionLocal

logger = logging.getLogger(__name__)

# Comp query: nearby parcels, same zone, sold in last 24 months
COMP_SQL = text("""
    SELECT p.last_sale_price
    FROM parcels p
    WHERE p.last_sale_price IS NOT NULL
        AND p.last_sale_price > 0
        AND p.zone_code = :zone_code
        AND p.county::text = :county
        AND p.last_sale_date >= :cutoff_date
        AND ST_DWithin(
            p.geometry::geography,
            (SELECT geometry::geography FROM parcels WHERE id = :parcel_id),
            804.672  -- 0.5 miles in meters (geography cast, never degrees)
        )
        AND p.id != :parcel_id
    ORDER BY p.last_sale_date DESC
    LIMIT 10
""")


def estimate_arv(session, parcel_id: str, county: str, zone_code: str, assessed_value: int) -> tuple[int, bool]:
    """Estimate ARV per home using comps. Returns (arv_per_home, is_estimated)."""
    cutoff = datetime.utcnow() - timedelta(days=730)
    result = session.execute(COMP_SQL, {
        "parcel_id": parcel_id,
        "county": county,
        "zone_code": zone_code,
        "cutoff_date": cutoff.date(),
    })
    prices = [row[0] for row in result]

    if prices:
        arv = int(sum(prices) / len(prices) * settings.ARV_MULTIPLIER)
        return arv, False
    else:
        # No comps — use assessed value with markup, flag as estimated
        arv = int((assessed_value or 0) * 1.35 * settings.ARV_MULTIPLIER)
        return arv, True


def calculate_profit(candidate: dict) -> dict:
    """Calculate full profit model for a candidate dict from scorer.

    Expected keys: parcel_id, county, zone_code, assessed_value, potential_splits
    """
    session = SessionLocal()
    try:
        splits = candidate["potential_splits"]
        assessed = candidate.get("assessed_value") or 0

        arv_per_home, is_estimated = estimate_arv(
            session,
            str(candidate["parcel_id"]),
            candidate["county"],
            candidate.get("zone_code", ""),
            assessed,
        )

        dev_cost_per_lot = (
            settings.COST_SHORT_PLAT_BASE
            + settings.COST_ENGINEERING_PER_LOT
            + settings.COST_UTILITY_PER_LOT
        )

        estimated_land_value = assessed // splits if splits else 0
        estimated_dev_cost = dev_cost_per_lot * splits
        estimated_build_cost = settings.COST_BUILD_PER_SF * settings.TARGET_HOME_SF * splits
        estimated_arv = arv_per_home * splits
        estimated_profit = estimated_arv - (assessed + estimated_dev_cost + estimated_build_cost)
        estimated_margin_pct = (estimated_profit / estimated_arv * 100) if estimated_arv else 0.0

        return {
            "estimated_land_value": estimated_land_value,
            "estimated_dev_cost": estimated_dev_cost,
            "estimated_build_cost": estimated_build_cost,
            "estimated_arv": estimated_arv,
            "estimated_profit": estimated_profit,
            "estimated_margin_pct": round(estimated_margin_pct, 2),
            "flagged_for_review": is_estimated,
        }
    finally:
        session.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Profit model — run via scorer or main orchestrator.")
