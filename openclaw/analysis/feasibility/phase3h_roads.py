from __future__ import annotations

import geopandas as gpd

from ._geo import parcel_query_geom
from .api_client import FeasibilityAPIClient
from .context import AnalysisContext

URL = "https://gismaps.snoco.org/snocogis2/rest/services/planning/mp_Transportation/MapServer"


def run(ctx: AnalysisContext, client: FeasibilityAPIClient) -> AnalysisContext:
    if ctx.parcel_geom is None or len(ctx.parcel_geom) == 0:
        return ctx

    roads = client.query_feature_layer(URL, 0, geometry=parcel_query_geom(ctx.parcel_geom))
    ctx.constraint_layers["roads"] = roads
    if len(roads) == 0:
        ctx.add_tag("RISK_INSUFFICIENT_FRONTAGE")
        return ctx

    parcel_boundary = ctx.parcel_geom.geometry.iloc[0].boundary
    frontage = 0.0
    for geom in roads.geometry:
        frontage += parcel_boundary.buffer(50).intersection(geom.buffer(50)).length

    frontage = float(frontage)
    ctx.metrics["road_frontage_ft"] = frontage
    ctx.add_tag(f"INFO_ROAD_FRONTAGE_FT:{int(frontage)}")

    if frontage < 40:
        ctx.add_tag("RISK_INSUFFICIENT_FRONTAGE")
    elif frontage < 100:
        ctx.add_tag("INFO_FLAG_LOT_CANDIDATE")

    return ctx
