#!/usr/bin/env python3
"""Load WA Wetlands (clipped to county bbox) and Agricultural Land into PostGIS.

Usage:
    DATABASE_URL=postgresql://... python load_critical_areas.py <wetlands_gpkg> <ag_gpkg> <county>

Snohomish County approximate bbox (EPSG:4326):
    lon: -122.7 to -121.4
    lat: 47.7 to 48.3
"""
import sys
import os
import logging

import psycopg2
from psycopg2.extras import execute_values

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

BATCH_SIZE = 1000

# Snohomish County bounding box in WGS84 — used to clip statewide wetlands
SNOHOMISH_BBOX = (-122.75, 47.70, -121.35, 48.35)


def parse_db_url(url):
    return url.replace("postgresql+psycopg2://", "postgresql://")


def load_wetlands(gpkg_path, county, conn_dst):
    import sqlite3

    logger.info(f"Loading wetlands from {gpkg_path}")
    conn_src = sqlite3.connect(gpkg_path)
    cur_src = conn_src.cursor()

    cur_src.execute("SELECT table_name FROM gpkg_contents WHERE data_type='features'")
    layer = cur_src.fetchone()[0]
    logger.info(f"Wetlands layer: {layer}")

    cur_src.execute(f"SELECT srs_id FROM gpkg_geometry_columns WHERE table_name='{layer}'")
    srid = int(cur_src.fetchone()[0])
    logger.info(f"Wetlands SRID: {srid}")

    cur_src.execute(f"PRAGMA table_info('{layer}')")
    cols = {r[1]: r[0] for r in cur_src.fetchall()}
    geom_col = next((c for c in cols if c.lower() in ('shape', 'geom', 'geometry')), None)

    if srid != 4326:
        geom_expr = f"ST_Transform(ST_GeomFromWKB(%s::bytea, {srid}), 4326)"
    else:
        geom_expr = f"ST_GeomFromWKB(%s::bytea, 4326)"

    # Clear existing wetlands for this county
    cur_dst = conn_dst.cursor()
    cur_dst.execute("DELETE FROM critical_areas WHERE source='wetlands' AND area_type LIKE %s", (f"{county}%",))
    conn_dst.commit()
    logger.info("Cleared existing wetlands")

    # Use bbox envelope to filter statewide dataset — much faster than loading all 611K
    minlon, minlat, maxlon, maxlat = SNOHOMISH_BBOX

    # Build a PostGIS bbox filter — we'll filter after transform
    # For SRID 4326 input just use min/max lon/lat directly
    # For SRID 3857 (web mercator) we need to convert bbox
    if srid == 4326:
        bbox_filter = f"minx >= {minlon} AND miny >= {minlat} AND maxx <= {maxlon} AND maxy <= {maxlat}"
    else:
        # We'll load everything and let PostGIS filter — too complex for bbox pre-filter
        bbox_filter = None

    upsert_sql = """
        INSERT INTO critical_areas (source, area_type, geometry)
        VALUES %s
    """

    def get(row, field):
        idx = cols.get(field)
        return row[idx] if idx is not None else None

    # Query using GPKG rtree index if available for bbox filter
    cur_src.execute(f"SELECT count(*) FROM '{layer}'")
    total = cur_src.fetchone()[0]
    logger.info(f"Total wetland features: {total:,} — loading Snohomish area subset")

    # Use rtree spatial index if available
    rtree_table = f"rtree_{layer}_{geom_col}"
    try:
        if srid == 4326:
            cur_src.execute(f"""
                SELECT w.* FROM '{layer}' w
                JOIN '{rtree_table}' r ON w.rowid = r.id
                WHERE r.miny >= {minlat} AND r.maxy <= {maxlat}
                  AND r.minx >= {minlon} AND r.maxx <= {maxlon}
            """)
            logger.info("Using rtree spatial index for bbox filter")
        else:
            cur_src.execute(f"SELECT * FROM '{layer}'")
    except Exception:
        logger.info("rtree not available, loading all wetlands")
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

            wetland_type = get(row, "WETLAND_TYPE") or "Wetland"
            area_type = f"{county}:{wetland_type}"

            batch.append(("wetlands", area_type, wkb))
        except Exception as e:
            errors += 1
            if errors <= 3:
                logger.warning(f"Row skip: {e}")
            continue

        if len(batch) >= BATCH_SIZE:
            try:
                execute_values(cur_dst, upsert_sql, batch,
                    template=f"(%s,%s,{geom_expr})")
                conn_dst.commit()
                inserted += len(batch)
                if inserted % 10000 == 0:
                    logger.info(f"  Wetlands: {inserted:,} loaded...")
            except Exception as e:
                logger.error(f"Batch error: {e}")
                conn_dst.rollback()
            batch = []

    if batch:
        try:
            execute_values(cur_dst, upsert_sql, batch,
                template=f"(%s,%s,{geom_expr})")
            conn_dst.commit()
            inserted += len(batch)
        except Exception as e:
            logger.error(f"Final batch error: {e}")
            conn_dst.rollback()

    logger.info(f"Wetlands loaded: {inserted:,} (errors: {errors:,})")
    conn_src.close()
    return inserted


