"""Mike's Building System — Web Dashboard."""

import json
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, Request, Depends, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, case, text
from sqlalchemy.orm import Session, joinedload

from openclaw.db.session import get_session
from openclaw.db.models import Parcel, Candidate, Lead, ScoreTierEnum, LeadStatusEnum, CountyEnum

BASE_DIR = Path(__file__).resolve().parent

import os
_root_path = os.environ.get("ROOT_PATH", "")
app = FastAPI(title="Mike's Building System", docs_url=None, redoc_url=None, root_path=_root_path)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
templates.env.globals["base_url"] = _root_path


def fmt_money(value):
    if value is None:
        return "—"
    return f"${value:,.0f}"


def fmt_pct(value):
    if value is None:
        return "—"
    return f"{value:.1f}%"


templates.env.filters["money"] = fmt_money
templates.env.filters["pct"] = fmt_pct


def db():
    session = next(get_session())
    try:
        yield session
    finally:
        session.close()


# ── Dashboard ────────────────────────────────────────────────────────────────

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
    new_leads_week = session.query(func.count(Lead.id)).filter(Lead.created_at >= week_ago).scalar() or 0

    county_counts = dict(
        session.query(Parcel.county, func.count(Parcel.id))
        .join(Candidate, Candidate.parcel_id == Parcel.id)
        .group_by(Parcel.county).all()
    )
    counties = [c.value.title() for c in CountyEnum]
    county_data = [county_counts.get(c, 0) for c in CountyEnum]

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "total_parcels": total_parcels,
        "total_candidates": total_candidates,
        "tier_a": tier_a, "tier_b": tier_b, "tier_c": tier_c,
        "new_leads_week": new_leads_week,
        "counties_json": json.dumps(counties),
        "county_data_json": json.dumps(county_data),
        "tier_data_json": json.dumps([tier_a, tier_b, tier_c]),
    })


# ── Candidates ───────────────────────────────────────────────────────────────

@app.get("/candidates", response_class=HTMLResponse)
def candidates_page(
    request: Request,
    search: str = Query("", alias="q"),
    tier: str = Query("", alias="tier"),
    county: str = Query("", alias="county"),
    sort: str = Query("profit", alias="sort"),
    session: Session = Depends(db),
):
    q = (
        session.query(Candidate)
        .join(Parcel)
        .options(joinedload(Candidate.parcel))
    )
    if search:
        q = q.filter(Parcel.address.ilike(f"%{search}%"))
    if tier and tier in ("A", "B", "C"):
        q = q.filter(Candidate.score_tier == ScoreTierEnum(tier))
    if county and county in [c.value for c in CountyEnum]:
        q = q.filter(Parcel.county == CountyEnum(county))

    sort_map = {
        "profit": Candidate.estimated_profit.desc().nulls_last(),
        "margin": Candidate.estimated_margin_pct.desc().nulls_last(),
        "lot": Parcel.lot_sf.desc().nulls_last(),
        "splits": Candidate.potential_splits.desc().nulls_last(),
    }
    q = q.order_by(sort_map.get(sort, Candidate.estimated_profit.desc().nulls_last()))
    rows = q.limit(500).all()

    return templates.TemplateResponse("candidates.html", {
        "request": request,
        "candidates": rows,
        "search": search, "tier": tier, "county": county, "sort": sort,
    })


# ── Candidate detail (JSON for modal) ───────────────────────────────────────

@app.get("/api/candidate/{candidate_id}")
def candidate_detail(candidate_id: str, session: Session = Depends(db)):
    c = session.query(Candidate).options(joinedload(Candidate.parcel)).filter(Candidate.id == candidate_id).first()
    if not c:
        return JSONResponse({"error": "not found"}, 404)
    return {
        "id": str(c.id),
        "tier": c.score_tier.value if c.score_tier else None,
        "address": c.parcel.address,
        "county": c.parcel.county.value.title() if c.parcel.county else None,
        "lot_sf": c.parcel.lot_sf,
        "zone_code": c.parcel.zone_code,
        "owner_name": c.parcel.owner_name,
        "assessed_value": c.parcel.assessed_value,
        "splits": c.potential_splits,
        "land_value": c.estimated_land_value,
        "dev_cost": c.estimated_dev_cost,
        "build_cost": c.estimated_build_cost,
        "arv": c.estimated_arv,
        "profit": c.estimated_profit,
        "margin_pct": c.estimated_margin_pct,
        "critical_area": c.has_critical_area_overlap,
        "shoreline": c.has_shoreline_overlap,
    }


# ── Leads ────────────────────────────────────────────────────────────────────

@app.get("/leads", response_class=HTMLResponse)
def leads_page(request: Request, session: Session = Depends(db)):
    leads = (
        session.query(Lead)
        .options(joinedload(Lead.candidate).joinedload(Candidate.parcel))
        .order_by(Lead.updated_at.desc().nulls_last())
        .limit(500)
        .all()
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
        return JSONResponse({"error": "not found"}, 404)
    try:
        lead.status = LeadStatusEnum(status)
    except ValueError:
        return JSONResponse({"error": "invalid status"}, 400)
    session.commit()
    return {"ok": True}


# ── Map ──────────────────────────────────────────────────────────────────────

@app.get("/map", response_class=HTMLResponse)
def map_page(request: Request):
    return templates.TemplateResponse("map.html", {"request": request})


@app.get("/api/map/points")
def map_points(session: Session = Depends(db)):
    rows = (
        session.query(
            Candidate.id,
            Candidate.score_tier,
            Candidate.estimated_profit,
            Candidate.potential_splits,
            Parcel.address,
            func.ST_Y(func.ST_Centroid(Parcel.geometry)).label("lat"),
            func.ST_X(func.ST_Centroid(Parcel.geometry)).label("lng"),
        )
        .join(Parcel)
        .filter(Parcel.geometry.isnot(None))
        .limit(2000)
        .all()
    )
    features = []
    for r in rows:
        if r.lat is None or r.lng is None:
            continue
        features.append({
            "id": str(r.id),
            "tier": r.score_tier.value if r.score_tier else "C",
            "address": r.address or "Unknown",
            "profit": r.estimated_profit,
            "splits": r.potential_splits,
            "lat": float(r.lat),
            "lng": float(r.lng),
        })
    return features


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("openclaw.web.app:app", host="0.0.0.0", port=8470, reload=True)
