"""Learning routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from openclaw.learning.analyzer import run_nightly_learning
from openclaw.web.common import db, templates

router = APIRouter()


@router.get("/learning", response_class=HTMLResponse)
def learning_page(request: Request, session: Session = Depends(db)):
    proposals = session.execute(text("""
        SELECT * FROM learning_proposals
        WHERE status = 'pending'
        ORDER BY
            CASE confidence WHEN 'HIGH' THEN 1 WHEN 'MEDIUM' THEN 2 ELSE 3 END,
            run_date DESC
    """)).mappings().all()

    history = session.execute(text("""
        SELECT * FROM learning_proposals
        WHERE status != 'pending'
        ORDER BY reviewed_at DESC
        LIMIT 20
    """)).mappings().all()

    return templates.TemplateResponse("learning.html", {
        "request": request,
        "proposals": [dict(p) for p in proposals],
        "history": [dict(h) for h in history],
    })


@router.post("/api/learning/run-now")
def run_learning_now(session: Session = Depends(db)):
    count = run_nightly_learning(session=session)
    return {"ok": True, "proposals_generated": count}


@router.post("/api/learning/{proposal_id}/approve")
def approve_proposal(proposal_id: int, session: Session = Depends(db)):
    session.execute(text("""
        UPDATE learning_proposals
        SET status = 'approved', reviewed_at = NOW()
        WHERE id = :id
    """), {"id": proposal_id})
    session.commit()
    return {"ok": True}


@router.post("/api/learning/{proposal_id}/reject")
def reject_proposal(proposal_id: int, session: Session = Depends(db)):
    session.execute(text("""
        UPDATE learning_proposals
        SET status = 'rejected', reviewed_at = NOW()
        WHERE id = :id
    """), {"id": proposal_id})
    session.commit()
    return {"ok": True}
