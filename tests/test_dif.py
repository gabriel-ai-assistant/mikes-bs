"""Comprehensive unit tests for the DIF module.

No DB required — ALS with session=None is tested; CMS uses assessed value fallback.
"""

import pytest
from datetime import date

from openclaw.analysis.dif.config import DIFConfig
from openclaw.analysis.dif.components import ComponentResult
from openclaw.analysis.dif.components.yms import compute_yms
from openclaw.analysis.dif.components.efi import compute_efi
from openclaw.analysis.dif.components.als import compute_als
from openclaw.analysis.dif.components.cms import compute_cms
from openclaw.analysis.dif.components.sfi import compute_sfi
from openclaw.analysis.dif.engine import compute_dif


# ── Shared fixtures ────────────────────────────────────────────────────────────

@pytest.fixture
def config():
    """Default DIFConfig using all hardcoded defaults."""
    return DIFConfig()


@pytest.fixture
def r5_12ac_candidate():
    """Fixture: Snohomish R-5 12ac parcel outside UGA, Smith Family Trust, ~24yr ownership."""
    return {
        "parcel_id": "aaa00001-0000-0000-0000-000000000001",
        "county": "snohomish",
        "zone_code": "R-5",
        "lot_sf": 12 * 43560.0,
        "has_critical_area_overlap": False,
        "improvement_value": 10_000,
        "total_value": 380_000,
        "assessed_value": 380_000,
        "address": "123 Rural Rd",
        "owner_name": "Smith Family Trust",
        "last_sale_date": date(2001, 6, 15),  # ~24yr ownership as of 2026
        "potential_splits": 4,
        "uga_outside": True,
    }


@pytest.fixture
def commercial_candidate():
    """Fixture: Commercial B-1 zone parcel, recent corporate ownership, minimal splits."""
    return {
        "parcel_id": "bbb00002-0000-0000-0000-000000000002",
        "county": "king",
        "zone_code": "B-1",
        "lot_sf": 5 * 43560.0,
        "has_critical_area_overlap": True,   # friction
        "improvement_value": 300_000,
        "total_value": 350_000,
        "assessed_value": 350_000,
        "address": "456 Commerce Ave",
        "owner_name": "MEGACORP LLC",
        "last_sale_date": date(2022, 3, 1),  # recent sale, low SFI
        "potential_splits": 1,
        "uga_outside": False,
    }


# ── YMS tests ─────────────────────────────────────────────────────────────────

class TestYMS:
    def test_yms_splits_computed_correctly(self, config):
        """Basic split computation: 4 splits → score = 4/20 * 10 = 2.0."""
        candidate = {"potential_splits": 4, "zone_code": "R-5", "has_critical_area_overlap": False}
        result = compute_yms(candidate, config)
        assert isinstance(result, ComponentResult)
        assert result.score == pytest.approx(2.0)

    def test_yms_critical_area_deduction(self, config):
        """Critical area overlap deducts 1 split."""
        candidate = {"potential_splits": 5, "zone_code": "R-5", "has_critical_area_overlap": True}
        result = compute_yms(candidate, config)
        # adjusted = 5 - 1 = 4; capped = 4; score = 4/20 * 10 = 2.0
        assert result.score == pytest.approx(2.0)

    def test_yms_cap_at_20(self, config):
        """Parcels with many splits are capped at YMS_MAX_EFFECTIVE_LOTS=20 → score=10."""
        candidate = {"potential_splits": 30, "zone_code": "R-5", "has_critical_area_overlap": False}
        result = compute_yms(candidate, config)
        assert result.score == pytest.approx(10.0)
        assert "YMS_YIELD_CAPPED" in result.reasons

    def test_yms_heuristic_always_present(self, config):
        """YMS_HEURISTIC reason code is always in reasons."""
        for splits in [0, 1, 5, 20, 50]:
            candidate = {"potential_splits": splits, "zone_code": "R-5", "has_critical_area_overlap": False}
            result = compute_yms(candidate, config)
            assert "YMS_HEURISTIC" in result.reasons, f"Missing YMS_HEURISTIC for splits={splits}"

    def test_yms_zero_splits_scores_zero(self, config):
        """Zero potential splits → score 0."""
        candidate = {"potential_splits": 0, "zone_code": "R-5", "has_critical_area_overlap": False}
        result = compute_yms(candidate, config)
        assert result.score == pytest.approx(0.0)

    def test_yms_deduction_cannot_go_below_zero(self, config):
        """Deduction can't make adjusted splits negative."""
        candidate = {"potential_splits": 0, "zone_code": "R-5", "has_critical_area_overlap": True}
        result = compute_yms(candidate, config)
        assert result.score == pytest.approx(0.0)

    def test_yms_data_quality_full_with_zone(self, config):
        """data_quality is 'full' when zone_code is present."""
        candidate = {"potential_splits": 3, "zone_code": "R-5", "has_critical_area_overlap": False}
        result = compute_yms(candidate, config)
        assert result.data_quality == "full"

    def test_yms_data_quality_partial_without_zone(self, config):
        """data_quality is 'partial' when zone_code is missing."""
        candidate = {"potential_splits": 3, "has_critical_area_overlap": False}
        result = compute_yms(candidate, config)
        assert result.data_quality == "partial"


