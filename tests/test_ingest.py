"""Tests for ingest base agent — mock HTTP and normalization."""

import pytest
import geopandas as gpd

from openclaw.db.models import CountyEnum
from openclaw.ingest.base import BaseIngestAgent


class MockAgent(BaseIngestAgent):
    county = CountyEnum.king
    endpoint = "https://example.com/query"
    field_map = {
        "PIN": "parcel_id",
        "SITUSADDR": "address",
        "SQ_FT_LOT": "lot_sf",
        "PRESENT_USE": "present_use",
        "ZONE_CODE": "zone_code",
        "APPRAISED_VALUE": "assessed_value",
        "OWNER_NAME": "owner_name",
    }

    @property
    def out_fields(self) -> str:
        return ",".join(self.field_map.keys())


MOCK_GEOJSON = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "properties": {
                "PIN": "1234567890",
                "SITUSADDR": "123 Main St",
                "SQ_FT_LOT": 15000,
                "PRESENT_USE": "SINGLE FAMILY",
                "ZONE_CODE": "R-8",
                "APPRAISED_VALUE": 450000,
                "OWNER_NAME": "John Smith",
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [-122.0, 47.0], [-122.0, 47.001],
                    [-121.999, 47.001], [-121.999, 47.0], [-122.0, 47.0]
                ]],
            },
        },
        {
            "type": "Feature",
            "properties": {
                "PIN": "9876543210",
                "SITUSADDR": "456 Oak Ave",
                "SQ_FT_LOT": 8400,
                "PRESENT_USE": "VACANT",
                "ZONE_CODE": "R-4",
                "APPRAISED_VALUE": 200000,
                "OWNER_NAME": "ABC Holdings LLC",
            },
            "geometry": None,
        },
    ],
}


def test_normalize_returns_geodataframe():
    agent = MockAgent()
    gdf = agent.normalize(MOCK_GEOJSON)
    assert isinstance(gdf, gpd.GeoDataFrame)
    assert len(gdf) == 2


def test_normalize_field_mapping():
    agent = MockAgent()
    gdf = agent.normalize(MOCK_GEOJSON)
    row = gdf.iloc[0]
    assert row["parcel_id"] == "1234567890"
    assert row["address"] == "123 Main St"
    assert row["lot_sf"] == 15000
    assert row["present_use"] == "SINGLE FAMILY"
    assert row["zone_code"] == "R-8"
    assert row["assessed_value"] == 450000
    assert row["owner_name"] == "John Smith"
    assert row["county"] == "king"


def test_normalize_handles_null_geometry():
    agent = MockAgent()
    gdf = agent.normalize(MOCK_GEOJSON)
    assert gdf.iloc[1].geometry is None


def test_normalize_empty_features():
    agent = MockAgent()
    gdf = agent.normalize({"features": []})
    assert isinstance(gdf, gpd.GeoDataFrame)
    assert len(gdf) == 0


def test_normalize_valid_geometry():
    agent = MockAgent()
    gdf = agent.normalize(MOCK_GEOJSON)
    geom = gdf.iloc[0].geometry
    assert geom is not None
    assert geom.geom_type == "Polygon"
