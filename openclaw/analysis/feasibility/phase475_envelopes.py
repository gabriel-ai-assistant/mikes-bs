from __future__ import annotations

import geopandas as gpd

from .context import AnalysisContext


def run(ctx: AnalysisContext) -> AnalysisContext:
    front = float((ctx.zoning_rules or {}).get("setback_front_ft", 25))
    side = float((ctx.zoning_rules or {}).get("setback_side_ft", 10))
    rear = float((ctx.zoning_rules or {}).get("setback_rear_ft", 20))
    max_cov = float((ctx.zoning_rules or {}).get("max_lot_coverage_pct", 0.35))
    inset = max(front, side, rear)

    for layout in ctx.layouts:
        lots = layout.get("lots")
        if lots is None or len(lots) == 0:
            continue

        envelopes = []
        areas = []
        for lot in lots.geometry:
            env = lot.buffer(-inset)
            if env.is_empty:
                continue
            rect = env.minimum_rotated_rectangle
            capped = rect.intersection(lot.buffer(0))
            max_area = lot.area * max_cov
            if capped.area > max_area:
                # keep geometry valid while honoring coverage limit with a conservative inward buffer
                shrink = max(0.0, (capped.area - max_area) / max(capped.length, 1.0))
                capped = capped.buffer(-shrink)
                if capped.is_empty:
                    continue
            envelopes.append(capped)
            areas.append(float(capped.area))
            if capped.area < 1500:
                layout.setdefault("tags", []).append("RISK_TIGHT_BUILDING_ENVELOPE")
                ctx.add_tag("RISK_TIGHT_BUILDING_ENVELOPE")

        layout["envelopes"] = gpd.GeoDataFrame({"area_sqft": areas}, geometry=envelopes, crs="EPSG:2285")

    return ctx