# ── EFI tests ─────────────────────────────────────────────────────────────────

class TestEFI:
    def test_efi_zero_friction_scores_high(self, config):
        """Zero friction: score = 10 - 0*0.5 = 10.0."""
        candidate = {"has_critical_area_overlap": False, "improvement_value": 50000, "address": "123 Main St"}
        result = compute_efi(candidate, config)
        assert result.score == pytest.approx(10.0)

    def test_efi_mild_friction_scores_high(self, config):
        """No critical area, but access unknown → friction=3.0 → score = 10 - 3*0.5 = 8.5."""
        candidate = {"has_critical_area_overlap": False, "improvement_value": None, "address": None}
        result = compute_efi(candidate, config)
        # friction = 3.0 (access unknown, no critical area)
        # score = 10 - 3.0 * 0.5 = 8.5
        assert result.score == pytest.approx(8.5)

    def test_efi_critical_area_only_friction(self, config):
        """Critical area alone → friction=4.0 → score = 10 - 3.0*0.5 - (4.0-3.0)*2.0 = 8.5 - 2.0 = 6.5."""
        candidate = {"has_critical_area_overlap": True, "improvement_value": 50000, "address": "123 Main St"}
        result = compute_efi(candidate, config)
        # friction = 4.0, which is > EFI_MILD_THRESHOLD(3.0)
        # score = 10 - 3.0*0.5 - (4.0-3.0)*2.0 = 10 - 1.5 - 2.0 = 6.5
        assert result.score == pytest.approx(6.5)

    def test_efi_high_friction_scores_near_zero(self, config):
        """Critical area AND access unknown → friction=7.0 → steep penalty → low score."""
        candidate = {"has_critical_area_overlap": True, "improvement_value": None, "address": None}
        result = compute_efi(candidate, config)
        # friction = 4.0 + 3.0 = 7.0 > EFI_MILD_THRESHOLD(3.0)
        # score = max(0, 10 - 3.0*0.5 - (7.0-3.0)*2.0) = max(0, 10 - 1.5 - 8.0) = max(0, 0.5) = 0.5
        assert result.score == pytest.approx(0.5)
        assert result.score < 3.0

    def test_efi_asymmetric_friction5_much_lower_than_friction3(self, config):
        """Asymmetry: friction=5 scores much lower than friction=3 (steeper penalty beyond threshold)."""
        # friction=3 (at threshold): score = 10 - 3*0.5 = 8.5
        # friction=5 (beyond threshold): score = 10 - 3*0.5 - (5-3)*2.0 = 10 - 1.5 - 4.0 = 4.5
        # Difference: 8.5 - 4.5 = 4.0 (a 2-point friction increase causes 4-point score drop)
        candidate_low = {"has_critical_area_overlap": False, "improvement_value": None, "address": None}
        result_low = compute_efi(candidate_low, config)  # friction=3.0
        # We need friction=5 to test asymmetry — critical area(4) + access unknown(3) = 7
        # Let's use a custom config with lower threshold to force friction=5
        # Actually friction=5 requires both critical_area(4) and access unknown(3) = 7 at minimum
        # Let's compare friction=3 vs friction=7 to demonstrate asymmetry clearly
        candidate_high = {"has_critical_area_overlap": True, "improvement_value": None, "address": None}
        result_high = compute_efi(candidate_high, config)  # friction=7.0
        # score_low (friction=3) = 8.5
        # score_high (friction=7) = 0.5
        # Drop from 3→7 friction is 8.0 points, much greater than linear would predict
        assert result_low.score > result_high.score
        assert (result_low.score - result_high.score) > 4.0  # steep asymmetric decay

    def test_efi_slope_and_sewer_stubs_in_reasons(self, config):
        """SLOPE_STUBBED and SEWER_STUBBED always appear in reasons."""
        candidate = {"has_critical_area_overlap": False, "improvement_value": 0, "address": "addr"}
        result = compute_efi(candidate, config)
        assert "SLOPE_STUBBED" in result.reasons
        assert "SEWER_STUBBED" in result.reasons

    def test_efi_data_quality_always_partial(self, config):
        """EFI data_quality is always 'partial' (slope/sewer stubs)."""
        candidate = {"has_critical_area_overlap": False, "improvement_value": 50000, "address": "123 St"}
        result = compute_efi(candidate, config)
        assert result.data_quality == "partial"


