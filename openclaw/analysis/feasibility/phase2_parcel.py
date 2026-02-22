from __future__ import annotations

from dataclasses import dataclass

import geopandas as gpd

from .api_client import FeasibilityAPIClient
from .context import AnalysisContext


class ParcelNotFoundError(RuntimeError):
    pass


class CityParcelError(RuntimeError):
    pass


@dataclass
class _ParcelSource:
    url: str
    layer_id: int
    parcel_field: str


PARCEL_SOURCES = [
    _ParcelSource(
        url="https://gismaps.snoco.org/snocogis2/rest/services/cadastral/tax_parcels/MapServer",
        layer_id=0,
        parcel_field="Parcel_ID",
    ),
    _ParcelSource(
        url="https://gismaps.snoco.org/snocogis2/rest/services/planning/mp_ParcelLabels/MapServer",
        layer_id=0,
        parcel_field="Parcel_ID",
    ),
    _ParcelSource(
        url="https://gis.snoco.org/sas/rest/services/SCOPI/SCOPI_Labels_House_Number/MapServer",
        layer_id=0,
        parcel_field="Parcel_ID",
    ),
]


def _detect_city_parcel(gdf: gpd.GeoDataFrame) -> bool:
    city_fields = ["CITY", "MUNICIPALITY", "JURISDICTION"]
    for field in city_fields:
        if field in gdf.columns:
            values = {str(v).strip().lower() for v in gdf[field].dropna().tolist()}
            if values and values != {"unincorporated"}:
                return True
    return False


def run(ctx: AnalysisContext, client: FeasibilityAPIClient) -> AnalysisContext:
    parcel_gdf = gpd.GeoDataFrame(geometry=[], crs="EPSG:2285")

    for src in PARCEL_SOURCES:
        gdf = client.query_by_parcel_id(src.url, src.layer_id, src.parcel_field, ctx.parcel_id)
        if len(gdf) > 0:
            parcel_gdf = gdf.to_crs(epsg=2285)
            break

    if len(parcel_gdf) == 0:
        raise ParcelNotFoundError(f"Parcel {ctx.parcel_id} not found in source chain")

    if _detect_city_parcel(parcel_gdf):
        raise CityParcelError(f"Parcel {ctx.parcel_id} appears inside incorporated city")

    ctx.parcel_geom = parcel_gdf
    row = parcel_gdf.iloc[0]
    ctx.parcel_attrs = {
        "Parcel_ID": row.get("Parcel_ID") or row.get("PARCEL_ID") or ctx.parcel_id,
        "GIS_ACRES": row.get("GIS_ACRES"),
        "GIS_SQ_FT": row.get("GIS_SQ_FT"),
        "address": row.get("SITUS_ADDRESS") or row.get("address") or row.get("FULL_ADDRESS"),
        "owner": row.get("OWNER_NAME") or row.get("owner") or row.get("OWNER"),
    }
    return ctx
