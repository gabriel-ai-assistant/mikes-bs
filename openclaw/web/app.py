"""Mike's Building System — Web Dashboard."""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path

from typing import List, Optional

from fastapi import FastAPI, Request, Depends, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, text
from sqlalchemy.orm import Session, joinedload

from openclaw.db.session import get_session
from openclaw.db.models import (
    Parcel, Candidate, Lead, ZoningRule,
    ScoreTierEnum, LeadStatusEnum, CountyEnum,
)

BASE_DIR = Path(__file__).resolve().parent
_root_path = os.environ.get("ROOT_PATH", "")

app = FastAPI(title="Mike's Building System", docs_url=None, redoc_url=None, root_path=_root_path)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
templates.env.globals["base_url"] = _root_path


def fmt_money(v):
    return f"${v:,.0f}" if v is not None else "—"

def fmt_acres(v):
    return f"{v/43560:.2f} ac" if v else "—"

def fmt_sqft(v):
    return f"{v:,.0f} sf" if v else "—"


templates.env.filters["money"] = fmt_money
templates.env.filters["acres"] = fmt_acres
templates.env.filters["sqft"] = fmt_sqft


def db():
    s = next(get_session())
    try:
        yield s
    finally:
        s.close()


# ── Dashboard ──────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, session: Session = Depends(db)):
    total_parcels = session.query(func.count(Parcel.id)).scalar() or 0

    tier_counts = dict(
        session.query(Candidate.score_tier, func.count(Candidate.id))
        .group_by(Candidate.score_tier).all()
    )
    tier_a = tier_counts.get(ScoreTierEnum.A, 0)
    tier_b = tier_counts.get(ScoreTierEnum.B, 0)
    tier_c = tier_counts.get(ScoreTierEnum.C, 0)
    tier_d = tier_counts.get(ScoreTierEnum.D, 0)
    tier_e = tier_counts.get(ScoreTierEnum.E, 0)
    tier_f = tier_counts.get(ScoreTierEnum.F, 0)
    total_candidates = tier_a + tier_b + tier_c + tier_d + tier_e + tier_f

    week_ago = datetime.utcnow() - timedelta(days=7)
    new_leads = session.query(func.count(Lead.id)).filter(Lead.created_at >= week_ago).scalar() or 0
    total_leads = session.query(func.count(Lead.id)).scalar() or 0

    # Top 5 candidates for quick view
    top5 = (
        session.query(Candidate)
        .join(Parcel)
        .options(joinedload(Candidate.parcel))
        .filter(Candidate.score_tier == ScoreTierEnum.A)
        .order_by(Candidate.potential_splits.desc())
        .limit(5).all()
    )

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "total_parcels": total_parcels,
        "total_candidates": total_candidates,
        "tier_a": tier_a, "tier_b": tier_b, "tier_c": tier_c,
        "tier_d": tier_d, "tier_e": tier_e, "tier_f": tier_f,
        "new_leads": new_leads,
        "total_leads": total_leads,
        "top5": top5,
        "tier_data_json": json.dumps([tier_a, tier_b, tier_c, tier_d, tier_e, tier_f]),
    })


# ── Candidates ─────────────────────────────────────────────────────────────

