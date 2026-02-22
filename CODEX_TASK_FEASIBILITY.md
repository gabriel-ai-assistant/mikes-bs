# CODEX TASK: Subdivision Feasibility Engine — mikes-bs Integration

## YOUR JOB

You are building a production-grade geospatial subdivision feasibility analysis engine
and integrating it into the existing mikes-bs app. Do NOT create a separate repo.
Everything goes into THIS repo.

**Before writing a single line of code**: read the full existing codebase. Understand
what exists. Don't duplicate. Don't break anything. Build on top of it cleanly.

---

## STEP 0 — FULL CODEBASE AUDIT (do this first)

Read every file in:
- `openclaw/analysis/` — all analysis modules
- `openclaw/db/models.py` — DB schema
- `openclaw/web/app.py` — all routes
- `openclaw/web/templates/` — all templates
- `alembic/versions/` — migration history

Document what exists in a file: `openclaw/analysis/feasibility/AUDIT.md`

Then do the tag inventory (Phase 1 from the directive):
- Read `openclaw/analysis/edge_config.py` — all EDGE/RISK tag weights
- Read `openclaw/analysis/tagger.py` — tag producers
- Read `openclaw/analysis/rule_engine.py` — scoring consumers
- Output: `openclaw/analysis/feasibility/tag_inventory.json`

---

## STEP 1 — PACKAGE STRUCTURE

Create this structure inside the existing repo:

```
openclaw/analysis/feasibility/
    __init__.py
    context.py          # AnalysisContext dataclass — shared state passed between phases
    phase1_tags.py      # Tag inventory (audit existing system)
    phase2_parcel.py    # Parcel geometry acquisition (ArcGIS REST)
    phase25_zoning.py   # Zoning lookup + rules
    phase3a_streams.py  # NHD + Snoco watercourse buffers
    phase3b_wetlands.py # NWI wetland buffers
    phase3c_flood.py    # FEMA NFHL flood zones
    phase3d_slope.py    # USGS 3DEP DEM + slope
    phase3e_geology.py  # DNR landslide/liquefaction/volcanic
    phase3f_soils.py    # NRCS SDA soil data + septic viability
    phase3g_utilities.py # Snoco utility districts (water/sewer)
    phase3h_roads.py    # Road frontage + access
    phase3i_flu.py      # Future land use
    phase3j_shoreline.py # Shoreline management
    phase4_buildable.py # Buildable area computation
    phase425_lots.py    # Lot layout generator (5 strategies)
    phase43_stormwater.py # Stormwater reserve
    phase45_driveways.py  # Driveway routing
    phase475_envelopes.py # Building envelopes
    phase5_scoring.py   # Layout scoring + ranking
    phase6_costs.py     # Cost estimation
    phase7_export.py    # GeoJSON/GPKG/PNG export
    orchestrator.py     # Calls all phases in order
    api_client.py       # Shared ArcGIS REST client with retry/cache
    AUDIT.md
    tag_inventory.json

openclaw/config/
    zoning_rules.json
    buffer_rules.json
    scoring_weights.json

tests/
    test_feasibility.py  # 5 test parcels
```

---

## STEP 2 — KEY IMPLEMENTATION RULES

### AnalysisContext (context.py)
```python
@dataclass
class AnalysisContext:
    parcel_id: str
    parcel_geom: Optional[GeoDataFrame] = None  # EPSG:2285
    zoning_code: Optional[str] = None
    zoning_rules: Optional[dict] = None
    constraint_layers: dict = field(default_factory=dict)
    buildable_geom: Optional[GeoDataFrame] = None
    layouts: list = field(default_factory=list)
    tags: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    cost_estimates: dict = field(default_factory=dict)
    export_paths: dict = field(default_factory=dict)
```

All phases receive ctx, mutate it, return it.

### api_client.py — ArcGIS REST client
- `query_feature_layer(url, layer_id, geometry=None, where="1=1", out_sr=2285)` → GeoDataFrame
- `query_by_parcel_id(url, layer_id, parcel_id_field, parcel_id)` → GeoDataFrame
- `export_image_raster(url, bbox, bbox_sr=2285, size=(500,500), rendering_rule=None)` → numpy array
- Always reproject result to EPSG:2285
- Retry 3x with exponential backoff on 5xx
- Cache results in `/tmp/feasibility_cache/{hash}.geojson`
- Add 0.5s delay between requests
- Return empty GeoDataFrame on failure, add `RISK_DATA_INCOMPLETE` to ctx.tags

