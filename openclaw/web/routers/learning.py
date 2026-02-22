"""Learning routes."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import case
from sqlalchemy.orm import Session

from openclaw.db.models import LearningProposal, ScoringRule
from openclaw.learning.analyzer import run_nightly_learning
from openclaw.web.common import db, templates

router = APIRouter()
LEARNING_WEIGHT_MAX_DELTA = int(os.getenv("LEARNING_WEIGHT_MAX_DELTA", "15"))
LEARNED_RULE_PREFIX = os.getenv("LEARNED_RULE_PREFIX", "LEARNED:")


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


def _bounded_delta(value: int) -> int:
    return max(-LEARNING_WEIGHT_MAX_DELTA, min(LEARNING_WEIGHT_MAX_DELTA, value))


def _extract_delta(value: str | None) -> int | None:
    if not value:
        return None
    match = re.search(r"([+-]?\d+)", value)
    if not match:
        return None
    return int(match.group(1))


def _rule_payload_from_proposal(proposal: LearningProposal) -> dict | None:
    if (proposal.proposal_type or "").strip().lower() != "adjust_rule_weight":
        return None

    proposed_text = (proposal.proposed_value or "").strip()
    payload = None
    if proposed_text.startswith("{"):
        try:
            parsed = json.loads(proposed_text)
            if isinstance(parsed, dict):
                payload = parsed
        except json.JSONDecodeError:
            payload = None

    if payload:
        delta = _extract_delta(str(payload.get("score_adj")))
        if delta is None:
            return None
        return {
            "name": str(payload.get("name") or f"{LEARNED_RULE_PREFIX} proposal:{proposal.id}"),
            "field": str(payload.get("field") or "tags"),
            "operator": str(payload.get("operator") or "tag_contains"),
            "value": str(payload.get("value") or ""),
            "action": "adjust_score",
            "score_adj": _bounded_delta(delta),
            "priority": int(payload.get("priority") or 70),
        }

    merged_text = f"{proposal.description or ''} {proposal.proposed_value or ''}"
    tag_match = re.search(r"\b((?:EDGE|RISK)_[A-Z0-9_]+)\b", merged_text)
    delta = _extract_delta(proposal.proposed_value) or _extract_delta(proposal.description)
    if not tag_match or delta is None:
        return None

    return {
        "name": f"{LEARNED_RULE_PREFIX} proposal:{proposal.id}",
        "field": "tags",
        "operator": "tag_contains",
        "value": tag_match.group(1),
        "action": "adjust_score",
        "score_adj": _bounded_delta(delta),
        "priority": 70,
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

    now = datetime.utcnow()
    proposal.status = "approved"
    proposal.reviewed_at = now

    applied_rule = None
    payload = _rule_payload_from_proposal(proposal)
    if payload and payload["value"]:
        applied_rule = ScoringRule(
            name=payload["name"],
            field=payload["field"],
            operator=payload["operator"],
            value=payload["value"],
            action=payload["action"],
            score_adj=payload["score_adj"],
            priority=payload["priority"],
            active=True,
        )
        session.add(applied_rule)
        proposal.applied_at = now

    session.commit()
    return {
        "ok": True,
        "rule_applied": bool(applied_rule),
        "applied_rule_id": str(applied_rule.id) if applied_rule else None,
    }


@router.post("/api/learning/{proposal_id}/reject")
def reject_proposal(proposal_id: int, session: Session = Depends(db)):
    proposal = session.query(LearningProposal).filter(LearningProposal.id == proposal_id).first()
    if not proposal:
        return {"ok": False}
    proposal.status = "rejected"
    proposal.reviewed_at = datetime.utcnow()
    session.commit()
    return {"ok": True}
