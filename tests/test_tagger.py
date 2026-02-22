"""Tests for EDGE/RISK zoning arbitrage tagger."""
import pytest
from openclaw.analysis.tagger import compute_tags
from openclaw.analysis.edge_config import EdgeConfig


def make_parcel(**kwargs):
    defaults = dict(
        county="snohomish",
        zone_code="R-5",
        lot_sf=10 * 43560.0,  # 10 acres
        has_critical_area_overlap=False,
        improvement_value=5000,
        total_value=200000,
        address="123 Rural Rd",
        owner_name="John Smith",
        potential_splits=3,
    )
    defaults.update(kwargs)
    return defaults


def default_cfg():
    return EdgeConfig(
        lsa_min_acres=10.0,
        rural_cluster_min_acres=5.0,
        hb1110_urban_zones=set(),
        unit_lot_zones=set(),
        lsa_zones={"R-5", "RD", "F&R"},
    )


class TestLSATag:
    def test_r5_12_acres_gets_lsa_tag(self):
        p = make_parcel(lot_sf=12 * 43560.0)
        tags, reasons = compute_tags(p, config=default_cfg())
        assert "EDGE_SNOCO_LSA_R5_RD_FR" in tags
        assert any("EDGE_SNOCO_LSA_R5_RD_FR" in r for r in reasons)

    def test_r5_12_acres_gets_rural_cluster_tag(self):
        p = make_parcel(lot_sf=12 * 43560.0)
        tags, _ = compute_tags(p, config=default_cfg())
        assert "EDGE_SNOCO_RURAL_CLUSTER_BONUS" in tags

    def test_r5_12_acres_uga_unknown(self):
        p = make_parcel(lot_sf=12 * 43560.0)
        tags, _ = compute_tags(p, config=default_cfg())
        assert "EDGE_UGA_STATUS_UNKNOWN" in tags


class TestLotTooSmall:
    def test_r5_3_acres_no_lsa_tag(self):
        p = make_parcel(lot_sf=3 * 43560.0)
        tags, _ = compute_tags(p, config=default_cfg())
        assert "EDGE_SNOCO_LSA_R5_RD_FR" not in tags
        assert "RISK_LOT_TOO_SMALL" in tags

    def test_r5_3_acres_no_rural_cluster_tag(self):
        p = make_parcel(lot_sf=3 * 43560.0)
        tags, _ = compute_tags(p, config=default_cfg())
        assert "EDGE_SNOCO_RURAL_CLUSTER_BONUS" not in tags


class TestHB1110:
    def test_urban_zone_hb1110_not_configured_emits_risk(self):
        p = make_parcel(zone_code="RS-6", county="snohomish")
        tags, _ = compute_tags(p, config=default_cfg())
        assert "EDGE_WA_HB1110_MIDDLE_HOUSING" not in tags
        assert "RISK_HB1110_DATA_UNAVAILABLE" in tags

    def test_urban_zone_hb1110_configured_emits_edge(self):
        cfg = default_cfg()
        cfg.hb1110_urban_zones = {"RS-6", "RS-8"}
        p = make_parcel(zone_code="RS-6", county="snohomish")
        tags, _ = compute_tags(p, config=cfg)
        assert "EDGE_WA_HB1110_MIDDLE_HOUSING" in tags
        assert "RISK_HB1110_DATA_UNAVAILABLE" not in tags


class TestCriticalAreas:
    def test_critical_area_adds_risk_not_suppress_edge(self):
        p = make_parcel(lot_sf=15 * 43560.0, has_critical_area_overlap=True)
        tags, _ = compute_tags(p, config=default_cfg())
        assert "EDGE_SNOCO_LSA_R5_RD_FR" in tags
        assert "RISK_CRITICAL_AREAS" in tags


class TestSepticWater:
    def test_no_improvement_value_emits_septic_water_unknown(self):
        p = make_parcel(lot_sf=15 * 43560.0, improvement_value=0)
        tags, _ = compute_tags(p, config=default_cfg())
        assert "RISK_SEPTIC_UNKNOWN" in tags
        assert "RISK_WATER_UNKNOWN" in tags
        # EDGE tag still present (improvement_value=0 doesn't suppress)
        assert "EDGE_SNOCO_LSA_R5_RD_FR" in tags


class TestRUTA:
    def test_ruta_not_confirmed_emits_risk(self):
        p = make_parcel(lot_sf=12 * 43560.0)
        tags, _ = compute_tags(p, config=default_cfg(), ruta_confirmed=False)
        assert "EDGE_SNOCO_RUTA_ARBITRAGE" not in tags
        assert "RISK_RUTA_DATA_UNAVAILABLE" in tags

    def test_ruta_confirmed_emits_edge(self):
        p = make_parcel(lot_sf=12 * 43560.0)
        tags, _ = compute_tags(p, config=default_cfg(), ruta_confirmed=True)
        assert "EDGE_SNOCO_RUTA_ARBITRAGE" in tags
        assert "RISK_RUTA_DATA_UNAVAILABLE" not in tags


class TestScoreBoost:
    def test_edge_lsa_boosts_score(self):
        """R-5 12-acre parcel should score higher than non-qualifying parcel."""
        from openclaw.analysis.rule_engine import base_score, evaluate_candidate

        edge_parcel = make_parcel(lot_sf=12 * 43560.0)
        flat_parcel = make_parcel(zone_code="B-1", lot_sf=12 * 43560.0)  # non-rural

        # evaluate_candidate with empty rules
        edge_tier, edge_score, excl, edge_tags, _ = evaluate_candidate(edge_parcel, [])
        flat_tier, flat_score, excl2, flat_tags, _ = evaluate_candidate(flat_parcel, [])

        assert edge_score > flat_score, (
            f"Edge parcel should score higher: {edge_score} vs {flat_score}"
        )


class TestUserVoteTag:
    def test_vote_net_threshold_applies_upvote_tag(self):
        p = make_parcel(vote_net=1)
        tags, reasons = compute_tags(p, config=default_cfg())
        assert "EDGE_USER_UPVOTE" in tags
        assert any("EDGE_USER_UPVOTE" in r for r in reasons)

    def test_zero_vote_net_does_not_apply_upvote_tag(self):
        p = make_parcel(vote_net=0)
        tags, _ = compute_tags(p, config=default_cfg())
        assert "EDGE_USER_UPVOTE" not in tags
