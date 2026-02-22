"""Bundle detection helpers."""

# DATA CONTRACT: Adjacency operates on parcels present in the local PostGIS DB.
# ArcGIS REST is used only to refresh owner/taxpayer fields when stale or missing.
# If a neighbor parcel is missing from DB, log a warning — do NOT fetch geometry from ArcGIS.

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import re

try:
    from rapidfuzz import fuzz
except Exception:  # pragma: no cover - fallback only when rapidfuzz is missing
    fuzz = None

_SUFFIX_RE = re.compile(r"\b(LLC|INC|TRUST|CORP|ET\s*AL|ETAL|LTD|LP)\b", re.IGNORECASE)
_WS_RE = re.compile(r"\s+")
_ZIP_RE = re.compile(r"\b(\d{5})(?:-\d{4})?\b")


def canonical_owner_name(
    db_owner_name: str | None,
    arcgis_owner_name: str | None = None,
    arcgis_taxpayer_name: str | None = None,
) -> tuple[str | None, str | None]:
    """Choose canonical owner string using the FIX-C fallback chain."""
    for value, basis in (
        (db_owner_name, "db_owner"),
        (arcgis_owner_name, "arcgis_owner"),
        (arcgis_taxpayer_name, "arcgis_taxpayer"),
    ):
        normalized = (value or "").strip()
        if normalized:
            return normalized, basis
    return None, None


def normalize_owner_name(value: str | None) -> str:
    """Normalize owner names for exact/fuzzy matching."""
    cleaned = (value or "").lower().strip()
    cleaned = _SUFFIX_RE.sub(" ", cleaned)
    cleaned = re.sub(r"[^a-z0-9\s]", " ", cleaned)
    cleaned = _WS_RE.sub(" ", cleaned).strip()
    return cleaned


def extract_zip(value: str | None) -> str | None:
    """Extract ZIP from a freeform mailing address string."""
    if not value:
        return None
    match = _ZIP_RE.search(value)
    return match.group(1) if match else None


def fuzzy_owner_match(
    owner_a: str | None,
    owner_b: str | None,
    zip_a: str | None,
    zip_b: str | None,
    threshold: float = 0.85,
    min_name_length: int = 6,
) -> tuple[bool, float]:
    """Return fuzzy match verdict + similarity score (0.0-1.0).

    FIX-D gates:
    - Minimum normalized name length
    - ZIP exact-match gate for fuzzy-tier comparisons
    """
    left = normalize_owner_name(owner_a)
    right = normalize_owner_name(owner_b)

    if not left or not right:
        return False, 0.0
    if min(len(left), len(right)) < min_name_length:
        return False, 0.0

    if zip_a and zip_b and zip_a != zip_b:
        return False, 0.0

    if fuzz is not None:
        score = float(fuzz.token_set_ratio(left, right)) / 100.0
    else:  # pragma: no cover
        from difflib import SequenceMatcher

        score = SequenceMatcher(None, left, right).ratio()

    return score >= threshold, score


def is_bundle_stale(bundle_data: dict | None, now: datetime | None = None, ttl_days: int = 7) -> bool:
    """TTL staleness check for stored bundle payloads (FIX-G)."""
    payload = bundle_data or {}
    if payload.get("stale"):
        return True

    detected_at = payload.get("detected_at")
    if not detected_at:
        return True

    now = now or datetime.now(timezone.utc)
    try:
        detected_dt = datetime.fromisoformat(str(detected_at).replace("Z", "+00:00"))
    except ValueError:
        return True

    return (now - detected_dt) > timedelta(days=ttl_days)


def mark_bundle_stale(bundle_data: dict | None) -> dict:
    """Set stale flag on existing bundle payload."""
    payload = deepcopy(bundle_data or {})
    payload["stale"] = True
    return payload


def should_invalidate_bundle(
    old_owner_name_canonical: str | None,
    new_owner_name_canonical: str | None,
    geometry_changed: bool,
) -> bool:
    """Invalidation predicate for bundle cache (FIX-G)."""
    if geometry_changed:
        return True
    return normalize_owner_name(old_owner_name_canonical) != normalize_owner_name(new_owner_name_canonical)
