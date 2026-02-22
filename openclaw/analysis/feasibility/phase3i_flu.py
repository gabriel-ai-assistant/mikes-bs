from __future__ import annotations

from ._geo import parcel_query_geom
from .api_client import FeasibilityAPIClient
from .context import AnalysisContext

URL = "https://gismaps.snoco.org/snocogis/rest/services/planning/mp_Future_Land_Use/MapServer"


def run(ctx: AnalysisContext, client: FeasibilityAPIClient) -> AnalysisContext:
    if ctx.parcel_geom is None or len(ctx.parcel_geom) == 0:
        return ctx

    flu = client.query_feature_layer(URL, 0, geometry=parcel_query_geom(ctx.parcel_geom))
    ctx.constraint_layers["flu"] = flu
    if len(flu) == 0:
        return ctx

    row = flu.iloc[0]
    des = row.get("DESIGNATION") or row.get("FLU_DESC") or row.get("LABEL")
    if des:
        ctx.add_tag(f"INFO_FLU_DESIGNATION:{des}")

    zoning = (ctx.zoning_code or "").upper()
    text = " ".join(str(v).upper() for v in row.drop(labels=["geometry"], errors="ignore").tolist())
    if zoning and zoning not in text:
        ctx.add_tag("INFO_FLU_ZONING_MISMATCH")
    return ctx