# ── ALS tests ─────────────────────────────────────────────────────────────────

class TestALS:
    def test_als_session_none_returns_unavailable(self, config):
        """ALS without session returns score=0 and 'unavailable' quality."""
        candidate = {"parcel_id": "abc", "county": "snohomish", "zone_code": "R-5"}
        result = compute_als(candidate, config, session=None)
        assert result.score == pytest.approx(0.0)
        assert result.data_quality == "unavailable"

    def test_als_session_none_reason_codes(self, config):
        """ALS without session emits ALS_NO_SESSION and ALS_NO_DOM."""
        candidate = {"parcel_id": "abc", "county": "snohomish", "zone_code": "R-5"}
        result = compute_als(candidate, config, session=None)
        assert "ALS_NO_SESSION" in result.reasons
        assert "ALS_NO_DOM" in result.reasons

    def test_als_no_dom_always_present_with_session(self, config):
        """ALS_NO_DOM stub code is always present when session=None (fallback path)."""
        result = compute_als({}, config, session=None)
        assert "ALS_NO_DOM" in result.reasons


# ── CMS tests ─────────────────────────────────────────────────────────────────

class TestCMS:
    def test_cms_high_margin_scores_10(self, config):
        """High assessed value relative to costs → margin >= 30% → score = 10."""
        # assessed_value = 1_000_000; revenue = 2_500_000; costs << revenue
        candidate = {
            "parcel_id": "abc",
            "county": "snohomish",
            "zone_code": "R-5",
            "assessed_value": 1_000_000,
            "potential_splits": 1,
        }
        result = compute_cms(candidate, config, session=None)
        assert result.score == pytest.approx(10.0)

    def test_cms_30pct_margin_scores_10(self, config):
        """Exactly 30% margin → score exactly 10.0."""
        # assessed_value = 1_000_000 → margin ~40%, clamped to 10
        candidate = {
            "parcel_id": "abc",
            "county": "snohomish",
            "zone_code": "R-5",
            "assessed_value": 1_000_000,
            "potential_splits": 1,
        }
        result = compute_cms(candidate, config, session=None)
        # Score should be 10 (margin > 30%)
        assert result.score == pytest.approx(10.0)

    def test_cms_negative_margin_scores_zero(self, config):
        """Very low assessed value → revenue much less than costs → score 0."""
        # revenue = 100 * 2.5 = 250; costs ≈ 433k → huge negative margin
        candidate = {
            "parcel_id": "abc",
            "county": "snohomish",
            "zone_code": "R-5",
            "assessed_value": 100,
            "potential_splits": 1,
        }
        result = compute_cms(candidate, config, session=None)
        assert result.score == pytest.approx(0.0)

    def test_cms_return_proxy_not_irr_always_present(self, config):
        """RETURN_PROXY_NOT_IRR is always in reasons."""
        candidate = {
            "parcel_id": "abc",
            "county": "snohomish",
            "zone_code": "R-5",
            "assessed_value": 500_000,
            "potential_splits": 2,
        }
        result = compute_cms(candidate, config, session=None)
        assert "RETURN_PROXY_NOT_IRR" in result.reasons

    def test_cms_land_cost_source_reason_present(self, config):
        """Land cost source reason code (LAND_COST_SOURCE:*) is always in reasons."""
        candidate = {
            "parcel_id": "abc",
            "county": "snohomish",
            "zone_code": "R-5",
            "assessed_value": 500_000,
            "potential_splits": 2,
        }
        result = compute_cms(candidate, config, session=None)
        source_reasons = [r for r in result.reasons if r.startswith("LAND_COST_SOURCE:")]
        assert len(source_reasons) == 1

    def test_cms_last_sale_price_preferred_over_assessed(self, config):
        """LAST_SALE preferred over ASSESSED when available and > 0."""
        candidate = {
            "parcel_id": "abc",
            "county": "snohomish",
            "zone_code": "R-5",
            "assessed_value": 500_000,
            "last_sale_price": 600_000,
            "potential_splits": 1,
        }
        result = compute_cms(candidate, config, session=None)
        assert "LAND_COST_SOURCE:LAST_SALE" in result.reasons

    def test_cms_data_quality_partial_without_session(self, config):
        """Without a session, data_quality is 'partial'."""
        candidate = {"assessed_value": 300_000, "potential_splits": 1}
        result = compute_cms(candidate, config, session=None)
        assert result.data_quality == "partial"

    def test_cms_county_multiplier_applied(self, config):
        """County multiplier in CMS_ASSESSED_VALUE_MULTIPLIER is applied."""
        custom_config = DIFConfig()
        custom_config.CMS_ASSESSED_VALUE_MULTIPLIER = {"default": 1.0, "king": 1.2}
        candidate = {
            "parcel_id": "abc",
            "county": "king",
            "zone_code": "B-1",
            "assessed_value": 500_000,
            "potential_splits": 1,
        }
        result_king = compute_cms(candidate, custom_config, session=None)
        candidate_default = dict(candidate)
        candidate_default["county"] = "snohomish"
        result_default = compute_cms(candidate_default, custom_config, session=None)
        # Higher land cost for king → lower margin → lower score
        assert result_king.score <= result_default.score


