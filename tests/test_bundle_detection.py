from datetime import datetime, timedelta, timezone

from openclaw.analysis.bundle_detection import (
    canonical_owner_name,
    extract_zip,
    fuzzy_owner_match,
    is_bundle_stale,
    should_invalidate_bundle,
)


def test_canonical_owner_fallback_chain():
    assert canonical_owner_name("DB Owner", "Arc Owner", "Tax Owner") == ("DB Owner", "db_owner")
    assert canonical_owner_name("", "Arc Owner", "Tax Owner") == ("Arc Owner", "arcgis_owner")
    assert canonical_owner_name(None, None, "Tax Owner") == ("Tax Owner", "arcgis_taxpayer")


def test_extract_zip():
    assert extract_zip("123 Main St, Everett WA 98201") == "98201"
    assert extract_zip("No zip") is None


def test_fuzzy_match_min_length_gate():
    matched, score = fuzzy_owner_match("ABCD", "ABCE", "98201", "98201")
    assert matched is False
    assert score == 0.0


def test_fuzzy_match_zip_gate():
    matched, score = fuzzy_owner_match("Northwest Property Group LLC", "Northwest Property Group", "98201", "98101")
    assert matched is False
    assert score == 0.0


def test_fuzzy_match_positive():
    matched, score = fuzzy_owner_match("Northwest Property Group LLC", "Northwest Property Group Inc", "98201", "98201")
    assert matched is True
    assert score >= 0.85


def test_bundle_ttl_staleness():
    fresh = {"detected_at": datetime.now(timezone.utc).isoformat(), "stale": False}
    stale = {"detected_at": (datetime.now(timezone.utc) - timedelta(days=8)).isoformat(), "stale": False}
    assert is_bundle_stale(fresh) is False
    assert is_bundle_stale(stale) is True


def test_bundle_invalidation_on_owner_or_geometry_change():
    assert should_invalidate_bundle("Jane Smith", "Jane Smith", geometry_changed=True) is True
    assert should_invalidate_bundle("Jane Smith", "John Smith", geometry_changed=False) is True
    assert should_invalidate_bundle("Jane Smith", "Jane Smith", geometry_changed=False) is False
