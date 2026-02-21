#!/usr/bin/env python3
"""Load county parcels from GeoPackage into PostGIS.

Usage:
    DATABASE_URL=postgresql://... python load_parcels_gpkg.py <gpkg_path> <county>

GPKG geometry is stored as WKB with an 8-byte GPKG envelope header.
Strip the header, pass raw WKB to PostGIS ST_GeomFromWKB, then ST_Transform to 4326.
"""
import sys
import os
import logging
from datetime import datetime

import psycopg2
from psycopg2.extras import execute_values

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

BATCH_SIZE = 500


def parse_db_url(url: str) -> str:
    return url.replace("postgresql+psycopg2://", "postgresql://")


def build_owner_address(row, cols: dict) -> str | None:
    def get(field):
        idx = cols.get(field)
        v = row[idx] if idx is not None else None
        return str(v).strip() if v else ""

    line1 = get("OWNERLINE1")
    city = get("OWNERCITY")
    state = get("OWNERSTATE")
    zipcode = get("OWNERZIP")
    state_zip = f"{state} {zipcode}".strip()
    parts = [p for p in [line1, city, state_zip] if p]
    return ", ".join(parts) or None


def parse_corrdate(val) -> datetime | None:
    if not val:
        return None
    try:
        return datetime.fromisoformat(str(val).replace("Z", "+00:00"))
    except Exception:
        return None


def safe_float(v) -> float | None:
    try:
        return float(v) if v is not None else None
    except (ValueError, TypeError):
        return None


def safe_int(v) -> int | None:
    try:
        return int(float(v)) if v is not None else None
    except (ValueError, TypeError):
        return None


def load(gpkg_path: str, county: str) -> None:
    import sqlite3

    logger.info(f"Opening GPKG: {gpkg_path}")
    conn_src = sqlite3.connect(gpkg_path)
    cur_src = conn_src.cursor()

    # Detect SRID
    cur_src.execute("SELECT srs_id FROM gpkg_geometry_columns WHERE table_name='Parcels'")
    row = cur_src.fetchone()
    srid = int(row[0]) if row else 4326
    logger.info(f"Source SRID: {srid}")

    # Column index map
    cur_src.execute("PRAGMA table_info('Parcels')")
    cols = {r[1]: r[0] for r in cur_src.fetchall()}
    logger.info(f"Columns ({len(cols)}): {list(cols.keys())}")

    # Detect geometry column name (SHAPE or geom depending on source)
    geom_col = "SHAPE" if "SHAPE" in cols else "geom"
    logger.info(f"Geometry column: {geom_col}")

    # Total active count
    cur_src.execute("SELECT count(*) FROM Parcels WHERE STATUS='A'")
    total = cur_src.fetchone()[0]
    logger.info(f"Active parcels to load: {total:,}")

    db_url = parse_db_url(os.environ["DATABASE_URL"])
    conn_dst = psycopg2.connect(db_url)
    cur_dst = conn_dst.cursor()

    # Build geometry expression — strip 8-byte GPKG header, transform if needed
    if srid != 4326:
        geom_expr = f"ST_Transform(ST_GeomFromWKB(%s::bytea, {srid}), 4326)"
    else:
        geom_expr = "ST_GeomFromWKB(%s::bytea, 4326)"

    upsert_sql = """
        INSERT INTO parcels (
            county, parcel_id, lrsn, corrdate,
            address, owner_name, owner_address,
            lot_sf, present_use,
            assessed_value, improvement_value, total_value,
            geometry
        ) VALUES %s
        ON CONFLICT (parcel_id, county) DO UPDATE SET
            lrsn              = EXCLUDED.lrsn,
            corrdate          = EXCLUDED.corrdate,
            address           = EXCLUDED.address,
            owner_name        = EXCLUDED.owner_name,
            owner_address     = EXCLUDED.owner_address,
            lot_sf            = EXCLUDED.lot_sf,
            present_use       = EXCLUDED.present_use,
            assessed_value    = EXCLUDED.assessed_value,
            improvement_value = EXCLUDED.improvement_value,
            total_value       = EXCLUDED.total_value,
            geometry          = EXCLUDED.geometry,
            updated_at        = now()
    """

    def get_col(row, field):
        idx = cols.get(field)
        return row[idx] if idx is not None else None

    cur_src.execute("SELECT * FROM Parcels WHERE STATUS='A'")

    batch = []
    inserted = 0
    errors = 0

    for row in cur_src:
        try:
            geom_raw = get_col(row, geom_col)
            if geom_raw is None or not isinstance(geom_raw, bytes) or len(geom_raw) < 9:
                errors += 1
                continue

            # Strip 8-byte GPKG geometry header → raw WKB
            wkb = geom_raw[8:]

            batch.append((
                county,
                get_col(row, "PARCEL_ID"),
                get_col(row, "LRSN"),
                parse_corrdate(get_col(row, "CORRDATE")),
                get_col(row, "SITUSLINE1"),
                get_col(row, "OWNERNAME"),
                build_owner_address(row, cols),
                safe_float(get_col(row, "GIS_SQ_FT")),
                get_col(row, "USECODE"),
                safe_int(get_col(row, "MKLND")),
                safe_int(get_col(row, "MKIMP")),
                safe_int(get_col(row, "MKTTL")),
                wkb,
            ))
        except Exception as e:
            errors += 1
            if errors <= 5:
                logger.warning(f"Row skip: {e}")
            continue

        if len(batch) >= BATCH_SIZE:
            try:
                execute_values(
                    cur_dst, upsert_sql, batch,
                    template=f"(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,{geom_expr})"
                )
                conn_dst.commit()
                inserted += len(batch)
                if (inserted // 10000) != ((inserted - len(batch)) // 10000):
                    logger.info(f"  Progress: {inserted:,}/{total:,} ({100*inserted//total}%)")
            except Exception as e:
                logger.error(f"Batch insert error at offset {inserted}: {e}")
                conn_dst.rollback()
                errors += len(batch)
            batch = []

    # Final batch
    if batch:
        try:
            execute_values(
                cur_dst, upsert_sql, batch,
                template=f"(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,{geom_expr})"
            )
            conn_dst.commit()
            inserted += len(batch)
        except Exception as e:
            logger.error(f"Final batch error: {e}")
            conn_dst.rollback()

    logger.info(f"Load complete — inserted/updated: {inserted:,}, skipped: {errors:,}")

    # Upsert watermark
    cur_dst.execute("""
        INSERT INTO sync_watermarks (county, source, last_sync, records_synced)
        VALUES (%s, 'gpkg_seed', now(), %s)
        ON CONFLICT (county, source) DO UPDATE SET
            last_sync = now(), records_synced = EXCLUDED.records_synced
    """, (county, inserted))
    conn_dst.commit()

    cur_src.close(); conn_src.close()
    cur_dst.close(); conn_dst.close()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <gpkg_path> <county>")
        sys.exit(1)
    load(sys.argv[1], sys.argv[2])
