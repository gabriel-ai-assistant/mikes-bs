from __future__ import annotations

import geopandas as gpd
from shapely.geometry import box

from .context import AnalysisContext


STRATEGIES = [
    "max_lots",
    "equal_split",
    "road_optimized",
    "constraint_adaptive",
    "hybrid",
]


def _split_polygon(poly, n: int):
    minx, miny, maxx, maxy = poly.bounds
    width = (maxx - minx) / max(n, 1)
    lots = []
    for i in range(n):
        clip = box(minx + i * width, miny, minx + (i + 1) * width, maxy)
        part = poly.intersection(clip)
        if not part.is_empty:
            lots.append(part)
    return lots


def run(ctx: AnalysisContext) -> AnalysisContext:
    if ctx.buildable_geom is None or len(ctx.buildable_geom) == 0:
        return ctx

    poly = ctx.buildable_geom.geometry.iloc[0]
    min_lot_sqft = float((ctx.zoning_rules or {}).get("min_lot_sqft", 999999999))
    min_lot_width = float((ctx.zoning_rules or {}).get("min_lot_width_ft", 40))

    area = float(poly.area)
    max_n = int(area // min_lot_sqft)
    if max_n < 2:
        return ctx

    for strategy in STRATEGIES:
        if strategy == "max_lots":
            n = max_n
        elif strategy == "equal_split":
            n = min(3, max_n)
        elif strategy == "road_optimized":
            n = min(4, max_n)
        elif strategy == "constraint_adaptive":
            n = min(2, max_n)
        else:
            n = max(2, min(5, max_n))

        lots = _split_polygon(poly, n)
        valid_lots = []
        for lot in lots:
            minx, miny, maxx, maxy = lot.bounds
            width = min(maxx - minx, maxy - miny)
            if lot.area >= min_lot_sqft and width >= min_lot_width:
                valid_lots.append(lot)

        if len(valid_lots) < 2:
            continue

        plat_tag = "INFO_SHORT_PLAT" if len(valid_lots) <= 4 else "INFO_FORMAL_SUBDIVISION"
        ctx.layouts.append(
            {
                "id": f"{strategy}_{len(ctx.layouts)+1}",
                "strategy": strategy,
                "lot_count": len(valid_lots),
                "lots": gpd.GeoDataFrame(
                    {"lot_id": list(range(1, len(valid_lots) + 1))},
                    geometry=valid_lots,
                    crs="EPSG:2285",
                ),
                "tags": [plat_tag],
            }
        )

    return ctx
