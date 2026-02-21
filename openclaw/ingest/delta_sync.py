"""Nightly delta sync — pulls changed/new parcels from ArcGIS REST API
using CORRDATE watermark, upserts into PostGIS, then re-scores affected parcels.

County endpoints:
  snohomish: https://gis.snoco.org/host/rest/services/Hosted/CADASTRAL__parcels/FeatureServer/0/query
  king:       https://gismaps.kingcounty.gov/arcgis/rest/services/Property/KingCo_PropertyInfo/MapServer/2/query
"""
import logging
import os
from datetime import datetime, timezone
from typing import Optional

import httpx
from sqlalchemy import text

from openclaw.db.session import SessionLocal

logger = logging.getLogger(__name__)

PAGE_SIZE = 1000
REQUEST_TIMEOUT = 30.0

ENDPOINTS = {
    "snohomish": {
        "url": "https://gis.snoco.org/host/rest/services/Hosted/CADASTRAL__parcels/FeatureServer/0/query",
        "fields": "PARCEL_ID,LRSN,CORRDATE,GIS_SQ_FT,USECODE,MKLND,MKIMP,MKTTL,SITUSLINE1,OWNERNAME,OWNERLINE1,OWNERCITY,OWNERSTATE,OWNERZIP",
        "where_field": "CORRDATE",
        "parcel_id_field": "PARCEL_ID",
    },
    "king": {
        "url": "https://gismaps.kingcounty.gov/arcgis/rest/services/Property/KingCo_PropertyInfo/MapServer/2/query",
        "fields": "PIN,ADDR_FULL,LOTSQFT,PREUSE_DESC,KCA_ZONING,APPRLNDVAL",
        "where_field": "LAST_UPDATE_DATE",
        "parcel_id_field": "PIN",
    },
}


def get_watermark(session, county: str) -> Optional[datetime]:
    """Get last sync corrdate watermark for a county."""
    row = session.execute(text("""
        SELECT last_corrdate FROM sync_watermarks
        WHERE county = :county AND source = 'arcgis_delta'
    """), {"county": county}).fetchone()
    return row[0] if row else None


def set_watermark(session, county: str, corrdate: datetime, records: int):
    """Update the delta sync watermark."""
    session.execute(text("""
        INSERT INTO sync_watermarks (county, source, last_sync, last_corrdate, records_synced)
        VALUES (:county, 'arcgis_delta', now(), :corrdate, :records)
        ON CONFLICT (county, source) DO UPDATE SET
            last_sync = now(),
            last_corrdate = EXCLUDED.last_corrdate,
            records_synced = EXCLUDED.records_synced
    """), {"county": county, "corrdate": corrdate, "records": records})
    session.commit()


def fetch_delta(county: str, since: Optional[datetime]) -> list[dict]:
    """Fetch parcels changed since `since` from ArcGIS REST API."""
    ep = ENDPOINTS.get(county)
    if not ep:
        logger.warning(f"No endpoint configured for county: {county}")
        return []

    where_field = ep["where_field"]
    if since:
        # ArcGIS uses timestamp format: 'YYYY-MM-DD HH:MM:SS'
        since_str = since.strftime("%Y-%m-%d %H:%M:%S")
        where = f"{where_field} > TIMESTAMP '{since_str}'"
    else:
        # First run — only pull last 30 days to avoid overwhelming
        where = f"{where_field} > TIMESTAMP '2026-01-01 00:00:00'"

    params = {
        "where": where,
        "outFields": ep["fields"],
        "returnGeometry": "true",
        "outSR": "4326",
        "f": "json",
        "resultOffset": 0,
        "resultRecordCount": PAGE_SIZE,
    }

    all_features = []
    offset = 0

    with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
        while True:
            params["resultOffset"] = offset
            try:
                resp = client.get(ep["url"], params=params)
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                logger.error(f"ArcGIS API error (county={county}, offset={offset}): {e}")
                break

            if "error" in data:
                logger.error(f"ArcGIS error response: {data['error']}")
                break

            features = data.get("features", [])
            if not features:
                break

            all_features.extend(features)
            logger.info(f"  Fetched {len(all_features):,} records so far (county={county})")

            if not data.get("exceededTransferLimit", False):
                break

            offset += PAGE_SIZE

    return all_features