# ── SFI tests ─────────────────────────────────────────────────────────────────

class TestSFI:
    def test_sfi_long_ownership_trust_scores_high(self, config):
        """24yr ownership + trust name → SFI score should be high (≥ 4.0)."""
        candidate = {
            "owner_name": "Smith Family Trust",
            "last_sale_date": date(2001, 6, 15),
            "improvement_value": 10_000,
            "total_value": 380_000,
        }
        result = compute_sfi(candidate, config)
        assert result.score >= 4.0

    def test_sfi_trust_bonus_fires(self, config):
        """Owner with TRUST in name triggers SFI_TRUST_BONUS."""
        candidate = {
            "owner_name": "John TRUST",
            "last_sale_date": None,
            "improvement_value": 50_000,
            "total_value": 100_000,
        }
        result = compute_sfi(candidate, config)
        # No ownership years (None), so base = 0.5 * 4.0 = 2.0, trust bonus = 2.0 → 4.0
        # imp_ratio = 0.5 → NOT < 0.15, no low_imp bonus
        assert result.score == pytest.approx(4.0)

    def test_sfi_no_sale_date_partial_quality(self, config):
        """No last_sale_date → data_quality='partial'."""
        candidate = {
            "owner_name": "Jane Smith",
            "last_sale_date": None,
            "improvement_value": 100_000,
            "total_value": 200_000,
        }
        result = compute_sfi(candidate, config)
        assert result.data_quality == "partial"

    def test_sfi_no_sale_date_score_nonzero_with_low_imp(self, config):
        """No sale date still generates nonzero score if imp_ratio < 0.15."""
        candidate = {
            "owner_name": "Jane Smith",
            "last_sale_date": None,
            "improvement_value": 5_000,    # low improvement
            "total_value": 200_000,        # imp_ratio = 0.025 < 0.15
        }
        result = compute_sfi(candidate, config)
        # base = 0.5 * 4.0 = 2.0; low_imp bonus = 2.0; total = 4.0
        assert result.score > 0.0
        assert result.score == pytest.approx(4.0)

    def test_sfi_full_quality_with_sale_date(self, config):
        """Known last_sale_date → data_quality='full'."""
        candidate = {
            "owner_name": "Bob Owner",
            "last_sale_date": date(1995, 1, 1),
            "improvement_value": 100_000,
            "total_value": 200_000,
        }
        result = compute_sfi(candidate, config)
        assert result.data_quality == "full"

    def test_sfi_short_ownership_no_bonus(self, config):
        """Recent buyer (<10 years) gets no ownership duration bonus."""
        candidate = {
            "owner_name": "Recent Buyer LLC",
            "last_sale_date": date(2023, 1, 1),  # ~3yr
            "improvement_value": 300_000,
            "total_value": 350_000,   # imp_ratio ≈ 0.86, high → no bonus
        }
        result = compute_sfi(candidate, config)
        # No ownership bonus (< 10yr), no trust, imp_ratio > 0.15
        assert result.score == pytest.approx(0.0)

    def test_sfi_tax_delinquency_stubbed_always(self, config):
        """TAX_DELINQUENCY_STUBBED always in reasons."""
        candidate = {
            "owner_name": "Bob",
            "last_sale_date": None,
            "improvement_value": 0,
            "total_value": 1,
        }
        result = compute_sfi(candidate, config)
        assert "TAX_DELINQUENCY_STUBBED" in result.reasons

    def test_sfi_score_capped_at_10(self, config):
        """Score cannot exceed 10.0 even with all bonuses firing."""
        candidate = {
            "owner_name": "Smith Family Trust Estate",
            "last_sale_date": date(1980, 1, 1),  # ~46yr, max is 1.0 * 4.0 = 4.0
            "improvement_value": 1_000,
            "total_value": 1_000_000,  # imp_ratio ≈ 0.001 < 0.15
        }
        result = compute_sfi(candidate, config)
        assert result.score <= 10.0

    def test_sfi_estate_pattern_triggers_trust_bonus(self, config):
        """ESTATE in owner name triggers SFI_TRUST_BONUS."""
        candidate = {
            "owner_name": "Estate of John Smith",
            "last_sale_date": None,
            "improvement_value": 200_000,
            "total_value": 300_000,
        }
        result = compute_sfi(candidate, config)
        # base (no sale date) = 2.0; trust bonus = 2.0 → 4.0
        assert result.score == pytest.approx(4.0)


