"""Candidates and property-detail routes."""

from __future__ import annotations

import json
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import func, text
from sqlalchemy.orm import Session, joinedload

from openclaw.analysis.bundles_service import detect_bundle_for_candidate
from openclaw.db.models import Candidate, CandidateFeedback, CandidateNote, Parcel, ScoreTierEnum, ZoningRule
from openclaw.web.common import db, fmt_acres, fmt_money, fmt_sqft, templates

router = APIRouter()


@router.get("/candidates", response_class=HTMLResponse)
def candidates_page(
    request: Request,
    search: str = Query("", alias="q"),
    tier: str = Query("", alias="tier"),
    sort: str = Query("splits", alias="sort"),
    wetland: str = Query("", alias="wetland"),
    ag: str = Query("", alias="ag"),
    use_type: str = Query("", alias="use_type"),
    tags: str | None = Query(None, alias="tags"),
    tags_mode: str = Query("any", alias="tags_mode"),
    session: Session = Depends(db),
):
    q = (
        session.query(Candidate)
        .join(Parcel)
        .options(joinedload(Candidate.parcel))
    )
    if search:
        # TODO(FIX-I Phase 2): if this query exceeds ~200ms, enable pg_trgm:
        #   CREATE EXTENSION IF NOT EXISTS pg_trgm;
        #   CREATE INDEX idx_candidates_display_trgm ON candidates USING GIN (display_text gin_trgm_ops);
        q = q.filter(
            func.coalesce(
                Candidate.display_text,
                func.concat_ws(" ", Parcel.address, func.coalesce(Candidate.owner_name_canonical, Parcel.owner_name)),
            ).ilike(f"%{search}%")
        )
    if tier in ("A", "B", "C", "D", "E", "F"):
        q = q.filter(Candidate.score_tier == ScoreTierEnum(tier))
    if wetland == "1":
        q = q.filter(Candidate.has_critical_area_overlap.is_(True))
    if ag == "1":
        q = q.filter(Candidate.flagged_for_review.is_(True))
    if use_type:
        q = q.filter(Parcel.present_use.ilike(f"%{use_type}%"))
    if tags:
        tags_list = [t.strip() for t in tags.split(",") if t.strip()]
        if tags_list:
            if tags_mode == "all":
                for _t in tags_list:
                    q = q.filter(text(":_tag = ANY(candidates.tags)").bindparams(_tag=_t))
            else:
                from sqlalchemy import or_

                q = q.filter(or_(*[
                    text(f":_tag_{i} = ANY(candidates.tags)").bindparams(**{f"_tag_{i}": _t})
                    for i, _t in enumerate(tags_list)
                ]))

    sort_map = {
        "splits": Candidate.potential_splits.desc(),
        "lot": Parcel.lot_sf.desc(),
        "value": Parcel.assessed_value.desc(),
    }
    rows = q.order_by(sort_map.get(sort, Candidate.potential_splits.desc())).limit(500).all()

    parcel_ids = [str(c.parcel_id) for c in rows]
    feas_rows = []
    if parcel_ids:
        feas_rows = session.execute(text("""
            SELECT DISTINCT ON (parcel_id)
                parcel_id::text AS parcel_id,
                best_score
            FROM feasibility_results
            WHERE status = 'complete'
              AND parcel_id::text = ANY(:parcel_ids)
            ORDER BY parcel_id, completed_at DESC NULLS LAST, created_at DESC
        """), {"parcel_ids": parcel_ids}).mappings().all()
    feas_map = {r["parcel_id"]: r["best_score"] for r in feas_rows}

    zone_labels = dict(
        session.query(ZoningRule.zone_code, ZoningRule.notes)
        .filter(ZoningRule.county == "snohomish").all()
    )

    return templates.TemplateResponse("candidates.html", {
        "request": request,
        "candidates": rows,
        "zone_labels": zone_labels,
        "search": search,
        "tier": tier,
        "sort": sort,
        "wetland": wetland,
        "ag": ag,
        "use_type": use_type,
        "tags": tags or "",
        "tags_mode": tags_mode,
        "feasibility_scores": feas_map,
    })


@router.get("/api/tags")
def get_all_tags(session: Session = Depends(db)):
    rows = session.execute(text("""
        SELECT DISTINCT unnest(tags) as tag, count(*) as cnt
        FROM candidates
        WHERE tags IS NOT NULL
        GROUP BY tag ORDER BY cnt DESC
    """)).mappings().all()
    return [{"tag": r["tag"], "count": r["cnt"]} for r in rows]


