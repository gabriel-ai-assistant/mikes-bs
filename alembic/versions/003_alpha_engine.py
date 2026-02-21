"""Alpha Engine: deal_analysis, assumptions_versioned, candidates.uga_outside.

Revision ID: 003
Revises: 002
Create Date: 2026-02-21
"""
from typing import Sequence, Union
from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # Table: deal_analysis
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS deal_analysis (
            id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            parcel_id                 UUID NOT NULL REFERENCES parcels(id),
            county                    VARCHAR NOT NULL,
            run_date                  TIMESTAMP NOT NULL DEFAULT now(),
            run_id                    UUID,
            assumptions_version       VARCHAR NOT NULL,
            tags                      TEXT[],
            edge_score                FLOAT,
            tier                      VARCHAR(1),
            annualized_return_estimate FLOAT,
            reasons                   JSONB,
            underwriting_json         JSONB,
            analysis_timestamp        TIMESTAMP NOT NULL DEFAULT now()
        )
    """)

    # Functional unique index (can't be inline in CREATE TABLE for older PG)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_deal_parcel_date_version
        ON deal_analysis (parcel_id, (run_date::date), assumptions_version)
    """)

    op.execute("CREATE INDEX IF NOT EXISTS idx_deal_analysis_parcel     ON deal_analysis(parcel_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_deal_analysis_run        ON deal_analysis(run_date)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_deal_analysis_tier       ON deal_analysis(tier)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_deal_analysis_edge_score ON deal_analysis(edge_score DESC)")

    # ------------------------------------------------------------------
    # Table: assumptions_versioned
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS assumptions_versioned (
            version     VARCHAR PRIMARY KEY,
            created_at  TIMESTAMP DEFAULT now(),
            created_by  VARCHAR DEFAULT 'system',
            config_json JSONB NOT NULL,
            notes       TEXT
        )
    """)

    # Seed initial defaults
    op.execute("""
        INSERT INTO assumptions_versioned (version, config_json, notes)
        VALUES ('v1', '{}', 'Initial Alpha Engine defaults')
        ON CONFLICT (version) DO NOTHING
    """)

    # ------------------------------------------------------------------
    # candidates.uga_outside BOOLEAN
    # ------------------------------------------------------------------
    op.execute("ALTER TABLE candidates ADD COLUMN IF NOT EXISTS uga_outside BOOLEAN")
    op.execute("CREATE INDEX IF NOT EXISTS idx_candidates_uga ON candidates(uga_outside)")


def downgrade() -> None:
    # Reverse indexes + columns
    op.execute("DROP INDEX IF EXISTS idx_candidates_uga")
    op.execute("ALTER TABLE candidates DROP COLUMN IF EXISTS uga_outside")

    # assumptions_versioned
    op.execute("DROP TABLE IF EXISTS assumptions_versioned")

    # deal_analysis (indexes dropped with table)
    op.execute("DROP INDEX IF EXISTS idx_deal_analysis_edge_score")
    op.execute("DROP INDEX IF EXISTS idx_deal_analysis_tier")
    op.execute("DROP INDEX IF EXISTS idx_deal_analysis_run")
    op.execute("DROP INDEX IF EXISTS idx_deal_analysis_parcel")
    op.execute("DROP INDEX IF EXISTS uq_deal_parcel_date_version")
    op.execute("DROP TABLE IF EXISTS deal_analysis")
