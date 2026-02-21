#!/usr/bin/env python3
"""
Reverse geocode missing/unknown parcel addresses using OSM Nominatim.
Rate limited to 1 req/sec per Nominatim ToS.
"""

import psycopg2
import urllib.request
import urllib.parse
import json
import time
import re
import sys

DB_URL = "postgresql://openclaw:password@postgis:5432/openclaw"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
USER_AGENT = "MikesBuildingSystem/1.0 contact@holdendev.com"
MAX_PARCELS = 500
RATE_LIMIT_SEC = 1.1  # slightly above 1/sec to be safe

def get_db():
    return psycopg2.connect(DB_URL)

def is_unknown(addr):
    if not addr:
        return True
    normalized = re.sub(r'\s+', ' ', addr.strip().upper())
    # Match various "UNKNOWN" patterns
    if re.match(r'^(UNKNOWN[\s,]*)+$', normalized):
        return True
    if normalized == '':
        return True
    return False

def nominatim_reverse(lat, lon):
    """Call Nominatim reverse geocoding. Returns parsed result dict."""
    params = urllib.parse.urlencode({
        'lat': lat,
        'lon': lon,
        'format': 'json',
        'addressdetails': 1,
    })
    url = f"{NOMINATIM_URL}?{params}"
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        return data
    except Exception as e:
        print(f"  Nominatim error: {e}", flush=True)
        return None

def build_address(result):
    """Build a clean address string from Nominatim result."""
    if not result:
        return None
    addr = result.get('address', {})
    
    # Try to build: "123 Main St, City, ST"
    parts = []
    
    house = addr.get('house_number', '')
    road = addr.get('road', '') or addr.get('path', '') or addr.get('footway', '')
    city = (addr.get('city', '') or addr.get('town', '') or 
            addr.get('village', '') or addr.get('hamlet', '') or
            addr.get('suburb', '') or addr.get('county', ''))
    state = addr.get('state', '')
    
    if house and road:
        parts.append(f"{house} {road}")
    elif road:
        parts.append(road)
    
    if city:
        parts.append(city)
    
    if state:
        # Abbreviate state if possible
        parts.append(state)
    
    if parts:
        return ', '.join(parts)
    
    # Fallback to display_name (first ~80 chars)
    display = result.get('display_name', '')
    if display:
        return display[:120]
    
    return None

def detect_non_developable(result):
    """Check if Nominatim result indicates non-developable land."""
    if not result:
        return False
    
    non_dev_keywords = [
        'park', 'nature_reserve', 'university', 'college', 'school',
        'cemetery', 'hospital', 'government', 'military', 'recreation_ground',
        'conservation', 'forest', 'national_park', 'protected_area',
        'water', 'reservoir', 'wetland'
    ]
    
    # Check category/type/class fields
    cat = result.get('category', '').lower()
    typ = result.get('type', '').lower()
    cls = result.get('class', '').lower()
    
    for keyword in non_dev_keywords:
        if keyword in cat or keyword in typ or keyword in cls:
            return True
    
    # Check address components
    addr = result.get('address', {})
    for key, val in addr.items():
        val_lower = str(val).lower()
        key_lower = key.lower()
        for keyword in non_dev_keywords:
            if keyword in val_lower or keyword in key_lower:
                return True
    
    return False

def main():
    conn = get_db()
    cur = conn.cursor()
    
    print("Querying parcels with unknown/missing addresses...", flush=True)
    
    # Get top 500 missing-address parcels by lot_sf (largest first)
    # Note: %% escapes literal % in psycopg2 queries
    cur.execute("""
        SELECT 
            id,
            parcel_id,
            address,
            ST_Y(ST_Centroid(geometry)) as lat,
            ST_X(ST_Centroid(geometry)) as lon,
            lot_sf
        FROM parcels
        WHERE (
            address IS NULL 
            OR address = ''
            OR UPPER(TRIM(address)) ~ '^(UNKNOWN[[:space:],]*)+$'
            OR UPPER(address) ILIKE 'UNKNOWN ADDRESS%%'
            OR address ILIKE '%%UNKOWN%%'
        )
        AND geometry IS NOT NULL
        ORDER BY lot_sf DESC NULLS LAST
        LIMIT %s
    """, (MAX_PARCELS,))
    
    rows = cur.fetchall()
    print(f"Found {len(rows)} parcels to geocode", flush=True)
    
    geocoded = 0
    failed = 0
    non_dev_found = []
    
    for i, (pid, parcel_id, old_addr, lat, lon, lot_sf) in enumerate(rows):
        print(f"[{i+1}/{len(rows)}] Parcel {parcel_id} ({lot_sf:.0f} sf) lat={lat:.4f} lon={lon:.4f}", flush=True)
        
        result = nominatim_reverse(lat, lon)
        
        if result:
            new_addr = build_address(result)
            if new_addr and not is_unknown(new_addr):
                cur.execute(
                    "UPDATE parcels SET address = %s, updated_at = NOW() WHERE id = %s",
                    (new_addr, pid)
                )
                print(f"  -> {new_addr}", flush=True)
                geocoded += 1
                
                # Check if non-developable
                if detect_non_developable(result):
                    non_dev_found.append(pid)
                    print(f"  ** RISK_NON_DEVELOPABLE detected (type={result.get('type')}, class={result.get('class')})", flush=True)
            else:
                print(f"  -> No usable address from Nominatim", flush=True)
                failed += 1
        else:
            failed += 1
        
        conn.commit()
        time.sleep(RATE_LIMIT_SEC)
    
    print(f"\n=== Geocoding Complete ===", flush=True)
    print(f"Geocoded: {geocoded}", flush=True)
    print(f"Failed/no result: {failed}", flush=True)
    print(f"Non-developable detected by geocode: {len(non_dev_found)}", flush=True)
    
    # Flag non-developable from geocoding results
    if non_dev_found:
        cur.execute("""
            UPDATE candidates 
            SET tags = array_append(tags, 'RISK_NON_DEVELOPABLE')
            WHERE parcel_id IN %s
            AND 'RISK_NON_DEVELOPABLE' != ALL(COALESCE(tags, '{}'))
        """, (tuple(non_dev_found),))
        print(f"Flagged {cur.rowcount} candidates as RISK_NON_DEVELOPABLE via geocode check", flush=True)
        conn.commit()
    
    cur.close()
    conn.close()

if __name__ == '__main__':
    main()