@router.get("/api/candidates")
def get_candidates_api(
    search: str = Query("", alias="q"),
    tier: str = Query("", alias="tier"),
    sort: str = Query("splits", alias="sort"),
    wetland: str = Query("", alias="wetland"),
    ag: str = Query("", alias="ag"),
    use_type: str = Query("", alias="use_type"),
    tags: str | None = Query(None, alias="tags"),
    tags_mode: str = Query("any", alias="tags_mode"),
    limit: int = Query(500),
    offset: int = Query(0),
    session: Session = Depends(db),
):
    q = (
        session.query(
            Candidate,
            func.ST_Y(func.ST_Centroid(Parcel.geometry)).label("lat"),
            func.ST_X(func.ST_Centroid(Parcel.geometry)).label("lng"),
        )
        .join(Parcel)
        .options(joinedload(Candidate.parcel))
    )
    if search:
        q = q.filter(
            func.coalesce(
                Candidate.display_text,
                func.concat_ws(" ", Parcel.address, func.coalesce(Candidate.owner_name_canonical, Parcel.owner_name)),
            ).ilike(f"%{search}%")
        )
    if tier in ("A", "B", "C", "D", "E", "F"):
        q = q.filter(Candidate.score_tier == ScoreTierEnum(tier))
    if wetland == "1":
        q = q.filter(Candidate.has_critical_area_overlap.is_(True))
    if ag == "1":
        q = q.filter(Candidate.flagged_for_review.is_(True))
    if use_type:
        q = q.filter(Parcel.present_use.ilike(f"%{use_type}%"))
    if tags:
        tags_list = [t.strip() for t in tags.split(",") if t.strip()]
        if tags_list:
            if tags_mode == "all":
                for _t in tags_list:
                    q = q.filter(text(":_tag = ANY(candidates.tags)").bindparams(_tag=_t))
            else:
                from sqlalchemy import or_

                q = q.filter(or_(*[
                    text(f":_tag_{i} = ANY(candidates.tags)").bindparams(**{f"_tag_{i}": _t})
                    for i, _t in enumerate(tags_list)
                ]))

    total = q.count()
    sort_map = {
        "splits": Candidate.potential_splits.desc(),
        "splits_desc": Candidate.potential_splits.desc(),
        "lot": Parcel.lot_sf.desc(),
        "value": Parcel.assessed_value.desc(),
    }
    rows = q.order_by(sort_map.get(sort, Candidate.potential_splits.desc())).offset(offset).limit(limit).all()

    parcel_ids = [str(c.parcel_id) for c, _lat, _lng in rows]
    feas_rows = []
    if parcel_ids:
        feas_rows = session.execute(text("""
            SELECT DISTINCT ON (parcel_id)
                parcel_id::text AS parcel_id,
                best_score,
                best_layout_id
            FROM feasibility_results
            WHERE status = 'complete'
              AND parcel_id::text = ANY(:parcel_ids)
            ORDER BY parcel_id, completed_at DESC NULLS LAST, created_at DESC
        """), {"parcel_ids": parcel_ids}).mappings().all()
    feas_map = {r["parcel_id"]: {"score": r["best_score"], "layout": r["best_layout_id"]} for r in feas_rows}

    return {
        "total": total,
        "count": len(rows),
        "candidates": [
            {
                "id": str(c.id),
                "parcel_id": c.parcel.parcel_id,
                "address": c.parcel.address,
                "owner": c.owner_name_canonical or c.parcel.owner_name,
                "tier": c.score_tier.value if c.score_tier else None,
                "use_type": c.parcel.present_use,
                "splits": c.potential_splits,
                "splits_min": c.splits_min,
                "splits_max": c.splits_max,
                "splits_confidence": c.splits_confidence,
                "subdivision_access_mode": c.subdivision_access_mode,
                "economic_margin_pct": c.economic_margin_pct,
                "arbitrage_depth_score": c.arbitrage_depth_score,
                "tags": c.tags or [],
                "feasibility_score": (feas_map.get(str(c.parcel_id)) or {}).get("score"),
                "feasibility_best_layout": (feas_map.get(str(c.parcel_id)) or {}).get("layout"),
                "display_text": c.display_text,
                "lat": float(lat) if lat is not None else None,
                "lng": float(lng) if lng is not None else None,
            }
            for c, lat, lng in rows
        ],
    }