### CRS requirement
ALL geometry operations in EPSG:2285 (WA State Plane North, NAD83, US Feet).
Input from APIs may be WGS84 or Web Mercator — always reproject on ingest.
```python
gdf = gdf.to_crs(epsg=2285)
```

---

## STEP 3 — PHASE IMPLEMENTATIONS

### phase2_parcel.py
Try these endpoints in order (fallback chain):
1. `https://gismaps.snoco.org/snocogis2/rest/services/cadastral/tax_parcels/MapServer` 
   - query: `where=Parcel_ID='{parcel_id}'`
2. `https://gismaps.snoco.org/snocogis2/rest/services/planning/mp_ParcelLabels/MapServer`
3. `https://gis.snoco.org/sas/rest/services/SCOPI/SCOPI_Labels_House_Number/MapServer/0`

If parcel not found in any → raise `ParcelNotFoundError`
If parcel is in an incorporated city → raise `CityParcelError` (out of scope)

Key fields to extract: Parcel_ID, GIS_ACRES, GIS_SQ_FT, address, owner

### phase25_zoning.py
Query: `https://gismaps.snoco.org/snocogis2/rest/services/planning/mp_Zoning_OZ/MapServer`
Use parcel centroid for spatial query.
Load rules from `openclaw/config/zoning_rules.json`.
Feasibility gate: if parcel_sf / min_lot_sqft < 2 → add `RISK_NOT_SUBDIVIDABLE` and set ctx.stop=True

### phase3a_streams.py
Primary: `https://gismaps.snoco.org/snocogis/rest/services/hydrography/Watercourse/MapServer` layer 0
Fallback: NHD `https://hydro.nationalmap.gov/arcgis/rest/services/nhd/MapServer` layer 6
Buffer rules from `buffer_rules.json`:
- Type S: 150ft, Type F: 100ft, Type Np: 50ft, Type Ns: 25ft, default: 75ft
Tags: `RISK_STREAM_BUFFER_IMPACT` if buffer_overlap_pct > 20

### phase3b_wetlands.py  
`https://fwspublicservices.wim.usgs.gov/wetlandsmapservice/rest/services/Wetlands/MapServer` layer 0
Decode Cowardin code → category (I/II/III/IV)
Buffer: Cat I=100ft, Cat II=50ft, Cat III=40ft, Cat IV=25ft
Tags: `RISK_WETLAND_PRESENT`, `RISK_WETLAND_BUFFER_IMPACT`

### phase3c_flood.py
`https://hazards.fema.gov/gis/nfhl/rest/services/public/NFHL/MapServer` layer 28
Tags: `RISK_FEMA_100YR_FLOOD` (Zone A/AE/AO/AH), `INFO_FEMA_500YR_FLOOD` (Zone X shaded)
Special: `RISK_ENTIRE_PARCEL_FLOODPLAIN` if >90% of parcel is Zone A/AE

### phase3d_slope.py
USGS 3DEP: `https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer`
Use exportImage with renderingRule={"rasterFunction":"Slope Degrees"}
Compute % of parcel area with slope ≥33%, 15-33%
Tags: `RISK_STEEP_SLOPE_33PCT`, `RISK_EROSION_HAZARD_15PCT`, `INFO_SLOPE_CONSTRAINT`

### phase3e_geology.py
DNR Landslides: `https://gis.dnr.wa.gov/site1/rest/services/Public_Geology/Landslide_Inventory_Database/MapServer`
Note: CRS is EPSG:2927 — reproject to 2285
DNR Ground Response: liquefaction + seismic
DNR Volcanic Hazards: lahar zones
Tags: `RISK_LANDSLIDE_HAZARD`, `RISK_LIQUEFACTION`, `RISK_LAHAR_ZONE`, `RISK_GEOLOGIC_HAZARD`

