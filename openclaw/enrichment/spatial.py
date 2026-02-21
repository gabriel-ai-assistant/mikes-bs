"""
Spatial enrichment jobs — run at ingestion, NOT at scoring time.
Materializes computed spatial attributes as columns on candidates/parcels.
"""
import logging
from sqlalchemy import text
from openclaw.db.session import SessionLocal

logger = logging.getLogger(__name__)


def populate_uga_outside(session) -> dict:
    """
    Materialize uga_outside on candidates via spatial join with future_land_use.
    future_land_use.uga: 0 = outside UGA (rural), 1 = inside UGA (urban)
    Sets candidates.uga_outside = True if outside, False if inside, NULL if no coverage.
    Returns count dict: {true: N, false: N, null: N}
    """
    session.execute(text("""
        UPDATE candidates c
        SET uga_outside = CASE
            WHEN flu.uga = 0 THEN true
            WHEN flu.uga = 1 THEN false
            ELSE NULL
        END
        FROM parcels p
        JOIN future_land_use flu ON ST_Within(p.geometry, flu.geometry)
        WHERE c.parcel_id = p.id
          AND c.uga_outside IS NULL
    """))
    session.commit()

    counts = session.execute(text("""
        SELECT uga_outside, count(*) FROM candidates GROUP BY uga_outside
    """)).fetchall()
    result_dict = {str(r[0]): r[1] for r in counts}
    logger.info(
        f"UGA enrichment: outside={result_dict.get('True', 0)}, "
        f"inside={result_dict.get('False', 0)}, "
        f"unknown={result_dict.get('None', 0)}"
    )
    return result_dict


def run_spatial_enrichment(session=None) -> None:
    """Run all spatial enrichments. Creates session if not provided."""
    own_session = session is None
    if own_session:
        session = SessionLocal()
    try:
        populate_uga_outside(session)
    finally:
        if own_session:
            session.close()


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    run_spatial_enrichment()
