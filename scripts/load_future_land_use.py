#!/usr/bin/env python3
"""Load Future Land Use GPKG into PostGIS, then spatial-join to assign zone_code to parcels.

Usage:
    DATABASE_URL=postgresql://... python load_future_land_use.py <gpkg_path> <county>
"""
import sys
import os
import json
import logging

import psycopg2
from psycopg2.extras import execute_values

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

BATCH_SIZE = 200


def parse_db_url(url):
    return url.replace("postgresql+psycopg2://", "postgresql://")


def load(gpkg_path, county):
    import sqlite3

    logger.info(f"Opening GPKG: {gpkg_path}")
    conn_src = sqlite3.connect(gpkg_path)
    cur_src = conn_src.cursor()

    # Find layer name
    cur_src.execute("SELECT table_name FROM gpkg_contents")
    layers = [r[0] for r in cur_src.fetchall()]
    layer = layers[0]
    logger.info(f"Layer: {layer}")

    # Get SRID
    cur_src.execute(f"SELECT srs_id FROM gpkg_geometry_columns WHERE table_name='{layer}'")
    row = cur_src.fetchone()
    srid = int(row[0]) if row else 4326
    logger.info(f"Source SRID: {srid}")

    # Column map
    cur_src.execute(f"PRAGMA table_info('{layer}')")
    cols = {r[1]: r[0] for r in cur_src.fetchall()}
    logger.info(f"Columns: {list(cols.keys())}")

    # Detect geometry column
    geom_col = next((c for c in cols if c.lower() in ('shape', 'geom', 'geometry')), None)
    logger.info(f"Geometry column: {geom_col}")

    cur_src.execute(f"SELECT count(*) FROM '{layer}'")
    total = cur_src.fetchone()[0]
    logger.info(f"FLU polygons to load: {total}")

    db_url = parse_db_url(os.environ["DATABASE_URL"])
    conn_dst = psycopg2.connect(db_url)
    cur_dst = conn_dst.cursor()

    # Truncate and reload (small table, full replace)
    cur_dst.execute(f"DELETE FROM future_land_use WHERE county = %s", (county,))
    conn_dst.commit()

    if srid != 4326:
        geom_expr = f"ST_Transform(ST_GeomFromWKB(%s::bytea, {srid}), 4326)"
    else:
        geom_expr = f"ST_GeomFromWKB(%s::bytea, 4326)"

    upsert_sql = """
        INSERT INTO future_land_use (county, flu_code, abbrev, label, uga, geometry)
        VALUES %s
    """

    def get(row, field):
        idx = cols.get(field)
        return row[idx] if idx is not None else None

    cur_src.execute(f"SELECT * FROM '{layer}'")
    batch = []
    inserted = 0
    errors = 0

    for row in cur_src:
        try:
            geom_raw = get(row, geom_col)
            if not geom_raw or not isinstance(geom_raw, bytes) or len(geom_raw) < 9:
                errors += 1
                continue
            wkb = geom_raw[8:]

            # Try USE_ or OBJECTID for flu_code
            flu_code = get(row, "USE_") or get(row, "OBJECTID")
            abbrev = get(row, "ABBREV")
            label = get(row, "LABEL")
            uga_raw = get(row, "UGA")
            uga = int(uga_raw) if uga_raw is not None else None

            batch.append((county, flu_code, abbrev, label, uga, wkb))
        except Exception as e:
            errors += 1
            if errors <= 3:
                logger.warning(f"Row skip: {e}")
            continue

        if len(batch) >= BATCH_SIZE:
            try:
                execute_values(cur_dst, upsert_sql, batch,
                    template=f"(%s,%s,%s,%s,%s,{geom_expr})")
                conn_dst.commit()
                inserted += len(batch)
            except Exception as e:
                logger.error(f"Batch error: {e}")
                conn_dst.rollback()
            batch = []

    if batch:
        try:
            execute_values(cur_dst, upsert_sql, batch,
                template=f"(%s,%s,%s,%s,%s,{geom_expr})")
            conn_dst.commit()
            inserted += len(batch)
        except Exception as e:
            logger.error(f"Final batch error: {e}")
            conn_dst.rollback()

    logger.info(f"Loaded {inserted} FLU polygons (errors: {errors})")

    # Show unique zone codes
    cur_dst.execute("SELECT abbrev, label, count(*) FROM future_land_use WHERE county=%s GROUP BY abbrev, label ORDER BY count DESC LIMIT 20", (county,))
    logger.info("FLU zones loaded:")
    for r in cur_dst.fetchall():
        logger.info(f"  {r[0]}: {r[1]} ({r[2]} polygons)")

    # Spatial join: assign zone_code to parcels using FLU polygons
    logger.info("Running spatial join to assign zone_code to parcels...")
    cur_dst.execute("""
        UPDATE parcels p
        SET zone_code = f.abbrev
        FROM future_land_use f
        WHERE p.county = %s
          AND p.geometry IS NOT NULL
          AND f.county = %s
          AND ST_Intersects(ST_PointOnSurface(p.geometry), f.geometry)
    """, (county, county))
    updated = cur_dst.rowcount
    conn_dst.commit()
    logger.info(f"Assigned zone_code to {updated:,} parcels")

    # Stats
    cur_dst.execute("""
        SELECT zone_code, count(*) as cnt
        FROM parcels WHERE county=%s AND zone_code IS NOT NULL
        GROUP BY zone_code ORDER BY cnt DESC LIMIT 15
    """, (county,))
    logger.info("Top zone codes assigned:")
    for r in cur_dst.fetchall():
        logger.info(f"  {r[0]}: {r[1]:,}")

    cur_src.close(); conn_src.close()
    cur_dst.close(); conn_dst.close()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <gpkg_path> <county>")
        sys.exit(1)
    load(sys.argv[1], sys.argv[2])
