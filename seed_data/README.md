# Seed Data — Mike's Building System

All source data files used to populate the mikes-bs database for Snohomish County, WA.

## Storage Locations

- **Small files (< 25MB)**: Committed to this repo under `seed_data/snohomish/`
- **Large files (> 25MB)**: Stored on Google Drive → `mikes-bs-seed-data/` folder + permanently on aidev01 at `/home/gabriel/approved_files/`
- **All files**: Backed up on aidev01 at `/home/gabriel/approved_files/`

Google Drive folder: `mikes-bs-seed-data` (gabriel.opus.soong@gmail.com)

---

## File Inventory

### ✅ In Repo (committed)

| File | Size | Source | Loader | Description |
|------|------|--------|--------|-------------|
| `snohomish/ruta_boundary.gpkg` | 220K | Snohomish County GIS | `openclaw/enrichment/ruta.py` | Rural Urban Transition Area boundaries (24 polygons) — fires `EDGE_SNOCO_RUTA_ARBITRAGE` (+30 pts) |
| `snohomish/snoco_sales_history.xlsx` | 21MB | Snohomish County Assessor | `scripts/load_sales_history.py` | 73,187 property sales records (AllSales sheet) — populates `parcel_sales` table, enriches `last_sale_date/price` on parcels |

### 📁 Large Files (Google Drive + aidev01 only)

| File | Size | Source | Loader | Description |
|------|------|--------|--------|-------------|
| `Streets.geojson` | 93MB | Snohomish County GIS | `scripts/load_streets.py` | Road centerlines — populates `road_centerlines` table, used for parcel frontage calculation |
| `Contours_5ft_NE.gpkg` | 1.1GB | Snohomish County GIS | `scripts/load_contours.py` | 5ft elevation contours, NE quadrant |
| `Contours_5ft_NW.gpkg` | 1.0GB | Snohomish County GIS | `scripts/load_contours.py` | 5ft elevation contours, NW quadrant |
| `Contours_5ft_SE.gpkg` | 1.3GB | Snohomish County GIS | `scripts/load_contours.py` | 5ft elevation contours, SE quadrant |
| `Contours_5ft_SW.gpkg` | 1.0GB | Snohomish County GIS | `scripts/load_contours.py` | 5ft elevation contours, SW quadrant |

### ✅ Already Loaded (original seed files, in repo)

| File | Source | Loader | Description |
|------|--------|--------|-------------|
| `Parcels_422492635121449766.gpkg` | Snohomish County GIS | `openclaw/ingest/delta_sync.py` | 314,017 parcels with geometry (SRID 3857) |
| `Future_Land_Use_8877344351894507330.gpkg` | Snohomish County GIS | `scripts/load_future_land_use.py` | Zone codes + UGA boundaries |
| `WA_geopackage_wetlands.zip` | WA Dept of Ecology | `scripts/load_critical_areas.py` | Wetland boundaries statewide |
| `Agricultural_Land_3103138862041303774.gpkg` | Snohomish County GIS | `scripts/load_critical_areas.py` | Agricultural notification areas |

---

## Data Sources

- **Snohomish County GIS Portal**: https://www.snohomishcountywa.gov/966/GIS-Data
- **Snohomish County Assessor Sales Data**: https://www.snohomishcountywa.gov/1683/Assessor-Data
- **Snohomish County Treasurer Tax List**: https://snohomishcountywa.gov/DocumentCenter/View/142441/snohomish_tax_data_totals
- **WA Dept of Ecology Wetlands**: https://ecology.wa.gov/research-data/gis-mapping/geodata-catalog

---

## Loading Order (fresh install)

```bash
# 1. Apply all migrations
alembic upgrade head

# 2. Load parcels (required first — everything joins to this)
python -m openclaw.ingest.delta_sync  # or load from GPKG

# 3. Load spatial reference data
python scripts/load_future_land_use.py    # zone codes + UGA
python scripts/load_critical_areas.py    # wetlands + ag

# 4. Score candidates
python -m openclaw.analysis.rule_engine  # initial scoring

# 5. Enrich with additional data
python -m openclaw.enrichment.spatial    # populate uga_outside boolean
python -m openclaw.enrichment.ruta       # RUTA boundary tagging

# 6. Load sales history + tax delinquency
python scripts/load_sales_history.py     # parcel_sales table
python scripts/load_tax_delinquency.py   # tax_delinquency table (auto-downloads)

# 7. Load road centerlines (requires ogr2ogr / gdal-bin)
ogr2ogr -f PostgreSQL PG:'...' seed_data/snohomish/streets.geojson -nln road_centerlines

# 8. Load contours (heavy — run overnight)
# python scripts/load_contours.py  # loads from approved_files/

# 9. Final rescore with all enrichments
python -m openclaw.analysis.rule_engine

# 10. Run discovery
python -m openclaw.discovery.engine --county snohomish
```

---

## Notes

- Contour files require ~20GB+ of PostGIS storage and several hours to load — run overnight
- Tax delinquency list is downloaded automatically by `load_tax_delinquency.py` — no local file needed
- Slope data for A/B/C candidates is fetched on-demand from OpenTopoData API (free, 1 req/sec)
- All file sizes are approximate; exact sizes vary by export date