@router.get("/api/use-types")
def get_use_types(session: Session = Depends(db)):
    rows = (
        session.query(Parcel.present_use)
        .filter(Parcel.present_use.isnot(None))
        .filter(Parcel.present_use != "")
        .distinct()
        .order_by(Parcel.present_use.asc())
        .all()
    )
    return {"use_types": [r[0] for r in rows]}


@router.get("/api/candidate/{candidate_id}")
def candidate_detail(candidate_id: str, session: Session = Depends(db)):
    c = (
        session.query(Candidate)
        .options(joinedload(Candidate.parcel))
        .filter(Candidate.id == candidate_id)
        .first()
    )
    if not c:
        return JSONResponse({"error": "not found"}, status_code=404)

    p = c.parcel
    zone_label = None
    if p.zone_code:
        zr = session.query(ZoningRule).filter(
            ZoningRule.county == (p.county.value if p.county else "snohomish"),
            ZoningRule.zone_code == p.zone_code,
        ).first()
        zone_label = zr.notes if zr else p.zone_code

    coords = session.execute(text("""
        SELECT ST_Y(ST_Centroid(geometry)) as lat, ST_X(ST_Centroid(geometry)) as lng
        FROM parcels WHERE id = :pid
    """), {"pid": str(c.parcel_id)}).fetchone()
    lat = float(coords.lat) if coords and coords.lat else None
    lng = float(coords.lng) if coords and coords.lng else None

    reason_codes = c.reason_codes or []
    feas = session.execute(text("""
        SELECT best_score, best_layout_id, status
        FROM feasibility_results
        WHERE parcel_id = :pid
        ORDER BY completed_at DESC NULLS LAST, created_at DESC
        LIMIT 1
    """), {"pid": str(c.parcel_id)}).mappings().first()

    return {
        "id": str(c.id),
        "parcel_id": p.parcel_id,
        "tier": c.score_tier.value if c.score_tier else None,
        "score": c.score,
        "address": p.address,
        "county": p.county.value.title() if p.county else None,
        "lot_sf": p.lot_sf,
        "lot_acres": round(p.lot_sf / 43560, 2) if p.lot_sf else None,
        "zone_code": p.zone_code,
        "zone_label": zone_label,
        "owner_name": c.owner_name_canonical or p.owner_name,
        "owner_name_canonical": c.owner_name_canonical,
        "owner_address": p.owner_address,
        "present_use": p.present_use,
        "assessed_value": p.assessed_value,
        "improvement_value": p.improvement_value,
        "total_value": p.total_value,
        "splits": c.potential_splits,
        "splits_min": c.splits_min,
        "splits_max": c.splits_max,
        "splits_confidence": c.splits_confidence,
        "subdivision_access_mode": c.subdivision_access_mode,
        "economic_margin_pct": c.economic_margin_pct,
        "arbitrage_depth_score": c.arbitrage_depth_score,
        "land_value": c.estimated_land_value,
        "profit": c.estimated_profit,
        "margin_pct": c.estimated_margin_pct,
        "wetland_flag": c.has_critical_area_overlap,
        "ag_flag": c.flagged_for_review,
        "shoreline_flag": c.has_shoreline_overlap,
        "tags": c.tags or [],
        "reason_codes": reason_codes,
        "bundle_data": c.bundle_data,
        "subdivision": {
            "feasibility": c.subdivision_feasibility,
            "score": c.subdivisibility_score,
            "flags": c.subdivision_flags or [],
            "splits_min": c.splits_min,
            "splits_max": c.splits_max,
            "splits_confidence": c.splits_confidence,
            "access_mode": c.subdivision_access_mode,
            "economic_margin_pct": c.economic_margin_pct,
            "arbitrage_depth_score": c.arbitrage_depth_score,
            "feasible_splits": next((int(r.split("_")[-1]) for r in reason_codes if r.startswith("SUBDIV_FEASIBLE_SPLITS_")), None),
            "plat_type": next((r.split("SUBDIV_PLAT_TYPE_")[1] for r in reason_codes if r.startswith("SUBDIV_PLAT_TYPE_")), None),
            "sewer": "SEWER_AVAILABLE" in reason_codes,
            "access": "ACCESS_CONFIRMED" in reason_codes,
        },
        "lat": lat,
        "lng": lng,
        "feasibility": dict(feas) if feas else None,
    }


@router.post("/api/candidate/{candidate_id}/notes")
async def add_note(candidate_id: str, request: Request, session: Session = Depends(db)):
    data = await request.json()
    note_text = data.get("note", "").strip()
    if not note_text:
        return JSONResponse({"error": "note is required"}, status_code=400)
    author = data.get("author", "user")
    session.add(CandidateNote(candidate_id=candidate_id, note=note_text, author=author))
    session.commit()
    return {"ok": True}


