from __future__ import annotations

import geopandas as gpd

from ._geo import safe_union
from .context import AnalysisContext


def run(ctx: AnalysisContext) -> AnalysisContext:
    if ctx.parcel_geom is None or len(ctx.parcel_geom) == 0:
        ctx.add_tag("RISK_DATA_INCOMPLETE")
        return ctx

    parcel = ctx.parcel_geom.geometry.iloc[0]

    front = float((ctx.zoning_rules or {}).get("setback_front_ft", 25))
    side = float((ctx.zoning_rules or {}).get("setback_side_ft", 10))
    rear = float((ctx.zoning_rules or {}).get("setback_rear_ft", 20))
    inset = max(front, side, rear)

    setback_envelope = parcel.buffer(-inset) if inset > 0 else parcel
    if setback_envelope.is_empty:
        ctx.buildable_geom = gpd.GeoDataFrame(geometry=[], crs="EPSG:2285")
        ctx.add_tag("RISK_NOT_SUBDIVIDABLE")
        ctx.stop = True
        return ctx

    excluded = []
    for name, layer in ctx.constraint_layers.items():
        if name in {"roads", "flu"}:
            continue
        if layer is not None and len(layer) > 0:
            excluded.append(layer)

    excluded_union = None
    if excluded:
        merged = gpd.GeoDataFrame(geometry=[g for layer in excluded for g in layer.geometry], crs="EPSG:2285")
        excluded_union = safe_union(merged)

    buildable = setback_envelope if excluded_union is None else setback_envelope.difference(excluded_union)

    if buildable.is_empty:
        out = gpd.GeoDataFrame(geometry=[], crs="EPSG:2285")
    else:
        out = gpd.GeoDataFrame(geometry=[buildable], crs="EPSG:2285")

    ctx.buildable_geom = out

    min_lot_sqft = float((ctx.zoning_rules or {}).get("min_lot_sqft", 999999999))
    if len(out) == 0 or out.geometry.area.iloc[0] < 2 * min_lot_sqft:
        ctx.add_tag("RISK_NOT_SUBDIVIDABLE")
        ctx.stop = True

    return ctx
