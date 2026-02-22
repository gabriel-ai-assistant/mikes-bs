"""Lead routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session, joinedload

from openclaw.db.models import Candidate, Lead
from openclaw.web.common import LEAD_STATUSES, db, templates

router = APIRouter()


@router.get("/leads", response_class=HTMLResponse)
def leads_page(request: Request, session: Session = Depends(db)):
    leads = (
        session.query(Lead)
        .options(joinedload(Lead.candidate).joinedload(Candidate.parcel))
        .order_by(Lead.updated_at.desc())
        .limit(500)
        .all()
    )
    columns = {s: [] for s in LEAD_STATUSES}
    for lead in leads:
        columns.setdefault(lead.status, []).append(lead)

    return templates.TemplateResponse("leads.html", {
        "request": request,
        "columns": columns,
        "statuses": LEAD_STATUSES,
    })


@router.post("/api/lead/{lead_id}/status")
def update_lead_status(lead_id: str, status: str = Query(...), session: Session = Depends(db)):
    lead = session.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        return JSONResponse({"error": "not found"}, status_code=404)
    if status not in LEAD_STATUSES:
        return JSONResponse({"error": "invalid status"}, status_code=400)

    lead.status = status
    session.commit()
    return {"ok": True}
