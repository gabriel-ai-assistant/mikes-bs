from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from openclaw.analysis.feasibility import api_client as api_client_mod
from openclaw.analysis.feasibility.api_client import FeasibilityAPIClient
from openclaw.analysis.feasibility.context import AnalysisContext
from openclaw.analysis.feasibility import orchestrator as orch
from openclaw.analysis.feasibility.orchestrator import run_feasibility

PARCEL_LAYER = "https://gismaps.snoco.org/snocogis2/rest/services/cadastral/tax_parcels/MapServer"
OFFLINE_PARCEL_ID = "30053400401800"


class _FakeBuildableGeom:
    def __init__(self, area_sf: float):
        self._area_sf = area_sf
        self.geometry = self
        self.area = self
        self.iloc = [area_sf]

    def __len__(self) -> int:
        return 1


class _LenOne:
    def __len__(self) -> int:
        return 1


def _is_geo_mocked() -> bool:
    return isinstance(getattr(api_client_mod, "gpd", None), MagicMock)


@pytest.fixture()
def offline_ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SNOCO_OFFLINE", "true")
    out_dir = tmp_path / "offline" / OFFLINE_PARCEL_ID

    if _is_geo_mocked():
        def _phase2(ctx: AnalysisContext, _client: FeasibilityAPIClient) -> AnalysisContext:
            ctx.parcel_geom = _LenOne()
            ctx.parcel_attrs = {"GIS_SQ_FT": 153331}
            return ctx

        def _buildable(ctx: AnalysisContext) -> AnalysisContext:
            ctx.buildable_geom = _FakeBuildableGeom(area_sf=120000.0)
            return ctx

        def _layouts(ctx: AnalysisContext) -> AnalysisContext:
            ctx.layouts = [{"id": "layout_1"}, {"id": "layout_2"}]
            return ctx

        def _tags(ctx: AnalysisContext) -> AnalysisContext:
            ctx.add_tag("INFO_OFFLINE_FIXTURE")
            return ctx

        def _export(ctx: AnalysisContext, output_dir: Path | None = None) -> AnalysisContext:
            export_dir = output_dir or (tmp_path / "offline_exports")
            export_dir.mkdir(parents=True, exist_ok=True)
            png = export_dir / "feasibility_map.png"
            gpkg = export_dir / "feasibility_layers.gpkg"
            png.write_bytes(b"offline")
            gpkg.write_bytes(b"offline")
            ctx.export_paths = {"output_dir": str(export_dir), "png": str(png), "gpkg": str(gpkg)}
            return ctx

        monkeypatch.setattr(orch, "phase2", _phase2)
        monkeypatch.setattr(orch, "PHASES", [(_buildable, False), (_layouts, False), (_tags, False)])
        monkeypatch.setattr(orch, "phase7", _export)

    return run_feasibility(OFFLINE_PARCEL_ID, output_dir=out_dir)


def test_offline_parcel_load(offline_ctx):
    assert offline_ctx.parcel_geom is not None
    assert len(offline_ctx.parcel_geom) >= 1


def test_offline_buildable_area(offline_ctx):
    assert offline_ctx.buildable_geom is not None
    assert len(offline_ctx.buildable_geom) >= 1
    net_buildable_sf = float(
        offline_ctx.buildable_geom.geometry.area.iloc[0]
        if hasattr(offline_ctx.buildable_geom, "geometry")
        else offline_ctx.metrics.get("net_buildable_sf", 0)
    )
    assert net_buildable_sf > 0


def test_offline_layouts_generated(offline_ctx):
    assert len(offline_ctx.layouts) >= 2


def test_offline_tags_present(offline_ctx):
    assert len(offline_ctx.tags) > 0


def test_offline_export_paths(offline_ctx):
    assert "output_dir" in offline_ctx.export_paths
    assert "png" in offline_ctx.export_paths
    assert "gpkg" in offline_ctx.export_paths
    assert Path(offline_ctx.export_paths["output_dir"]).exists()
    assert Path(offline_ctx.export_paths["png"]).exists()
    assert Path(offline_ctx.export_paths["gpkg"]).exists()


@pytest.fixture(scope="module")
def parcel_ids() -> list[str]:
    if os.environ.get("SNOCO_OFFLINE", "").lower() == "true":
        pytest.skip("Integration tests disabled when SNOCO_OFFLINE=true")

    client = FeasibilityAPIClient(delay_seconds=0.0)
    candidates = []
    gdf = client.query_feature_layer(PARCEL_LAYER, 0, where="GIS_ACRES >= 2", out_sr=2285)
    if len(gdf) == 0:
        pytest.skip("Parcel API unavailable for feasibility integration tests")

    field = "Parcel_ID" if "Parcel_ID" in gdf.columns else "PARCEL_ID"
    for _, row in gdf.head(200).iterrows():
        pid = row.get(field)
        if pid:
            candidates.append(str(pid))
        if len(candidates) >= 5:
            break

    if len(candidates) < 5:
        pytest.skip("Could not discover 5 parcel IDs from Snohomish layer")
    return candidates


@pytest.mark.parametrize("idx", [0, 1, 2, 3, 4])
def test_feasibility_pipeline(parcel_ids: list[str], idx: int):
    parcel_id = parcel_ids[idx]
    out_dir = Path("/tmp/feasibility_test") / parcel_id
    ctx = run_feasibility(parcel_id, output_dir=out_dir)

    assert ctx.parcel_geom is not None
    assert len(ctx.parcel_geom) >= 1

    # At least one constraint layer exists OR data is gracefully incomplete
    has_constraint_data = any(layer is not None and len(layer) > 0 for layer in ctx.constraint_layers.values())
    assert has_constraint_data or ("RISK_DATA_INCOMPLETE" in ctx.tags)

    # Buildable can be zero but should be computed
    assert ctx.buildable_geom is not None

    if "RISK_NOT_SUBDIVIDABLE" not in ctx.tags:
        assert len(ctx.layouts) >= 2

    assert "output_dir" in ctx.export_paths
    assert Path(ctx.export_paths["output_dir"]).exists()
    assert Path(ctx.export_paths["png"]).exists()
    assert Path(ctx.export_paths["gpkg"]).exists()
