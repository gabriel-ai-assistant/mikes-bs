from __future__ import annotations

try:
    import requests
except Exception:  # pragma: no cover - optional dependency fallback
    requests = None
import httpx

from ._geo import parcel_query_geom
from .api_client import FeasibilityAPIClient
from .context import AnalysisContext

SDA_URL = "https://SDMDataAccess.sc.egov.usda.gov/Tabular/post.rest"
SEPTIC_LAYER = "https://gis.snoco.org/host/rest/services/Hosted/Septic_Parcels/FeatureServer"


def _query_sda(wkt: str) -> list[dict]:
    sql = {
        "format": "JSON",
        "query": f"SELECT TOP 5 mukey FROM SDA_Get_Mukey_from_intersection_with_WktWgs84('{wkt}')",
    }
    try:
        if requests is not None:
            r = requests.post(SDA_URL, json=sql, timeout=45)
            r.raise_for_status()
            return r.json().get("Table", [])

        with httpx.Client(timeout=45.0) as client:
            r = client.post(SDA_URL, json=sql)
            r.raise_for_status()
            payload = r.json()
            return payload.get("Table", []) if isinstance(payload, dict) else []
    except Exception:
        return []


def run(ctx: AnalysisContext, client: FeasibilityAPIClient) -> AnalysisContext:
    if ctx.parcel_geom is None or len(ctx.parcel_geom) == 0:
        return ctx

    centroid = ctx.parcel_geom.geometry.iloc[0].centroid
    centroid_wgs = ctx.parcel_geom.to_crs(epsg=4326).geometry.iloc[0].centroid
    mukeys = _query_sda(centroid_wgs.wkt)
    if mukeys:
        ctx.add_tag("INFO_SOIL_TYPE")
        joined = " ".join(str(v).lower() for row in mukeys for v in row.values())
        if "poor" in joined or "drain" in joined:
            ctx.add_tag("RISK_POOR_SOIL_DRAINAGE")
    else:
        ctx.add_tag("RISK_DATA_INCOMPLETE")

    septic = client.query_feature_layer(SEPTIC_LAYER, 0, geometry=parcel_query_geom(ctx.parcel_geom))
    if len(septic) > 0:
        # if present in septic parcel layer, septic permitting complexity likely applies
        ctx.add_tag("RISK_SEPTIC_LIMITATION")
    return ctx
