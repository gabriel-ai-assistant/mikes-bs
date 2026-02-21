"""Mike's Building System — Web Dashboard."""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path

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
    total_candidates = tier_a + tier_b + tier_c

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
        "new_leads": new_leads,
        "total_leads": total_leads,
        "top5": top5,
        "tier_data_json": json.dumps([tier_a, tier_b, tier_c]),
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
    if tier in ("A", "B", "C"):
        q = q.filter(Candidate.score_tier == ScoreTierEnum(tier))
    if wetland == "1":
        q = q.filter(Candidate.has_critical_area_overlap == True)
    if ag == "1":
        q = q.filter(Candidate.flagged_for_review == True)

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
    })


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

    return {
        "id": str(c.id),
        "tier": c.score_tier.value if c.score_tier else None,
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
        "land_value": c.estimated_land_value,
        "profit": c.estimated_profit,
        "margin_pct": c.estimated_margin_pct,
        "wetland_flag": c.has_critical_area_overlap,
        "ag_flag": c.flagged_for_review,
        "shoreline_flag": c.has_shoreline_overlap,
    }


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
            Candidate.potential_splits,
            Candidate.has_critical_area_overlap,
            Candidate.flagged_for_review,
            Parcel.address,
            Parcel.owner_name,
            Parcel.lot_sf,
            Parcel.zone_code,
            Parcel.assessed_value,
            func.ST_Y(func.ST_Centroid(Parcel.geometry)).label("lat"),
            func.ST_X(func.ST_Centroid(Parcel.geometry)).label("lng"),
        ).join(Parcel).filter(Parcel.geometry.isnot(None))

        if tier in ("A", "B", "C"):
            q = q.filter(Candidate.score_tier == ScoreTierEnum(tier))
        if ag_only:
            q = q.filter(Candidate.flagged_for_review == True)

        # Prioritise A then B, cap at 3000
        q = q.order_by(Candidate.score_tier, Candidate.potential_splits.desc()).limit(3000)
        rows = q.all()

        return [
            {
                "id": str(r.id),
                "tier": r.score_tier.value if r.score_tier else "C",
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
        SELECT p.id::text, p.address, p.owner_name, p.lot_sf, p.assessed_value,
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
            "id": r["id"], "tier": "parcel",
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("openclaw.web.app:app", host="0.0.0.0", port=8470, reload=True)
