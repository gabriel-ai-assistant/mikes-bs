from __future__ import annotations

import os

from .context import AnalysisContext


def _rate(name: str, default: float) -> float:
    return float(os.getenv(name, str(default)))


def run(ctx: AnalysisContext) -> AnalysisContext:
    survey = _rate("FEAS_COST_SURVEY_ENGINEERING", 25000)
    plat_app = _rate("FEAS_COST_PLAT_APPLICATION", 18000)
    road_per_ft = _rate("FEAS_COST_ROAD_PER_FT", 220)
    utility_per_lot = _rate("FEAS_COST_UTILITY_PER_LOT", 18000)
    stormwater_base = _rate("FEAS_COST_STORMWATER_BASE", 60000)
    clearing_per_ac = _rate("FEAS_COST_CLEARING_PER_ACRE", 22000)

    for layout in ctx.layouts:
        lot_count = int(layout.get("lot_count", 0))
        driveways = layout.get("driveways")
        road_len = float(driveways.length.sum()) if driveways is not None and len(driveways) > 0 else 0.0
        build_area = float(ctx.buildable_geom.geometry.area.iloc[0]) if ctx.buildable_geom is not None and len(ctx.buildable_geom) > 0 else 0.0
        acres = build_area / 43560.0

        total = (
            survey
            + plat_app
            + road_len * road_per_ft
            + lot_count * utility_per_lot
            + stormwater_base
            + acres * clearing_per_ac
        )

        layout_cost = {
            "survey_engineering": round(survey, 2),
            "plat_application": round(plat_app, 2),
            "road": round(road_len * road_per_ft, 2),
            "utilities": round(lot_count * utility_per_lot, 2),
            "stormwater": round(stormwater_base, 2),
            "clearing": round(acres * clearing_per_ac, 2),
            "total": round(total, 2),
        }
        layout["cost_estimate"] = layout_cost

    ctx.cost_estimates = {layout["id"]: layout.get("cost_estimate", {}) for layout in ctx.layouts}
    return ctx
