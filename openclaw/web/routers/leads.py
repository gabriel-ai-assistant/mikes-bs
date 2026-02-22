"""Lead routes."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session, joinedload

from openclaw.config import settings
from openclaw.db.models import (
    Candidate,
    ContactMethodEnum,
    ContactOutcomeEnum,
    EnrichmentResult,
    Lead,
    LeadContactLog,
)
from openclaw.enrich.pipeline import run_lead_enrichment
from openclaw.web.common import LEAD_STATUSES, db, templates

router = APIRouter()


STATUS_LABELS = {
    "new": "New",
    "researching": "Researching",
    "contacted": "Contacted",
    "negotiating": "Negotiating",
    "closed_won": "Closed Won",
    "closed_lost": "Closed Lost",
    "dead": "Dead",
}


def _parse_user_id(request: Request) -> int | None:
    raw = request.cookies.get("user_id")
    if not raw:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _osint_ui_link(lead: Lead) -> str | None:
    if not lead.osint_investigation_id:
        return None
    base = (settings.OSINT_UI_URL or "").strip().rstrip("/")
    if not base:
        return None
    return f"{base}/investigations/{lead.osint_investigation_id}"


@router.get("/leads", response_class=HTMLResponse)
def leads_page(request: Request, session: Session = Depends(db)):
    leads = (
        session.query(Lead)
        .options(
            joinedload(Lead.candidate).joinedload(Candidate.parcel),
            joinedload(Lead.promoted_by_user),
        )
        .order_by(Lead.updated_at.desc())
        .limit(500)
        .all()
    )
    columns = {s: [] for s in LEAD_STATUSES}
    for lead in leads:
        columns.setdefault(lead.status, []).append(lead)

    return templates.TemplateResponse(
        "leads.html",
        {
            "request": request,
            "columns": columns,
            "statuses": LEAD_STATUSES,
            "status_labels": STATUS_LABELS,
        },
    )


@router.get("/leads/{lead_id}", response_class=HTMLResponse)
def lead_detail_page(lead_id: str, request: Request, session: Session = Depends(db)):
    lead = (
        session.query(Lead)
        .options(
            joinedload(Lead.candidate).joinedload(Candidate.parcel),
            joinedload(Lead.promoted_by_user),
            joinedload(Lead.enrichment_results),
            joinedload(Lead.contact_log_entries).joinedload(LeadContactLog.user),
        )
        .filter(Lead.id == lead_id)
        .first()
    )
    if not lead:
        return HTMLResponse("<h3>Lead not found</h3>", status_code=404)

    grouped: dict[str, list[EnrichmentResult]] = defaultdict(list)
    for row in sorted(lead.enrichment_results, key=lambda r: r.fetched_at or datetime.min, reverse=True):
        grouped[row.provider].append(row)

    contact_entries = sorted(lead.contact_log_entries, key=lambda r: r.contacted_at or datetime.min, reverse=True)

    return templates.TemplateResponse(
        "lead_detail.html",
        {
            "request": request,
            "lead": lead,
            "status_labels": STATUS_LABELS,
            "statuses": LEAD_STATUSES,
            "grouped_enrichment": dict(grouped),
            "contact_entries": contact_entries,
            "method_values": [m.value for m in ContactMethodEnum],
            "outcome_values": [o.value for o in ContactOutcomeEnum],
            "osint_ui_link": _osint_ui_link(lead),
        },
    )


@router.post("/api/leads")
async def promote_to_lead(request: Request, background_tasks: BackgroundTasks, session: Session = Depends(db)):
    body = await request.json()
    candidate_id = (body.get("candidate_id") or "").strip()
    reason = (body.get("reason") or "").strip()
    notes = (body.get("notes") or "").strip() or None

    if not candidate_id:
        return JSONResponse({"error": "candidate_id is required"}, status_code=400)

    candidate = (
        session.query(Candidate)
        .options(joinedload(Candidate.parcel))
        .filter(Candidate.id == candidate_id)
        .first()
    )
    if not candidate:
        return JSONResponse({"error": "candidate not found"}, status_code=404)

    existing = (
        session.query(Lead)
        .filter(Lead.candidate_id == candidate.id)
        .filter(Lead.status.notin_(["dead", "closed_lost"]))
        .order_by(Lead.updated_at.desc())
        .first()
    )
    if existing:
        return JSONResponse(
            {
                "error": "lead already exists for candidate",
                "lead_id": str(existing.id),
                "status": existing.status,
            },
            status_code=409,
        )

    parcel = candidate.parcel
    owner_snapshot = {
        "name": parcel.owner_name if parcel else None,
        "mailing_address": parcel.owner_address if parcel else None,
    }
    user_id = _parse_user_id(request)
    now = datetime.utcnow()

    lead = Lead(
        candidate_id=candidate.id,
        status="new",
        owner_snapshot=owner_snapshot,
        reason=reason or None,
        notes=notes,
        score_at_promotion=candidate.score,
        bundle_snapshot=candidate.bundle_data,
        promoted_by=user_id,
        promoted_at=now,
    )
    session.add(lead)
    session.commit()
    session.refresh(lead)

    background_tasks.add_task(run_lead_enrichment, str(lead.id), user_id, None)

    return {
        "ok": True,
        "lead_id": str(lead.id),
        "lead_detail_url": f"/leads/{lead.id}",
    }


@router.post("/api/leads/{lead_id}/enrich")
async def enrich_lead(lead_id: str, request: Request, background_tasks: BackgroundTasks, session: Session = Depends(db)):
    lead = session.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        return JSONResponse({"error": "not found"}, status_code=404)

    provider = None
    if request.headers.get("content-type", "").startswith("application/json"):
        body = await request.json()
        provider = (body.get("provider") or "").strip() or None
    user_id = _parse_user_id(request)
    background_tasks.add_task(run_lead_enrichment, str(lead.id), user_id, provider)
    return {"ok": True, "queued": True, "provider": provider}


@router.delete("/api/leads/{lead_id}/enrichment")
def delete_lead_enrichment(lead_id: str, session: Session = Depends(db)):
    lead = session.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        return JSONResponse({"error": "not found"}, status_code=404)

    deleted = session.query(EnrichmentResult).filter(EnrichmentResult.lead_id == lead.id).delete(synchronize_session=False)
    lead.osint_investigation_id = None
    lead.osint_status = None
    lead.osint_queried_at = None
    lead.osint_summary = None
    session.add(lead)
    session.commit()
    return {"ok": True, "deleted": int(deleted)}


@router.post("/api/leads/{lead_id}/contact-log")
async def add_contact_log(lead_id: str, request: Request, session: Session = Depends(db)):
    lead = session.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        return JSONResponse({"error": "not found"}, status_code=404)

    user_id = _parse_user_id(request)
    if not user_id:
        return JSONResponse({"error": "unauthenticated"}, status_code=401)

    body = await request.json()
    method = (body.get("method") or "").strip()
    outcome = (body.get("outcome") or "").strip()
    notes = (body.get("notes") or "").strip() or None
    contacted_at_raw = (body.get("contacted_at") or "").strip()

    valid_methods = {m.value for m in ContactMethodEnum}
    valid_outcomes = {o.value for o in ContactOutcomeEnum}
    if method not in valid_methods:
        return JSONResponse({"error": "invalid method"}, status_code=400)
    if outcome not in valid_outcomes:
        return JSONResponse({"error": "invalid outcome"}, status_code=400)

    contacted_at = datetime.utcnow()
    if contacted_at_raw:
        try:
            contacted_at = datetime.fromisoformat(contacted_at_raw)
        except ValueError:
            return JSONResponse({"error": "invalid contacted_at"}, status_code=400)

    row = LeadContactLog(
        lead_id=lead.id,
        user_id=user_id,
        method=method,
        outcome=outcome,
        notes=notes,
        contacted_at=contacted_at,
    )
    session.add(row)
    lead.contacted_at = contacted_at
    lead.contact_method = method
    lead.outcome = outcome
    session.add(lead)
    session.commit()
    session.refresh(row)

    return {
        "ok": True,
        "entry": {
            "id": row.id,
            "method": row.method.value if hasattr(row.method, "value") else str(row.method),
            "outcome": row.outcome.value if hasattr(row.outcome, "value") else str(row.outcome),
            "notes": row.notes,
            "contacted_at": row.contacted_at.isoformat() if row.contacted_at else None,
            "username": row.user.username if row.user else None,
        },
    }


@router.get("/api/leads/{lead_id}/contact-log")
def list_contact_log(lead_id: str, session: Session = Depends(db)):
    lead = session.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        return JSONResponse({"error": "not found"}, status_code=404)

    rows = (
        session.query(LeadContactLog)
        .options(joinedload(LeadContactLog.user))
        .filter(LeadContactLog.lead_id == lead.id)
        .order_by(LeadContactLog.contacted_at.desc())
        .limit(200)
        .all()
    )
    return [
        {
            "id": row.id,
            "method": row.method.value if hasattr(row.method, "value") else str(row.method),
            "outcome": row.outcome.value if hasattr(row.outcome, "value") else str(row.outcome),
            "notes": row.notes,
            "contacted_at": row.contacted_at.isoformat() if row.contacted_at else None,
            "username": row.user.username if row.user else None,
        }
        for row in rows
    ]


@router.post("/api/lead/{lead_id}/status")
def update_lead_status(lead_id: str, status: str = Query(...), session: Session = Depends(db)):
    lead = session.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        return JSONResponse({"error": "not found"}, status_code=404)
    if status not in LEAD_STATUSES:
        return JSONResponse({"error": "invalid status"}, status_code=400)

    lead.status = status
    session.add(lead)
    session.commit()
    return {"ok": True}
