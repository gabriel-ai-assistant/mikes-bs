from __future__ import annotations

import geopandas as gpd

from ._config import load_json
from ._geo import overlap_pct, parcel_query_geom
from .api_client import FeasibilityAPIClient
from .context import AnalysisContext

PRIMARY = "https://gismaps.snoco.org/snocogis/rest/services/hydrography/Watercourse/MapServer"
FALLBACK = "https://hydro.nationalmap.gov/arcgis/rest/services/nhd/MapServer"


def run(ctx: AnalysisContext, client: FeasibilityAPIClient) -> AnalysisContext:
    if ctx.parcel_geom is None or len(ctx.parcel_geom) == 0:
        return ctx

    rules = load_json("buffer_rules.json").get("streams", {})
    qgeom = parcel_query_geom(ctx.parcel_geom)

    streams = client.query_feature_layer(PRIMARY, 0, geometry=qgeom)
    if len(streams) == 0:
        streams = client.query_feature_layer(FALLBACK, 6, geometry=qgeom)

    if len(streams) == 0:
        ctx.add_tag("RISK_DATA_INCOMPLETE")
        ctx.constraint_layers["streams"] = streams
        return ctx

    type_field = "StreamType" if "StreamType" in streams.columns else "TYPE"
    def _buf(row) -> float:
        t = str(row.get(type_field, "")).strip()
        return float(rules.get(t, rules.get("default", 75)))

    buf_geom = [g.buffer(_buf(row)) for _, row in streams.iterrows() for g in [row.geometry]]
    buffered = gpd.GeoDataFrame(streams.drop(columns=["geometry"], errors="ignore"), geometry=buf_geom, crs="EPSG:2285")
    ctx.constraint_layers["streams"] = buffered

    if overlap_pct(ctx.parcel_geom, buffered) > 0.20:
        ctx.add_tag("RISK_STREAM_BUFFER_IMPACT")
    return ctx
