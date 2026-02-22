from __future__ import annotations

from .api_client import FeasibilityAPIClient
from .context import AnalysisContext

URL = "https://gis.snoco.org/scd/rest/services/MapService/pds_utility_districts/MapServer"


def run(ctx: AnalysisContext, client: FeasibilityAPIClient) -> AnalysisContext:
    if ctx.parcel_geom is None or len(ctx.parcel_geom) == 0:
        return ctx

    centroid = ctx.parcel_geom.geometry.iloc[0].centroid

    water = client.query_feature_layer(URL, 0)
    sewer = client.query_feature_layer(URL, 1)

    water_ok = len(water[water.geometry.contains(centroid)]) > 0 if len(water) > 0 else False
    sewer_ok = len(sewer[sewer.geometry.contains(centroid)]) > 0 if len(sewer) > 0 else False

    if water_ok:
        ctx.add_tag("INFO_PUBLIC_WATER_AVAILABLE")
    else:
        ctx.add_tag("RISK_WELL_REQUIRED")

    if sewer_ok:
        ctx.add_tag("INFO_PUBLIC_SEWER_AVAILABLE")
    else:
        ctx.add_tag("RISK_SEPTIC_REQUIRED")

    return ctx
