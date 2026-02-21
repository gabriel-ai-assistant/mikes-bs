"""Initial schema with all tables and zoning seed data.

Revision ID: 001
Revises: None
Create Date: 2026-02-20
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
import geoalchemy2

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

county_enum = sa.Enum("king", "snohomish", "skagit", name="countyenum", create_type=False)
score_tier_enum = sa.Enum("A", "B", "C", name="scoretierenum", create_type=False)
lead_status_enum = sa.Enum("new", "reviewed", "outreach", "active", "dead", name="leadstatusenum", create_type=False)


def upgrade() -> None:
    # Enable PostGIS
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    county_enum.create(op.get_bind(), checkfirst=True)
    score_tier_enum.create(op.get_bind(), checkfirst=True)
    lead_status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "parcels",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("parcel_id", sa.String, nullable=False, index=True),
        sa.Column("county", county_enum, nullable=False),
        sa.Column("address", sa.String),
        sa.Column("owner_name", sa.String),
        sa.Column("owner_mailing_address", sa.String),
        sa.Column("lot_sf", sa.Integer),
        sa.Column("zone_code", sa.String),
        sa.Column("present_use", sa.String),
        sa.Column("assessed_value", sa.Integer),
        sa.Column("last_sale_price", sa.Integer),
        sa.Column("last_sale_date", sa.Date),
        sa.Column("geometry", geoalchemy2.Geometry("POLYGON", srid=4326)),
        sa.Column("ingested_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
        sa.UniqueConstraint("parcel_id", "county", name="uq_parcel_county"),
    )

    op.create_table(
        "zoning_rules",
        sa.Column("county", county_enum, nullable=False),
        sa.Column("zone_code", sa.String, nullable=False),
        sa.Column("min_lot_sf", sa.Integer),
        sa.Column("min_lot_width_ft", sa.Integer),
        sa.Column("max_du_per_acre", sa.Float),
        sa.Column("notes", sa.String),
        sa.PrimaryKeyConstraint("county", "zone_code"),
    )

    op.create_table(
        "candidates",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("parcel_id", UUID(as_uuid=True), sa.ForeignKey("parcels.id"), nullable=False),
        sa.Column("score_tier", score_tier_enum),
        sa.Column("potential_splits", sa.Integer),
        sa.Column("estimated_land_value", sa.Integer),
        sa.Column("estimated_dev_cost", sa.Integer),
        sa.Column("estimated_build_cost", sa.Integer),
        sa.Column("estimated_arv", sa.Integer),
        sa.Column("estimated_profit", sa.Integer),
        sa.Column("estimated_margin_pct", sa.Float),
        sa.Column("has_critical_area_overlap", sa.Boolean, server_default="false"),
        sa.Column("has_shoreline_overlap", sa.Boolean, server_default="false"),
        sa.Column("flagged_for_review", sa.Boolean, server_default="false"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "leads",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("candidate_id", UUID(as_uuid=True), sa.ForeignKey("candidates.id"), nullable=False),
        sa.Column("status", lead_status_enum, server_default="new"),
        sa.Column("owner_phone", sa.String),
        sa.Column("owner_email", sa.String),
        sa.Column("notes", sa.Text),
        sa.Column("contacted_at", sa.DateTime),
        sa.Column("contact_method", sa.String),
        sa.Column("outcome", sa.String),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "critical_areas",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("source", sa.String),
        sa.Column("area_type", sa.String),
        sa.Column("geometry", geoalchemy2.Geometry("POLYGON", srid=4326)),
    )

    op.create_table(
        "shoreline_buffer",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("geometry", geoalchemy2.Geometry("POLYGON", srid=4326)),
    )

    # Seed zoning rules — real WA state residential zones
    op.execute("""
        INSERT INTO zoning_rules (county, zone_code, min_lot_sf, min_lot_width_ft, max_du_per_acre, notes) VALUES
        ('king',      'R-1',  43560, 135, 1.0,  'Rural residential, 1 acre minimum'),
        ('king',      'R-4',  8400,   70, 4.0,  'Urban residential, 4 du/acre'),
        ('king',      'R-6',  7200,   60, 6.0,  'Urban residential, 6 du/acre'),
        ('king',      'R-8',  5000,   50, 8.0,  'Urban residential, 8 du/acre'),
        ('king',      'R-12', 3600,   30, 12.0, 'Urban residential, 12 du/acre'),
        ('king',      'R-18', 2400,   0,  18.0, 'Urban residential, 18 du/acre'),
        ('king',      'R-48', 1800,   0,  48.0, 'Urban residential, 48 du/acre'),
        ('snohomish', 'R-7200',  7200, 60, 6.0,  'Residential 7200 sf min lot'),
        ('snohomish', 'R-8400',  8400, 70, 5.2,  'Residential 8400 sf min lot'),
        ('snohomish', 'R-9600',  9600, 80, 4.5,  'Residential 9600 sf min lot'),
        ('snohomish', 'LDMR',    5000, 50, 8.7,  'Low density multifamily residential'),
        ('skagit',    'R',     12500, 80, 3.5,  'Residential general'),
        ('skagit',    'RRv',   43560, 100, 1.0, 'Rural reserve'),
        ('skagit',    'R-C',    7000, 60, 6.2,  'Residential compact')
    """)


def downgrade() -> None:
    op.drop_table("shoreline_buffer")
    op.drop_table("critical_areas")
    op.drop_table("leads")
    op.drop_table("candidates")
    op.drop_table("zoning_rules")
    op.drop_table("parcels")
    lead_status_enum.drop(op.get_bind(), checkfirst=True)
    score_tier_enum.drop(op.get_bind(), checkfirst=True)
    county_enum.drop(op.get_bind(), checkfirst=True)
