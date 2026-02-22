from __future__ import annotations

import geopandas as gpd

from ._geo import parcel_query_geom
from .api_client import FeasibilityAPIClient
from .context import AnalysisContext

LANDSLIDE = "https://gis.dnr.wa.gov/site1/rest/services/Public_Geology/Landslide_Inventory_Database/MapServer"
GROUND = "https://gis.dnr.wa.gov/site1/rest/services/Public_Geology/Ground_Response/MapServer"
VOLCANIC = "https://gis.dnr.wa.gov/site1/rest/services/Public_Geology/Volcanic_Hazards/MapServer"


def run(ctx: AnalysisContext, client: FeasibilityAPIClient) -> AnalysisContext:
    if ctx.parcel_geom is None or len(ctx.parcel_geom) == 0:
        return ctx

    qgeom = parcel_query_geom(ctx.parcel_geom)
    landslides = client.query_feature_layer(LANDSLIDE, 0, geometry=qgeom)
    ground = client.query_feature_layer(GROUND, 0, geometry=qgeom)
    volcanic = client.query_feature_layer(VOLCANIC, 0, geometry=qgeom)

    layers = []
    if len(landslides) > 0:
        ctx.add_tag("RISK_LANDSLIDE_HAZARD")
        layers.append(landslides)
    if len(ground) > 0:
        lower_cols = {c.lower(): c for c in ground.columns}
        joined = " ".join(str(v).lower() for v in ground.drop(columns=["geometry"], errors="ignore").iloc[0].tolist()) if len(ground) else ""
        if "liquef" in joined:
            ctx.add_tag("RISK_LIQUEFACTION")
        layers.append(ground)
    if len(volcanic) > 0:
        ctx.add_tag("RISK_LAHAR_ZONE")
        layers.append(volcanic)

    if layers:
        combined = gpd.GeoDataFrame(
            geometry=gpd.GeoSeries([g for layer in layers for g in layer.geometry], crs="EPSG:2285"),
            crs="EPSG:2285",
        )
        ctx.constraint_layers["geology"] = combined
        if any(tag in ctx.tags for tag in ["RISK_LANDSLIDE_HAZARD", "RISK_LIQUEFACTION", "RISK_LAHAR_ZONE"]):
            ctx.add_tag("RISK_GEOLOGIC_HAZARD")
    else:
        ctx.constraint_layers["geology"] = gpd.GeoDataFrame(geometry=[], crs="EPSG:2285")

    return ctx
