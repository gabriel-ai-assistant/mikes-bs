"""Config-driven weights and zone sets for EDGE/RISK tag system."""
from dataclasses import dataclass, field
import os


@dataclass
class EdgeConfig:
    # Zone sets
    lsa_zones: set = field(default_factory=lambda: {"R-5", "RD", "F&R"})

    # Thresholds
    lsa_min_acres: float = field(default_factory=lambda: float(os.getenv("EDGE_LSA_MIN_ACRES", "10.0")))
    rural_cluster_min_acres: float = field(default_factory=lambda: float(os.getenv("EDGE_RURAL_CLUSTER_MIN_ACRES", "5.0")))

    # Configurable zone sets (admin-supplied via env)
    hb1110_urban_zones: set = field(default_factory=lambda: set(
        z.strip() for z in os.getenv("EDGE_HB1110_URBAN_ZONES", "").split(",") if z.strip()
    ))
    unit_lot_zones: set = field(default_factory=lambda: set(
        z.strip() for z in os.getenv("EDGE_UNIT_LOT_ZONES", "").split(",") if z.strip()
    ))

    # Score weights (config-driven)
    weight_lsa: int = field(default_factory=lambda: int(os.getenv("EDGE_WEIGHT_LSA", "35")))
    weight_ruta: int = field(default_factory=lambda: int(os.getenv("EDGE_WEIGHT_RUTA", "30")))
    weight_hb1110: int = field(default_factory=lambda: int(os.getenv("EDGE_WEIGHT_HB1110", "25")))
    weight_unit_lot: int = field(default_factory=lambda: int(os.getenv("EDGE_WEIGHT_UNIT_LOT", "20")))
    weight_rural_cluster: int = field(default_factory=lambda: int(os.getenv("EDGE_WEIGHT_RURAL_CLUSTER", "15")))
    weight_user_upvote: int = field(default_factory=lambda: int(os.getenv("EDGE_WEIGHT_USER_UPVOTE", "8")))
    weight_bundle_same_owner: int = field(default_factory=lambda: int(os.getenv("EDGE_WEIGHT_BUNDLE_SAME_OWNER", "10")))
    weight_bundle_adjacent: int = field(default_factory=lambda: int(os.getenv("EDGE_WEIGHT_BUNDLE_ADJACENT", "5")))
    bundle_score_cap: int = field(default_factory=lambda: int(os.getenv("BUNDLE_SCORE_CAP", "15")))
    weight_risk_penalty: int = field(default_factory=lambda: int(os.getenv("EDGE_WEIGHT_RISK_PENALTY", "-8")))


edge_config = EdgeConfig()
