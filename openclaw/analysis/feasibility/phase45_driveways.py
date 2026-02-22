from __future__ import annotations

import geopandas as gpd
from shapely.geometry import LineString

from .context import AnalysisContext


def run(ctx: AnalysisContext) -> AnalysisContext:
    roads = ctx.constraint_layers.get("roads")
    if roads is None or len(roads) == 0:
        for layout in ctx.layouts:
            layout.setdefault("tags", []).append("RISK_DRIVEWAY_INFEASIBLE")
        ctx.add_tag("RISK_DRIVEWAY_INFEASIBLE")
        return ctx

    for layout in ctx.layouts:
        lots = layout.get("lots")
        if lots is None or len(lots) == 0:
            continue

        lines = []
        lengths = []
        for lot in lots.geometry:
            c = lot.centroid
            nearest = roads.geometry.distance(c).idxmin()
            road = roads.loc[nearest].geometry
            p1 = road.interpolate(road.project(c))
            line = LineString([c, p1])
            lines.append(line)
            length = float(line.length)
            lengths.append(length)
            grade = length * 0.02 / max(length, 1) * 100  # proxy
            if grade > 12:
                layout.setdefault("tags", []).append("RISK_DRIVEWAY_STEEP")
                ctx.add_tag("RISK_DRIVEWAY_STEEP")
            if length > 200:
                layout.setdefault("tags", []).append("RISK_DRIVEWAY_INFEASIBLE")
                ctx.add_tag("RISK_DRIVEWAY_INFEASIBLE")

        dgdf = gpd.GeoDataFrame({"length_ft": lengths}, geometry=lines, crs="EPSG:2285")
        layout["driveways"] = dgdf
        if lengths:
            layout.setdefault("tags", []).append(f"INFO_DRIVEWAY_LENGTH:{int(sum(lengths))}")

    return ctx
