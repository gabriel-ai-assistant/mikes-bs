# Mike's Building System — Architecture Discovery Report
*Generated 2026-02-22*

---

## 1. Tech Stack Summary

| Layer | Choice |
|---|---|
| **Backend** | Python 3.12 + FastAPI (sync + async handlers, Jinja2 server-side rendering) |
| **Database** | PostgreSQL 16 + PostGIS 3.4 (via Docker) |
| **Frontend** | Vanilla JS (no framework) — all HTML rendered server-side via Jinja2 templates |
| **ORM** | SQLAlchemy 2.0 (declarative base, sync sessions) + GeoAlchemy2 for geometry |
| **Migrations** | Alembic — 8 versions applied (001–008); versions NOT in volume mount, applied via direct SQL workaround |
| **App Server** | Uvicorn (standard extras) on port 8470 |
| **Reverse Proxy** | nginx — handles SSL termination + `/mikes-bs` path prefix via `ROOT_PATH` |
| **Geospatial** | GeoPandas, Shapely, PyProj, Rasterio, Fiona |
| **Background Jobs** | APScheduler (in-process) — nightly learning cron + delta sync; FastAPI `BackgroundTasks` for feasibility runs |
| **Package Manager** | pip with `requirements.txt`; `.venv` local virtualenv |
| **Deployment** | Docker Compose (`postgis`, `app`, `web` services); `./openclaw:/app/openclaw` volume mount for live code reload |
| **LLM Integration** | OpenAI GPT-4o (`openai` package, `OPENAI_API_KEY` env) — learning analyzer only |

---

## 2. File Tree (depth 2)

