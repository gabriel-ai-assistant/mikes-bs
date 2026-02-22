"""Session auth helpers."""

from __future__ import annotations

import os

from passlib.context import CryptContext
from sqlalchemy.orm import Session

from openclaw.db.models import User, UserRoleEnum

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    return pwd_context.verify(plain_password, password_hash)


def get_user_by_username(session: Session, username: str) -> User | None:
    return session.query(User).filter(User.username == username).first()


def seed_admin_user(session: Session) -> None:
    username = os.getenv("ADMIN_USERNAME", "admin")
    password = os.getenv("ADMIN_PASSWORD", "admin")

    existing = get_user_by_username(session, username)
    if existing:
        return

    admin = User(
        username=username,
        password_hash=get_password_hash(password),
        role=UserRoleEnum.admin.value,
    )
    session.add(admin)
    session.commit()
