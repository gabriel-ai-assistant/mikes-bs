"""Subdivision candidate scoring engine.

Finds parcels eligible for subdivision and scores them into tiers.
All spatial operations use PostGIS — no Python geometry processing.
"""

import logging
import math

from sqlalchemy import text

from openclaw.db.session import SessionLocal

logger = logging.getLogger(__name__)

# Candidate query: finds parcels that meet subdivision criteria
CANDIDATE_SQL = text("""
    SELECT
        p.id AS parcel_id,
        p.parcel_id AS parcel_code,
        p.county,
        p.address,
        p.lot_sf,
        p.zone_code,
        p.present_use,
        p.assessed_value,
        p.last_sale_price,
        z.min_lot_sf,
        FLOOR(p.lot_sf::float / z.min_lot_sf) AS potential_splits
    FROM parcels p
    JOIN zoning_rules z
        ON p.county::text = z.county::text
        AND p.zone_code = z.zone_code
    WHERE
        p.lot_sf >= (z.min_lot_sf * 2.1)
        AND UPPER(COALESCE(p.present_use, '')) IN (
            'SINGLE FAMILY', 'VACANT RES', 'VACANT', 'UNDEVELOPED'
        )
        AND NOT EXISTS (
            SELECT 1 FROM critical_areas ca
            WHERE ST_Intersects(p.geometry, ca.geometry)
        )
        AND NOT EXISTS (
            SELECT 1 FROM shoreline_buffer sb
            WHERE ST_Intersects(p.geometry, sb.geometry)
        )
        AND NOT EXISTS (
            SELECT 1 FROM candidates c WHERE c.parcel_id = p.id
        )
""")


def assign_tier(potential_splits: int, margin_pct: float) -> str:
    """Assign score tier based on splits and margin."""
    if potential_splits >= 3 and margin_pct >= 20.0:
        return "A"
    elif potential_splits >= 2 and margin_pct >= 12.0:
        return "B"
    return "C"


def find_candidates() -> list[dict]:
    """Run candidate query and return list of raw candidate dicts."""
    session = SessionLocal()
    try:
        result = session.execute(CANDIDATE_SQL)
        candidates = []
        for row in result.mappings():
            candidates.append(dict(row))
        logger.info(f"Found {len(candidates)} new subdivision candidates")
        return candidates
    finally:
        session.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    candidates = find_candidates()
    for c in candidates[:10]:
        logger.info(f"  {c['address']} ({c['county']}) — {c['potential_splits']} splits")
