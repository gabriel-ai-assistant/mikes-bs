"""Tests for subdivision range/confidence, economic gate, and arbitrage depth."""

from openclaw.analysis.arbitrage import compute_arbitrage_depth
from openclaw.analysis.subdivision import assess_subdivision
from openclaw.analysis.subdivision_econ import compute_economic_margin


def make_candidate(**kwargs):
    data = {
        "has_critical_area_overlap": False,
        "flagged_for_review": False,
        "uga_outside": False,
        "lot_sf": None,
        "assessed_value": 250000,
        "last_sale_price": None,
    }
    data.update(kwargs)
    return data


def make_parcel(**kwargs):
    data = {
        "zone_code": "ULDR",
        "lot_sf": 30762,
        "frontage_ft": 75,
        "parcel_width_ft": None,
        "address": "123 Main St",
    }
    data.update(kwargs)
    return data


def test_uldr_071ac_frontage_75_is_constrained_and_uncertain():
    c = make_candidate(uga_outside=False)
    p = make_parcel(zone_code="ULDR", lot_sf=30762, frontage_ft=75)

    r = assess_subdivision(c, p)

    assert r.splits_max <= 3
    assert r.splits_confidence in {"LOW", "MEDIUM"}
    assert (
        "RISK_ACCESS_TRACT_REQUIRED" in r.flags
        or "RISK_WIDTH_CONSTRAINED" in r.flags
    )


def test_null_frontage_is_fail_closed_low_confidence_with_reason():
    c = make_candidate()
    p = make_parcel(frontage_ft=None, parcel_width_ft=None)

    r = assess_subdivision(c, p)

    assert r.splits_confidence == "LOW"
    assert "FRONTAGE_UNKNOWN" in r.reasons


def test_rural_r5_5ac_has_high_confidence_and_strong_splits():
    c = make_candidate(uga_outside=False)
    p = make_parcel(
        zone_code="R-5",
        lot_sf=217800,
        frontage_ft=300,
        parcel_width_ft=1000,
        address="456 County Rd",
    )

    r = assess_subdivision(c, p)

    assert r.splits_confidence == "HIGH"
    assert r.splits_most_likely >= 3


def test_economic_gate_emits_loss_and_thin_margin_tags():
    # Negative margin case.
    loss_margin, loss_tags, _loss_reasons = compute_economic_margin(
        {"assessed_value": 100000, "last_sale_price": None},
        splits=4,
        zone_code="UMDR",
    )
    assert loss_margin < 0
    assert "RISK_ECON_LOSS_AT_ASK" in loss_tags

    # Thin positive margin case.
    thin_margin, thin_tags, _thin_reasons = compute_economic_margin(
        {"assessed_value": 1800000, "last_sale_price": None},
        splits=2,
        zone_code="R-4",
    )
    assert 0 < thin_margin < 0.20
    assert "RISK_ARV_MARGIN_THIN" in thin_tags


def test_arbitrage_depth_rural_outside_uga_with_ruta_is_high():
    candidate = {
        "zone_code": "R-5",
        "lot_sf": 500000,
        "assessed_value": 350000,
        "uga_outside": True,
    }

    score, tags, _reasons = compute_arbitrage_depth(
        candidate,
        tags=["EDGE_SNOCO_RUTA_ARBITRAGE"],
    )

    assert score >= 60
    assert "EDGE_ARBITRAGE_DEPTH_HIGH" in tags