@app.get("/candidates", response_class=HTMLResponse)
def candidates_page(
    request: Request,
    search: str = Query("", alias="q"),
    tier: str = Query("", alias="tier"),
    sort: str = Query("splits", alias="sort"),
    wetland: str = Query("", alias="wetland"),
    ag: str = Query("", alias="ag"),
    use_type: str = Query("", alias="use_type"),
    tags: Optional[str] = Query(None, alias="tags"),
    tags_mode: str = Query("any", alias="tags_mode"),
    session: Session = Depends(db),
):
    q = (
        session.query(Candidate)
        .join(Parcel)
        .options(joinedload(Candidate.parcel))
    )
    if search:
        q = q.filter(
            Parcel.address.ilike(f"%{search}%") |
            Parcel.owner_name.ilike(f"%{search}%") |
            Parcel.owner_address.ilike(f"%{search}%")
        )
    if tier in ("A", "B", "C", "D", "E", "F"):
        q = q.filter(Candidate.score_tier == ScoreTierEnum(tier))
    if wetland == "1":
        q = q.filter(Candidate.has_critical_area_overlap == True)
    if ag == "1":
        q = q.filter(Candidate.flagged_for_review == True)
    if use_type:
        q = q.filter(Parcel.present_use.ilike(f"%{use_type}%"))
    if tags:
        tags_list = [t.strip() for t in tags.split(",") if t.strip()]
        if tags_list:
            if tags_mode == "all":
                # ALL tags must be present: each tag = ANY(candidates.tags)
                for _t in tags_list:
                    q = q.filter(text(":_tag = ANY(candidates.tags)").bindparams(_tag=_t))
            else:
                # ANY tag must be present
                from sqlalchemy import or_
                q = q.filter(or_(*[
                    text(f":_tag_{i} = ANY(candidates.tags)").bindparams(**{f"_tag_{i}": _t})
                    for i, _t in enumerate(tags_list)
                ]))

    sort_map = {
        "splits": Candidate.potential_splits.desc(),
        "lot":    Parcel.lot_sf.desc(),
        "value":  Parcel.assessed_value.desc(),
    }
    q = q.order_by(sort_map.get(sort, Candidate.potential_splits.desc()))
    rows = q.limit(500).all()

    # Load zone labels from zoning_rules
    zone_labels = dict(
        session.query(ZoningRule.zone_code, ZoningRule.notes)
        .filter(ZoningRule.county == "snohomish").all()
    )

    return templates.TemplateResponse("candidates.html", {
        "request": request,
        "candidates": rows,
        "zone_labels": zone_labels,
        "search": search, "tier": tier, "sort": sort,
        "wetland": wetland, "ag": ag,
        "use_type": use_type,
        "tags": tags or "", "tags_mode": tags_mode,
    })



@app.get("/api/tags")
def get_all_tags(session: Session = Depends(db)):
    """Return all distinct tags used across candidates with counts."""
    rows = session.execute(text("""
        SELECT DISTINCT unnest(tags) as tag, count(*) as cnt
        FROM candidates
        WHERE tags IS NOT NULL
        GROUP BY tag ORDER BY cnt DESC
    """)).mappings().all()
    return [{"tag": r["tag"], "count": r["cnt"]} for r in rows]


@app.get("/api/candidates")
def get_candidates_api(
    search: str = Query("", alias="q"),
    tier: str = Query("", alias="tier"),
    sort: str = Query("splits", alias="sort"),
    wetland: str = Query("", alias="wetland"),
    ag: str = Query("", alias="ag"),
    use_type: str = Query("", alias="use_type"),
    tags: Optional[str] = Query(None, alias="tags"),
    tags_mode: str = Query("any", alias="tags_mode"),
    limit: int = Query(500),
    offset: int = Query(0),
    session: Session = Depends(db),
):
    """JSON API for candidates with optional tag filtering."""
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
            Parcel.address.ilike(f"%{search}%") |
            Parcel.owner_name.ilike(f"%{search}%") |
            Parcel.owner_address.ilike(f"%{search}%")
        )
    if tier in ("A", "B", "C", "D", "E", "F"):
        q = q.filter(Candidate.score_tier == ScoreTierEnum(tier))
    if wetland == "1":
        q = q.filter(Candidate.has_critical_area_overlap == True)
    if ag == "1":
        q = q.filter(Candidate.flagged_for_review == True)
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
    q = q.order_by(sort_map.get(sort, Candidate.potential_splits.desc()))
    rows = q.offset(offset).limit(limit).all()
    return {
        "total": total,
        "count": len(rows),
        "candidates": [
            {
                "id": str(c.id),
                "parcel_id": c.parcel.parcel_id,
                "address": c.parcel.address,
                "owner": c.parcel.owner_name,
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
                "lat": float(lat) if lat is not None else None,
                "lng": float(lng) if lng is not None else None,
            }
            for c, lat, lng in rows
        ]
    }


@app.get("/api/use-types")
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


# ── Candidate detail API ───────────────────────────────────────────────────