@router.get("/api/candidate/{candidate_id}/notes")
def get_notes(candidate_id: str, limit: int = Query(10), session: Session = Depends(db)):
    rows = (
        session.query(CandidateNote)
        .filter(CandidateNote.candidate_id == candidate_id)
        .order_by(CandidateNote.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": r.id,
            "note": r.note,
            "author": r.author,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@router.get("/property/{parcel_id}", response_class=HTMLResponse)
def property_detail(parcel_id: str, request: Request, session: Session = Depends(db)):
    p = session.query(Parcel).filter(Parcel.parcel_id == parcel_id).first()
    if not p:
        return HTMLResponse("<h3>Property not found</h3>", status_code=404)

    c = (
        session.query(Candidate)
        .filter(Candidate.parcel_id == p.id)
        .order_by(Candidate.score.desc())
        .first()
    )

    zone_label = None
    if p.zone_code and c:
        county_str = p.county.value if p.county else "snohomish"
        zr = session.query(ZoningRule).filter(
            ZoningRule.county == county_str,
            ZoningRule.zone_code == p.zone_code,
        ).first()
        zone_label = zr.notes if zr else None

    coords = session.execute(text("""
        SELECT ST_Y(ST_Centroid(geometry)) as lat, ST_X(ST_Centroid(geometry)) as lng
        FROM parcels WHERE id = :pid
    """), {"pid": str(p.id)}).fetchone()
    lat = float(coords.lat) if coords and coords.lat else None
    lng = float(coords.lng) if coords and coords.lng else None

    encoded_address = quote((p.address or "").strip(), safe="")
    external_links = {
        "nwmls": "https://www.nwmls.com/",
        "zillow": f"https://www.zillow.com/homes/{encoded_address}_rb/" if encoded_address else "https://www.zillow.com/",
        "redfin": f"https://www.redfin.com/search?q={encoded_address}" if encoded_address else "https://www.redfin.com/",
        "snoco_tax": "https://www.snoco.org/proptax/",
        "snoco_tax_hint": f"Search Parcel No: {p.parcel_id}",
    }

    notes = []
    feedback = {"thumbs_up": 0, "thumbs_down": 0}
    if c:
        note_rows = (
            session.query(CandidateNote)
            .filter(CandidateNote.candidate_id == c.id)
            .order_by(CandidateNote.created_at.desc())
            .limit(20)
            .all()
        )
        notes = [{"note": r.note, "author": r.author, "created_at": r.created_at} for r in note_rows]

        fb_row = session.query(
            func.count(CandidateFeedback.id).filter(CandidateFeedback.rating == "up").label("thumbs_up"),
            func.count(CandidateFeedback.id).filter(CandidateFeedback.rating == "down").label("thumbs_down"),
        ).filter(CandidateFeedback.candidate_id == c.id).first()
        feedback = {
            "thumbs_up": int(fb_row.thumbs_up or 0),
            "thumbs_down": int(fb_row.thumbs_down or 0),
        }

    feasibility = session.execute(text("""
        SELECT status, best_layout_id, best_score, result_json, created_at, completed_at
        FROM feasibility_results
        WHERE parcel_id = :pid
        ORDER BY completed_at DESC NULLS LAST, created_at DESC
        LIMIT 1
    """), {"pid": str(p.id)}).mappings().first()

    return templates.TemplateResponse("property.html", {
        "request": request,
        "p": p,
        "c": c,
        "zone_label": zone_label,
        "lat": lat,
        "lng": lng,
        "notes": notes,
        "feedback": feedback,
        "feasibility": dict(feasibility) if feasibility else None,
        "external_links": external_links,
        "fmt_money": fmt_money,
        "fmt_acres": fmt_acres,
        "fmt_sqft": fmt_sqft,
    })


@router.get("/api/candidate/{candidate_id}/bundle")
def get_bundle(candidate_id: str, session: Session = Depends(db)):
    candidate = session.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not candidate:
        return JSONResponse({"error": "not found"}, status_code=404)
    return candidate.bundle_data or {}


@router.post("/api/candidate/{candidate_id}/detect-bundle")
def detect_bundle(candidate_id: str, session: Session = Depends(db)):
    payload = detect_bundle_for_candidate(session, candidate_id)
    if payload is None:
        return JSONResponse({"error": "candidate not found"}, status_code=404)
    return payload
