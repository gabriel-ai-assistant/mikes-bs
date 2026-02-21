"""Abstract base class for county parcel ingest agents."""

import abc
import logging
import time
from datetime import datetime

import geopandas as gpd
import httpx
from shapely.geometry import shape
from sqlalchemy.dialects.postgresql import insert

from openclaw.db.models import Parcel, CountyEnum
from openclaw.db.session import SessionLocal

logger = logging.getLogger(__name__)

PAGE_SIZE = 2000
MAX_RETRIES = 3


class BaseIngestAgent(abc.ABC):
    """Base class for county ArcGIS REST API ingest agents."""

    county: CountyEnum
    endpoint: str
    field_map: dict[str, str]  # ArcGIS field -> our field

    @property
    @abc.abstractmethod
    def out_fields(self) -> str:
        """Comma-separated ArcGIS field names to request."""

    def _build_params(self, offset: int) -> dict:
        return {
            "where": "1=1",
            "outFields": self.out_fields,
            "outSR": "4326",
            "f": "geojson",
            "resultOffset": offset,
            "resultRecordCount": PAGE_SIZE,
        }

    async def fetch_page(self, client: httpx.AsyncClient, offset: int) -> dict:
        """Fetch a single page from ArcGIS REST API with retry."""
        params = self._build_params(offset)
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = await client.get(self.endpoint, params=params, timeout=60)
                resp.raise_for_status()
                data = resp.json()
                if "features" not in data:
                    raise ValueError(f"No 'features' key in response: {list(data.keys())}")
                return data
            except (httpx.HTTPError, ValueError) as e:
                if attempt == MAX_RETRIES:
                    raise
                wait = 2 ** attempt
                logger.warning(f"{self.county.value} page {offset}: attempt {attempt} failed ({e}), retrying in {wait}s")
                time.sleep(wait)

    def normalize(self, geojson: dict) -> gpd.GeoDataFrame:
        """Normalize ArcGIS GeoJSON features to standard schema."""
        records = []
        for feat in geojson.get("features", []):
            props = feat.get("properties", {})
            geom = feat.get("geometry")
            row = {"county": self.county.value}
            for arcgis_field, our_field in self.field_map.items():
                row[our_field] = props.get(arcgis_field)
            if geom:
                try:
                    row["geometry"] = shape(geom)
                except Exception:
                    row["geometry"] = None
            else:
                row["geometry"] = None
            records.append(row)

        if not records:
            return gpd.GeoDataFrame()

        gdf = gpd.GeoDataFrame(records, geometry="geometry", crs="EPSG:4326")
        return gdf

    def upsert(self, gdf: gpd.GeoDataFrame) -> dict:
        """Upsert normalized GeoDataFrame into parcels table. Returns counts."""
        if gdf.empty:
            return {"inserted": 0, "updated": 0}

        session = SessionLocal()
        inserted = 0
        updated = 0
        try:
            for _, row in gdf.iterrows():
                geom_wkt = row.geometry.wkt if row.geometry else None
                values = {
                    "parcel_id": str(row.get("parcel_id", "")),
                    "county": row["county"],
                    "address": row.get("address"),
                    "owner_name": row.get("owner_name"),
                    "lot_sf": int(row["lot_sf"]) if row.get("lot_sf") else None,
                    "zone_code": row.get("zone_code"),
                    "present_use": row.get("present_use"),
                    "assessed_value": int(row["assessed_value"]) if row.get("assessed_value") else None,
                    "geometry": f"SRID=4326;{geom_wkt}" if geom_wkt else None,
                    "updated_at": datetime.utcnow(),
                }
                stmt = insert(Parcel).values(**values, ingested_at=datetime.utcnow())
                stmt = stmt.on_conflict_do_update(
                    constraint="uq_parcel_county",
                    set_={k: v for k, v in values.items() if k != "parcel_id"},
                )
                result = session.execute(stmt)
                if result.rowcount:
                    inserted += 1  # simplified — counts both insert and update
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

        return {"inserted": inserted, "updated": updated}

    async def run(self) -> dict:
        """Run full ingest: paginate, normalize, upsert."""
        logger.info(f"Starting ingest for {self.county.value}")
        total_fetched = 0
        total_inserted = 0
        offset = 0

        async with httpx.AsyncClient() as client:
            while True:
                data = await self.fetch_page(client, offset)
                features = data.get("features", [])
                count = len(features)
                if count == 0:
                    break

                logger.info(f"{self.county.value}: page offset={offset}, records={count}")
                gdf = self.normalize(data)
                counts = self.upsert(gdf)

                total_fetched += count
                total_inserted += counts["inserted"]
                offset += PAGE_SIZE

                # ArcGIS signals end of data
                if count < PAGE_SIZE:
                    break

        summary = {
            "county": self.county.value,
            "total_fetched": total_fetched,
            "total_upserted": total_inserted,
        }
        logger.info(f"Ingest complete: {summary}")
        return summary


if __name__ == "__main__":
    print("Base ingest agent — not runnable standalone.")
