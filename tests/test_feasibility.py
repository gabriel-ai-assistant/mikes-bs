from __future__ import annotations

from pathlib import Path

import pytest

from openclaw.analysis.feasibility.api_client import FeasibilityAPIClient
from openclaw.analysis.feasibility.orchestrator import run_feasibility

PARCEL_LAYER = "https://gismaps.snoco.org/snocogis2/rest/services/cadastral/tax_parcels/MapServer"


@pytest.fixture(scope="module")
def parcel_ids() -> list[str]:
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
