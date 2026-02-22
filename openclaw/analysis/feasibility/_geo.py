from __future__ import annotations

import geopandas as gpd
from shapely.geometry import mapping


def empty_gdf() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(geometry=[], crs="EPSG:2285")


def parcel_query_geom(parcel: gpd.GeoDataFrame) -> dict:
    geom = parcel.geometry.iloc[0]
    if geom.geom_type == "Polygon":
        rings = [list(geom.exterior.coords)]
    else:
        poly = geom.convex_hull
        rings = [list(poly.exterior.coords)]
    return {"rings": rings, "spatialReference": {"wkid": 2285}}


def overlap_pct(parcel: gpd.GeoDataFrame, target: gpd.GeoDataFrame) -> float:
    if len(parcel) == 0 or len(target) == 0:
        return 0.0
    pgeom = parcel.geometry.iloc[0]
    inter_area = float(target.intersection(pgeom).area.sum())
    total = float(pgeom.area) or 1.0
    return inter_area / total


def safe_union(gdf: gpd.GeoDataFrame):
    if len(gdf) == 0:
        return None
    return gdf.unary_union


def to_feature_collection(gdf: gpd.GeoDataFrame) -> dict:
    features = []
    for _, row in gdf.iterrows():
        props = {k: v for k, v in row.items() if k != "geometry"}
        features.append({"type": "Feature", "geometry": mapping(row.geometry), "properties": props})
    return {"type": "FeatureCollection", "features": features}
