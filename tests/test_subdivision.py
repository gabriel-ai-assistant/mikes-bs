"""Tests for subdivision feasibility assessment."""

from openclaw.analysis.subdivision import assess_subdivision

SQFT_PER_ACRE = 43560


def make_candidate(**kwargs):
    data = {
        "has_critical_area_overlap": False,
        "flagged_for_review": False,
        "uga_outside": False,
        "lot_sf": None,
    }
    data.update(kwargs)
    return data


def make_parcel(**kwargs):
    data = {
        "zone_code": "R-1",
        "lot_sf": int(2.2 * SQFT_PER_ACRE),
        "address": "123 Main St",
    }
    data.update(kwargs)
    return data


def test_short_plat_eligible():
    c = make_candidate(uga_outside=False)
    p = make_parcel()
    r = assess_subdivision(c, p)
    assert r.plat_type == "SHORT_PLAT"
    assert r.feasibility == "LIKELY"
    assert "EDGE_SHORT_PLAT_ELIGIBLE" in r.flags


def test_septic_penalty():
    c1 = make_candidate(uga_outside=False)
    c2 = make_candidate(uga_outside=True)
    p = make_parcel()
    r1 = assess_subdivision(c1, p)
    r2 = assess_subdivision(c2, p)
    assert "RISK_SEPTIC_REQUIRED" in r2.flags
    assert r2.score < r1.score


def test_access_unknown():
    c = make_candidate(uga_outside=False)
    p = make_parcel(address="UNKNOWN UNKNOWN")
    r = assess_subdivision(c, p)
    assert "RISK_ACCESS_UNKNOWN" in r.flags
    assert r.feasibility == "POSSIBLE"
    assert r.feasibility != "LIKELY"


def test_wetland_reduces_buildable():
    c = make_candidate(has_critical_area_overlap=True)
    p = make_parcel(lot_sf=100000)
    r = assess_subdivision(c, p)
    assert r.buildable_sf < int(p["lot_sf"] * 0.95)


def test_commercial_zone():
    c = make_candidate()
    p = make_parcel(zone_code="MUC")
    r = assess_subdivision(c, p)
    assert r.plat_type == "NOT_FEASIBLE"
    assert "COMMERCIAL_ZONE" in r.reasons


def test_long_plat():
    c = make_candidate(uga_outside=False)
    p = make_parcel(lot_sf=20 * SQFT_PER_ACRE)
    r = assess_subdivision(c, p)
    assert r.plat_type == "LONG_PLAT"
    assert "RISK_LONG_PLAT_REQUIRED" in r.flags


def test_not_feasible_too_small():
    c = make_candidate()
    p = make_parcel(lot_sf=70000, zone_code="R-1")
    r = assess_subdivision(c, p)
    assert r.feasible_splits < 2
    assert r.plat_type == "NOT_FEASIBLE"


def test_score_capped_0_to_100():
    high = assess_subdivision(make_candidate(uga_outside=False), make_parcel(lot_sf=100 * SQFT_PER_ACRE))
    low = assess_subdivision(make_candidate(uga_outside=True), make_parcel(lot_sf=1000, address="UNKNOWN UNKNOWN"))
    assert 0 <= high.score <= 100
    assert 0 <= low.score <= 100


def test_sewer_available_inside_uga():
    c = make_candidate(uga_outside=False)
    p = make_parcel()
    r = assess_subdivision(c, p)
    assert "EDGE_SEWER_AVAILABLE" in r.flags
    assert r.sewer_available is True


def test_subdivision_score_effects_applied():
    c = make_candidate(uga_outside=False)
    p = make_parcel()
    r = assess_subdivision(c, p)
    assert "EDGE_SHORT_PLAT_ELIGIBLE" in r.flags
    assert r.score >= 20