@app.get("/api/candidate/{candidate_id}")
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
            ZoningRule.zone_code == p.zone_code
        ).first()
        zone_label = zr.notes if zr else p.zone_code

    # Fetch centroid coordinates
    coords = session.execute(text("""
        SELECT ST_Y(ST_Centroid(geometry)) as lat, ST_X(ST_Centroid(geometry)) as lng
        FROM parcels WHERE id = :pid
    """), {"pid": str(c.parcel_id)}).fetchone()
    lat = float(coords.lat) if coords and coords.lat else None
    lng = float(coords.lng) if coords and coords.lng else None
    reason_codes = c.reason_codes or []

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
        "owner_name": p.owner_name,
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
            "feasible_splits": next(
                (int(r.split("_")[-1]) for r in reason_codes if r.startswith("SUBDIV_FEASIBLE_SPLITS_")),
                None,
            ),
            "plat_type": next(
                (r.split("SUBDIV_PLAT_TYPE_")[1] for r in reason_codes if r.startswith("SUBDIV_PLAT_TYPE_")),
                None,
            ),
            "sewer": "SEWER_AVAILABLE" in reason_codes,
            "access": "ACCESS_CONFIRMED" in reason_codes,
        },
        "lat": lat,
        "lng": lng,
    }


# ── Candidate Feedback ────────────────────────────────────────────────────

@app.post("/api/candidate/{candidate_id}/feedback")
async def submit_feedback(
    candidate_id: str,
    request: Request,
    rating: Optional[str] = Query(None),  # backward compatibility: 'up' or 'down'
    category: str = Query(""),
    notes: str = Query(""),
    session: Session = Depends(db),
):
    from sqlalchemy import text as sqlt

    def tier_for_score(score: int) -> ScoreTierEnum:
        if score >= 85:
            return ScoreTierEnum.A
        if score >= 70:
            return ScoreTierEnum.B
        if score >= 50:
            return ScoreTierEnum.C
        if score >= 35:
            return ScoreTierEnum.D
        if score >= 20:
            return ScoreTierEnum.E
        return ScoreTierEnum.F

    payload = {}
    try:
        payload = await request.json()
    except Exception:
        payload = {}

    feedback_type = payload.get("feedback_type")
    if feedback_type in ("thumbs_up", "thumbs_down"):
        rating_value = "up" if feedback_type == "thumbs_up" else "down"
    elif rating in ("up", "down"):
        rating_value = rating
        feedback_type = "thumbs_up" if rating == "up" else "thumbs_down"
    else:
        return JSONResponse({"error": "invalid feedback_type"}, status_code=400)

    category_value = (payload.get("category") or category or "").strip()
    notes_value = (payload.get("notes") or notes or "").strip()

    session.execute(sqlt("""
        INSERT INTO candidate_feedback (candidate_id, rating, category, notes)
        VALUES (:cid, :rating, :cat, :notes)
    """), {
        "cid": candidate_id,
        "rating": rating_value,
        "cat": category_value or None,
        "notes": notes_value or None,
    })

    candidate = session.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not candidate:
        session.rollback()
        return JSONResponse({"error": "candidate not found"}, status_code=404)

    current_score = int(candidate.score or 0)
    if feedback_type == "thumbs_down":
        current_score = max(0, current_score - 40)
        candidate.score = current_score
        candidate.score_tier = tier_for_score(current_score)

    tier = candidate.score_tier.value if candidate.score_tier else tier_for_score(current_score).value
    session.commit()
    return {"ok": True, "new_score": current_score, "new_tier": tier}


@app.get("/api/candidate/{candidate_id}/feedback")
def get_feedback(candidate_id: str, session: Session = Depends(db)):
    from sqlalchemy import text as sqlt
    row = session.execute(sqlt("""
        SELECT
            COUNT(*) FILTER (WHERE rating='up') as thumbs_up,
            COUNT(*) FILTER (WHERE rating='down') as thumbs_down
        FROM candidate_feedback
        WHERE candidate_id = :cid
    """), {"cid": candidate_id}).fetchone()
    return {
        "thumbs_up": int(row.thumbs_up or 0),
        "thumbs_down": int(row.thumbs_down or 0),
    }