```
mikes-bs/
├── alembic/
│   ├── env.py
│   └── versions/           (001–008, NOT in volume mount)
├── openclaw/
│   ├── analysis/           (tagger, rule_engine, scorer, arbitrage, subdivision, subdivision_econ, dif/, feasibility/)
│   ├── config/             (zoning_rules.json, buffer_rules.json, scoring_weights.json)
│   ├── db/                 (models.py, session.py)
│   ├── discovery/          (engine.py — weekly batch candidate discovery)
│   ├── enrich/             (dom_fetcher, owner, skip_trace, slope_loader, tax_status)
│   ├── enrichment/         (ruta.py, spatial.py)
│   ├── ingest/             (snohomish.py, king.py, skagit.py, delta_sync.py, ruta_loader, transit_loader)
│   ├── learning/           (analyzer.py — feedback → GPT-4o → proposals)
│   ├── notify/             (digest.py)
│   ├── underwriting/       (engine.py)
│   ├── utils/              (geo.py)
│   ├── web/
│   │   ├── app.py          (~1,100 lines — all routes)
│   │   └── templates/      (9 Jinja2 templates)
│   ├── config.py
│   └── main.py
├── scripts/                (8 one-shot data load scripts)
├── seed_data/
├── tests/
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

---

## 3. Data Model Inventory

### `Parcel` — `openclaw/db/models.py`
The source of truth for a physical land parcel.

| Field | Type | Notes |
|---|---|---|
| `parcel_id` | String | Human-readable county parcel number (e.g. `30053400401800`) |
| `county` | Enum (king/snohomish/skagit) | |
| `address`, `owner_name`, `owner_address` | String | |
| `lot_sf`, `frontage_ft`, `parcel_width_ft` | Float | |
| `zone_code`, `present_use` | String | |
| `assessed_value`, `improvement_value`, `total_value` | Integer | |
| `last_sale_price`, `last_sale_date` | Integer/Date | |
| `geometry` | Geometry (EPSG:4326) | PostGIS |
| `corrdate` | DateTime | ArcGIS delta sync watermark |

Relationships: `→ candidates` (1:many), `→ feasibility_results` (1:many)

---

### `Candidate` — `openclaw/db/models.py`
A parcel that passed initial filtering and has a score/tier.

| Field | Type | Notes |
|---|---|---|
| `parcel_id` | UUID FK → parcels | |
| `score_tier` | Enum (A/B/C/D/E/F) | |
| `score` | Integer (0–100) | |
| `potential_splits` | Integer | = `splits_most_likely` (backward compat) |
| `splits_min`, `splits_max` | Integer | Range output |
| `splits_confidence` | String (HIGH/MEDIUM/LOW) | |
| `subdivision_access_mode` | String (DIRECT/SHARED_TRACT) | |
| `arbitrage_depth_score` | Integer | 0–100 |
| `economic_margin_pct` | Float | |
| `estimated_land_value`, `estimated_dev_cost`, `estimated_build_cost`, `estimated_arv`, `estimated_profit`, `estimated_margin_pct` | Integer/Float | Underwriting engine outputs |
| `has_critical_area_overlap`, `has_shoreline_overlap`, `flagged_for_review` | Boolean | |
| `tags` | TEXT[] | EDGE_* and RISK_* signal codes |
| `reason_codes` | TEXT[] | Human-readable score reasons |
| `subdivisibility_score` | Integer | 0–100 from `subdivision.py` |
| `subdivision_feasibility` | String | FEASIBLE/MARGINAL/INFEASIBLE/UNKNOWN |
| `subdivision_flags` | TEXT[] | |

Relationships: `→ parcel` (many:1), `→ leads` (1:many)

---

### `Lead` — `openclaw/db/models.py`
CRM record attached to a Candidate.

| Field | Type | Notes |
|---|---|---|
| `candidate_id` | UUID FK → candidates | |
| `status` | Enum (new/reviewed/outreach/active/dead) | |
| `owner_phone`, `owner_email` | String | |
| `notes` | Text | |
| `contacted_at`, `contact_method`, `outcome` | String/DateTime | |

---

### `FeasibilityResult` — `openclaw/db/models.py`
Output of the 7-phase feasibility pipeline run.

| Field | Type | Notes |
|---|---|---|
| `parcel_id` | UUID FK → parcels | |
| `status` | String (pending/running/complete/failed) | |
| `result_json` | JSONB | Full pipeline output |
| `tags` | TEXT[] | |
| `best_layout_id`, `best_score` | String/Float | |
| `completed_at` | DateTime | |

---

### Tag System — `openclaw/analysis/tagger.py` + `edge_config.py`
Not a DB table — tags are `TEXT[]` stored on `candidates.tags`. Prefix convention:
- `EDGE_*` — positive signals (boost score)
- `RISK_*` — negative signals (penalize score)
- `INFO_*` — informational (no score effect)

Current named tags (from `edge_config.py` + `tagger.py`):
```
EDGE_SNOCO_LSA_R5_RD_FR        +35 pts
EDGE_SNOCO_RUTA_ARBITRAGE      +30 pts
EDGE_WA_HB1110_MIDDLE_HOUSING  +25 pts
EDGE_WA_UNIT_LOT_SUBDIVISION   +20 pts
EDGE_SNOCO_RURAL_CLUSTER_BONUS +15 pts
EDGE_ARBITRAGE_DEPTH_HIGH      (from arbitrage.py, threshold=60)
EDGE_FRONTAGE_PREMIUM          (frontage > 150ft)
RISK_* (any)                   -8 pts each (capped at -30 total)
```

---

### `ZoningRule` — `openclaw/db/models.py`
Per-county per-zone development standards.

| Field | Type |
|---|---|
| `county`, `zone_code` | PK |
| `min_lot_sf`, `min_lot_width_ft`, `max_du_per_acre` | Integer/Float |

Also: `openclaw/config/zoning_rules.json` — Snohomish-specific rules used by feasibility engine.

---

### Scoring/Learning Tables (DB only, no ORM model)
- `scoring_rules` — dynamic rules with `field`, `operator`, `value`, `action` (exclude/set_tier/adjust_score), `priority`
- `candidate_feedback` — `(candidate_id, rating ['up'/'down'], category, notes)`
- `learning_proposals` — AI-generated weight adjustment proposals with `status` (pending/approved/rejected)
- `candidate_notes` — free-text notes per candidate

---

### Other Spatial Tables (raw SQL, no ORM model)
- `critical_areas` — source, area_type, geometry (EPSG:4326)
- `shoreline_buffer` — geometry
- `ruta_boundaries` — 24 polygons (Rural Urban Transition Area)
- `road_centerlines` — 55,096 segments
- `parcel_sales` — 73,187 records
- `tax_delinquency` — 308,677 records

---

## 4. API Surface

### Candidates / Scoring
```
GET  /api/candidates            Paginated list w/ filters: tier, tag, use_type, score_min, score_max, page, limit
GET  /api/candidate/{id}        Full candidate detail + parcel + financials + tags
GET  /api/tags                  All distinct tags in DB
GET  /api/use-types             All distinct present_use values (262)
POST /api/rescore               Trigger full re-score of all candidates
GET  /api/rescore/preview       Dry-run re-score summary
```

### Feedback & Notes
```
POST /api/candidate/{id}/feedback     thumbs_up / thumbs_down (up sets score ≥ 90 → Tier A)
GET  /api/candidate/{id}/feedback     Feedback history for candidate
GET  /api/feedback/stats              Aggregate feedback stats
POST /api/candidate/{id}/notes        Add a note
GET  /api/candidate/{id}/notes        Get notes (limit param)
```

### Feasibility Engine
```
POST /api/feasibility/{parcel_id}         Trigger 7-phase pipeline (async BackgroundTask)
GET  /api/feasibility/{parcel_id}/status  Poll job status
GET  /api/feasibility/{parcel_id}/result  Full JSON result
```

### Map
```
GET  /api/map/points    GeoJSON points for map overlay (supports tier/tag/bbox filters)
```

### Rules / Settings
```
GET    /api/rules             All scoring rules
POST   /api/rules             Create rule
PUT    /api/rules/{id}        Update rule
DELETE /api/rules/{id}        Delete rule
PATCH  /api/rules/{id}/toggle Enable/disable rule
```

### Learning
```
GET  /learning                          Review page (HTML)
POST /api/learning/run-now              Trigger nightly learning analysis immediately
POST /api/learning/{id}/approve         Approve proposal (writes to scoring_rules)
POST /api/learning/{id}/reject          Reject proposal
```

### Leads
```
GET  /leads                             Leads list page (HTML)
POST /api/lead/{id}/status              Update lead status
```

---

## 5. Frontend Page Inventory

| Route | Template | Data Fetched |
|---|---|---|
| `GET /` | `dashboard.html` | Tier distribution counts, top Tier A deals (score + splits + margin), Snohomish county map points |
| `GET /candidates` | `candidates.html` | `/api/candidates` (paginated, filtered), `/api/tags`, `/api/use-types` |
| `GET /property/{parcel_id}` | `property.html` | `/api/candidate/{id}` (full detail), feasibility result if exists |
| `GET /feasibility/{parcel_id}` | `feasibility.html` | `/api/feasibility/{parcel_id}/result` |
| `GET /map` | `map.html` | `/api/map/points` (GeoJSON) |
| `GET /leads` | `leads.html` | Leads + candidate + parcel JOIN (server-side rendered) |
| `GET /settings` | `settings.html` | `/api/rules` |
| `GET /learning` | `learning.html` | `learning_proposals` (server-side rendered) |

All pages are server-side rendered Jinja2. JS is inline per-template — no build step, no bundler.

---

## 6. External Integrations

| Service | File | Credentials |
|---|---|---|
| **Snohomish County ArcGIS REST** (parcel delta sync) | `openclaw/ingest/delta_sync.py` | None (public API) |
| **Snohomish County ArcGIS REST** (feasibility: parcels, zoning, roads, FLU, shoreline, critical areas) | `openclaw/analysis/feasibility/api_client.py` | None (public) |
| **King County ArcGIS REST** (parcel delta sync) | `openclaw/ingest/delta_sync.py` | None (public) |
| **FEMA NFHL** (flood zones) | `openclaw/analysis/feasibility/phase3c_flood.py` | None (public) |
| **USGS 3DEP** (slope/DEM) | `openclaw/analysis/feasibility/phase3d_slope.py` | None (public) |
| **OpenTopoData** (slope enrichment for existing candidates) | `openclaw/enrich/slope_loader.py` | None (public) |
| **USGS NHD** (streams fallback) | `openclaw/analysis/feasibility/phase3a_streams.py` | None (public) |
| **USFWS Wetlands** (NWI) | `openclaw/analysis/feasibility/phase3b_wetlands.py` | None (public) |
| **WA DNR** (geology/landslide) | `openclaw/analysis/feasibility/phase3e_geology.py` | None (public) |
| **NRCS SDA** (soils/septic) | `openclaw/analysis/feasibility/phase3f_soils.py` | None (public) |
| **OpenAI GPT-4o** (learning analyzer) | `openclaw/learning/analyzer.py` | `OPENAI_API_KEY` env var |
| **Lob** (direct mail) | `openclaw/enrich/owner.py` + `config.py` | `LOB_API_KEY` env var (not yet wired) |
| **Skip Trace API** | `openclaw/enrich/skip_trace.py` | `SKIP_TRACE_API_KEY` env var (not yet wired) |
| **SMTP** (notifications) | `openclaw/notify/digest.py` | `SMTP_HOST/PORT/USER/PASS` env vars |

---

## 7. Scoring / Learning Pipeline

### Full scoring flow

```
parcels (raw)
    │
    ▼ discovery/engine.py
