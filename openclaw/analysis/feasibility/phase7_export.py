from __future__ import annotations

from pathlib import Path

import geopandas as gpd

from ._geo import to_feature_collection
from .context import AnalysisContext


def _safe_gdf(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Cast pandas StringDtype/ArrowDtype columns to object dtype so fiona/GDAL
    schema inference works across all pandas/geopandas version combinations.
    Note: str(StringDtype) returns 'str' in pandas 2.x, not 'string'.
    """
    import pandas as _pd
    gdf = gdf.copy()
    for col in gdf.columns:
        if col == gdf.geometry.name:
            continue
        dtype = gdf[col].dtype
        if isinstance(dtype, _pd.StringDtype) or (
            hasattr(_pd, "ArrowDtype") and isinstance(dtype, _pd.ArrowDtype)
        ):
            gdf[col] = gdf[col].astype(object)
    return gdf


def _write_geojson(gdf: gpd.GeoDataFrame, path: Path) -> None:
    if gdf is None or len(gdf) == 0:
        path.write_text('{"type":"FeatureCollection","features":[]}', encoding="utf-8")
        return
    _safe_gdf(gdf).to_file(path, driver="GeoJSON")


def run(ctx: AnalysisContext, output_dir: Path | None = None) -> AnalysisContext:
    out_dir = output_dir or ctx.ensure_output_dir()
    out_dir.mkdir(parents=True, exist_ok=True)

    if ctx.parcel_geom is not None:
        _write_geojson(ctx.parcel_geom, out_dir / "parcel.geojson")
    if ctx.buildable_geom is not None:
        _write_geojson(ctx.buildable_geom, out_dir / "buildable.geojson")

    for name, layer in ctx.constraint_layers.items():
        if layer is not None:
            _write_geojson(layer, out_dir / f"constraint_{name}.geojson")

    # layout exports
    for layout in ctx.layouts:
        lots = layout.get("lots")
        if lots is not None:
            _write_geojson(lots, out_dir / f"{layout['id']}_lots.geojson")
        driveways = layout.get("driveways")
        if driveways is not None:
            _write_geojson(driveways, out_dir / f"{layout['id']}_driveways.geojson")
        envelopes = layout.get("envelopes")
        if envelopes is not None:
            _write_geojson(envelopes, out_dir / f"{layout['id']}_envelopes.geojson")

    # geopackage — use _safe_gdf to avoid StringDtype fiona incompatibility
    gpkg = out_dir / "feasibility_layers.gpkg"
    if gpkg.exists():
        gpkg.unlink()
    if ctx.parcel_geom is not None and len(ctx.parcel_geom) > 0:
        _safe_gdf(ctx.parcel_geom).to_file(gpkg, layer="parcel", driver="GPKG")
    if ctx.buildable_geom is not None and len(ctx.buildable_geom) > 0:
        _safe_gdf(ctx.buildable_geom).to_file(gpkg, layer="buildable", driver="GPKG")

    # static PNG
    png_path = out_dir / "feasibility_map.png"
    try:
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(9, 7))
        if ctx.parcel_geom is not None and len(ctx.parcel_geom) > 0:
            ctx.parcel_geom.boundary.plot(ax=ax, color="black", linewidth=1.5, label="Parcel")
        for name, layer in ctx.constraint_layers.items():
            if layer is not None and len(layer) > 0 and name not in {"roads", "flu"}:
                layer.plot(ax=ax, facecolor="none", edgecolor="red", hatch="///", linewidth=0.7, alpha=0.6)
        if ctx.buildable_geom is not None and len(ctx.buildable_geom) > 0:
            ctx.buildable_geom.plot(ax=ax, color="#77c66e", alpha=0.4, label="Buildable")

        if ctx.layouts:
            best = ctx.layouts[0]
            lots = best.get("lots")
            if lots is not None and len(lots) > 0:
                lots.boundary.plot(ax=ax, color="blue", linestyle="--", linewidth=1, label="Lots")
            driveways = best.get("driveways")
            if driveways is not None and len(driveways) > 0:
                driveways.plot(ax=ax, color="orange", linewidth=1, label="Driveways")
            envelopes = best.get("envelopes")
            if envelopes is not None and len(envelopes) > 0:
                envelopes.boundary.plot(ax=ax, color="gray", linewidth=1, label="Envelopes")

        ax.set_title(f"Subdivision Feasibility: {ctx.parcel_id}")
        ax.set_axis_off()
        ax.legend(loc="upper right")
        fig.savefig(png_path, dpi=180, bbox_inches="tight")
        plt.close(fig)
    except Exception:
        png_path.write_bytes(b"")

    ctx.export_paths = {
        "output_dir": str(out_dir),
        "gpkg": str(gpkg),
        "png": str(png_path),
    }
    return ctx
