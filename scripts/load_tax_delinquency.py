#!/usr/bin/env python3
"""
Load Snohomish County tax delinquency data.

Usage:
    python3 scripts/load_tax_delinquency.py /path/to/snoco_tax_list.csv

Source: https://snohomishcountywa.gov/DocumentCenter/View/142441/snohomish_tax_data_totals
Format: Pipe-delimited, UTF-8 BOM, no header row
Columns (0-indexed):
  0: parcel_id, 1: tax_year, 2-6: property address, 7-12: owner/mailing,
  13: listing_date, 14: delinquent_amount, 15: first_half, 16: second_half
"""
import sys
import psycopg2
import os

DB_URL = os.getenv('DATABASE_URL', 'postgresql://openclaw:password@localhost:5433/openclaw')


def main(input_file):
    import psycopg2
    from urllib.parse import urlparse

    u = urlparse(DB_URL)
    conn = psycopg2.connect(
        host=u.hostname, port=u.port or 5432,
        dbname=u.path.lstrip('/'), user=u.username, password=u.password
    )
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS tax_delinquency (
        parcel_id TEXT PRIMARY KEY,
        delinquent_amount NUMERIC,
        tax_year INT,
        status TEXT,
        fetched_at TIMESTAMP DEFAULT NOW()
    );
    """)
    cur.execute("TRUNCATE tax_delinquency;")
    conn.commit()

    BATCH = 5000
    rows = []
    loaded = 0
    skipped = 0

    with open(input_file, 'r', encoding='utf-8-sig', errors='replace') as f:
        for line in f:
            parts = line.rstrip('\n\r').split('|')
            if len(parts) < 15:
                skipped += 1
                continue
            parcel_id = parts[0].strip()
            if not parcel_id:
                skipped += 1
                continue
            try:
                tax_year = int(parts[1].strip()) if parts[1].strip() else None
            except ValueError:
                tax_year = None
            try:
                amt = float(parts[14].strip()) if parts[14].strip() else None
            except ValueError:
                amt = None

            rows.append((parcel_id, amt, tax_year, 'DELINQUENT'))
            if len(rows) >= BATCH:
                cur.executemany(
                    "INSERT INTO tax_delinquency (parcel_id, delinquent_amount, tax_year, status) "
                    "VALUES (%s, %s, %s, %s) ON CONFLICT (parcel_id) DO UPDATE "
                    "SET delinquent_amount=EXCLUDED.delinquent_amount, tax_year=EXCLUDED.tax_year",
                    rows
                )
                conn.commit()
                loaded += len(rows)
                rows = []

    if rows:
        cur.executemany(
            "INSERT INTO tax_delinquency (parcel_id, delinquent_amount, tax_year, status) "
            "VALUES (%s, %s, %s, %s) ON CONFLICT (parcel_id) DO UPDATE "
            "SET delinquent_amount=EXCLUDED.delinquent_amount, tax_year=EXCLUDED.tax_year",
            rows
        )
        conn.commit()
        loaded += len(rows)

    print(f"Loaded {loaded:,} delinquent parcels (skipped {skipped:,})")

    # Tag candidates
    cur.execute("""
    UPDATE candidates SET
        tags = array_append(COALESCE(tags, '{}'), 'TAX_DELINQUENT'),
        reason_codes = array_append(COALESCE(reason_codes, '{}'), 'SFI_TAX_DELINQUENT_CONFIRMED')
    WHERE parcel_id IN (
        SELECT p.id FROM parcels p
        JOIN tax_delinquency td ON p.parcel_id = td.parcel_id
    )
    AND 'TAX_DELINQUENT' != ALL(COALESCE(tags, '{}'));
    """)
    tagged = cur.rowcount
    conn.commit()
    print(f"Tagged {tagged:,} candidates as TAX_DELINQUENT")

    cur.close()
    conn.close()


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else '/tmp/snoco_tax_list.csv')
