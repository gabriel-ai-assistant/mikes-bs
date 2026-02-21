"""Initial schema with all tables and zoning seed data.

Revision ID: 001
Revises: None
Create Date: 2026-02-20
"""
from typing import Sequence, Union
from alembic import op

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'countyenum') THEN
                CREATE TYPE countyenum AS ENUM ('king', 'snohomish', 'skagit');
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'scoretierenum') THEN
                CREATE TYPE scoretierenum AS ENUM ('A', 'B', 'C');
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'leadstatusenum') THEN
                CREATE TYPE leadstatusenum AS ENUM ('new', 'reviewed', 'outreach', 'active', 'dead');
            END IF;
        END $$
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS parcels (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            parcel_id VARCHAR NOT NULL,
            county countyenum NOT NULL,
            address VARCHAR,
            owner_name VARCHAR,
            owner_mailing_address VARCHAR,
            lot_sf INTEGER,
            zone_code VARCHAR,
            present_use VARCHAR,
            assessed_value INTEGER,
            last_sale_price INTEGER,
            last_sale_date DATE,
            geometry geometry(POLYGON, 4326),
            ingested_at TIMESTAMP DEFAULT now(),
            updated_at TIMESTAMP DEFAULT now(),
            CONSTRAINT uq_parcel_county UNIQUE (parcel_id, county)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_parcels_parcel_id ON parcels (parcel_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS zoning_rules (
            county countyenum NOT NULL,
            zone_code VARCHAR NOT NULL,
            min_lot_sf INTEGER,
            min_lot_width_ft INTEGER,
            max_du_per_acre DOUBLE PRECISION,
            notes VARCHAR,
            PRIMARY KEY (county, zone_code)
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS candidates (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            parcel_id UUID NOT NULL REFERENCES parcels(id),
            score_tier scoretierenum,
            potential_splits INTEGER,
            estimated_land_value INTEGER,
            estimated_dev_cost INTEGER,
            estimated_build_cost INTEGER,
            estimated_arv INTEGER,
            estimated_profit INTEGER,
            estimated_margin_pct DOUBLE PRECISION,
            has_critical_area_overlap BOOLEAN DEFAULT false,
            has_shoreline_overlap BOOLEAN DEFAULT false,
            flagged_for_review BOOLEAN DEFAULT false,
            created_at TIMESTAMP DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            candidate_id UUID NOT NULL REFERENCES candidates(id),
            status leadstatusenum DEFAULT 'new',
            owner_phone VARCHAR,
            owner_email VARCHAR,
            notes TEXT,
            contacted_at TIMESTAMP,
            contact_method VARCHAR,
            outcome VARCHAR,
            created_at TIMESTAMP DEFAULT now(),
            updated_at TIMESTAMP DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS critical_areas (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            source VARCHAR,
            area_type VARCHAR,
            geometry geometry(POLYGON, 4326)
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS shoreline_buffer (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            geometry geometry(POLYGON, 4326)
        )
    """)

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
        ON CONFLICT DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS shoreline_buffer")
    op.execute("DROP TABLE IF EXISTS critical_areas")
    op.execute("DROP TABLE IF EXISTS leads")
    op.execute("DROP TABLE IF EXISTS candidates")
    op.execute("DROP TABLE IF EXISTS zoning_rules")
    op.execute("DROP TABLE IF EXISTS parcels")
    op.execute("DROP TYPE IF EXISTS leadstatusenum")
    op.execute("DROP TYPE IF EXISTS scoretierenum")
    op.execute("DROP TYPE IF EXISTS countyenum")
