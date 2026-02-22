"""Add tax_delinquency and parcel_sales tables.

Revision ID: 005
Revises: 004
Create Date: 2026-02-22
"""
from alembic import op
import sqlalchemy as sa

revision = '005'
down_revision = '004'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    CREATE TABLE IF NOT EXISTS tax_delinquency (
        parcel_id TEXT PRIMARY KEY,
        delinquent_amount NUMERIC,
        tax_year INT,
        status TEXT,
        fetched_at TIMESTAMP DEFAULT NOW()
    );
    """)

    op.execute("""
    CREATE TABLE IF NOT EXISTS parcel_sales (
        id SERIAL PRIMARY KEY,
        parcel_number TEXT NOT NULL,
        sale_date DATE,
        sale_price NUMERIC,
        seller_name TEXT,
        buyer_name TEXT,
        instrument TEXT,
        created_at TIMESTAMP DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS ix_parcel_sales_parcel_number ON parcel_sales(parcel_number);
    CREATE INDEX IF NOT EXISTS ix_parcel_sales_sale_date ON parcel_sales(sale_date);
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS parcel_sales;")
    op.execute("DROP TABLE IF EXISTS tax_delinquency;")
