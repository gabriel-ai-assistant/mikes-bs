"""
RUTA Boundary Enrichment
========================
Batch-updates candidates whose parcel centroid falls inside the RUTA
(Rural-Urban Transition Area) boundary loaded in ruta_boundaries.

For matching candidates:
  - Appends EDGE_SNOCO_RUTA_ARBITRAGE to tags (if not already present)
  - Removes RISK_RUTA_DATA_UNAVAILABLE from tags (if present)
  - Boosts score by +30 pts (capped at 100)
  - Recalculates score_tier

Usage:
    python -m openclaw.enrichment.ruta
"""

import logging
import os
import json

import psycopg2
import psycopg2.extras

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [ruta] %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

# Extract DSN pieces from DATABASE_URL env var
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+psycopg2://openclaw:password@postgis:5432/openclaw",
)

# Build a psycopg2-compatible DSN
def _make_dsn(url: str) -> str:
    # Strip driver prefix
    url = url.replace("postgresql+psycopg2://", "postgresql://")
    url = url.replace("postgresql+psycopg2:", "postgresql:")
    return url


RUTA_TAG = "EDGE_SNOCO_RUTA_ARBITRAGE"
RUTA_RISK_TAG = "RISK_RUTA_DATA_UNAVAILABLE"
SCORE_BOOST = 30
SCORE_CAP = 100

# Mirrors rule_engine.TIER_CUTOFFS
TIER_CUTOFFS = [
    (80, "A"),
    (65, "B"),
    (50, "C"),
    (35, "D"),
    (20, "E"),
    (0, "F"),
]


def score_to_tier(score: int) -> str:
    for cutoff, tier in TIER_CUTOFFS:
        if score >= cutoff:
            return tier
    return "F"


def run():
    dsn = _make_dsn(DATABASE_URL)
    conn = psycopg2.connect(dsn)
    conn.autocommit = False

    try:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            # ── 1. Find candidates inside RUTA ──
            log.info("Finding candidates inside RUTA boundary …")
            cur.execute("""
                SELECT c.id::text, c.score, c.tags
                FROM candidates c
                JOIN parcels p ON c.parcel_id = p.id
                WHERE ST_Within(
                    ST_Centroid(ST_Transform(p.geometry, 4326)),
                    (SELECT ST_Union(geometry) FROM ruta_boundaries)
                )
            """)
            rows = cur.fetchall()

        if not rows:
            log.info("No candidates found inside RUTA. Nothing to update.")
            conn.close()
            return

        log.info(f"Found {len(rows)} candidates inside RUTA boundary.")

        # ── 2. Build update list ──
        updates = []
        already_tagged = 0

        for row in rows:
            cid = row[0]
            score = row[1] or 0
            tags = list(row[2]) if row[2] else []

            if RUTA_TAG in tags:
                already_tagged += 1
                continue

            # Add EDGE tag, remove RISK placeholder
            new_tags = [t for t in tags if t != RUTA_RISK_TAG]
            new_tags.append(RUTA_TAG)

            new_score = min(int(score) + SCORE_BOOST, SCORE_CAP)
            new_tier = score_to_tier(new_score)

            updates.append((new_tags, new_score, new_tier, cid))

        if already_tagged:
            log.info(f"  {already_tagged} candidates already had {RUTA_TAG} — skipped.")

        if not updates:
            log.info("No new updates needed.")
            conn.close()
            return

        log.info(f"Updating {len(updates)} candidates …")

        # ── 3. Batch update via executemany ──
        with conn.cursor() as cur:
            psycopg2.extras.execute_batch(
                cur,
                """
                UPDATE candidates
                SET
                    tags       = %s::text[],
                    score      = %s,
                    score_tier = %s::scoretierenum
                WHERE id = %s::uuid
                """,
                updates,
                page_size=500,
            )

        conn.commit()

        log.info(
            f"Done. {len(updates)} candidates tagged with {RUTA_TAG}, "
            f"score boosted by +{SCORE_BOOST} pts (capped at {SCORE_CAP})."
        )

        # ── 4. Summary ──
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM candidates WHERE %s = ANY(tags)",
                (RUTA_TAG,),
            )
            total = cur.fetchone()[0]
        log.info(f"Total candidates now tagged {RUTA_TAG}: {total}")

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    run()