def upsert_snohomish_parcels(session, features: list[dict]) -> int:
    """Upsert Snohomish parcels from ArcGIS feature list."""
    if not features:
        return 0

    upserted = 0
    for feat in features:
        props = feat.get("attributes", {})
        geom = feat.get("geometry")

        parcel_id = props.get("PARCEL_ID")
        if not parcel_id:
            continue

        # Build owner address
        parts = [
            str(props.get("OWNERLINE1") or "").strip(),
            str(props.get("OWNERCITY") or "").strip(),
            f"{(props.get('OWNERSTATE') or '').strip()} {(props.get('OWNERZIP') or '').strip()}".strip(),
        ]
        owner_address = ", ".join(p for p in parts if p) or None

        # Parse corrdate (ArcGIS returns epoch ms)
        corrdate_raw = props.get("CORRDATE")
        corrdate = datetime.fromtimestamp(corrdate_raw / 1000, tz=timezone.utc) if corrdate_raw else None

        # Build geometry WKT from rings if present
        geom_sql = None
        if geom:
            if "rings" in geom:
                rings = geom["rings"]
                if rings:
                    ring_str = ",".join(
                        f"({','.join(f'{pt[0]} {pt[1]}' for pt in ring)})"
                        for ring in rings
                    )
                    geom_sql = f"ST_GeomFromText('MULTIPOLYGON(({ring_str}))', 4326)"
            elif "x" in geom:
                gx, gy = geom["x"], geom["y"]
                geom_sql = f"ST_GeomFromText('POINT({gx} {gy})', 4326)"

        try:
            if geom_sql:
                session.execute(text(f"""
                    INSERT INTO parcels (
                        county, parcel_id, lrsn, corrdate,
                        address, owner_name, owner_address,
                        lot_sf, present_use, assessed_value, improvement_value, total_value,
                        geometry
                    ) VALUES (
                        'snohomish', :parcel_id, :lrsn, :corrdate,
                        :address, :owner_name, :owner_address,
                        :lot_sf, :present_use, :assessed_value, :improvement_value, :total_value,
                        {geom_sql}
                    )
                    ON CONFLICT (parcel_id, county) DO UPDATE SET
                        lrsn = EXCLUDED.lrsn,
                        corrdate = EXCLUDED.corrdate,
                        address = EXCLUDED.address,
                        owner_name = EXCLUDED.owner_name,
                        owner_address = EXCLUDED.owner_address,
                        lot_sf = EXCLUDED.lot_sf,
                        present_use = EXCLUDED.present_use,
                        assessed_value = EXCLUDED.assessed_value,
                        improvement_value = EXCLUDED.improvement_value,
                        total_value = EXCLUDED.total_value,
                        geometry = {geom_sql},
                        updated_at = now()
                """), {
                    "parcel_id": parcel_id,
                    "lrsn": props.get("LRSN"),
                    "corrdate": corrdate,
                    "address": props.get("SITUSLINE1"),
                    "owner_name": props.get("OWNERNAME"),
                    "owner_address": owner_address,
                    "lot_sf": props.get("GIS_SQ_FT"),
                    "present_use": str(props.get("USECODE")) if props.get("USECODE") else None,
                    "assessed_value": props.get("MKLND"),
                    "improvement_value": props.get("MKIMP"),
                    "total_value": props.get("MKTTL"),
                })
            upserted += 1
        except Exception as e:
            logger.warning(f"Upsert error for parcel {parcel_id}: {e}")

    session.commit()
    return upserted


def re_score_county(session, county: str):
    """Remove stale candidates for county and re-run scorer."""
    # Remove candidates for parcels in this county that may have changed
    session.execute(text("""
        DELETE FROM candidates
        WHERE parcel_id IN (
            SELECT id FROM parcels WHERE county = :county
        )
        AND created_at < now() - interval '1 day'
    """), {"county": county})
    session.commit()
    logger.info(f"Cleared stale candidates for {county}")


def run_delta_sync(counties: list[str] = None) -> dict:
    """Run delta sync for specified counties. Default: all configured."""
    if counties is None:
        counties = list(ENDPOINTS.keys())

    results = {}
    session = SessionLocal()

    try:
        for county in counties:
            logger.info(f"Delta sync: {county}")
            watermark = get_watermark(session, county)
            logger.info(f"  Last corrdate watermark: {watermark}")

            features = fetch_delta(county, watermark)
            logger.info(f"  Fetched {len(features):,} changed parcels")

            if not features:
                results[county] = {"fetched": 0, "upserted": 0}
                continue

            if county == "snohomish":
                upserted = upsert_snohomish_parcels(session, features)
            else:
                logger.warning(f"No upsert handler for county: {county}")
                upserted = 0

            # Update watermark to max corrdate seen
            max_corrdate = datetime.now(tz=timezone.utc)
            set_watermark(session, county, max_corrdate, upserted)

            # Assign zone codes to newly upserted parcels via spatial join
            session.execute(text("""
                UPDATE parcels p
                SET zone_code = f.abbrev
                FROM future_land_use f
                WHERE p.county = :county
                  AND p.zone_code IS NULL
                  AND p.geometry IS NOT NULL
                  AND ST_Intersects(ST_PointOnSurface(p.geometry), f.geometry)
            """), {"county": county})
            session.commit()
            logger.info(f"  Zone codes assigned to new parcels")

            results[county] = {"fetched": len(features), "upserted": upserted}
            logger.info(f"  {county}: {upserted:,} parcels upserted")

    finally:
        session.close()

    return results


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    counties = sys.argv[1:] or None
    results = run_delta_sync(counties)
    for county, r in results.items():
        print(f"{county}: fetched={r['fetched']}, upserted={r['upserted']}")
