"""Auth routes."""

from __future__ import annotations

from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from openclaw.db.models import User
from openclaw.web.auth_utils import get_user_by_username, verify_password
from openclaw.web.common import db, templates

router = APIRouter()


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@router.post("/api/auth/login")
async def login(request: Request, session: Session = Depends(db)):
    content_type = request.headers.get("content-type", "")
    username = ""
    password = ""

    if "application/json" in content_type:
        data = await request.json()
        username = (data.get("username") or "").strip()
        password = data.get("password") or ""
    else:
        body = (await request.body()).decode("utf-8")
        parsed = parse_qs(body)
        username = (parsed.get("username", [""])[0] or "").strip()
        password = parsed.get("password", [""])[0] or ""

    user = get_user_by_username(session, username)
    if not user or not verify_password(password, user.password_hash):
        if "application/json" in content_type:
            return JSONResponse({"error": "invalid credentials"}, status_code=401)
        return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid credentials"}, status_code=401)

    if "application/json" in content_type:
        response = JSONResponse({"ok": True, "user": {"id": user.id, "username": user.username, "role": user.role}})
    else:
        response = RedirectResponse(url="/", status_code=303)
    response.set_cookie("user_id", str(user.id), httponly=True, samesite="lax")
    response.set_cookie("username", user.username, httponly=True, samesite="lax")
    response.set_cookie("role", user.role, httponly=True, samesite="lax")
    return response


@router.post("/api/auth/logout")
def logout(request: Request):
    response = JSONResponse({"ok": True})
    response.delete_cookie("user_id")
    response.delete_cookie("username")
    response.delete_cookie("role")
    return response


@router.get("/logout")
def logout_page(request: Request):
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("user_id")
    response.delete_cookie("username")
    response.delete_cookie("role")
    return response


@router.get("/api/auth/me")
def whoami(request: Request, session: Session = Depends(db)):
    user_id = request.cookies.get("user_id")
    if not user_id:
        return JSONResponse({"error": "unauthenticated"}, status_code=401)
    user = session.query(User).filter(User.id == user_id).first()
    if not user:
        return JSONResponse({"error": "unauthenticated"}, status_code=401)
    return {"id": user.id, "username": user.username, "role": user.role}
