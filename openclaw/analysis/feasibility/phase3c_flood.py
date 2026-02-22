from __future__ import annotations

from ._geo import overlap_pct, parcel_query_geom
from .api_client import FeasibilityAPIClient
from .context import AnalysisContext

URL = "https://hazards.fema.gov/gis/nfhl/rest/services/public/NFHL/MapServer"


HIGH_RISK = {"A", "AE", "AO", "AH"}


def run(ctx: AnalysisContext, client: FeasibilityAPIClient) -> AnalysisContext:
    if ctx.parcel_geom is None or len(ctx.parcel_geom) == 0:
        return ctx

    flood = client.query_feature_layer(URL, 28, geometry=parcel_query_geom(ctx.parcel_geom))
    ctx.constraint_layers["flood"] = flood
    if len(flood) == 0:
        return ctx

    zone_field = "FLD_ZONE" if "FLD_ZONE" in flood.columns else "ZONE_SUBTY"
    zones = {str(z).strip().upper() for z in flood.get(zone_field, []) if z is not None}

    if zones & HIGH_RISK:
        ctx.add_tag("RISK_FEMA_100YR_FLOOD")
    if any("X" in z for z in zones):
        ctx.add_tag("INFO_FEMA_500YR_FLOOD")

    pct = overlap_pct(ctx.parcel_geom, flood[flood[zone_field].astype(str).str.upper().isin(HIGH_RISK)] if zone_field in flood.columns else flood)
    if pct > 0.90:
        ctx.add_tag("RISK_ENTIRE_PARCEL_FLOODPLAIN")
    return ctx