def load_agricultural(gpkg_path, county, conn_dst):
    import sqlite3

    logger.info(f"Loading agricultural areas from {gpkg_path}")
    conn_src = sqlite3.connect(gpkg_path)
    cur_src = conn_src.cursor()

    cur_src.execute("SELECT table_name FROM gpkg_contents WHERE data_type='features'")
    layer = cur_src.fetchone()[0]

    cur_src.execute(f"SELECT srs_id FROM gpkg_geometry_columns WHERE table_name='{layer}'")
    srid = int(cur_src.fetchone()[0])

    cur_src.execute(f"PRAGMA table_info('{layer}')")
    cols = {r[1]: r[0] for r in cur_src.fetchall()}
    geom_col = next((c for c in cols if c.lower() in ('shape', 'geom', 'geometry')), None)

    if srid != 4326:
        geom_expr = f"ST_Transform(ST_GeomFromWKB(%s::bytea, {srid}), 4326)"
    else:
        geom_expr = f"ST_GeomFromWKB(%s::bytea, 4326)"

    cur_dst = conn_dst.cursor()
    cur_dst.execute("DELETE FROM agricultural_areas WHERE county=%s", (county,))
    conn_dst.commit()

    upsert_sql = """
        INSERT INTO agricultural_areas (county, label, farmlands, flu_desig, notice, geometry)
        VALUES %s
    """

    def get(row, field):
        idx = cols.get(field)
        return row[idx] if idx is not None else None

    cur_src.execute(f"SELECT * FROM '{layer}'")
    batch = []
    inserted = 0

    for row in cur_src:
        try:
            geom_raw = get(row, geom_col)
            if not geom_raw or not isinstance(geom_raw, bytes) or len(geom_raw) < 9:
                continue
            wkb = geom_raw[8:]
            batch.append((
                county,
                get(row, "LABEL"),
                get(row, "FARMLANDS"),
                get(row, "FLU_DESIG"),
                get(row, "NOTICE"),
                wkb,
            ))
        except Exception:
            continue

    if batch:
        try:
            execute_values(cur_dst, upsert_sql, batch,
                template=f"(%s,%s,%s,%s,%s,{geom_expr})")
            conn_dst.commit()
            inserted = len(batch)
        except Exception as e:
            logger.error(f"Ag load error: {e}")
            conn_dst.rollback()

    logger.info(f"Agricultural areas loaded: {inserted}")
    conn_src.close()
    return inserted


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print(f"Usage: {sys.argv[0]} <wetlands_gpkg> <ag_gpkg> <county>")
        sys.exit(1)

    wetlands_gpkg = sys.argv[1]
    ag_gpkg = sys.argv[2]
    county = sys.argv[3]

    db_url = parse_db_url(os.environ["DATABASE_URL"])
    conn = psycopg2.connect(db_url)

    w = load_wetlands(wetlands_gpkg, county, conn)
    a = load_agricultural(ag_gpkg, county, conn)

    conn.close()
    logger.info(f"Phase C complete — wetlands: {w:,}, ag areas: {a}")
