from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .api_client import FeasibilityAPIClient
from .context import AnalysisContext
from .phase1_tags import write_inventory
from .phase2_parcel import CityParcelError, ParcelNotFoundError, run as phase2
from .phase25_zoning import run as phase25
from .phase3a_streams import run as phase3a
from .phase3b_wetlands import run as phase3b
from .phase3c_flood import run as phase3c
from .phase3d_slope import run as phase3d
from .phase3e_geology import run as phase3e
from .phase3f_soils import run as phase3f
from .phase3g_utilities import run as phase3g
from .phase3h_roads import run as phase3h
from .phase3i_flu import run as phase3i
from .phase3j_shoreline import run as phase3j
from .phase4_buildable import run as phase4
from .phase425_lots import run as phase425
from .phase43_stormwater import run as phase43
from .phase45_driveways import run as phase45
from .phase475_envelopes import run as phase475
from .phase5_scoring import run as phase5
from .phase6_costs import run as phase6
from .phase7_export import run as phase7


PHASES = [
    (phase25, True),
    (phase3a, True),
    (phase3b, True),
    (phase3c, True),
    (phase3d, True),
    (phase3e, True),
    (phase3f, True),
    (phase3g, True),
    (phase3h, True),
    (phase3i, True),
    (phase3j, True),
    (phase4, False),
    (phase425, False),
    (phase43, False),
    (phase45, False),
    (phase475, False),
    (phase5, False),
    (phase6, False),
]


def run_feasibility(parcel_id: str, output_dir: Path | None = None) -> AnalysisContext:
    client = FeasibilityAPIClient()
    ctx = AnalysisContext(parcel_id=parcel_id, output_dir=output_dir)

    # keep tag inventory synchronized with runtime tag config
    write_inventory(Path(__file__).resolve().parent / "tag_inventory.json")

    try:
        ctx = phase2(ctx, client)
    except (ParcelNotFoundError, CityParcelError):
        raise
    except Exception as exc:
        ctx.add_tag("RISK_DATA_INCOMPLETE")
        ctx.add_warning(f"phase2_parcel failed: {exc}")
        return ctx

    for phase, needs_client in PHASES:
        if ctx.stop:
            break
        try:
            ctx = phase(ctx, client) if needs_client else phase(ctx)
        except Exception as exc:
            ctx.add_tag("RISK_DATA_INCOMPLETE")
            ctx.add_warning(f"{phase.__module__.split('.')[-1]} failed: {exc}")

    ctx = phase7(ctx, output_dir=output_dir)
    return ctx
