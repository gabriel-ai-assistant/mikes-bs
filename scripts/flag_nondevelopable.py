#!/usr/bin/env python3
"""
Flag candidates as RISK_NON_DEVELOPABLE based on:
1. Owner name keywords (CITY OF, COUNTY OF, UNIVERSITY, PARK, etc.)
2. Zone codes for institutional/open space uses
3. Present use descriptions indicating non-developable use

Also rescores flagged candidates to Tier F (score capped at 30).
"""

import psycopg2
import sys

DB_URL = "postgresql://openclaw:password@postgis:5432/openclaw"

def get_db():
    return psycopg2.connect(DB_URL)

def main():
    conn = get_db()
    cur = conn.cursor()
    
    print("=== RISK_NON_DEVELOPABLE Flagging ===\n", flush=True)
    
    # -----------------------------------------------------------------------
    # Step 1: Flag by owner_name keywords
    # -----------------------------------------------------------------------
    print("Step 1: Flagging by owner_name keywords...", flush=True)
    cur.execute("""
        UPDATE candidates 
        SET tags = array_append(COALESCE(tags, '{}'), 'RISK_NON_DEVELOPABLE')
        WHERE parcel_id IN (
            SELECT id FROM parcels WHERE 
                owner_name ILIKE ANY(ARRAY[
                    '%CITY OF%',
                    '%COUNTY OF%',
                    '%STATE OF%',
                    '% STATE %',
                    '%WA STATE%',
                    '%UNIVERSITY%',
                    '%SCHOOL DIST%',
                    '%SCHOOL DISTRICT%',
                    '%PARK%',
                    '%CEMETERY%',
                    '%DEPT OF%',
                    '%TRANSIT%',
                    '%PORT OF%',
                    '%DNR%',
                    '%DEPT NATURAL%',
                    '%FIRE DIST%',
                    '%FIRE RESCUE%',
                    '%FIRE DEPT%',
                    '%WATER DIST%',
                    '%PUBLIC UTIL%',
                    '%HOUSING AUTH%',
                    '%PORT DIST%',
                    '%RECREATION%',
                    '%CONSERVATION%',
                    '%NATURE RESERVE%',
                    '%WILDLIFE%'
                ])
        )
        AND 'RISK_NON_DEVELOPABLE' != ALL(COALESCE(tags, '{}'))
    """)
    owner_flagged = cur.rowcount
    print(f"  Owner name flags: {owner_flagged} candidates", flush=True)
    conn.commit()
    
    # -----------------------------------------------------------------------
    # Step 2: Flag by zone_code institutional/open-space patterns
    # -----------------------------------------------------------------------
    print("Step 2: Flagging by zone_code...", flush=True)
    cur.execute("""
        UPDATE candidates 
        SET tags = array_append(COALESCE(tags, '{}'), 'RISK_NON_DEVELOPABLE')
        WHERE parcel_id IN (
            SELECT id FROM parcels WHERE 
                zone_code ILIKE ANY(ARRAY[
                    '%OSP%',   -- Open Space Preservation
                    'P-%',     -- Park zones
                    '%INS%',   -- Institutional
                    '%CF%',    -- Community Facility
                    '%GC%',    -- Government/Civic
                    'OS%',     -- Open Space
                    '%NR%',    -- Natural Resource
                    '%AG%',    -- Agricultural (large lots)
                    '%FR%',    -- Forest Resource
                    '%RR/5%'   -- Rural Residential 5-acre (large, often public)
                ])
        )
        AND 'RISK_NON_DEVELOPABLE' != ALL(COALESCE(tags, '{}'))
    """)
    zone_flagged = cur.rowcount
    print(f"  Zone code flags: {zone_flagged} candidates", flush=True)
    conn.commit()
    
    # -----------------------------------------------------------------------
    # Step 3: Flag by present_use field if it exists
    # -----------------------------------------------------------------------
    print("Step 3: Flagging by present_use field...", flush=True)
    cur.execute("""
        UPDATE candidates 
        SET tags = array_append(COALESCE(tags, '{}'), 'RISK_NON_DEVELOPABLE')
        WHERE parcel_id IN (
            SELECT id FROM parcels WHERE 
                present_use ILIKE ANY(ARRAY[
                    '%PARK%',
                    '%CEMETERY%',
                    '%SCHOOL%',
                    '%UNIVERSITY%',
                    '%CHURCH%',
                    '%GOVERNMENT%',
                    '%MILITARY%',
                    '%FOREST%',
                    '%WILDLIFE%',
                    '%WETLAND%',
                    '%OPEN SPACE%',
                    '%RECREATION%',
                    '%HOSPITAL%',
                    '%FIRE STATION%',
                    '%PUBLIC%'
                ])
        )
        AND 'RISK_NON_DEVELOPABLE' != ALL(COALESCE(tags, '{}'))
    """)
    use_flagged = cur.rowcount
    print(f"  Present use flags: {use_flagged} candidates", flush=True)
    conn.commit()
    
    # -----------------------------------------------------------------------
    # Step 4: Count total flagged
    # -----------------------------------------------------------------------
    cur.execute("""
        SELECT count(*) FROM candidates 
        WHERE 'RISK_NON_DEVELOPABLE' = ANY(COALESCE(tags, '{}'))
    """)
    total_flagged = cur.fetchone()[0]
    print(f"\nTotal candidates flagged RISK_NON_DEVELOPABLE: {total_flagged}", flush=True)
    
    # -----------------------------------------------------------------------
    # Step 5: Rescore flagged candidates to Tier F
    # -----------------------------------------------------------------------
    print("\nStep 5: Rescoring flagged candidates to Tier F...", flush=True)
    cur.execute("""
        UPDATE candidates 
        SET score = LEAST(score, 30),
            score_tier = 'F'
        WHERE 'RISK_NON_DEVELOPABLE' = ANY(COALESCE(tags, '{}'))
        AND score_tier IN ('A','B','C','D','E')
    """)
    rescored = cur.rowcount
    print(f"  Rescored to Tier F: {rescored} candidates", flush=True)
    conn.commit()
    
    # -----------------------------------------------------------------------
    # Step 6: Show breakdown by owner/zone
    # -----------------------------------------------------------------------
    print("\nTop flagged owners:", flush=True)
    cur.execute("""
        SELECT p.owner_name, count(*) as cnt
        FROM candidates c
        JOIN parcels p ON c.parcel_id = p.id
        WHERE 'RISK_NON_DEVELOPABLE' = ANY(COALESCE(c.tags, '{}'))
        GROUP BY p.owner_name
        ORDER BY cnt DESC
        LIMIT 15
    """)
    for row in cur.fetchall():
        print(f"  {row[1]:4d}  {row[0]}", flush=True)
    
    print("\n=== Done ===", flush=True)
    print(f"Summary: owner_name={owner_flagged}, zone_code={zone_flagged}, present_use={use_flagged}, total={total_flagged}, rescored={rescored}", flush=True)
    
    cur.close()
    conn.close()

if __name__ == '__main__':
    main()
