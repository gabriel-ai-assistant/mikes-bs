#!/usr/bin/env python3
"""
Load Snohomish County sales history from XLSX.

Usage:
    python3 scripts/load_sales_history.py /path/to/snoco_sales.xlsx

Source: Snohomish County Assessor AllSales export
Sheet: AllSales
Columns: LRSN, Parcel_Id, Status, ..., Sale_Date, Sale_Price, ..., Deed_Type, ...
"""
import sys
import os
import psycopg2
import openpyxl
from datetime import datetime, date

DB_URL = os.getenv('DATABASE_URL', 'postgresql://openclaw:password@localhost:5433/openclaw')

COL_PARCEL = 1
COL_OWNER  = 8
COL_DATE   = 9
COL_PRICE  = 10
COL_INSTR  = 12


def main(input_file):
    from urllib.parse import urlparse
    u = urlparse(DB_URL)
    conn = psycopg2.connect(
        host=u.hostname, port=u.port or 5432,
        dbname=u.path.lstrip('/'), user=u.username, password=u.password
    )
    cur = conn.cursor()

    cur.execute("""
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
    cur.execute("TRUNCATE parcel_sales RESTART IDENTITY;")
    conn.commit()

    wb = openpyxl.load_workbook(input_file, read_only=True)
    ws = wb['AllSales']

    BATCH = 2000
    rows = []
    loaded = 0
    skipped = 0
    header_done = False

    for row in ws.iter_rows(values_only=True):
        if not header_done:
            header_done = True
            continue
        parcel_number = row[COL_PARCEL]
        if not parcel_number:
            skipped += 1
            continue
        parcel_number = str(parcel_number).strip()

        raw_date = row[COL_DATE]
        if isinstance(raw_date, (datetime, date)):
            sale_date = raw_date.date() if isinstance(raw_date, datetime) else raw_date
        else:
            sale_date = None

        raw_price = row[COL_PRICE]
        try:
            sale_price = float(raw_price) if raw_price is not None else None
        except (ValueError, TypeError):
            sale_price = None

        owner_name = str(row[COL_OWNER]).strip() if row[COL_OWNER] else None
        instrument = str(row[COL_INSTR]).strip() if row[COL_INSTR] else None

        rows.append((parcel_number, sale_date, sale_price, owner_name, owner_name, instrument))
        if len(rows) >= BATCH:
            cur.executemany(
                "INSERT INTO parcel_sales (parcel_number, sale_date, sale_price, seller_name, buyer_name, instrument) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                rows
            )
            conn.commit()
            loaded += len(rows)
            rows = []

    if rows:
        cur.executemany(
            "INSERT INTO parcel_sales (parcel_number, sale_date, sale_price, seller_name, buyer_name, instrument) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            rows
        )
        conn.commit()
        loaded += len(rows)

    wb.close()
    print(f"Loaded {loaded:,} sales records (skipped {skipped:,})")

    # Update parcels with most recent sale
    cur.execute("""
    UPDATE parcels p SET
        last_sale_date = s.sale_date,
        last_sale_price = s.sale_price::integer
    FROM (
        SELECT DISTINCT ON (parcel_number) parcel_number, sale_date, sale_price
        FROM parcel_sales
        WHERE sale_price > 0
        ORDER BY parcel_number, sale_date DESC NULLS LAST
    ) s
    WHERE p.parcel_id = s.parcel_number
      AND (p.last_sale_date IS NULL OR s.sale_date > p.last_sale_date);
    """)
    updated = cur.rowcount
    conn.commit()
    print(f"Updated {updated:,} parcels with real last_sale data")

    cur.close()
    conn.close()


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else '/tmp/snoco_sales.xlsx')
