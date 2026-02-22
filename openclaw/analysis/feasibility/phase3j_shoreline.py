from __future__ import annotations

from ._geo import parcel_query_geom
from .api_client import FeasibilityAPIClient
from .context import AnalysisContext

URL = "https://gismaps.snoco.org/snocogis/rest/services/planning/mp_ShorelineManagementProgram/MapServer"


def run(ctx: AnalysisContext, client: FeasibilityAPIClient) -> AnalysisContext:
    if ctx.parcel_geom is None or len(ctx.parcel_geom) == 0:
        return ctx

    shore = client.query_feature_layer(URL, 0, geometry=parcel_query_geom(ctx.parcel_geom))
    ctx.constraint_layers["shoreline"] = shore
    if len(shore) == 0:
        return ctx

    if shore.distance(ctx.parcel_geom.geometry.iloc[0]).min() <= 200:
        ctx.add_tag("RISK_SHORELINE_JURISDICTION")
    return ctx
