"""Add feasibility_results table.

Revision ID: 008
Revises: 007
Create Date: 2026-02-22
"""
from typing import Sequence, Union

from alembic import op

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS feasibility_results (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            parcel_id UUID NOT NULL REFERENCES parcels(id),
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            result_json JSONB,
            tags TEXT[] DEFAULT '{}',
            best_layout_id VARCHAR,
            best_score DOUBLE PRECISION,
            created_at TIMESTAMP DEFAULT now(),
            completed_at TIMESTAMP
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_feasibility_results_parcel_id ON feasibility_results(parcel_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_feasibility_results_status ON feasibility_results(status)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_feasibility_results_status")
    op.execute("DROP INDEX IF EXISTS ix_feasibility_results_parcel_id")
    op.execute("DROP TABLE IF EXISTS feasibility_results")
