"""Tests for the Underwriting Engine — Stream C.

All tests use real compute_proforma() — no DB required.
ARV is passed directly to avoid any DB calls.

CRITICAL: The return metric is `annualized_return_estimate`.
          It is NOT a true IRR. Reason code RETURN_PROXY_NOT_IRR is always emitted.
"""

import pytest
from openclaw.underwriting.engine import (
    compute_proforma,
    run_scenario,
    UWConfig,
    DEFAULT_SCENARIOS,
    ProForma,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_CANDIDATE = {
    "parcel_id": "test-uuid",
    "county": "snohomish",
    "zone_code": "R-5",
    "potential_splits": 4,
    "assessed_value": 380000,
    "last_sale_price": None,  # → uses assessed_value → land_cost_source = ASSESSED
    "improvement_value": 0,
    "total_value": 380000,
}

SAMPLE_ARV = 1_100_000  # $1.1M per home × 4 splits = $4.4M revenue


def _make_pf(candidate=None, arv=None, config=None):
    """Helper: build a ProForma from defaults or overrides."""
    return compute_proforma(
        candidate=candidate or SAMPLE_CANDIDATE,
        arv_per_home=arv or SAMPLE_ARV,
        config=config or UWConfig(),
        assumptions_version="v1",
    )


# ---------------------------------------------------------------------------
# Test 1 — All required ProForma fields are present
# ---------------------------------------------------------------------------

def test_base_proforma_has_all_required_fields():
    """ProForma must expose every field specified in the data contract."""
    pf = _make_pf()

    required_fields = [
        "parcel_id",
        "assumptions_version",
        "land_acquisition",
        "land_cost_source",
        "dev_cost",
        "build_cost",
        "carry_cost",
        "financing_cost",
        "total_cost",
        "total_revenue",
        "gross_profit",
        "margin_pct",
        "annualized_return_estimate",
        "months_to_exit",
        "risk_class",
        "reasons",
        "scenarios",
    ]

    for f in required_fields:
        assert hasattr(pf, f), f"ProForma missing required field: {f}"


# ---------------------------------------------------------------------------
# Test 2 — Exactly 8 sensitivity scenarios
# ---------------------------------------------------------------------------

def test_sensitivity_produces_8_scenarios():
    """compute_proforma must run all 8 DEFAULT_SCENARIOS."""
    pf = _make_pf()
    assert len(pf.scenarios) == 8, f"Expected 8 scenarios, got {len(pf.scenarios)}"


# ---------------------------------------------------------------------------
# Test 3 — +10% hard costs reduces margin vs base
# ---------------------------------------------------------------------------

def test_hard_cost_10pct_reduces_margin():
    """+10% hard cost scenario must have lower margin than base."""
    pf = _make_pf()

    base_scenario = next(s for s in pf.scenarios if s["label"] == "base")
    stress_scenario = next(s for s in pf.scenarios if s["label"] == "+10% hard costs")

    assert stress_scenario["margin_pct"] < base_scenario["margin_pct"], (
        f"+10% hard costs margin ({stress_scenario['margin_pct']:.4f}) should be < "
        f"base margin ({base_scenario['margin_pct']:.4f})"
    )


# ---------------------------------------------------------------------------
# Test 4 — +20% hard costs is worse than +10%
# ---------------------------------------------------------------------------

def test_hard_cost_20pct_worse_than_10pct():
    """+20% hard cost scenario must have lower margin than +10%."""
    pf = _make_pf()

    s10 = next(s for s in pf.scenarios if s["label"] == "+10% hard costs")
    s20 = next(s for s in pf.scenarios if s["label"] == "+20% hard costs")

    assert s20["margin_pct"] < s10["margin_pct"], (
        f"+20% margin ({s20['margin_pct']:.4f}) should be worse than "
        f"+10% margin ({s10['margin_pct']:.4f})"
    )


# ---------------------------------------------------------------------------
# Test 5 — -5% sale price reduces margin
# ---------------------------------------------------------------------------

def test_price_down_5pct_reduces_margin():
    """-5% sale price scenario must have lower margin than base."""
    pf = _make_pf()

    base_s = next(s for s in pf.scenarios if s["label"] == "base")
    stress_s = next(s for s in pf.scenarios if s["label"] == "-5% sale price")

    assert stress_s["margin_pct"] < base_s["margin_pct"], (
        f"-5% price margin ({stress_s['margin_pct']:.4f}) should be < "
        f"base margin ({base_s['margin_pct']:.4f})"
    )


# ---------------------------------------------------------------------------
# Test 6 — +3mo delay increases total cost (extra carry)
# ---------------------------------------------------------------------------

def test_delay_3mo_increases_total_cost():
    """+3mo delay must increase total cost relative to base (extra carry cost)."""
    pf = _make_pf()

    base_s = next(s for s in pf.scenarios if s["label"] == "base")
    delay_s = next(s for s in pf.scenarios if s["label"] == "+3mo delay")

    assert delay_s["total_cost"] > base_s["total_cost"], (
        f"+3mo delay total_cost ({delay_s['total_cost']:.0f}) should exceed "
        f"base total_cost ({base_s['total_cost']:.0f})"
    )


# ---------------------------------------------------------------------------
# Test 7 — +200bps rate increases financing cost
# ---------------------------------------------------------------------------

def test_rate_up_200bps_increases_financing():
    """+200bps rate scenario must have higher financing cost than base."""
    pf = _make_pf()

    base_s = next(s for s in pf.scenarios if s["label"] == "base")
    rate_s = next(s for s in pf.scenarios if s["label"] == "+200bps rate")

    assert rate_s["financing_cost"] > base_s["financing_cost"], (
        f"+200bps financing_cost ({rate_s['financing_cost']:.0f}) should exceed "
        f"base financing_cost ({base_s['financing_cost']:.0f})"
    )


# ---------------------------------------------------------------------------
# Test 8 — Risk class A at ≥25% margin
# ---------------------------------------------------------------------------

def test_risk_class_a_at_25pct_margin():
    """Very high ARV relative to costs must yield risk_class = 'A' (margin ≥ 25%)."""
    # Use a very high ARV to ensure margin > 25%
    # 4 splits × $2M ARV = $8M revenue; costs ≈ $2.7M → margin ~66%
    pf = compute_proforma(
        candidate=SAMPLE_CANDIDATE,
        arv_per_home=2_000_000,
        config=UWConfig(),
        assumptions_version="v1",
    )

    assert pf.margin_pct >= 0.25, (
        f"Expected margin_pct >= 0.25 for high-ARV scenario, got {pf.margin_pct:.4f}"
    )
    assert pf.risk_class == "A", (
        f"Expected risk_class 'A' at margin {pf.margin_pct:.4f}, got '{pf.risk_class}'"
    )


# ---------------------------------------------------------------------------
# Test 9 — Risk class D at low/negative margin
# ---------------------------------------------------------------------------

def test_risk_class_d_at_low_margin():
    """Very low ARV must yield risk_class = 'D' (margin < 5%)."""
    # Use a tiny ARV so total costs exceed revenue
    pf = compute_proforma(
        candidate=SAMPLE_CANDIDATE,
        arv_per_home=200_000,  # 4 × $200k = $800k revenue, costs >> $800k
        config=UWConfig(),
        assumptions_version="v1",
    )

    assert pf.margin_pct < 0.05, (
        f"Expected margin_pct < 0.05 for low-ARV scenario, got {pf.margin_pct:.4f}"
    )
    assert pf.risk_class == "D", (
        f"Expected risk_class 'D' at margin {pf.margin_pct:.4f}, got '{pf.risk_class}'"
    )


# ---------------------------------------------------------------------------
# Test 10 — annualized_return_estimate field exists
# ---------------------------------------------------------------------------

def test_annualized_return_estimate_field_exists():
    """ProForma must have annualized_return_estimate attribute."""
    pf = _make_pf()
    assert hasattr(pf, "annualized_return_estimate"), (
        "ProForma is missing required field: annualized_return_estimate"
    )
    assert isinstance(pf.annualized_return_estimate, float), (
        f"annualized_return_estimate must be float, got {type(pf.annualized_return_estimate)}"
    )


# ---------------------------------------------------------------------------
# Test 11 — No irr or irr_estimate fields (naming discipline)
# ---------------------------------------------------------------------------

def test_no_irr_field_exists():
    """ProForma must NOT have 'irr' or 'irr_estimate' fields.
    The correct name is annualized_return_estimate (see RETURN_PROXY_NOT_IRR).
    """
    pf = _make_pf()
    assert not hasattr(pf, "irr"), (
        "ProForma must not have field 'irr' — use annualized_return_estimate"
    )
    assert not hasattr(pf, "irr_estimate"), (
        "ProForma must not have field 'irr_estimate' — use annualized_return_estimate"
    )


# ---------------------------------------------------------------------------
# Test 12 — RETURN_PROXY_NOT_IRR reason code always present
# ---------------------------------------------------------------------------

def test_return_proxy_reason_in_reasons():
    """ProForma.reasons must always contain 'RETURN_PROXY_NOT_IRR'."""
    pf = _make_pf()
    assert "RETURN_PROXY_NOT_IRR" in pf.reasons, (
        f"Expected 'RETURN_PROXY_NOT_IRR' in reasons, got: {pf.reasons}"
    )


# ---------------------------------------------------------------------------
# Test 13 — assumptions_version is recorded correctly
# ---------------------------------------------------------------------------

def test_assumptions_version_recorded():
    """ProForma.assumptions_version must match the version passed to compute_proforma."""
    pf = compute_proforma(
        candidate=SAMPLE_CANDIDATE,
        arv_per_home=SAMPLE_ARV,
        config=UWConfig(),
        assumptions_version="v1",
    )
    assert pf.assumptions_version == "v1", (
        f"Expected assumptions_version 'v1', got '{pf.assumptions_version}'"
    )