### phase3f_soils.py
NRCS SDA: `https://SDMDataAccess.sc.egov.usda.gov/Tabular/post.rest`
Get mukey from parcel centroid WKT, then query soil properties.
Query septic interpretation from cointerp table.
Also check: `https://gis.snoco.org/host/rest/services/Hosted/Septic_Parcels/FeatureServer/0`
Tags: `RISK_POOR_SOIL_DRAINAGE`, `RISK_SEPTIC_LIMITATION`, `INFO_SOIL_TYPE`

### phase3g_utilities.py
`https://gis.snoco.org/scd/rest/services/MapService/pds_utility_districts/MapServer`
Layer 0: Water Districts, Layer 1: Sewer Districts
Spatial contains check for parcel centroid
Tags: `INFO_PUBLIC_SEWER_AVAILABLE`, `INFO_PUBLIC_WATER_AVAILABLE`, 
      `RISK_SEPTIC_REQUIRED`, `RISK_WELL_REQUIRED`

### phase3h_roads.py
`https://gismaps.snoco.org/snocogis2/rest/services/planning/mp_Transportation/MapServer`
Find road segments within 200ft of parcel boundary.
Compute frontage = length of parcel boundary within 50ft of road centerline.
Tags: `RISK_INSUFFICIENT_FRONTAGE`, `INFO_FLAG_LOT_CANDIDATE`, `INFO_ROAD_FRONTAGE_FT`

### phase3i_flu.py
`https://gismaps.snoco.org/snocogis/rest/services/planning/mp_Future_Land_Use/MapServer`
Tags: `INFO_FLU_DESIGNATION`, `INFO_FLU_ZONING_MISMATCH`

### phase3j_shoreline.py
`https://gismaps.snoco.org/snocogis/rest/services/planning/mp_ShorelineManagementProgram/MapServer`
If parcel within 200ft of shoreline-designated body → `RISK_SHORELINE_JURISDICTION`

### phase4_buildable.py
Union all constraint buffers into one "excluded" polygon.
Apply zoning setbacks to parcel boundary (inset parcel by front/side/rear setback).
buildable = setback_envelope.difference(excluded_union)
If buildable area < 2 × min_lot_sqft → add `RISK_NOT_SUBDIVIDABLE`, set ctx.stop=True

### phase425_lots.py
5 strategies:
1. max_lots — grid/strip subdivision maximizing count
2. equal_split — equal area halves/thirds/etc
3. road_optimized — minimize shared road/driveway infrastructure
4. constraint_adaptive — keep lots as far from constraint edges as possible
5. hybrid — balance lot count vs. infrastructure

For each layout: validate min lot size, min lot width (simulate by checking bounding box),
assign short_plat (≤4 lots) or formal_subdivision (≥5 lots) tags.

### phase43_stormwater.py
Reserve 7.5% of buildable area for stormwater (midpoint of 5-10% range).
If remaining buildable after stormwater < lot_count × min_lot_sqft → `RISK_STORMWATER_CONSTRAINED`

### phase45_driveways.py
For each lot: find nearest point on road network.
Draw straight-line driveway from lot centroid to road access point.
Sample DEM along line at 10 intervals to compute grade.
Max grade 12%, min width 12ft, turnaround if >150ft.
Tags: `RISK_DRIVEWAY_INFEASIBLE`, `RISK_DRIVEWAY_STEEP`, `INFO_DRIVEWAY_LENGTH`

