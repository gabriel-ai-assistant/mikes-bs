from openclaw.analysis.tagger import compute_tags
from openclaw.analysis.edge_config import EdgeConfig

SQFT_PER_ACRE = 43560.0


def make_r5_parcel(**kwargs):
    defaults = dict(
        county="snohomish", zone_code="R-5",
        lot_sf=12 * SQFT_PER_ACRE,
        has_critical_area_overlap=False,
        improvement_value=5000, total_value=300000,
        address="123 Rural Rd", owner_name="John Smith",
        potential_splits=4,
    )
    defaults.update(kwargs)
    return defaults


def default_cfg():
    return EdgeConfig(lsa_min_acres=10.0, rural_cluster_min_acres=5.0,
                      hb1110_urban_zones=set(), unit_lot_zones=set(),
                      lsa_zones={"R-5", "RD", "F&R"})


def test_uga_outside_emits_lsa_without_unknown():
    tags, reasons = compute_tags(make_r5_parcel(), config=default_cfg(), uga_outside=True)
    assert "EDGE_SNOCO_LSA_R5_RD_FR" in tags
    assert "EDGE_UGA_STATUS_UNKNOWN" not in tags
    assert any("UGA=outside(confirmed)" in r for r in reasons)


def test_uga_inside_suppresses_lsa():
    tags, reasons = compute_tags(make_r5_parcel(), config=default_cfg(), uga_outside=False)
    assert "EDGE_SNOCO_LSA_R5_RD_FR" not in tags
    assert "RISK_INSIDE_UGA" in tags


def test_uga_none_emits_unknown():
    tags, reasons = compute_tags(make_r5_parcel(), config=default_cfg(), uga_outside=None)
    assert "EDGE_UGA_STATUS_UNKNOWN" in tags
