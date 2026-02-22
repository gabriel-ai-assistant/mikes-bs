from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Optional

import geopandas as gpd
try:
    import numpy as np
except Exception:  # pragma: no cover - optional dependency fallback
    np = None
import requests
from shapely.geometry import shape


CACHE_DIR = Path("/tmp/feasibility_cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)
FIXTURES_DIR = Path(__file__).resolve().parents[3] / "tests" / "fixtures"


class FeasibilityAPIClient:
    def __init__(self, delay_seconds: float = 0.5, timeout: int = 45):
        self.delay_seconds = delay_seconds
        self.timeout = timeout

    def _cache_key(self, payload: dict[str, Any]) -> str:
        raw = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def _cache_path(self, key: str) -> Path:
        return CACHE_DIR / f"{key}.geojson"

    def _sleep(self) -> None:
        time.sleep(self.delay_seconds)

    def _offline_enabled(self) -> bool:
        return os.environ.get("SNOCO_OFFLINE", "").lower() == "true"

    def _constraint_fixture_key(self, url: str, layer_id: int) -> str:
        u = url.lower()
        if "watercourse" in u or "/nhd/" in u:
            return "streams"
        if "wetlands" in u:
            return "wetlands"
        if "nfhl" in u:
            return "flood"
        if "landslide" in u:
            return "geology_landslide"
        if "ground_response" in u:
            return "geology_ground"
        if "volcanic" in u:
            return "geology_volcanic"
        if "pds_utility_districts" in u:
            return "utilities_water" if int(layer_id) == 0 else "utilities_sewer"
        if "transportation" in u:
            return "roads"
        if "future_land_use" in u:
            return "flu"
        if "shoreline" in u:
            return "shoreline"
        if "septic_parcels" in u:
            return "septic"
        return "default"

    def _offline_payload(self, url: str, layer_id: int) -> dict[str, Any]:
        u = url.lower()
        if "zoning" in u:
            fixture = FIXTURES_DIR / "zoning_lookup.json"
            return json.loads(fixture.read_text(encoding="utf-8"))
        if "parcel" in u or "tax_parcels" in u:
            fixture = FIXTURES_DIR / "parcel_feature.json"
            return json.loads(fixture.read_text(encoding="utf-8"))

        fixture = FIXTURES_DIR / "constraints_empty.json"
        payload = json.loads(fixture.read_text(encoding="utf-8"))
        if isinstance(payload, dict) and "layers" in payload:
            key = self._constraint_fixture_key(url, layer_id)
            layer_payload = payload["layers"].get(key) or payload["layers"].get("default") or {}
            if isinstance(layer_payload, dict):
                return layer_payload
        return payload if isinstance(payload, dict) else {"features": []}

    def _request(self, url: str, params: dict[str, Any], expect_json: bool = True) -> Any:
        attempt = 0
        while attempt < 3:
            attempt += 1
            try:
                self._sleep()
                resp = requests.get(url, params=params, timeout=self.timeout)
                if resp.status_code >= 500:
                    raise requests.HTTPError(f"HTTP {resp.status_code}", response=resp)
                resp.raise_for_status()
                return resp.json() if expect_json else resp.content
            except Exception:
                if attempt >= 3:
                    raise
                time.sleep(2 ** (attempt - 1))
        return None

    def _to_gdf(self, features: list[dict[str, Any]], out_crs: int = 2285) -> gpd.GeoDataFrame:
        if not features:
            return gpd.GeoDataFrame(geometry=[], crs=f"EPSG:{out_crs}")

        rows = []
        geoms = []
        source_epsg = 4326
        for feat in features:
            geom = feat.get("geometry")
            attrs = feat.get("attributes") or feat.get("properties", {})
            if not geom:
                continue
            try:
                if isinstance(geom, dict) and "spatialReference" in geom:
                    wkid = geom.get("spatialReference", {}).get("wkid")
                    if wkid is not None:
                        source_epsg = int(wkid)
                parsed_geom = geom
                if isinstance(geom, dict) and "rings" in geom:
                    parsed_geom = {"type": "Polygon", "coordinates": geom["rings"]}
                elif isinstance(geom, dict) and "paths" in geom:
                    parsed_geom = {"type": "LineString", "coordinates": geom["paths"][0] if geom["paths"] else []}
                elif isinstance(geom, dict) and "x" in geom and "y" in geom:
                    parsed_geom = {"type": "Point", "coordinates": [geom["x"], geom["y"]]}

                geoms.append(shape(parsed_geom))
                rows.append(attrs)
            except Exception:
                continue

        if not geoms:
            return gpd.GeoDataFrame(geometry=[], crs=f"EPSG:{out_crs}")

        gdf = gpd.GeoDataFrame(rows, geometry=geoms, crs=f"EPSG:{source_epsg}")
        try:
            return gdf if int(source_epsg) == int(out_crs) else gdf.to_crs(epsg=out_crs)
        except Exception:
            return gdf

    def _empty(self, out_sr: int = 2285) -> gpd.GeoDataFrame:
        return gpd.GeoDataFrame(geometry=[], crs=f"EPSG:{out_sr}")

    def query_feature_layer(
        self,
        url: str,
        layer_id: int,
        geometry: Optional[dict[str, Any]] = None,
        where: str = "1=1",
        out_sr: int = 2285,
    ) -> gpd.GeoDataFrame:
        if self._offline_enabled():
            payload = self._offline_payload(url=url, layer_id=layer_id)
            features = payload.get("features", [])
            return self._to_gdf(features, out_crs=out_sr)

        endpoint = f"{url.rstrip('/')}/{layer_id}/query"
        params: dict[str, Any] = {
            "f": "geojson",
            "where": where,
            "outFields": "*",
            "returnGeometry": "true",
            "outSR": out_sr,
        }
        if geometry is not None:
            params["geometry"] = json.dumps(geometry)
            params["geometryType"] = "esriGeometryPolygon"
            params["spatialRel"] = "esriSpatialRelIntersects"

        cache_payload = {"endpoint": endpoint, "params": params}
        key = self._cache_key(cache_payload)
        cpath = self._cache_path(key)
        if cpath.exists():
            try:
                gdf = gpd.read_file(cpath)
                if gdf.crs is None:
                    gdf = gdf.set_crs(epsg=4326)
                return gdf.to_crs(epsg=2285)
            except Exception:
                pass

        try:
            payload = self._request(endpoint, params)
            features = payload.get("features", [])
            gdf = self._to_gdf(features, out_crs=out_sr)
            if len(gdf) > 0:
                try:
                    gdf.to_file(cpath, driver="GeoJSON")
                except Exception:
                    pass
            return gdf.to_crs(epsg=2285) if gdf.crs else gdf
        except Exception:
            return self._empty(out_sr)

    def query_by_parcel_id(
        self,
        url: str,
        layer_id: int,
        parcel_id_field: str,
        parcel_id: str,
    ) -> gpd.GeoDataFrame:
        where = f"{parcel_id_field}='{parcel_id}'"
        return self.query_feature_layer(url=url, layer_id=layer_id, where=where, out_sr=2285)

    def export_image_raster(
        self,
        url: str,
        bbox: tuple[float, float, float, float],
        bbox_sr: int = 2285,
        size: tuple[int, int] = (500, 500),
        rendering_rule: Optional[dict[str, Any]] = None,
    ) -> np.ndarray:
        endpoint = f"{url.rstrip('/')}/exportImage"
        params: dict[str, Any] = {
            "f": "json",
            "bbox": ",".join(str(v) for v in bbox),
            "bboxSR": bbox_sr,
            "imageSR": bbox_sr,
            "size": f"{size[0]},{size[1]}",
            "format": "tiff",
            "pixelType": "F32",
        }
        if rendering_rule:
            params["renderingRule"] = json.dumps(rendering_rule)

        try:
            payload = self._request(endpoint, params)
            href = payload.get("href")
            if not href:
                return np.array([]) if np is not None else []
            content = self._request(href, {}, expect_json=False)
            # fallback parse-less mode if rasterio unavailable in runtime
            try:
                import rasterio
                from rasterio.io import MemoryFile

                with MemoryFile(content) as mem:
                    with mem.open() as ds:
                        return ds.read(1)
            except Exception:
                return np.array([]) if np is not None else []
        except Exception:
            return np.array([]) if np is not None else []
