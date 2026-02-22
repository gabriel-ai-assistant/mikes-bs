from __future__ import annotations

import inspect
import json
from pathlib import Path

from openclaw.analysis import edge_config, tagger


def build_tag_inventory() -> dict:
    cfg = edge_config.edge_config
    inv = {
        "weights": {
            "EDGE_SNOCO_LSA_R5_RD_FR": cfg.weight_lsa,
            "EDGE_SNOCO_RUTA_ARBITRAGE": cfg.weight_ruta,
            "EDGE_WA_HB1110_MIDDLE_HOUSING": cfg.weight_hb1110,
            "EDGE_WA_UNIT_LOT_SUBDIVISION": cfg.weight_unit_lot,
            "EDGE_SNOCO_RURAL_CLUSTER_BONUS": cfg.weight_rural_cluster,
            "RISK_*": cfg.weight_risk_penalty,
        },
        "producers": sorted({
            "openclaw.analysis.tagger.compute_tags",
            "openclaw.analysis.subdivision.assess_subdivision",
            "openclaw.analysis.subdivision_econ.compute_economic_margin",
            "openclaw.analysis.arbitrage.compute_arbitrage_depth",
        }),
        "consumers": [
            "openclaw.analysis.rule_engine.evaluate_candidate",
            "openclaw.analysis.rule_engine.rescore_all",
        ],
        "tagger_doc_excerpt": inspect.getdoc(tagger) or "",
    }
    return inv


def write_inventory(path: Path) -> dict:
    inv = build_tag_inventory()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(inv, indent=2), encoding="utf-8")
    return inv
