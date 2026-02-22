"""Map routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from openclaw.db.models import Candidate, Parcel, ScoreTierEnum
from openclaw.web.common import db, templates

router = APIRouter()


@router.get("/map", response_class=HTMLResponse)
def map_page(request: Request):
    return templates.TemplateResponse("map.html", {"request": request})


@router.get("/api/map/points")
def map_points(
    tier: str = Query("", alias="tier"),
    ag_only: bool = Query(False),
    session: Session = Depends(db),
):
    candidate_count = session.query(func.count(Candidate.id)).scalar() or 0

    if candidate_count > 0:
        q = session.query(
            Candidate.id,
            Candidate.score_tier,
            Candidate.score,
            Candidate.potential_splits,
            Candidate.has_critical_area_overlap,
            Candidate.flagged_for_review,
            Parcel.parcel_id,
            Parcel.address,
            Parcel.owner_name,
            Parcel.lot_sf,
            Parcel.zone_code,
            Parcel.assessed_value,
            func.ST_Y(func.ST_Centroid(Parcel.geometry)).label("lat"),
            func.ST_X(func.ST_Centroid(Parcel.geometry)).label("lng"),
        ).join(Parcel).filter(Parcel.geometry.isnot(None))

        if tier in ("A", "B", "C", "D", "E", "F"):
            q = q.filter(Candidate.score_tier == ScoreTierEnum(tier))
        if ag_only:
            q = q.filter(Candidate.flagged_for_review.is_(True))

        rows = q.order_by(Candidate.score_tier, Candidate.potential_splits.desc()).limit(3000).all()
        return [
            {
                "id": str(r.id),
                "parcel_id": r.parcel_id,
                "tier": r.score_tier.value if r.score_tier else "C",
                "score": r.score,
                "address": r.address or "No address",
                "owner": r.owner_name or "Unknown owner",
                "splits": r.potential_splits,
                "lot_sf": r.lot_sf,
                "zone": r.zone_code,
                "value": r.assessed_value,
                "wetland": r.has_critical_area_overlap,
                "ag": r.flagged_for_review,
                "lat": float(r.lat),
                "lng": float(r.lng),
            }
            for r in rows
            if r.lat is not None and r.lng is not None
        ]

    rows = session.execute(text("""
        SELECT p.id::text, p.parcel_id, p.address, p.owner_name, p.lot_sf, p.assessed_value,
               p.zone_code,
               ST_Y(ST_Centroid(p.geometry)) AS lat,
               ST_X(ST_Centroid(p.geometry)) AS lng
        FROM parcels p
        WHERE p.geometry IS NOT NULL
        ORDER BY p.lot_sf DESC NULLS LAST
        LIMIT 5000
    """)).mappings().all()

    return [
        {
            "id": r["id"],
            "parcel_id": r["parcel_id"],
            "tier": "parcel",
            "score": None,
            "address": r["address"] or "No address",
            "owner": r["owner_name"] or "Unknown",
            "splits": None,
            "lot_sf": r["lot_sf"],
            "zone": r["zone_code"],
            "value": r["assessed_value"],
            "wetland": False,
            "ag": False,
            "lat": float(r["lat"]),
            "lng": float(r["lng"]),
        }
        for r in rows
        if r["lat"] is not None
    ]
