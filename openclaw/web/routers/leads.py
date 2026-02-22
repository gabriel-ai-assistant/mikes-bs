"""Lead routes."""

from __future__ import annotations

import csv
import io
from collections import defaultdict
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from sqlalchemy.orm import Session, joinedload

from openclaw.config import settings
from openclaw.db.models import (
    Candidate,
    ContactMethodEnum,
    ContactOutcomeEnum,
    EnrichmentResult,
    Lead,
    LeadContactLog,
    Reminder,
    ReminderStatusEnum,
)
from openclaw.enrich.pipeline import run_lead_enrichment, run_lead_osint
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


def _normalize_csv_columns(raw: str | None, allowed: dict[str, str], defaults: list[str]) -> list[str]:
    if not raw:
        return defaults
    cols: list[str] = []
    seen: set[str] = set()
    for part in raw.split(","):
        key = part.strip()
        if key in allowed and key not in seen:
            cols.append(key)
            seen.add(key)
    return cols or defaults


def _extract_contact_from_enrichment(data) -> tuple[str | None, str | None]:
    if not isinstance(data, dict):
        return None, None

    phone = None
    email = None
    for key in ("phone", "owner_phone", "phone_number"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            phone = value.strip()
            break

    for key in ("email", "owner_email", "email_address"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            email = value.strip()
            break

    if not phone:
        phones = data.get("phones")
        if isinstance(phones, list) and phones:
            first = phones[0]
            if isinstance(first, str) and first.strip():
                phone = first.strip()
            elif isinstance(first, dict):
                for key in ("number", "phone"):
                    candidate = first.get(key)
                    if isinstance(candidate, str) and candidate.strip():
                        phone = candidate.strip()
                        break

    if not email:
        emails = data.get("emails")
        if isinstance(emails, list) and emails:
            first = emails[0]
            if isinstance(first, str) and first.strip():
                email = first.strip()
            elif isinstance(first, dict):
                for key in ("address", "email"):
                    candidate = first.get(key)
                    if isinstance(candidate, str) and candidate.strip():
                        email = candidate.strip()
                        break
    return phone, email


def _csv_stream(headers: list[str], rows: list[list]) -> io.StringIO:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(headers)
    yield buffer.getvalue()
    buffer.seek(0)
    buffer.truncate(0)

    for row in rows:
        writer.writerow(row)
        yield buffer.getvalue()
        buffer.seek(0)
        buffer.truncate(0)


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
            joinedload(Lead.reminders),
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
    pending_reminders = sorted(
        [r for r in lead.reminders if (r.status.value if hasattr(r.status, "value") else str(r.status)) == "pending"],
        key=lambda r: r.remind_at or datetime.max,
    )

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
            "osint_enabled": bool(settings.OSINT_ENABLED),
            "pending_reminders": pending_reminders,
            "now_utc": datetime.utcnow(),
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


@router.get("/api/leads/{lead_id}/osint")
def get_lead_osint(lead_id: str, session: Session = Depends(db)):
    lead = session.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        return JSONResponse({"error": "not found"}, status_code=404)
    return {
        "ok": True,
        "enabled": bool(settings.OSINT_ENABLED),
        "investigation_id": lead.osint_investigation_id,
        "status": lead.osint_status,
        "summary": lead.osint_summary,
        "queried_at": lead.osint_queried_at.isoformat() if lead.osint_queried_at else None,
        "ui_url": _osint_ui_link(lead),
    }


@router.post("/api/leads/{lead_id}/osint")
def run_lead_osint_endpoint(lead_id: str, request: Request):
    if not settings.OSINT_ENABLED:
        return JSONResponse({"error": "OSINT disabled"}, status_code=503)
    user_id = _parse_user_id(request)
    result = run_lead_osint(lead_id, triggered_by=user_id, require_health=True)
    if not result.get("ok"):
        error = result.get("error") or "OSINT execution failed"
        status_code = 404 if error == "not found" else 503
        return JSONResponse({"error": error}, status_code=status_code)
    return result


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


@router.post("/api/leads/{lead_id}/reminders")
async def create_lead_reminder(lead_id: str, request: Request, session: Session = Depends(db)):
    lead = session.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        return JSONResponse({"error": "not found"}, status_code=404)

    user_id = _parse_user_id(request)
    if not user_id:
        return JSONResponse({"error": "unauthenticated"}, status_code=401)

    body = await request.json()
    remind_at_raw = (body.get("remind_at") or "").strip()
    message = (body.get("message") or "").strip() or None
    if not remind_at_raw:
        return JSONResponse({"error": "remind_at is required"}, status_code=400)

    try:
        remind_at = datetime.fromisoformat(remind_at_raw)
    except ValueError:
        return JSONResponse({"error": "invalid remind_at"}, status_code=400)

    reminder = Reminder(
        lead_id=lead.id,
        user_id=user_id,
        remind_at=remind_at,
        message=message,
        status=ReminderStatusEnum.pending,
    )
    session.add(reminder)
    session.commit()
    session.refresh(reminder)
    return {
        "ok": True,
        "id": reminder.id,
        "lead_id": str(reminder.lead_id),
        "status": reminder.status.value if hasattr(reminder.status, "value") else str(reminder.status),
        "remind_at": reminder.remind_at.isoformat(),
        "message": reminder.message,
    }


@router.post("/api/reminders/{reminder_id}/dismiss")
def dismiss_reminder(reminder_id: int, request: Request, session: Session = Depends(db)):
    user_id = _parse_user_id(request)
    if not user_id:
        return JSONResponse({"error": "unauthenticated"}, status_code=401)

    reminder = (
        session.query(Reminder)
        .filter(Reminder.id == reminder_id)
        .filter(Reminder.user_id == user_id)
        .first()
    )
    if not reminder:
        return JSONResponse({"error": "not found"}, status_code=404)
    reminder.status = ReminderStatusEnum.dismissed
    session.add(reminder)
    session.commit()
    return {"ok": True}


@router.get("/api/reminders/pending")
def pending_reminders(request: Request, session: Session = Depends(db)):
    user_id = _parse_user_id(request)
    if not user_id:
        return []

    now = datetime.utcnow()
    rows = (
        session.query(Reminder)
        .options(
            joinedload(Reminder.lead).joinedload(Lead.candidate).joinedload(Candidate.parcel),
            joinedload(Reminder.user),
        )
        .filter(Reminder.user_id == user_id)
        .filter(Reminder.status == ReminderStatusEnum.pending)
        .order_by(Reminder.remind_at.asc())
        .limit(200)
        .all()
    )
    return [
        {
            "id": row.id,
            "lead_id": str(row.lead_id),
            "remind_at": row.remind_at.isoformat() if row.remind_at else None,
            "message": row.message,
            "status": row.status.value if hasattr(row.status, "value") else str(row.status),
            "is_overdue": bool(row.remind_at and row.remind_at < now),
            "lead_address": (
                row.lead.candidate.parcel.address
                if row.lead and row.lead.candidate and row.lead.candidate.parcel
                else None
            ),
        }
        for row in rows
    ]


@router.get("/api/leads/export")
def export_leads_csv(
    request: Request,
    format: str = Query("csv"),
    columns: str | None = Query(None),
    status: str | None = Query(None),
    sort: str = Query("updated_desc"),
    session: Session = Depends(db),
):
    if format.lower() != "csv":
        return JSONResponse({"error": "only csv export is supported"}, status_code=400)

    allowed = {
        "lead_id": "Lead ID",
        "status": "Status",
        "address": "Address",
        "owner_name": "Owner",
        "score_at_promotion": "Score At Promotion",
        "reason": "Promotion Reason",
        "owner_phone": "Owner Phone",
        "owner_email": "Owner Email",
        "enrichment_phone": "Enrichment Phone",
        "enrichment_email": "Enrichment Email",
        "osint_status": "OSINT Status",
        "osint_summary": "OSINT Summary",
        "promoted_at": "Promoted At",
        "updated_at": "Updated At",
    }
    default_cols = [
        "lead_id",
        "status",
        "address",
        "owner_name",
        "score_at_promotion",
        "owner_phone",
        "owner_email",
        "enrichment_phone",
        "enrichment_email",
        "osint_status",
        "osint_summary",
        "updated_at",
    ]
    selected = _normalize_csv_columns(columns, allowed, default_cols)

    query = (
        session.query(Lead)
        .options(
            joinedload(Lead.candidate).joinedload(Candidate.parcel),
            joinedload(Lead.enrichment_results),
        )
    )
    if status:
        query = query.filter(Lead.status == status)
    if sort == "created_asc":
        query = query.order_by(Lead.created_at.asc())
    elif sort == "created_desc":
        query = query.order_by(Lead.created_at.desc())
    elif sort == "updated_asc":
        query = query.order_by(Lead.updated_at.asc())
    else:
        query = query.order_by(Lead.updated_at.desc())

    max_rows = max(1, int(settings.EXPORT_MAX_ROWS))
    total = query.count()
    rows = query.limit(max_rows).all()

    csv_rows: list[list] = []
    for lead in rows:
        parcel = lead.candidate.parcel if lead.candidate and lead.candidate.parcel else None
        enrichment_phone = None
        enrichment_email = None
        for item in sorted(lead.enrichment_results, key=lambda r: r.fetched_at or datetime.min, reverse=True):
            phone, email = _extract_contact_from_enrichment(item.data)
            enrichment_phone = enrichment_phone or phone
            enrichment_email = enrichment_email or email
            if enrichment_phone and enrichment_email:
                break

        record = {
            "lead_id": str(lead.id),
            "status": lead.status,
            "address": parcel.address if parcel else None,
            "owner_name": (lead.owner_snapshot or {}).get("name") if isinstance(lead.owner_snapshot, dict) else None,
            "score_at_promotion": lead.score_at_promotion,
            "reason": lead.reason,
            "owner_phone": lead.owner_phone,
            "owner_email": lead.owner_email,
            "enrichment_phone": enrichment_phone,
            "enrichment_email": enrichment_email,
            "osint_status": lead.osint_status,
            "osint_summary": lead.osint_summary,
            "promoted_at": lead.promoted_at.isoformat() if lead.promoted_at else None,
            "updated_at": lead.updated_at.isoformat() if lead.updated_at else None,
        }
        if not record["owner_name"] and parcel:
            record["owner_name"] = parcel.owner_name
        csv_rows.append([record.get(col) for col in selected])

    headers = [allowed[col] for col in selected]
    filename = "leads_export.csv"
    stream = _csv_stream(headers, csv_rows)
    response = StreamingResponse(stream, media_type="text/csv") if len(csv_rows) > 1000 else StreamingResponse(stream, media_type="text/csv")
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.headers["X-Export-Total"] = str(total)
    response.headers["X-Export-Limit"] = str(max_rows)
    response.headers["X-Export-Returned"] = str(len(csv_rows))
    response.headers["X-Export-Truncated"] = "1" if total > max_rows else "0"
    response.headers["Cache-Control"] = "no-store"
    return response