### phase475_envelopes.py
Inset each lot polygon by front/side/rear setbacks.
Compute largest inscribed rectangle (use shapely's minimum_rotated_rectangle as proxy).
Apply max_lot_coverage_pct.
Tags: `RISK_TIGHT_BUILDING_ENVELOPE` if envelope < 1500sqft

### phase5_scoring.py
Score each layout 0-100 per the weighted factors.
Apply bonus/penalty multipliers.
Store `SCORE_SUBDIVISION_FEASIBILITY` and `SCORE_BEST_LAYOUT` in ctx.tags.
Sort layouts by score descending.

### phase6_costs.py
Per layout: survey+engineering, plat application, road, utilities, stormwater, clearing.
Use per-unit rates from directive. Return `cost_estimate` dict per layout.

### phase7_export.py
Write all GeoJSON files to output_dir.
Write single GeoPackage with all layers.
Render PNG using matplotlib: parcel (black), constraints (red hatch), buildable (green),
lots (blue dashed), driveways (orange), envelopes (gray), north arrow, scale bar, legend.

---

## STEP 4 — WEB INTEGRATION

Add to `openclaw/web/app.py`:

```python
@app.post("/api/feasibility/{parcel_id}")
async def run_feasibility(parcel_id: str):
    # Spawn orchestrator, return job_id
    # Store result in feasibility_results table

@app.get("/api/feasibility/{parcel_id}/status")
async def feasibility_status(parcel_id: str):
    # Return job status + result summary

@app.get("/api/feasibility/{parcel_id}/result")
async def feasibility_result(parcel_id: str):
    # Return full JSON result

@app.get("/feasibility/{parcel_id}", response_class=HTMLResponse)
async def feasibility_page(parcel_id: str):
    # Render feasibility report page
```

Add DB migration for `feasibility_results` table:
- parcel_id (FK)
- status (pending/running/complete/failed)
- result_json (JSONB)
- tags (TEXT[])
- best_layout_id
- best_score
- created_at, completed_at

Add a "Run Feasibility Analysis" button on the property detail page (`/property/{parcel_id}`).
Show status indicator. When complete, show summary: best layout, lot count, score, estimated cost.
Link to full feasibility report page.

Add to candidates list and modal: if feasibility result exists for this parcel, show
`SCORE_SUBDIVISION_FEASIBILITY` score badge.

---

## STEP 5 — CONFIG FILES

### openclaw/config/zoning_rules.json
Include all Snohomish County residential zones:
R-4, R-5, R-6, R-7.2, R-8, R-9.6, R-12.5, R-18, R-20, R-24, R-48,
RA-2.5, RA-5, RA-10, MR, LI, B-1, B-2, A-10, F, NB

Use the values from the directive as a starting point. Where values aren't given, use
reasonable estimates from SCC Title 30 Chapter 30.23 and 30.31A.

### openclaw/config/buffer_rules.json
Stream type → buffer distance in feet.
Wetland category → buffer distance in feet.

### openclaw/config/scoring_weights.json
All scoring weights as env-overridable config (same pattern as edge_config.py).

---

## STEP 6 — DEPENDENCIES

Add to requirements.txt (create if missing):
```
geopandas>=0.14
shapely>=2.0
rasterio>=1.3
fiona>=1.9
pyproj>=3.6
requests>=2.31
matplotlib>=3.7
numpy>=1.24
```

DO NOT add ESRI SDKs. Use only open-source.

---

## STEP 7 — TESTS

`tests/test_feasibility.py` — test against 5 real Snohomish County parcel IDs.
First, query the tax parcel layer to find suitable test cases:
- Easy: RA-10 zone, >5 acres, no constraints near centroid
- Medium: R-9.6, 2-3 acres, stream on one side
- Hard: near wetlands + steep slope + narrow frontage
- Edge: high flood zone overlap
- Edge: at UGA boundary

For each test: run full orchestrator, assert:
- parcel geometry loaded
- at least one constraint layer returned data (or gracefully skipped)
- buildable area computed (may be 0)
- if subdividable: at least 2 layouts generated
- export files created

---

## STEP 8 — AFTER EVERYTHING IS BUILT

1. Run: `python -m pytest tests/test_feasibility.py -v` — fix any failures
2. Run a real analysis on parcel `30053400401800` (a known large parcel in Snohomish County) 
   to verify end-to-end pipeline produces output
3. Commit everything: `git add -A && git commit -m "feat: subdivision feasibility engine (7-phase pipeline)"`
4. Push: `git push origin main`

---

## CONSTRAINTS

- No new boolean columns — tags only (TEXT[])
- All weights/thresholds config-driven (env vars or JSON config)
- Fail closed on missing data — tag `RISK_DATA_INCOMPLETE`, continue
- Keep existing mikes-bs functionality intact — don't break anything
- Volume mount: `./openclaw:/app/openclaw` — web changes are live; restart needed for new routes
- Python 3.11+ syntax OK
- Use existing DB session pattern from `openclaw/db/session.py`
- Follow existing code style (SQLAlchemy, FastAPI, Jinja2)

## TIMELINE

This is a large build. Work methodically through each phase. Don't rush.
Do it right the first time. The auditor will review every module.
