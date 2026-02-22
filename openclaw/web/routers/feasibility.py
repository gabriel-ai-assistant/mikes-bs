"""Feasibility routes."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from openclaw.db.models import FeasibilityResult, Parcel
from openclaw.db.session import SessionLocal
from openclaw.web.common import db, templates

router = APIRouter()

_feasibility_jobs: dict[str, dict] = {}


def _run_feasibility_job(parcel_id: str) -> None:
    from openclaw.analysis.feasibility.orchestrator import run_feasibility

    session = SessionLocal()
    try:
        parcel = session.query(Parcel).filter(Parcel.parcel_id == parcel_id).first()
        if not parcel:
            _feasibility_jobs[parcel_id] = {"status": "failed", "error": "parcel not found"}
            return

        _feasibility_jobs[parcel_id] = {"status": "running", "started_at": datetime.utcnow().isoformat()}

        fr = FeasibilityResult(parcel_id=parcel.id, status="running")
        session.add(fr)
        session.commit()
        session.refresh(fr)

        try:
            ctx = run_feasibility(parcel_id=parcel_id)
            best = ctx.layouts[0] if ctx.layouts else {}
            result_json = {
                "parcel_id": parcel_id,
                "tags": ctx.tags,
                "warnings": ctx.warnings,
                "metrics": ctx.metrics,
                "layouts": [
                    {
                        "id": l.get("id"),
                        "strategy": l.get("strategy"),
                        "lot_count": l.get("lot_count"),
                        "score": l.get("score"),
                        "tags": l.get("tags", []),
                        "cost_estimate": l.get("cost_estimate", {}),
                    }
                    for l in ctx.layouts
                ],
                "best_layout": best.get("id"),
                "best_score": best.get("score"),
                "exports": ctx.export_paths,
            }

            fr.status = "complete"
            fr.result_json = result_json
            fr.tags = ctx.tags
            fr.best_layout_id = best.get("id")
            fr.best_score = best.get("score")
            fr.completed_at = datetime.utcnow()
            session.commit()
            _feasibility_jobs[parcel_id] = {"status": "complete", "result": result_json}
        except Exception as exc:
            fr.status = "failed"
            fr.result_json = {"error": str(exc)}
            fr.completed_at = datetime.utcnow()
            session.commit()
            _feasibility_jobs[parcel_id] = {"status": "failed", "error": str(exc)}
    finally:
        session.close()


@router.post("/api/feasibility/{parcel_id}")
async def run_feasibility_api(parcel_id: str, background_tasks: BackgroundTasks, session: Session = Depends(db)):
    parcel = session.query(Parcel).filter(Parcel.parcel_id == parcel_id).first()
    if not parcel:
        return JSONResponse({"error": "parcel not found"}, status_code=404)

    _feasibility_jobs[parcel_id] = {"status": "pending", "queued_at": datetime.utcnow().isoformat()}
    background_tasks.add_task(_run_feasibility_job, parcel_id)
    return {"ok": True, "job_id": parcel_id, "status": "pending"}


@router.get("/api/feasibility/{parcel_id}/status")
async def feasibility_status(parcel_id: str, session: Session = Depends(db)):
    parcel = session.query(Parcel).filter(Parcel.parcel_id == parcel_id).first()
    if not parcel:
        return JSONResponse({"error": "parcel not found"}, status_code=404)

    latest = session.execute(text("""
        SELECT status, best_layout_id, best_score, created_at, completed_at
        FROM feasibility_results
        WHERE parcel_id = :pid
        ORDER BY completed_at DESC NULLS LAST, created_at DESC
        LIMIT 1
    """), {"pid": str(parcel.id)}).mappings().first()

    job_state = _feasibility_jobs.get(parcel_id, {})
    return {"parcel_id": parcel_id, "job": job_state, "db": dict(latest) if latest else None}


@router.get("/api/feasibility/{parcel_id}/result")
async def feasibility_result(parcel_id: str, session: Session = Depends(db)):
    parcel = session.query(Parcel).filter(Parcel.parcel_id == parcel_id).first()
    if not parcel:
        return JSONResponse({"error": "parcel not found"}, status_code=404)

    latest = session.execute(text("""
        SELECT status, result_json, tags, best_layout_id, best_score, created_at, completed_at
        FROM feasibility_results
        WHERE parcel_id = :pid
        ORDER BY completed_at DESC NULLS LAST, created_at DESC
        LIMIT 1
    """), {"pid": str(parcel.id)}).mappings().first()
    if not latest:
        return JSONResponse({"error": "no result"}, status_code=404)
    return dict(latest)


@router.get("/feasibility/{parcel_id}", response_class=HTMLResponse)
async def feasibility_page(parcel_id: str, request: Request, session: Session = Depends(db)):
    parcel = session.query(Parcel).filter(Parcel.parcel_id == parcel_id).first()
    if not parcel:
        return HTMLResponse("<h3>Property not found</h3>", status_code=404)

    latest = session.execute(text("""
        SELECT status, result_json, tags, best_layout_id, best_score, created_at, completed_at
        FROM feasibility_results
        WHERE parcel_id = :pid
        ORDER BY completed_at DESC NULLS LAST, created_at DESC
        LIMIT 1
    """), {"pid": str(parcel.id)}).mappings().first()

    return templates.TemplateResponse("feasibility.html", {
        "request": request,
        "parcel": parcel,
        "feasibility": dict(latest) if latest else None,
    })
