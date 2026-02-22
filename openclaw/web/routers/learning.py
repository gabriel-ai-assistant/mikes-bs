"""Learning routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import case
from sqlalchemy.orm import Session

from openclaw.db.models import LearningProposal
from openclaw.learning.analyzer import run_nightly_learning
from openclaw.web.common import db, templates

router = APIRouter()


def _proposal_to_dict(p: LearningProposal) -> dict:
    return {
        "id": p.id,
        "run_date": p.run_date,
        "proposal_type": p.proposal_type,
        "description": p.description,
        "evidence": p.evidence,
        "current_value": p.current_value,
        "proposed_value": p.proposed_value,
        "confidence": p.confidence,
        "estimated_impact": p.estimated_impact,
        "status": p.status,
        "reviewed_at": p.reviewed_at,
        "applied_at": p.applied_at,
    }


@router.get("/learning", response_class=HTMLResponse)
def learning_page(request: Request, session: Session = Depends(db)):
    proposals = (
        session.query(LearningProposal)
        .filter(LearningProposal.status == "pending")
        .order_by(
            case(
                (LearningProposal.confidence == "HIGH", 1),
                (LearningProposal.confidence == "MEDIUM", 2),
                else_=3,
            ),
            LearningProposal.run_date.desc(),
        )
        .all()
    )

    history = (
        session.query(LearningProposal)
        .filter(LearningProposal.status != "pending")
        .order_by(LearningProposal.reviewed_at.desc())
        .limit(20)
        .all()
    )

    return templates.TemplateResponse("learning.html", {
        "request": request,
        "proposals": [_proposal_to_dict(p) for p in proposals],
        "history": [_proposal_to_dict(h) for h in history],
    })


@router.post("/api/learning/run-now")
def run_learning_now(session: Session = Depends(db)):
    count = run_nightly_learning(session=session)
    return {"ok": True, "proposals_generated": count}


@router.post("/api/learning/{proposal_id}/approve")
def approve_proposal(proposal_id: int, session: Session = Depends(db)):
    proposal = session.query(LearningProposal).filter(LearningProposal.id == proposal_id).first()
    if not proposal:
        return {"ok": False}
    proposal.status = "approved"
    from datetime import datetime
    proposal.reviewed_at = datetime.utcnow()
    session.commit()
    return {"ok": True}


@router.post("/api/learning/{proposal_id}/reject")
def reject_proposal(proposal_id: int, session: Session = Depends(db)):
    proposal = session.query(LearningProposal).filter(LearningProposal.id == proposal_id).first()
    if not proposal:
        return {"ok": False}
    proposal.status = "rejected"
    from datetime import datetime
    proposal.reviewed_at = datetime.utcnow()
    session.commit()
    return {"ok": True}
