"""Add splits range, access mode, arbitrage depth, economic margin, and parcel width.

Revision ID: 007
Revises: 006
Create Date: 2026-02-22
"""
from typing import Sequence, Union
from alembic import op

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE candidates ADD COLUMN IF NOT EXISTS splits_min INTEGER")
    op.execute("ALTER TABLE candidates ADD COLUMN IF NOT EXISTS splits_max INTEGER")
    op.execute("ALTER TABLE candidates ADD COLUMN IF NOT EXISTS splits_confidence VARCHAR(10)")
    op.execute("ALTER TABLE candidates ADD COLUMN IF NOT EXISTS subdivision_access_mode VARCHAR(20)")
    op.execute("ALTER TABLE candidates ADD COLUMN IF NOT EXISTS arbitrage_depth_score INTEGER")
    op.execute("ALTER TABLE candidates ADD COLUMN IF NOT EXISTS economic_margin_pct DOUBLE PRECISION")
    op.execute("ALTER TABLE parcels ADD COLUMN IF NOT EXISTS parcel_width_ft DOUBLE PRECISION")


def downgrade() -> None:
    op.execute("ALTER TABLE parcels DROP COLUMN IF EXISTS parcel_width_ft")
    op.execute("ALTER TABLE candidates DROP COLUMN IF EXISTS economic_margin_pct")
    op.execute("ALTER TABLE candidates DROP COLUMN IF EXISTS arbitrage_depth_score")
    op.execute("ALTER TABLE candidates DROP COLUMN IF EXISTS subdivision_access_mode")
    op.execute("ALTER TABLE candidates DROP COLUMN IF EXISTS splits_confidence")
    op.execute("ALTER TABLE candidates DROP COLUMN IF EXISTS splits_max")
    op.execute("ALTER TABLE candidates DROP COLUMN IF EXISTS splits_min")
