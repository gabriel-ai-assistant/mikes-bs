#!/usr/bin/env python3
"""Load a county GeoJSON file directly into PostGIS parcels table.

Usage: python load_geojson.py <geojson_path> <county>
Example: python load_geojson.py /data/snohomish_parcels.geojson snohomish
"""
import json
import sys
import os
import logging
from datetime import datetime

import psycopg2
from psycopg2.extras import execute_values

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DB_URL = os.environ.get("DATABASE_URL", "postgresql://openclaw:password@postgis:5432/openclaw")

# Map GeoJSON properties to our DB columns per county
COUNTY_FIELD_MAPS = {
    "snohomish": {
        "parcel_id": "PARCEL_ID",
        "lot_sf": "GIS_SQ_FT",
        "address": "SITUSLINE1",
        "owner_name": "OWNERNAME",
        "present_use": "USECODE",
        "assessed_value": "MKLND",
    },
}

STATUS_FIELD = "STATUS"
ACTIVE_STATUS = "A"
BATCH_SIZE = 5000


def parse_dsn(url: str) -> str:
    """Convert SQLAlchemy URL to psycopg2 DSN."""
    url = url.replace("postgresql+psycopg2://", "postgresql://")
    return url


def load_geojson(path: str, county: str):
    field_map = COUNTY_FIELD_MAPS.get(county)
    if not field_map:
        logger.error(f"No field map for county: {county}")
        sys.exit(1)

    logger.info(f"Loading {path} for county={county}")
    logger.info("Reading GeoJSON (this may take a moment for large files)...")

    with open(path, "r") as f:
        data = json.load(f)

    features = data.get("features", [])
    logger.info(f"Total features in file: {len(features)}")

    # Filter to active parcels only
    active = [f for f in features if f.get("properties", {}).get(STATUS_FIELD) == ACTIVE_STATUS]
    logger.info(f"Active parcels (STATUS=A): {len(active)}")

    conn = psycopg2.connect(parse_dsn(DB_URL))
    cur = conn.cursor()

    # Ensure PostGIS extension
    cur.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    inserted = 0
    skipped = 0

    for i in range(0, len(active), BATCH_SIZE):
        batch = active[i:i + BATCH_SIZE]
        rows = []
        for feat in batch:
            props = feat.get("properties", {})
            geom = feat.get("geometry")

            parcel_id = props.get(field_map["parcel_id"])
            if not parcel_id:
                skipped += 1
                continue

            lot_sf_raw = props.get(field_map.get("lot_sf", ""), None)
            lot_sf = int(float(lot_sf_raw)) if lot_sf_raw else None

            assessed_raw = props.get(field_map.get("assessed_value", ""), None)
            assessed = int(float(assessed_raw)) if assessed_raw else None

            geom_json = json.dumps(geom) if geom else None

            rows.append((
                str(parcel_id),
                county,
                props.get(field_map.get("address", ""), None),
                props.get(field_map.get("owner_name", ""), None),
                lot_sf,
                None,  # zone_code — not in this dataset
                props.get(field_map.get("present_use", ""), None),
                assessed,
                geom_json,
                datetime.utcnow(),
                datetime.utcnow(),
            ))

        if rows:
            execute_values(cur, """
                INSERT INTO parcels (parcel_id, county, address, owner_name, lot_sf, zone_code, present_use, assessed_value, geometry, ingested_at, updated_at)
                VALUES %s
                ON CONFLICT ON CONSTRAINT uq_parcel_county
                DO UPDATE SET
                    address = EXCLUDED.address,
                    owner_name = EXCLUDED.owner_name,
                    lot_sf = EXCLUDED.lot_sf,
                    present_use = EXCLUDED.present_use,
                    assessed_value = EXCLUDED.assessed_value,
                    geometry = EXCLUDED.geometry,
                    updated_at = EXCLUDED.updated_at
            """, rows, template="(%s, %s, %s, %s, %s, %s, %s, %s, ST_GeomFromGeoJSON(%s), %s, %s)")
            conn.commit()
            inserted += len(rows)
            logger.info(f"  Batch {i//BATCH_SIZE + 1}: inserted/updated {len(rows)} (total: {inserted})")

    cur.close()
    conn.close()
    logger.info(f"Done. Loaded {inserted} parcels, skipped {skipped}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <geojson_path> <county>")
        sys.exit(1)
    load_geojson(sys.argv[1], sys.argv[2])
