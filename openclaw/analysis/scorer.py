"""Subdivision candidate scoring engine.

Strategy:
1. Find parcels with lot_sf >= 2.1x zone minimum (fast index scan)
2. Score tier based on potential splits + zone type
3. Flag wetland/ag overlaps after inserting candidates (GIST-optimized)

All spatial ops use PostGIS.
"""
import logging
from sqlalchemy import text
from openclaw.db.session import SessionLocal

logger = logging.getLogger(__name__)


# Step 1: Insert raw candidates from zoning join (no spatial filter yet — fast)
INSERT_CANDIDATES_SQL = text("""
    INSERT INTO candidates (
        parcel_id, score_tier, potential_splits,
        estimated_land_value, has_critical_area_overlap, has_shoreline_overlap, flagged_for_review
    )
    SELECT
        p.id,
        CASE
            WHEN FLOOR(p.lot_sf / z.min_lot_sf) >= 4 THEN 'A'::scoretierenum
            WHEN FLOOR(p.lot_sf / z.min_lot_sf) >= 2 THEN 'B'::scoretierenum
            ELSE 'C'::scoretierenum
        END,
        FLOOR(p.lot_sf / z.min_lot_sf)::int,
        COALESCE(p.assessed_value, 0),
        false,
        false,
        false
    FROM parcels p
    JOIN zoning_rules z
        ON p.county::text = z.county::text
        AND p.zone_code = z.zone_code
    WHERE
        p.lot_sf >= (z.min_lot_sf * 2.1)
        AND p.geometry IS NOT NULL
        -- Exclude non-buildable use codes
        AND COALESCE(p.present_use, '') NOT IN (
            '183 Non Residential Structure',
            '915 Common Areas',
            '940 Open Space General RCW 84.34',
            '880 DF Timber Acres Only RCW 84.33',
            '830 Open Space Agriculture RCW 84.34',
            '184 Utility, Transportation',
            '910 Undeveloped (Vacant) Land'
        )
        -- Exclude utility/govt/non-purchasable owners
        AND NOT (
            COALESCE(p.owner_name, '') ILIKE ANY(ARRAY[
                '%SNOPUD%', '%PUBLIC UTILITY%', '%UTILITY DISTRICT%',
                '%WATER DISTRICT%', '% PUD%',
                '%STATE OF WA%', '%WASHINGTON STATE%',
                '%UNITED STATES%', '% COUNTY%',
                '%CITY OF %'
            ])
        )
        -- Exclude parcels with no address and no improvement value (likely utility strips)
        AND NOT (p.address IS NULL AND COALESCE(p.improvement_value, 0) = 0 AND COALESCE(p.total_value, 0) < 5000)
        AND NOT EXISTS (
            SELECT 1 FROM candidates c WHERE c.parcel_id = p.id
        )
    RETURNING id
""")

# Step 2: Flag candidates with wetland overlap (uses GIST index on both sides)
FLAG_WETLAND_SQL = text("""
    UPDATE candidates c
    SET has_critical_area_overlap = true
    FROM parcels p, critical_areas ca
    WHERE c.parcel_id = p.id
      AND c.has_critical_area_overlap = false
      AND p.geometry && ca.geometry
      AND ST_Intersects(p.geometry, ca.geometry)
""")

# Step 3: Flag candidates in agricultural notification zones
FLAG_AG_SQL = text("""
    UPDATE candidates c
    SET flagged_for_review = true
    FROM parcels p, agricultural_areas ag
    WHERE c.parcel_id = p.id
      AND p.geometry && ag.geometry
      AND ST_Intersects(p.geometry, ag.geometry)
""")

# Step 4: Downgrade tier for wetland-affected candidates
DOWNGRADE_WETLAND_SQL = text("""
    UPDATE candidates
    SET score_tier = 'C'::scoretierenum
    WHERE has_critical_area_overlap = true
      AND score_tier IN ('A', 'B')
""")

# Step 5: Flag HOA-owned parcels for review (don't delete — Mike may still approach)
FLAG_HOA_SQL = text("""
    UPDATE candidates c
    SET flagged_for_review = true
    FROM parcels p
    WHERE c.parcel_id = p.id
      AND COALESCE(p.owner_name, '') ILIKE ANY(ARRAY[
          '%ASSOCIATION%', '%HOMEOWNERS%', '% HOA%', '%ASSN%'
      ])
""")

# Summary query
SUMMARY_SQL = text("""
    SELECT
        score_tier,
        count(*) as count,
        sum(potential_splits) as total_splits,
        round(avg(estimated_land_value)::numeric, 0) as avg_land_value,
        sum(CASE WHEN has_critical_area_overlap THEN 1 ELSE 0 END) as wetland_flagged,
        sum(CASE WHEN flagged_for_review THEN 1 ELSE 0 END) as ag_flagged
    FROM candidates
    GROUP BY score_tier
    ORDER BY score_tier
""")


def run_scoring() -> dict:
    """Full scoring pipeline. Returns summary stats."""
    session = SessionLocal()
    try:
        # Step 1: Insert candidates
        result = session.execute(INSERT_CANDIDATES_SQL)
        new_candidates = result.rowcount
        session.commit()
        logger.info(f"Inserted {new_candidates:,} new candidates")

        if new_candidates == 0:
            logger.info("No new candidates — already up to date")
        else:
            # Step 2: Flag wetland overlaps
            logger.info("Flagging wetland overlaps (spatial join)...")
            session.execute(FLAG_WETLAND_SQL)
            session.commit()
            logger.info("Wetland flagging done")

            # Step 3: Flag ag area overlaps
            logger.info("Flagging agricultural area overlaps...")
            session.execute(FLAG_AG_SQL)
            session.commit()
            logger.info("Ag flagging done")

            # Step 4: Downgrade wetland-affected candidates
            session.execute(DOWNGRADE_WETLAND_SQL)
            session.commit()
            logger.info("Tier downgrade for wetland parcels done")

            # Step 5: Flag HOA-owned parcels for review
            logger.info("Flagging HOA-owned parcels for review...")
            session.execute(FLAG_HOA_SQL)
            session.commit()
            logger.info("HOA flagging done")

        # Summary
        rows = session.execute(SUMMARY_SQL).fetchall()
        summary = {}
        for row in rows:
            tier = row[0]
            summary[tier] = {
                "count": row[1],
                "total_splits": row[2],
                "avg_land_value": int(row[3] or 0),
                "wetland_flagged": row[4],
                "ag_flagged": row[5],
            }
            logger.info(
                f"  Tier {tier}: {row[1]:,} candidates, "
                f"{row[2]:,} potential splits, "
                f"{row[4]} wetland flags, {row[5]} ag flags"
            )

        return summary

    finally:
        session.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    summary = run_scoring()
    print(f"\nScoring complete: {summary}")
