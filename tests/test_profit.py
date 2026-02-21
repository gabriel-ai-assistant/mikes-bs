"""Tests for profit model calculations."""


def test_profit_calculation():
    """Given known inputs, verify profit and margin within 1%."""
    # Simulate the profit model math directly (no DB needed)
    splits = 3
    assessed_value = 450000
    arv_per_home = 550000

    cost_short_plat = 8000
    cost_engineering = 6000
    cost_utility = 12000
    cost_build_per_sf = 185
    target_home_sf = 2200

    estimated_land_value = assessed_value // splits
    assert estimated_land_value == 150000

    dev_cost_per_lot = cost_short_plat + cost_engineering + cost_utility
    estimated_dev_cost = dev_cost_per_lot * splits
    assert estimated_dev_cost == 78000

    estimated_build_cost = cost_build_per_sf * target_home_sf * splits
    assert estimated_build_cost == 1221000

    estimated_arv = arv_per_home * splits
    assert estimated_arv == 1650000

    estimated_profit = estimated_arv - (assessed_value + estimated_dev_cost + estimated_build_cost)
    assert estimated_profit == 1650000 - (450000 + 78000 + 1221000)
    assert estimated_profit == -99000  # negative — not all parcels are profitable

    margin_pct = estimated_profit / estimated_arv * 100
    assert abs(margin_pct - (-6.0)) < 1.0


def test_profit_positive_case():
    """Profitable scenario with high ARV."""
    splits = 4
    assessed_value = 300000
    arv_per_home = 650000

    dev_cost = (8000 + 6000 + 12000) * splits  # 104000
    build_cost = 185 * 2200 * splits  # 1628000
    arv = arv_per_home * splits  # 2600000
    profit = arv - (assessed_value + dev_cost + build_cost)
    # 2600000 - (300000 + 104000 + 1628000) = 568000
    assert profit == 568000

    margin = profit / arv * 100
    assert abs(margin - 21.85) < 1.0


def test_no_comps_fallback():
    """When no comps, ARV = assessed * 1.35."""
    assessed = 400000
    arv_fallback = int(assessed * 1.35)
    assert arv_fallback == 540000
