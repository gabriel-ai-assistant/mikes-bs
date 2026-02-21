"""Tests for subdivision candidate scoring — using score_to_tier and base_score."""

from openclaw.analysis.rule_engine import score_to_tier, base_score, TIER_CUTOFFS

SQFT_PER_ACRE = 43560.0


# ---------------------------------------------------------------------------
# score_to_tier — tier threshold tests
# ---------------------------------------------------------------------------

def test_score_to_tier_a():
    """Scores >= 80 → A tier."""
    assert score_to_tier(80) == "A"
    assert score_to_tier(95) == "A"
    assert score_to_tier(100) == "A"


def test_score_to_tier_b():
    """Scores >= 65 but < 80 → B tier."""
    assert score_to_tier(65) == "B"
    assert score_to_tier(79) == "B"


def test_score_to_tier_c():
    """Scores >= 50 but < 65 → C tier."""
    assert score_to_tier(50) == "C"
    assert score_to_tier(64) == "C"


def test_score_to_tier_d():
    """Scores >= 35 but < 50 → D tier."""
    assert score_to_tier(35) == "D"
    assert score_to_tier(49) == "D"


def test_score_to_tier_e():
    """Scores >= 20 but < 35 → E tier."""
    assert score_to_tier(20) == "E"
    assert score_to_tier(34) == "E"


def test_score_to_tier_f():
    """Scores < 20 → F tier."""
    assert score_to_tier(0) == "F"
    assert score_to_tier(19) == "F"


def test_tier_boundary_exact():
    """Every exact TIER_CUTOFFS boundary maps to the right tier."""
    for cutoff, tier in TIER_CUTOFFS:
        assert score_to_tier(cutoff) == tier, f"Expected {tier} at score {cutoff}"


def test_tier_just_below_a():
    """Score just below A threshold → B."""
    assert score_to_tier(79) == "B"


def test_tier_just_below_b():
    """Score just below B threshold → C."""
    assert score_to_tier(64) == "C"


# ---------------------------------------------------------------------------
# base_score — structural tests (no DB, no tags)
# ---------------------------------------------------------------------------

def test_base_score_high_splits():
    """10 splits (max) + individual owner → high base score."""
    candidate = {
        "potential_splits": 10,
        "lot_sf": 10 * SQFT_PER_ACRE,
        "assessed_value": 2_000_000,
        "owner_name": "John Smith",
    }
    score = base_score(candidate)
    # split_score=40, value_score capped at 25, owner=15 → at least 55
    assert score >= 55


def test_base_score_low_splits():
    """1 split, corporate owner, low value → low score."""
    candidate = {
        "potential_splits": 1,
        "lot_sf": 1 * SQFT_PER_ACRE,
        "assessed_value": 80_000,
        "owner_name": "MEGACORP INC",
    }
    score = base_score(candidate)
    assert score < 30


def test_base_score_trust_owner():
    """Trust owner gets owner_score=12 (between individual=15 and corporate=10)."""
    candidate = {
        "potential_splits": 5,
        "lot_sf": 10 * SQFT_PER_ACRE,
        "assessed_value": 500_000,
        "owner_name": "Smith FAMILY TRUST",
    }
    score_trust = base_score(candidate)

    candidate_ind = dict(candidate, owner_name="Jane Smith")
    score_individual = base_score(candidate_ind)

    candidate_corp = dict(candidate, owner_name="Landbank LLC")
    score_corp = base_score(candidate_corp)

    # Individual >= Trust >= Corp (owner score order)
    assert score_individual >= score_trust >= score_corp


def test_base_score_capped_at_80():
    """base_score never exceeds 80 (EDGE boosts push above that)."""
    candidate = {
        "potential_splits": 100,
        "lot_sf": 100 * SQFT_PER_ACRE,
        "assessed_value": 100_000_000,
        "owner_name": "Jane Individual",
    }
    assert base_score(candidate) <= 80


def test_base_score_zero_splits():
    """Zero splits → low score (no split component)."""
    candidate = {
        "potential_splits": 0,
        "lot_sf": 5 * SQFT_PER_ACRE,
        "assessed_value": 300_000,
        "owner_name": "Someone",
    }
    score = base_score(candidate)
    assert score <= 25
