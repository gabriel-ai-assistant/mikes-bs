"""Add tags, reason_codes to candidates; create ruta_boundaries.

Revision ID: 002
Revises: 001
Create Date: 2026-02-21
"""
from typing import Sequence, Union
from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE candidates ADD COLUMN IF NOT EXISTS tags TEXT[] DEFAULT '{}'")
    op.execute("ALTER TABLE candidates ADD COLUMN IF NOT EXISTS reason_codes TEXT[] DEFAULT '{}'")
    op.execute("ALTER TABLE candidates ADD COLUMN IF NOT EXISTS score INTEGER DEFAULT 0")

    op.execute("""
        CREATE TABLE IF NOT EXISTS ruta_boundaries (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name TEXT,
            geometry GEOMETRY(GEOMETRY, 4326)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_ruta_boundaries_geom ON ruta_boundaries USING GIST(geometry)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_ruta_boundaries_geom")
    op.execute("DROP TABLE IF EXISTS ruta_boundaries")
    op.execute("ALTER TABLE candidates DROP COLUMN IF EXISTS tags")
    op.execute("ALTER TABLE candidates DROP COLUMN IF EXISTS reason_codes")
    op.execute("ALTER TABLE candidates DROP COLUMN IF EXISTS score")
