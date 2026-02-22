"""Mike's Building System — Web app composition."""

from __future__ import annotations

import json

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from openclaw.db.models import Candidate, Lead, Parcel, ScoreTierEnum
from openclaw.config import settings as app_settings
from openclaw.web.reminders import process_due_reminders
from openclaw.web.common import BASE_DIR, ROOT_PATH, db, templates
from openclaw.web.auth_utils import seed_admin_user
from openclaw.web.routers import auth, candidates, feasibility, leads, learning, map, scoring, settings

app = FastAPI(title="Mike's Building System", docs_url=None, redoc_url=None, root_path=ROOT_PATH)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

_AUTH_ALLOWLIST = {"/login", "/api/auth/login", "/api/auth/logout", "/api/auth/me", "/logout"}
_scheduler: BackgroundScheduler | None = None


@app.middleware("http")
async def require_auth(request: Request, call_next):
    path = request.url.path
    if path.startswith("/static") or path in _AUTH_ALLOWLIST:
        return await call_next(request)

    if not request.cookies.get("user_id"):
        return RedirectResponse(url="/login", status_code=303)

    return await call_next(request)


@app.on_event("startup")
def _seed_auth_defaults() -> None:
    from openclaw.db.session import SessionLocal

    session = SessionLocal()
    try:
        seed_admin_user(session)
    finally:
        session.close()

    global _scheduler
    if _scheduler is None:
        _scheduler = BackgroundScheduler()
        _scheduler.add_job(
            process_due_reminders,
            "interval",
            minutes=max(1, int(app_settings.REMINDER_CHECK_INTERVAL_MIN)),
            id="process_due_reminders",
            replace_existing=True,
        )
        _scheduler.start()


@app.on_event("shutdown")
def _shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, session: Session = Depends(db)):
    total_parcels = session.query(func.count(Parcel.id)).scalar() or 0

    tier_counts = dict(
        session.query(Candidate.score_tier, func.count(Candidate.id))
        .group_by(Candidate.score_tier)
        .all()
    )
    tier_a = tier_counts.get(ScoreTierEnum.A, 0)
    tier_b = tier_counts.get(ScoreTierEnum.B, 0)
    tier_c = tier_counts.get(ScoreTierEnum.C, 0)
    tier_d = tier_counts.get(ScoreTierEnum.D, 0)
    tier_e = tier_counts.get(ScoreTierEnum.E, 0)
    tier_f = tier_counts.get(ScoreTierEnum.F, 0)
    total_candidates = tier_a + tier_b + tier_c + tier_d + tier_e + tier_f

    from datetime import datetime, timedelta

    week_ago = datetime.utcnow() - timedelta(days=7)
    new_leads = session.query(func.count(Lead.id)).filter(Lead.created_at >= week_ago).scalar() or 0
    total_leads = session.query(func.count(Lead.id)).scalar() or 0

    top5 = (
        session.query(Candidate)
        .join(Parcel)
        .options(joinedload(Candidate.parcel))
        .filter(Candidate.score_tier == ScoreTierEnum.A)
        .order_by(Candidate.potential_splits.desc())
        .limit(5)
        .all()
    )

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "total_parcels": total_parcels,
        "total_candidates": total_candidates,
        "tier_a": tier_a,
        "tier_b": tier_b,
        "tier_c": tier_c,
        "tier_d": tier_d,
        "tier_e": tier_e,
        "tier_f": tier_f,
        "new_leads": new_leads,
        "total_leads": total_leads,
        "top5": top5,
        "tier_data_json": json.dumps([tier_a, tier_b, tier_c, tier_d, tier_e, tier_f]),
    })


app.include_router(auth.router)
app.include_router(candidates.router)
app.include_router(feasibility.router)
app.include_router(leads.router)
app.include_router(learning.router)
app.include_router(map.router)
app.include_router(scoring.router)
app.include_router(settings.router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("openclaw.web.app:app", host="0.0.0.0", port=8470, reload=True)
