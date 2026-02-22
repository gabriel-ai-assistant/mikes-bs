"""Reminder polling and scheduled delivery helpers."""

from __future__ import annotations

import logging
import smtplib
from datetime import datetime
from email.mime.text import MIMEText

from sqlalchemy.orm import joinedload

from openclaw.config import settings
from openclaw.db.models import Candidate, Lead, Reminder, ReminderStatusEnum
from openclaw.db.session import SessionLocal

logger = logging.getLogger(__name__)


def _can_send_email() -> bool:
    return bool(
        settings.REMINDER_EMAIL_ENABLED
        and settings.SMTP_HOST
        and settings.SMTP_USER
        and settings.NOTIFY_EMAIL
    )


def _send_reminder_email(subject: str, body: str) -> None:
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = settings.SMTP_USER
    msg["To"] = settings.NOTIFY_EMAIL

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
        server.starttls()
        server.login(settings.SMTP_USER, settings.SMTP_PASS)
        server.send_message(msg)


def process_due_reminders() -> dict[str, int]:
    """Process due pending reminders. Sends email only when SMTP is configured."""
    now = datetime.utcnow()
    session = SessionLocal()
    sent = 0
    skipped = 0
    try:
        rows = (
            session.query(Reminder)
            .options(joinedload(Reminder.lead).joinedload(Lead.candidate).joinedload(Candidate.parcel))
            .filter(Reminder.status == ReminderStatusEnum.pending)
            .filter(Reminder.remind_at <= now)
            .order_by(Reminder.remind_at.asc())
            .limit(200)
            .all()
        )

        if not rows:
            return {"due": 0, "sent": 0, "skipped": 0}

        email_enabled = _can_send_email()
        for reminder in rows:
            if not email_enabled:
                skipped += 1
                continue

            lead = reminder.lead
            address = (
                lead.candidate.parcel.address
                if lead and lead.candidate and lead.candidate.parcel
                else "Unknown address"
            )
            note = (reminder.message or "").strip()
            body = (
                f"Lead reminder due now\n\n"
                f"Lead ID: {lead.id if lead else 'unknown'}\n"
                f"Address: {address}\n"
                f"Remind At (UTC): {reminder.remind_at.isoformat()}\n"
                f"Message: {note or '—'}\n"
            )
            try:
                _send_reminder_email("Mike's BS Reminder", body)
                reminder.status = ReminderStatusEnum.sent
                session.add(reminder)
                sent += 1
            except Exception as exc:  # pragma: no cover - network behavior
                logger.warning("Failed to send reminder id=%s: %s", reminder.id, exc)

        if sent:
            session.commit()
        else:
            session.rollback()

        return {"due": len(rows), "sent": sent, "skipped": skipped}
    finally:
        session.close()
