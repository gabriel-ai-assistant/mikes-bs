"""Shared web-layer dependencies and template helpers."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi.templating import Jinja2Templates

from openclaw.db.models import LeadStatusEnum
from openclaw.db.session import get_session

BASE_DIR = Path(__file__).resolve().parent
ROOT_PATH = os.environ.get("ROOT_PATH", "")

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
templates.env.globals["base_url"] = ROOT_PATH


def fmt_money(v):
    return f"${v:,.0f}" if v is not None else "—"


def fmt_acres(v):
    return f"{v/43560:.2f} ac" if v else "—"


def fmt_sqft(v):
    return f"{v:,.0f} sf" if v else "—"


templates.env.filters["money"] = fmt_money
templates.env.filters["acres"] = fmt_acres
templates.env.filters["sqft"] = fmt_sqft

LEAD_STATUSES = [s.value for s in LeadStatusEnum]


def db():
    s = next(get_session())
    try:
        yield s
    finally:
        s.close()
