"""Add learning_proposals table for nightly AI scoring suggestions.

Revision ID: 006
Revises: 005
"""
from alembic import op
import sqlalchemy as sa

revision = '006'
down_revision = '005'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS learning_proposals (
            id               SERIAL PRIMARY KEY,
            run_date         TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
            proposal_type    TEXT,
            description      TEXT,
            evidence         TEXT,
            current_value    TEXT,
            proposed_value   TEXT,
            confidence       TEXT,
            estimated_impact TEXT,
            status           TEXT NOT NULL DEFAULT 'pending',
            reviewed_at      TIMESTAMP WITHOUT TIME ZONE,
            applied_at       TIMESTAMP WITHOUT TIME ZONE
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_learning_proposals_status
            ON learning_proposals (status)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_learning_proposals_run_date
            ON learning_proposals (run_date DESC)
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS learning_proposals")
