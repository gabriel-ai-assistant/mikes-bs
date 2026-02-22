from __future__ import annotations

try:
    import numpy as np
except Exception:  # pragma: no cover - optional dependency fallback
    np = None

from .api_client import FeasibilityAPIClient
from .context import AnalysisContext

URL = "https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer"


def run(ctx: AnalysisContext, client: FeasibilityAPIClient) -> AnalysisContext:
    if ctx.parcel_geom is None or len(ctx.parcel_geom) == 0:
        return ctx

    minx, miny, maxx, maxy = ctx.parcel_geom.total_bounds
    arr = client.export_image_raster(
        URL,
        bbox=(minx, miny, maxx, maxy),
        bbox_sr=2285,
        size=(300, 300),
        rendering_rule={"rasterFunction": "Slope Degrees"},
    )

    if np is None:
        ctx.add_tag("RISK_DATA_INCOMPLETE")
        return ctx

    if arr is None or getattr(arr, "size", 0) == 0:
        ctx.add_tag("RISK_DATA_INCOMPLETE")
        return ctx

    valid = arr[np.isfinite(arr)]
    if valid.size == 0:
        return ctx

    pct_33 = float((valid >= 33).sum()) / float(valid.size)
    pct_15_33 = float(((valid >= 15) & (valid < 33)).sum()) / float(valid.size)
    ctx.metrics["slope_pct_33"] = pct_33
    ctx.metrics["slope_pct_15_33"] = pct_15_33

    if pct_33 > 0.20:
        ctx.add_tag("RISK_STEEP_SLOPE_33PCT")
    if pct_15_33 > 0.20:
        ctx.add_tag("RISK_EROSION_HAZARD_15PCT")
    if pct_33 > 0 or pct_15_33 > 0:
        ctx.add_tag("INFO_SLOPE_CONSTRAINT")
    return ctx
