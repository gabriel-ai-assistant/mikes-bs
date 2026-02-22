from __future__ import annotations

from .context import AnalysisContext


def run(ctx: AnalysisContext) -> AnalysisContext:
    if ctx.buildable_geom is None or len(ctx.buildable_geom) == 0:
        return ctx

    base_area = float(ctx.buildable_geom.geometry.area.iloc[0])
    reserve = base_area * 0.075
    ctx.metrics["stormwater_reserve_sqft"] = reserve

    min_lot_sqft = float((ctx.zoning_rules or {}).get("min_lot_sqft", 999999999))
    for layout in ctx.layouts:
        remaining = max(0.0, base_area - reserve)
        layout["buildable_after_stormwater_sqft"] = remaining
        if remaining < layout["lot_count"] * min_lot_sqft:
            layout.setdefault("tags", []).append("RISK_STORMWATER_CONSTRAINED")
            ctx.add_tag("RISK_STORMWATER_CONSTRAINED")
    return ctx