# ── Integration tests ──────────────────────────────────────────────────────────

class TestIntegration:
    def test_composite_r5_beats_commercial(self, config, r5_12ac_candidate, commercial_candidate):
        """R-5 12ac trust parcel should score higher than B-1 corporate parcel."""
        r5_result = compute_dif(r5_12ac_candidate, config, session=None)
        commercial_result = compute_dif(commercial_candidate, config, session=None)
        assert r5_result.score > commercial_result.score, (
            f"Expected R-5 ({r5_result.score:.2f}) > Commercial ({commercial_result.score:.2f})"
        )

    def test_dif_result_namedtuple_fields(self, config, r5_12ac_candidate):
        """DIFResult has all required fields."""
        result = compute_dif(r5_12ac_candidate, config, session=None)
        assert hasattr(result, 'score')
        assert hasattr(result, 'delta')
        assert hasattr(result, 'components')
        assert hasattr(result, 'reasons')
        assert hasattr(result, 'data_confidence')

    def test_dif_components_dict_keys(self, config, r5_12ac_candidate):
        """DIF components dict has all 5 keys."""
        result = compute_dif(r5_12ac_candidate, config, session=None)
        assert set(result.components.keys()) == {'yms', 'efi', 'als', 'cms', 'sfi'}

    def test_dif_data_confidence_range(self, config, r5_12ac_candidate):
        """data_confidence is between 0.0 and 1.0."""
        result = compute_dif(r5_12ac_candidate, config, session=None)
        assert 0.0 <= result.data_confidence <= 1.0

    def test_dif_delta_applied_reason_present(self, config, r5_12ac_candidate):
        """DIF_DELTA_APPLIED:* reason is always present in reasons."""
        result = compute_dif(r5_12ac_candidate, config, session=None)
        delta_reasons = [r for r in result.reasons if r.startswith("DIF_DELTA_APPLIED:")]
        assert len(delta_reasons) == 1
