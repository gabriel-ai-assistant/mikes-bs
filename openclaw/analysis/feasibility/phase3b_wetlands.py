from __future__ import annotations

import geopandas as gpd

from ._config import load_json
from ._geo import overlap_pct, parcel_query_geom
from .api_client import FeasibilityAPIClient
from .context import AnalysisContext

URL = "https://fwspublicservices.wim.usgs.gov/wetlandsmapservice/rest/services/Wetlands/MapServer"


def _cowardin_category(code: str) -> str:
    c = (code or "").upper()
    if c.startswith("PEM") or c.startswith("PSS"):
        return "II"
    if c.startswith("PFO"):
        return "I"
    if c.startswith("R"):
        return "III"
    return "IV"


def run(ctx: AnalysisContext, client: FeasibilityAPIClient) -> AnalysisContext:
    if ctx.parcel_geom is None or len(ctx.parcel_geom) == 0:
        return ctx
    rules = load_json("buffer_rules.json").get("wetlands", {})
    wetlands = client.query_feature_layer(URL, 0, geometry=parcel_query_geom(ctx.parcel_geom))
    if len(wetlands) == 0:
        ctx.constraint_layers["wetlands"] = wetlands
        return ctx

    ctx.add_tag("RISK_WETLAND_PRESENT")

    code_field = "ATTRIBUTE" if "ATTRIBUTE" in wetlands.columns else "WETLAND_TY"
    cat = [_cowardin_category(str(v)) for v in wetlands.get(code_field, [])]
    wetlands = wetlands.copy()
    wetlands["wetland_cat"] = cat
    wetlands["buffer_ft"] = wetlands["wetland_cat"].map(lambda c: float(rules.get(c, 40)))
    buffered = gpd.GeoDataFrame(wetlands.drop(columns=["geometry"]), geometry=[r.geometry.buffer(float(r.buffer_ft)) for _, r in wetlands.iterrows()], crs="EPSG:2285")
    ctx.constraint_layers["wetlands"] = buffered

    if overlap_pct(ctx.parcel_geom, buffered) > 0.20:
        ctx.add_tag("RISK_WETLAND_BUFFER_IMPACT")
    return ctx
