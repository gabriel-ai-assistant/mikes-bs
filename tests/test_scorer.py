"""Tests for subdivision candidate scoring."""

from openclaw.analysis.scorer import assign_tier


def test_tier_a():
    """3+ splits and 20%+ margin → A tier."""
    assert assign_tier(3, 25.0) == "A"
    assert assign_tier(5, 20.0) == "A"


def test_tier_b():
    """2+ splits and 12%+ margin → B tier."""
    assert assign_tier(2, 15.0) == "B"
    assert assign_tier(3, 12.0) == "B"  # meets B but not A (margin < 20)


def test_tier_c():
    """Everything else → C tier."""
    assert assign_tier(1, 30.0) == "C"  # not enough splits
    assert assign_tier(2, 8.0) == "C"  # margin too low
    assert assign_tier(1, 5.0) == "C"


def test_tier_boundary():
    """Exact boundary values."""
    assert assign_tier(3, 20.0) == "A"
    assert assign_tier(2, 12.0) == "B"
    assert assign_tier(3, 19.9) == "B"  # just under A margin → B
    assert assign_tier(2, 11.9) == "C"  # just under B margin → C
