#!/usr/bin/env python3
"""Load zoning GeoJSON into zoning_polygons table, then spatial join to parcels.

Usage: python load_zoning.py <geojson_path> <county>
"""
import json
import sys
import os
import logging
from datetime import datetime, UTC

import psycopg2
from psycopg2.extras import execute_values

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DB_URL = os.environ.get("DATABASE_URL", "postgresql://openclaw:password@postgis:5432/openclaw")

BATCH_SIZE = 1000


def parse_dsn(url):
    return url.replace("postgresql+psycopg2://", "postgresql://")


def load_zoning(path, county):
    logger.info(f"Loading zoning from {path}")
    with open(path) as f:
        data = json.load(f)

    features = data.get("features", [])
    logger.info(f"Total zoning polygons: {len(features)}")

    conn = psycopg2.connect(parse_dsn(DB_URL))
    cur = conn.cursor()

    # Clear existing zoning polygons (full replace)
    cur.execute("TRUNCATE zoning_polygons")
    conn.commit()

    inserted = 0
    for i in range(0, len(features), BATCH_SIZE):
        batch = features[i:i + BATCH_SIZE]
        rows = []
        for feat in batch:
            props = feat.get("properties", {})
            geom = feat.get("geometry")
            if not geom:
                continue
            rows.append((
                props.get("ZONE_CD"),
                props.get("ABBREV"),
                props.get("LABEL"),
                json.dumps(geom),
            ))
        if rows:
            execute_values(cur, """
                INSERT INTO zoning_polygons (zone_cd, abbrev, label, geometry)
                VALUES %s
            """, rows, template="(%s, %s, %s, ST_GeomFromGeoJSON(%s))")
            conn.commit()
            inserted += len(rows)
            logger.info(f"  Batch {i//BATCH_SIZE+1}: {len(rows)} zones (total: {inserted})")

    logger.info(f"Loaded {inserted} zoning polygons")

    # Spatial join: assign zone_code to parcels
    logger.info(f"Running spatial join to assign zone codes to {county} parcels...")
    cur.execute("""
        UPDATE parcels p
        SET zone_code = z.abbrev
        FROM zoning_polygons z
        WHERE p.county = %s
          AND p.geometry IS NOT NULL
          AND ST_Intersects(ST_Centroid(p.geometry), z.geometry)
    """, (county,))
    updated = cur.rowcount
    conn.commit()
    logger.info(f"Assigned zone_code to {updated} parcels")

    # Stats
    cur.execute("SELECT zone_code, count(*) FROM parcels WHERE county = %s AND zone_code IS NOT NULL GROUP BY zone_code ORDER BY count DESC LIMIT 20", (county,))
    logger.info("Top zones:")
    for row in cur.fetchall():
        logger.info(f"  {row[0]}: {row[1]}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <geojson_path> <county>")
        sys.exit(1)
    load_zoning(sys.argv[1], sys.argv[2])