@app.get("/api/feedback/stats")
def feedback_stats(session: Session = Depends(db)):
    from sqlalchemy import text as sqlt
    rows = session.execute(sqlt("""
        SELECT rating, category, count(*) as cnt
        FROM candidate_feedback
        GROUP BY rating, category
        ORDER BY cnt DESC
    """)).mappings().all()
    return [dict(r) for r in rows]


# ── Candidate Notes ────────────────────────────────────────────────────────

@app.post("/api/candidate/{candidate_id}/notes")
async def add_note(candidate_id: str, request: Request, session: Session = Depends(db)):
    from sqlalchemy import text as sqlt
    data = await request.json()
    note_text = data.get("note", "").strip()
    if not note_text:
        return JSONResponse({"error": "note is required"}, status_code=400)
    author = data.get("author", "user")
    session.execute(sqlt("""
        INSERT INTO candidate_notes (candidate_id, note, author)
        VALUES (:cid, :note, :author)
    """), {"cid": candidate_id, "note": note_text, "author": author})
    session.commit()
    return {"ok": True}


@app.get("/api/candidate/{candidate_id}/notes")
def get_notes(candidate_id: str, limit: int = Query(10), session: Session = Depends(db)):
    from sqlalchemy import text as sqlt
    rows = session.execute(sqlt("""
        SELECT id, note, author, created_at
        FROM candidate_notes
        WHERE candidate_id = :cid
        ORDER BY created_at DESC
        LIMIT :lim
    """), {"cid": candidate_id, "lim": limit}).mappings().all()
    return [
        {
            "id": r["id"],
            "note": r["note"],
            "author": r["author"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        }
        for r in rows
    ]


# ── Property Detail Page ──────────────────────────────────────────────────

@app.get("/property/{parcel_id}", response_class=HTMLResponse)
def property_detail(parcel_id: str, request: Request, session: Session = Depends(db)):
    p = session.query(Parcel).filter(Parcel.parcel_id == parcel_id).first()
    if not p:
        return HTMLResponse("<h3>Property not found</h3>", status_code=404)

    # Get best candidate for this parcel
    c = (
        session.query(Candidate)
        .filter(Candidate.parcel_id == p.id)
        .order_by(Candidate.score.desc())
        .first()
    )

    # Get zone label
    zone_label = None
    if p.zone_code and c:
        county_str = p.county.value if p.county else "snohomish"
        zr = session.query(ZoningRule).filter(
            ZoningRule.county == county_str,
            ZoningRule.zone_code == p.zone_code
        ).first()
        zone_label = zr.notes if zr else None

    # Get centroid coordinates
    coords = session.execute(text("""
        SELECT ST_Y(ST_Centroid(geometry)) as lat, ST_X(ST_Centroid(geometry)) as lng
        FROM parcels WHERE id = :pid
    """), {"pid": str(p.id)}).fetchone()
    lat = float(coords.lat) if coords and coords.lat else None
    lng = float(coords.lng) if coords and coords.lng else None

    # Get notes and feedback if we have a candidate
    notes = []
    feedback = {"thumbs_up": 0, "thumbs_down": 0}
    if c:
        note_rows = session.execute(text("""
            SELECT note, author, created_at FROM candidate_notes
            WHERE candidate_id = :cid ORDER BY created_at DESC LIMIT 20
        """), {"cid": str(c.id)}).mappings().all()
        notes = [dict(r) for r in note_rows]

        fb_row = session.execute(text("""
            SELECT
                COUNT(*) FILTER (WHERE rating='up') as thumbs_up,
                COUNT(*) FILTER (WHERE rating='down') as thumbs_down
            FROM candidate_feedback WHERE candidate_id = :cid
        """), {"cid": str(c.id)}).fetchone()
        feedback = {
            "thumbs_up": int(fb_row.thumbs_up or 0),
            "thumbs_down": int(fb_row.thumbs_down or 0),
        }

    return templates.TemplateResponse("property.html", {
        "request": request,
        "p": p,
        "c": c,
        "zone_label": zone_label,
        "lat": lat,
        "lng": lng,
        "notes": notes,
        "feedback": feedback,
        "fmt_money": fmt_money,
        "fmt_acres": fmt_acres,
        "fmt_sqft": fmt_sqft,
    })


# ── Leads ──────────────────────────────────────────────────────────────────

@app.get("/leads", response_class=HTMLResponse)
def leads_page(request: Request, session: Session = Depends(db)):
    leads = (
        session.query(Lead)
        .options(joinedload(Lead.candidate).joinedload(Candidate.parcel))
        .order_by(Lead.updated_at.desc())
        .limit(500).all()
    )
    columns = {s: [] for s in LeadStatusEnum}
    for lead in leads:
        columns.setdefault(lead.status, []).append(lead)

    return templates.TemplateResponse("leads.html", {
        "request": request,
        "columns": columns,
        "statuses": LeadStatusEnum,
    })


@app.post("/api/lead/{lead_id}/status")
def update_lead_status(lead_id: str, status: str = Query(...), session: Session = Depends(db)):
    lead = session.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        return JSONResponse({"error": "not found"}, status_code=404)
    try:
        lead.status = LeadStatusEnum(status)
    except ValueError:
        return JSONResponse({"error": "invalid status"}, status_code=400)
    session.commit()
    return {"ok": True}


# ── Map ────────────────────────────────────────────────────────────────────

@app.get("/map", response_class=HTMLResponse)
def map_page(request: Request):
    return templates.TemplateResponse("map.html", {"request": request})


@app.get("/api/map/points")
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
            q = q.filter(Candidate.flagged_for_review == True)

        # Prioritise A then B, cap at 3000
        q = q.order_by(Candidate.score_tier, Candidate.potential_splits.desc()).limit(3000)
        rows = q.all()

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

    # Fallback: raw parcels
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
            "id": r["id"], "parcel_id": r["parcel_id"], "tier": "parcel",
            "score": None,
            "address": r["address"] or "No address",
            "owner": r["owner_name"] or "Unknown",
            "splits": None, "lot_sf": r["lot_sf"],
            "zone": r["zone_code"], "value": r["assessed_value"],
            "wetland": False, "ag": False,
            "lat": float(r["lat"]), "lng": float(r["lng"]),
        }
        for r in rows
        if r["lat"] is not None
    ]