candidates (initial filter: lot_sf, zone, UGA boundary)
    │
    ▼ analysis/tagger.py  ← edge_config.py (weights from env vars)
EDGE_* / RISK_* tags computed per candidate
    │
    ▼ analysis/subdivision.py  ← ZONE_MIN_LOT_SF lookup
splits_min / splits_max / splits_most_likely / access_mode / subdivisibility_score
    │
    ▼ analysis/subdivision_econ.py  ← env-driven cost thresholds
economic_margin_pct / economic_gate_pass
    │
    ▼ analysis/arbitrage.py  ← parcel_sales zone median PSF cache
arbitrage_depth_score / EDGE_ARBITRAGE_DEPTH_HIGH
    │
    ▼ analysis/rule_engine.py  ← scoring_rules table (DB-driven)
base_score (splits 40pts + value/lot 25pts + owner_type 15pts)
+ EDGE boosts (config weights)
+ RISK penalties (-8 each, cap -30)
+ DB rule adjustments (adjust_score / set_tier / exclude)
= final score (0–100) → tier (A–F via TIER_CUTOFFS)
    │
    ▼ candidates.score, score_tier, tags, reason_codes updated
      (bulk via psycopg2 execute_values)
```

### Weights — where defined

| Weight | Location | Override |
|---|---|---|
| EDGE tag weights | `edge_config.py` EdgeConfig dataclass | `EDGE_WEIGHT_*` env vars |
| Base score weights (splits/value/owner) | `rule_engine.py` constants | Hard-coded (SPLIT_WEIGHT=40, VALUE_WEIGHT=25, OWNER_WEIGHT=15) |
| Tier cutoffs | `rule_engine.py` TIER_CUTOFFS list | Hard-coded (A≥72, B≥58, C≥44, D≥30, E≥16) |
| Subdivision/econ/arbitrage weights | `openclaw/config/scoring_weights.json` + env vars | `ARBITRAGE_WEIGHT_*` env vars |
| Dynamic scoring rules | `scoring_rules` DB table | Admin UI at `/settings` |

### Feedback loop

```
User thumbs up/down
    │
    ▼ candidate_feedback table
    │
    ▼ APScheduler cron 02:00 UTC
    │
    ▼ learning/analyzer.py
      → fetch_feedback_signal() — tag co-occurrence analysis
      → build_analysis_prompt()
      → GPT-4o (gpt-4o, OPENAI_API_KEY)
      → JSON proposals
    │
    ▼ learning_proposals table (status=pending)
    │
    ▼ Human review at /learning
      → approve → INSERT into scoring_rules table
      → reject → status=rejected
