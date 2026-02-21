"""Add subdivision assessment columns to candidates.

Revision ID: 004
Revises: 003
Create Date: 2026-02-21
"""
from typing import Sequence, Union
from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE candidates ADD COLUMN IF NOT EXISTS subdivisibility_score INTEGER DEFAULT 0")
    op.execute("ALTER TABLE candidates ADD COLUMN IF NOT EXISTS subdivision_feasibility VARCHAR(20) DEFAULT 'UNKNOWN'")
    op.execute("ALTER TABLE candidates ADD COLUMN IF NOT EXISTS subdivision_flags TEXT[] DEFAULT '{}'")


def downgrade() -> None:
    op.execute("ALTER TABLE candidates DROP COLUMN IF EXISTS subdivision_flags")
    op.execute("ALTER TABLE candidates DROP COLUMN IF EXISTS subdivision_feasibility")
    op.execute("ALTER TABLE candidates DROP COLUMN IF EXISTS subdivisibility_score")
