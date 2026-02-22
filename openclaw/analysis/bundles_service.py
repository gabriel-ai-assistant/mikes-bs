"""Candidate parcel bundle detection."""

from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy import text
from sqlalchemy.orm import Session

from openclaw.analysis.bundle_detection import (
    canonical_owner_name,
    extract_zip,
    fuzzy_owner_match,
    is_bundle_stale,
    should_invalidate_bundle,
)
from openclaw.db.models import Candidate


def _adjacent_rows(session: Session, parcel_uuid: str) -> list[dict]:
    rows = session.execute(text("""
        SELECT
            p.id::text AS parcel_uuid,
            p.parcel_id,
            p.owner_name,
            p.owner_address,
            p.lot_sf,
            p.assessed_value
        FROM parcels base
        JOIN parcels p ON p.id != base.id
        WHERE base.id = :parcel_id
          AND (
            ST_Touches(base.geometry, p.geometry)
            OR ST_DWithin(
                base.geometry::geography,
                p.geometry::geography,
                3.048 -- 10 feet tolerance in meters (geography cast)
            )
          )
    """), {"parcel_id": parcel_uuid}).mappings().all()
    return [dict(r) for r in rows]


def detect_bundle_for_candidate(session: Session, candidate_id: str) -> dict | None:
    candidate = session.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not candidate or not candidate.parcel:
        return None

    owner_name, match_basis = canonical_owner_name(candidate.parcel.owner_name)
    if not owner_name:
        return None

    previous_owner = candidate.owner_name_canonical
    current_owner = owner_name

    geometry_changed = False
    if should_invalidate_bundle(previous_owner, current_owner, geometry_changed):
        candidate.bundle_data = None

    if candidate.bundle_data and not is_bundle_stale(candidate.bundle_data):
        return candidate.bundle_data

    base_zip = extract_zip(candidate.parcel.owner_address)
    neighbors = _adjacent_rows(session, str(candidate.parcel_id))

    parcels = []
    match_tier = "exact"
    best_similarity = 1.0

    for n in neighbors:
        neighbor_owner, _basis = canonical_owner_name(n.get("owner_name"))
        if not neighbor_owner:
            continue

        norm_exact = neighbor_owner.strip().lower() == owner_name.strip().lower()
        if norm_exact:
            parcels.append({
                "parcel_id": n["parcel_id"],
                "owner_name": neighbor_owner,
                "lot_sf": float(n.get("lot_sf") or 0),
                "assessed_value": int(n.get("assessed_value") or 0),
            })
            continue

        neighbor_zip = extract_zip(n.get("owner_address"))
        fuzzy_ok, similarity = fuzzy_owner_match(owner_name, neighbor_owner, base_zip, neighbor_zip)
        if fuzzy_ok:
            parcels.append({
                "parcel_id": n["parcel_id"],
                "owner_name": neighbor_owner,
                "lot_sf": float(n.get("lot_sf") or 0),
                "assessed_value": int(n.get("assessed_value") or 0),
            })
            match_tier = "fuzzy"
            best_similarity = max(best_similarity if match_tier == "exact" else 0.0, similarity)

    base_entry = {
        "parcel_id": candidate.parcel.parcel_id,
        "owner_name": owner_name,
        "lot_sf": float(candidate.parcel.lot_sf or 0),
        "assessed_value": int(candidate.parcel.assessed_value or 0),
    }

    payload = {
        "parcels": [base_entry] + parcels,
        "match_tier": match_tier,
        "match_basis": match_basis,
        "similarity_score": float(best_similarity if match_tier == "fuzzy" else 1.0),
        "total_acres": round(sum((p.get("lot_sf") or 0) for p in [base_entry] + parcels) / 43560.0, 4),
        "total_assessed_value": int(sum((p.get("assessed_value") or 0) for p in [base_entry] + parcels)),
        "detected_at": datetime.now(timezone.utc).isoformat(),
        "stale": False,
    }

    tags = set(candidate.tags or [])
    if len(parcels) > 0:
        tags.add("EDGE_BUNDLE_ADJACENT")
        tags.add("EDGE_BUNDLE_SAME_OWNER")

    candidate.owner_name_canonical = owner_name
    candidate.display_text = " ".join(x for x in [candidate.parcel.address, owner_name] if x)
    candidate.bundle_data = payload
    candidate.tags = sorted(tags)
    session.commit()
    return payload