# ── Settings ───────────────────────────────────────────────────────────────

@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request):
    return templates.TemplateResponse("settings.html", {"request": request})


# ── Scoring Rules API ─────────────────────────────────────────────────────

@app.get("/api/rules")
def get_rules(session: Session = Depends(db)):
    from sqlalchemy import text as sqlt
    rows = session.execute(sqlt("""
        SELECT id, name, field, operator, value, action, tier, score_adj, priority, active
        FROM scoring_rules ORDER BY priority ASC, created_at ASC
    """)).mappings().all()
    return [dict(r) for r in rows]

@app.post("/api/rules")
async def create_rule(request: Request, session: Session = Depends(db)):
    from sqlalchemy import text as sqlt
    data = await request.json()
    session.execute(sqlt("""
        INSERT INTO scoring_rules (name, field, operator, value, action, tier, score_adj, priority)
        VALUES (:name, :field, :operator, :value, :action, :tier, :score_adj, :priority)
    """), {
        'name': data['name'], 'field': data['field'],
        'operator': data['operator'], 'value': data['value'],
        'action': data['action'],
        'tier': data.get('tier') or None,
        'score_adj': int(data.get('score_adj') or 0),
        'priority': int(data.get('priority') or 100),
    })
    session.commit()
    return {"ok": True}

@app.put("/api/rules/{rule_id}")
async def update_rule(rule_id: str, request: Request, session: Session = Depends(db)):
    from sqlalchemy import text as sqlt
    data = await request.json()
    session.execute(sqlt("""
        UPDATE scoring_rules SET
            name=:name, field=:field, operator=:operator, value=:value,
            action=:action, tier=:tier, score_adj=:score_adj,
            priority=:priority, active=:active
        WHERE id=:id
    """), {**data, 'id': rule_id,
          'tier': data.get('tier') or None,
          'score_adj': int(data.get('score_adj') or 0),
          'active': data.get('active', True)})
    session.commit()
    return {"ok": True}