```

**Note:** Approved proposals create new DB scoring rules but do NOT auto-update static weights in `edge_config.py`. The feedback loop influences dynamic rule adjustments only; EDGE/RISK tag base weights require a code deploy to change.

### thumbs_up special case
`POST /api/candidate/{id}/feedback` with `rating=up` → sets `score = max(90, current+40)` → guaranteed Tier A regardless of automated scoring.

---

## 8. Caching + Logging

### Caching

| Cache | Type | Location | TTL |
|---|---|---|---|
| Zone median PSF | In-memory dict | `analysis/arbitrage.py` `_ZONE_MEDIAN_PSF_CACHE` | None (per-process lifetime, rebuilt on each rescore) |
| Feasibility API responses | File cache | `/tmp/feasibility_cache/{hash}.geojson` | None (permanent until /tmp cleared) |
| No Redis | — | — | — |
| No HTTP cache headers | — | — | — |

### Logging

- **Framework**: Python stdlib `logging`, `getLogger(__name__)` per module
- **Format**: Unstructured plain text
- **Default level**: INFO; DEBUG available in some modules for API response verbosity
- **Output**: stdout/stderr → Docker container logs (`docker logs mikes-bs-app-1` / `mikes-bs-web-1`)
- **Aggregation**: None — Loki/Promtail stack deployed on aidev01 but not wired to mikes-bs containers

---

## 9. Notable Gaps / Tech Debt

1. **`scoring_rules` has no ORM model** — accessed via raw SQL only
2. **`road_centerlines`, `parcel_sales`, `tax_delinquency`** — raw tables, no ORM models, no Alembic migrations
3. **Alembic volume mount gap** — `alembic/versions/` not in `./openclaw:/app/openclaw` mount; migrations 007+ applied via direct `psql` + manual `alembic_version` insert until `--no-cache` rebuild completes
4. **Learning proposals auto-apply not implemented** — approval creates DB rules but does not propagate to `edge_config.py` static weights
5. **No authentication** — internal tool only, open access assumed
6. **`Lead.status` enum** in models.py (new/reviewed/outreach/active/dead) is different from the lead pipeline Codex is building — will need reconciliation on merge
7. **`app.py` is monolithic** — ~1,100 lines, all routes in one file; no router separation
8. **Base score weights hard-coded** — `SPLIT_WEIGHT`, `VALUE_WEIGHT`, `OWNER_WEIGHT` in `rule_engine.py` are not env-overridable, inconsistent with the rest of the config pattern
9. **No test coverage for web layer** — `tests/` only covers analysis modules and feasibility pipeline; no FastAPI test client tests
10. **Duplicate migration file** — both `006_learning.py` and `006_splits_range_arbitrage.py` exist with revision ID `006`; DB currently has both `007` and `008` in `alembic_version` but Alembic head tracking is broken until container rebuild
