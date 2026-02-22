"""Block E: lead extension + enrichment results + lead contact log.

Revision ID: 011
Revises: 010
Create Date: 2026-02-22
"""
from typing import Sequence, Union

from alembic import op

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE leads ADD COLUMN IF NOT EXISTS owner_snapshot JSONB")
    op.execute("ALTER TABLE leads ADD COLUMN IF NOT EXISTS reason TEXT")
    op.execute("ALTER TABLE leads ADD COLUMN IF NOT EXISTS score_at_promotion INTEGER")
    op.execute("ALTER TABLE leads ADD COLUMN IF NOT EXISTS bundle_snapshot JSONB")
    op.execute("ALTER TABLE leads ADD COLUMN IF NOT EXISTS promoted_by INTEGER")
    op.execute("ALTER TABLE leads ADD COLUMN IF NOT EXISTS promoted_at TIMESTAMP WITHOUT TIME ZONE")
    op.execute("ALTER TABLE leads ADD COLUMN IF NOT EXISTS osint_investigation_id INTEGER")
    op.execute("ALTER TABLE leads ADD COLUMN IF NOT EXISTS osint_status TEXT")
    op.execute("ALTER TABLE leads ADD COLUMN IF NOT EXISTS osint_queried_at TIMESTAMP WITHOUT TIME ZONE")
    op.execute("ALTER TABLE leads ADD COLUMN IF NOT EXISTS osint_summary TEXT")

    op.execute("ALTER TABLE leads DROP CONSTRAINT IF EXISTS leads_promoted_by_fkey")
    op.execute(
        """
        ALTER TABLE leads
        ADD CONSTRAINT leads_promoted_by_fkey
        FOREIGN KEY (promoted_by) REFERENCES users(id)
        """
    )

    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'enrichment_status_enum') THEN
                CREATE TYPE enrichment_status_enum AS ENUM ('pending', 'running', 'success', 'partial', 'failed');
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'enrichment_source_class_enum') THEN
                CREATE TYPE enrichment_source_class_enum AS ENUM ('public_record', 'commercial_api', 'business_filing', 'osint');
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'lead_contact_method_enum') THEN
                CREATE TYPE lead_contact_method_enum AS ENUM ('phone', 'email', 'mail', 'in_person', 'other');
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'lead_contact_outcome_enum') THEN
                CREATE TYPE lead_contact_outcome_enum AS ENUM ('no_answer', 'voicemail', 'spoke', 'email_sent', 'letter_sent', 'meeting', 'other');
            END IF;
        END $$;
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS enrichment_results (
            id SERIAL PRIMARY KEY,
            lead_id UUID NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
            provider VARCHAR NOT NULL,
            status enrichment_status_enum NOT NULL DEFAULT 'pending',
            data JSONB,
            confidence DOUBLE PRECISION,
            source_class enrichment_source_class_enum NOT NULL,
            fetched_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
            expires_at TIMESTAMP WITHOUT TIME ZONE,
            error_message TEXT
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_enrichment_results_lead_id ON enrichment_results (lead_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_enrichment_results_provider ON enrichment_results (provider)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS lead_contact_log (
            id SERIAL PRIMARY KEY,
            lead_id UUID NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id),
            method lead_contact_method_enum NOT NULL,
            outcome lead_contact_outcome_enum NOT NULL,
            notes TEXT,
            contacted_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_lead_contact_log_lead_id ON lead_contact_log (lead_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_lead_contact_log_lead_id")
    op.execute("DROP TABLE IF EXISTS lead_contact_log")

    op.execute("DROP INDEX IF EXISTS ix_enrichment_results_provider")
    op.execute("DROP INDEX IF EXISTS ix_enrichment_results_lead_id")
    op.execute("DROP TABLE IF EXISTS enrichment_results")

    op.execute("ALTER TABLE leads DROP CONSTRAINT IF EXISTS leads_promoted_by_fkey")
    op.execute("ALTER TABLE leads DROP COLUMN IF EXISTS osint_summary")
    op.execute("ALTER TABLE leads DROP COLUMN IF EXISTS osint_queried_at")
    op.execute("ALTER TABLE leads DROP COLUMN IF EXISTS osint_status")
    op.execute("ALTER TABLE leads DROP COLUMN IF EXISTS osint_investigation_id")
    op.execute("ALTER TABLE leads DROP COLUMN IF EXISTS promoted_at")
    op.execute("ALTER TABLE leads DROP COLUMN IF EXISTS promoted_by")
    op.execute("ALTER TABLE leads DROP COLUMN IF EXISTS bundle_snapshot")
    op.execute("ALTER TABLE leads DROP COLUMN IF EXISTS score_at_promotion")
    op.execute("ALTER TABLE leads DROP COLUMN IF EXISTS reason")
    op.execute("ALTER TABLE leads DROP COLUMN IF EXISTS owner_snapshot")

    op.execute("DROP TYPE IF EXISTS lead_contact_outcome_enum")
    op.execute("DROP TYPE IF EXISTS lead_contact_method_enum")
    op.execute("DROP TYPE IF EXISTS enrichment_source_class_enum")
    op.execute("DROP TYPE IF EXISTS enrichment_status_enum")