@app.delete("/api/rules/{rule_id}")
def delete_rule(rule_id: str, session: Session = Depends(db)):
    from sqlalchemy import text as sqlt
    session.execute(sqlt("DELETE FROM scoring_rules WHERE id=:id"), {'id': rule_id})
    session.commit()
    return {"ok": True}

@app.patch("/api/rules/{rule_id}/toggle")
def toggle_rule(rule_id: str, session: Session = Depends(db)):
    from sqlalchemy import text as sqlt
    session.execute(sqlt("""
        UPDATE scoring_rules SET active = NOT active WHERE id=:id
    """), {'id': rule_id})
    session.commit()
    return {"ok": True}

@app.post("/api/rescore")
def rescore(session: Session = Depends(db)):
    """Re-score all candidates with current rule set."""
    from openclaw.analysis.rule_engine import rescore_all
    result = rescore_all()
    return result

@app.get("/api/rescore/preview")
def rescore_preview(session: Session = Depends(db)):
    """Preview what re-scoring would produce without committing."""
    from openclaw.analysis.rule_engine import load_rules, evaluate_candidate
    from sqlalchemy import text as sqlt
    rules = load_rules(session)
    rows = session.execute(sqlt("""
        SELECT c.id, c.potential_splits, c.has_critical_area_overlap, c.flagged_for_review,
               p.present_use, p.owner_name, p.zone_code, p.lot_sf, p.assessed_value,
               p.improvement_value, p.total_value
        FROM candidates c JOIN parcels p ON c.parcel_id = p.id
    """)).mappings().all()

    preview = {t: 0 for t in 'ABCDEF'}
    excluded = 0
    for row in rows:
        tier, score, excl, _tags, _reasons = evaluate_candidate(dict(row), rules)
        if excl:
            excluded += 1
        else:
            preview[tier] = preview.get(tier, 0) + 1
    return {'preview': preview, 'excluded': excluded, 'rules_active': len(rules)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("openclaw.web.app:app", host="0.0.0.0", port=8470, reload=True)

# ──────────────────────────────────────────────────────────────
# Learning — /learning review page + API endpoints
# ──────────────────────────────────────────────────────────────

@app.get('/learning', response_class=HTMLResponse)
def learning_page(request: Request, session: Session = Depends(db)):
    """Show pending AI proposals for human review."""
    from sqlalchemy import text as sqlt
    proposals = session.execute(sqlt("""
        SELECT * FROM learning_proposals
        WHERE status = 'pending'
        ORDER BY
            CASE confidence WHEN 'HIGH' THEN 1 WHEN 'MEDIUM' THEN 2 ELSE 3 END,
            run_date DESC
    """)).mappings().all()

    history = session.execute(sqlt("""
        SELECT * FROM learning_proposals
        WHERE status != 'pending'
        ORDER BY reviewed_at DESC
        LIMIT 20
    """)).mappings().all()

    return templates.TemplateResponse('learning.html', {
        'request':   request,
        'proposals': [dict(p) for p in proposals],
        'history':   [dict(h) for h in history],
    })


@app.post('/api/learning/run-now')
def run_learning_now(session: Session = Depends(db)):
    """Trigger the nightly learning run synchronously (for manual use from Settings)."""
    from openclaw.learning.analyzer import run_nightly_learning
    count = run_nightly_learning(session=session)
    return {'ok': True, 'proposals_generated': count}


@app.post('/api/learning/{proposal_id}/approve')
def approve_proposal(proposal_id: int, session: Session = Depends(db)):
    from sqlalchemy import text as sqlt
    session.execute(sqlt("""
        UPDATE learning_proposals
        SET status = 'approved', reviewed_at = NOW()
        WHERE id = :id
    """), {'id': proposal_id})
    session.commit()
    return {'ok': True}


@app.post('/api/learning/{proposal_id}/reject')
def reject_proposal(proposal_id: int, session: Session = Depends(db)):
    from sqlalchemy import text as sqlt
    session.execute(sqlt("""
        UPDATE learning_proposals
        SET status = 'rejected', reviewed_at = NOW()
        WHERE id = :id
    """), {'id': proposal_id})
    session.commit()
    return {'ok': True}
