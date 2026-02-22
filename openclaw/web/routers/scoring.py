"""Scoring, rules, and feedback endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, text

from openclaw.analysis.rule_engine import evaluate_candidate, load_rules, rescore_all
from openclaw.db.models import Candidate, CandidateFeedback, ScoringRule
from openclaw.web.common import db

router = APIRouter()


@router.post("/api/candidate/{candidate_id}/feedback")
async def submit_feedback(
    candidate_id: str,
    request: Request,
    rating: str | None = Query(None),
    category: str = Query(""),
    notes: str = Query(""),
    session: Session = Depends(db),
):
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
    else:
        return JSONResponse({"error": "invalid feedback_type"}, status_code=400)

    category_value = (payload.get("category") or category or "").strip()
    notes_value = (payload.get("notes") or notes or "").strip()

    session.add(CandidateFeedback(
        candidate_id=candidate_id,
        rating=rating_value,
        category=category_value or None,
        notes=notes_value or None,
    ))

    candidate = session.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not candidate:
        session.rollback()
        return JSONResponse({"error": "candidate not found"}, status_code=404)

    current_score = int(candidate.score or 0)
    tier = candidate.score_tier.value if candidate.score_tier else None
    session.commit()
    return {"ok": True, "new_score": current_score, "new_tier": tier}


@router.get("/api/candidate/{candidate_id}/feedback")
def get_feedback(candidate_id: str, session: Session = Depends(db)):
    row = session.query(
        func.count(CandidateFeedback.id).filter(CandidateFeedback.rating == "up").label("thumbs_up"),
        func.count(CandidateFeedback.id).filter(CandidateFeedback.rating == "down").label("thumbs_down"),
    ).filter(CandidateFeedback.candidate_id == candidate_id).first()
    return {
        "thumbs_up": int(row.thumbs_up or 0),
        "thumbs_down": int(row.thumbs_down or 0),
    }


@router.get("/api/feedback/stats")
def feedback_stats(session: Session = Depends(db)):
    rows = session.query(
        CandidateFeedback.rating,
        CandidateFeedback.category,
        func.count(CandidateFeedback.id).label("cnt"),
    ).group_by(
        CandidateFeedback.rating,
        CandidateFeedback.category,
    ).order_by(func.count(CandidateFeedback.id).desc()).all()
    return [{"rating": r.rating, "category": r.category, "cnt": r.cnt} for r in rows]


@router.get("/api/rules")
def get_rules(session: Session = Depends(db)):
    rows = session.query(ScoringRule).order_by(ScoringRule.priority.asc(), ScoringRule.created_at.asc()).all()
    return [
        {
            "id": str(r.id),
            "name": r.name,
            "field": r.field,
            "operator": r.operator,
            "value": r.value,
            "action": r.action,
            "tier": r.tier,
            "score_adj": r.score_adj,
            "priority": r.priority,
            "active": r.active,
        }
        for r in rows
    ]


@router.post("/api/rules")
async def create_rule(request: Request, session: Session = Depends(db)):
    data = await request.json()
    session.add(ScoringRule(
        name=data["name"],
        field=data["field"],
        operator=data["operator"],
        value=data["value"],
        action=data["action"],
        tier=data.get("tier") or None,
        score_adj=int(data.get("score_adj") or 0),
        priority=int(data.get("priority") or 100),
    ))
    session.commit()
    return {"ok": True}


@router.put("/api/rules/{rule_id}")
async def update_rule(rule_id: str, request: Request, session: Session = Depends(db)):
    data = await request.json()
    rule = session.query(ScoringRule).filter(ScoringRule.id == rule_id).first()
    if not rule:
        return JSONResponse({"error": "not found"}, status_code=404)
    rule.name = data.get("name", rule.name)
    rule.field = data.get("field", rule.field)
    rule.operator = data.get("operator", rule.operator)
    rule.value = data.get("value", rule.value)
    rule.action = data.get("action", rule.action)
    rule.tier = data.get("tier") or None
    rule.score_adj = int(data.get("score_adj") or 0)
    rule.priority = int(data.get("priority") or 100)
    rule.active = bool(data.get("active", True))
    session.commit()
    return {"ok": True}


@router.delete("/api/rules/{rule_id}")
def delete_rule(rule_id: str, session: Session = Depends(db)):
    session.query(ScoringRule).filter(ScoringRule.id == rule_id).delete(synchronize_session=False)
    session.commit()
    return {"ok": True}


@router.patch("/api/rules/{rule_id}/toggle")
def toggle_rule(rule_id: str, session: Session = Depends(db)):
    rule = session.query(ScoringRule).filter(ScoringRule.id == rule_id).first()
    if not rule:
        return JSONResponse({"error": "not found"}, status_code=404)
    rule.active = not bool(rule.active)
    session.commit()
    return {"ok": True}


@router.post("/api/rescore")
def rescore():
    return rescore_all()


@router.get("/api/rescore/preview")
def rescore_preview(session: Session = Depends(db)):
    rules = load_rules(session)
    rows = session.execute(text("""
        SELECT c.id, c.potential_splits, c.has_critical_area_overlap, c.flagged_for_review,
               p.present_use, p.owner_name, p.zone_code, p.lot_sf, p.assessed_value,
               p.improvement_value, p.total_value
        FROM candidates c JOIN parcels p ON c.parcel_id = p.id
    """)).mappings().all()

    preview = {t: 0 for t in "ABCDEF"}
    excluded = 0
    for row in rows:
        tier, _score, excl, _tags, _reasons = evaluate_candidate(dict(row), rules)
        if excl:
            excluded += 1
        else:
            preview[tier] = preview.get(tier, 0) + 1
    return {"preview": preview, "excluded": excluded, "rules_active": len(rules)}
