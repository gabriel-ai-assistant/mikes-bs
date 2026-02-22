"""Block G: reminders table.

Revision ID: 012
Revises: 011
Create Date: 2026-02-22
"""
from typing import Sequence, Union

from alembic import op

revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'reminder_status_enum') THEN
                CREATE TYPE reminder_status_enum AS ENUM ('pending', 'sent', 'dismissed');
            END IF;
        END $$;
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS reminders (
            id SERIAL PRIMARY KEY,
            lead_id UUID NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            remind_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
            message TEXT,
            status reminder_status_enum NOT NULL DEFAULT 'pending',
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_reminders_lead_id ON reminders (lead_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_reminders_user_id ON reminders (user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_reminders_status ON reminders (status)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_reminders_remind_at ON reminders (remind_at)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_reminders_remind_at")
    op.execute("DROP INDEX IF EXISTS ix_reminders_status")
    op.execute("DROP INDEX IF EXISTS ix_reminders_user_id")
    op.execute("DROP INDEX IF EXISTS ix_reminders_lead_id")
    op.execute("DROP TABLE IF EXISTS reminders")
    op.execute("DROP TYPE IF EXISTS reminder_status_enum")
