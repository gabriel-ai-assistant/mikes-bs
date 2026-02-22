"""FIX block architecture updates: lead status text+check and candidate metadata columns.

Revision ID: 009
Revises: 008
Create Date: 2026-02-22
"""
from typing import Sequence, Union

from alembic import op

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Candidate metadata for canonical owner matching, filter text, and bundle cache payload.
    op.execute("ALTER TABLE candidates ADD COLUMN IF NOT EXISTS owner_name_canonical VARCHAR")
    op.execute("ALTER TABLE candidates ADD COLUMN IF NOT EXISTS display_text TEXT")
    op.execute("ALTER TABLE candidates ADD COLUMN IF NOT EXISTS bundle_data JSONB")

    op.execute(
        """
        UPDATE candidates c
        SET owner_name_canonical = COALESCE(c.owner_name_canonical, p.owner_name),
            display_text = COALESCE(c.display_text, CONCAT_WS(' ', p.address, COALESCE(c.owner_name_canonical, p.owner_name)))
        FROM parcels p
        WHERE c.parcel_id = p.id
        """
    )

    # Lead status migration from enum to text+check.
    op.execute("ALTER TABLE leads ALTER COLUMN status TYPE TEXT USING status::TEXT")
    op.execute("UPDATE leads SET status = 'researching' WHERE status = 'reviewed'")
    op.execute("UPDATE leads SET status = 'contacted' WHERE status = 'outreach'")
    op.execute("UPDATE leads SET status = 'negotiating' WHERE status = 'active'")
    op.execute("ALTER TABLE leads ALTER COLUMN status DROP DEFAULT")
    op.execute("ALTER TABLE leads ALTER COLUMN status SET DEFAULT 'new'")
    op.execute(
        """
        ALTER TABLE leads
        DROP CONSTRAINT IF EXISTS leads_status_check
        """
    )
    op.execute(
        """
        ALTER TABLE leads
        ADD CONSTRAINT leads_status_check
        CHECK (status IN (
            'new', 'researching', 'contacted', 'negotiating',
            'closed_won', 'closed_lost', 'dead'
        ))
        """
    )
    op.execute("DROP TYPE IF EXISTS leadstatusenum")


def downgrade() -> None:
    op.execute("ALTER TABLE leads DROP CONSTRAINT IF EXISTS leads_status_check")
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'leadstatusenum') THEN
                CREATE TYPE leadstatusenum AS ENUM ('new', 'reviewed', 'outreach', 'active', 'dead');
            END IF;
        END $$;
        """
    )
    op.execute(
        """
        UPDATE leads SET status = 'reviewed' WHERE status = 'researching';
        UPDATE leads SET status = 'outreach' WHERE status = 'contacted';
        UPDATE leads SET status = 'active' WHERE status = 'negotiating';
        UPDATE leads SET status = 'dead' WHERE status IN ('closed_won', 'closed_lost', 'dead');
        """
    )
    op.execute("ALTER TABLE leads ALTER COLUMN status DROP DEFAULT")
    op.execute("ALTER TABLE leads ALTER COLUMN status SET DEFAULT 'new'::leadstatusenum")
    op.execute("ALTER TABLE leads ALTER COLUMN status TYPE leadstatusenum USING status::leadstatusenum")

    op.execute("ALTER TABLE candidates DROP COLUMN IF EXISTS bundle_data")
    op.execute("ALTER TABLE candidates DROP COLUMN IF EXISTS display_text")
    op.execute("ALTER TABLE candidates DROP COLUMN IF EXISTS owner_name_canonical")
