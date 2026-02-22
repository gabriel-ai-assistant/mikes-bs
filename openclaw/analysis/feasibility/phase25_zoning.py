from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd

from .api_client import FeasibilityAPIClient
from .context import AnalysisContext

ZONING_URL = "https://gismaps.snoco.org/snocogis2/rest/services/planning/mp_Zoning_OZ/MapServer"


def _rules_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "zoning_rules.json"


def _load_rules() -> dict:
    path = _rules_path()
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def run(ctx: AnalysisContext, client: FeasibilityAPIClient) -> AnalysisContext:
    if ctx.parcel_geom is None or len(ctx.parcel_geom) == 0:
        ctx.add_tag("RISK_DATA_INCOMPLETE")
        return ctx

    centroid = ctx.parcel_geom.geometry.iloc[0].centroid
    qgeom = {
        "rings": [list(ctx.parcel_geom.geometry.iloc[0].exterior.coords)],
        "spatialReference": {"wkid": 2285},
    }
    zdf = client.query_feature_layer(ZONING_URL, 0, geometry=qgeom, where="1=1")
    if len(zdf) == 0:
        # centroid fallback using parcel bbox
        zdf = client.query_feature_layer(ZONING_URL, 0, where="1=1")
        if len(zdf) > 0:
            zdf = zdf[zdf.geometry.contains(centroid)]

    if len(zdf) == 0:
        ctx.add_tag("RISK_DATA_INCOMPLETE")
        return ctx

    row = zdf.iloc[0]
    code = row.get("ZONE") or row.get("ZONE_CODE") or row.get("ZONING") or row.get("ZONECLASS")
    ctx.zoning_code = str(code).strip() if code else None

    rules = _load_rules()
    ctx.zoning_rules = rules.get(ctx.zoning_code or "", {})

    parcel_sf = float(ctx.parcel_attrs.get("GIS_SQ_FT") or ctx.parcel_geom.geometry.area.iloc[0])
    min_lot_sqft = float(ctx.zoning_rules.get("min_lot_sqft", 999999999))

    if min_lot_sqft > 0 and (parcel_sf / min_lot_sqft) < 2:
        ctx.add_tag("RISK_NOT_SUBDIVIDABLE")
        ctx.stop = True
    return ctx
