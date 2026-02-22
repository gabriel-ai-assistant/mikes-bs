from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import geopandas as gpd


@dataclass
class AnalysisContext:
    parcel_id: str
    parcel_geom: Optional[gpd.GeoDataFrame] = None  # EPSG:2285
    zoning_code: Optional[str] = None
    zoning_rules: Optional[dict[str, Any]] = None
    constraint_layers: dict[str, gpd.GeoDataFrame] = field(default_factory=dict)
    buildable_geom: Optional[gpd.GeoDataFrame] = None
    layouts: list[dict[str, Any]] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    cost_estimates: dict[str, Any] = field(default_factory=dict)
    export_paths: dict[str, str] = field(default_factory=dict)

    # orchestration/runtime fields
    stop: bool = False
    output_dir: Optional[Path] = None
    parcel_attrs: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)

    def add_tag(self, tag: str) -> None:
        if tag not in self.tags:
            self.tags.append(tag)

    def add_warning(self, warning: str) -> None:
        if warning not in self.warnings:
            self.warnings.append(warning)

    def ensure_output_dir(self) -> Path:
        if self.output_dir is None:
            self.output_dir = Path("/tmp") / "feasibility_outputs" / self.parcel_id
        self.output_dir.mkdir(parents=True, exist_ok=True)
        return self.output_dir
