# ALPHA ENGINE PLAN — Mike's Building System
## Compiled: 2026-02-21 (Code-Verified Inventory)

---

## PART 0 — SYSTEM MAP (CODE-DRIVEN INVENTORY)

### 0.1 Tag/Flag Pipeline — Exact File Map

```
ArcGIS REST API
    │
    ▼
openclaw/ingest/delta_sync.py          ← CORRDATE-watermarked upsert to parcels table
openclaw/ingest/snohomish.py           ← County-specific field mapping
    │
    ▼
openclaw/analysis/scorer.py            ← SQL: inserts candidates (lot_sf/zone ratio),
    │                                     then spatial flags (wetland, ag, HOA)
    │                                     Writes: candidates.has_critical_area_overlap,
    │                                             candidates.flagged_for_review
    ▼
openclaw/analysis/rule_engine.py       ← Python: evaluate_candidate()
    │   calls compute_tags() → base_score() → EDGE boosts → rule adjustments
    │   Reads tags via FIELD_MAP['tags'] for tag_contains operator
    │   Writes: candidates.score_tier, candidates.score,
    │           candidates.tags, candidates.reason_codes
    ▼
openclaw/analysis/tagger.py            ← compute_tags(candidate, config, ruta_confirmed)
    │   Returns (tags[], reason_codes[])
    ▼
openclaw/analysis/edge_config.py       ← EdgeConfig dataclass — all weights/zones
    │                                     sourced from env vars, fails safely
    ▼
openclaw/notify/digest.py              ← Email: queries A/B candidates, HTML table
    ▼
openclaw/main.py                       ← APScheduler: daily 6am UTC
                                          CLI: --run-now | --score-only
```

### 0.2 Tag Storage Format

| Column | Type | Table | Written By |
|---|---|---|---|
| `tags` | `TEXT[]` | `candidates` | `rule_engine.py:rescore_all()` |
| `reason_codes` | `TEXT[]` | `candidates` | `rule_engine.py:rescore_all()` |
| `has_critical_area_overlap` | `BOOLEAN` | `candidates` | `scorer.py:FLAG_WETLAND_SQL` |
| `has_shoreline_overlap` | `BOOLEAN` | `candidates` | `scorer.py` (spatial, populated) |
| `flagged_for_review` | `BOOLEAN` | `candidates` | `scorer.py:FLAG_AG_SQL + FLAG_HOA_SQL` |

**No boolean EDGE/RISK flags exist** — they are exclusively in `TEXT[]` tags. Constraint is already met.

### 0.3 Tag Identifiers — Currently Defined (tagger.py docstring)

**EDGE (positive):** `EDGE_SNOCO_LSA_R5_RD_FR`, `EDGE_SNOCO_RURAL_CLUSTER_BONUS`, `EDGE_SNOCO_RUTA_ARBITRAGE`, `EDGE_WA_HB1110_MIDDLE_HOUSING`, `EDGE_WA_UNIT_LOT_SUBDIVISION`

**INFORMATIONAL:** `EDGE_UGA_STATUS_UNKNOWN`

**RISK (negative):** `RISK_ACCESS_UNKNOWN`, `RISK_CRITICAL_AREAS`, `RISK_LOT_TOO_SMALL`, `RISK_SEPTIC_UNKNOWN`, `RISK_WATER_UNKNOWN`, `RISK_RUTA_DATA_UNAVAILABLE`, `RISK_HB1110_DATA_UNAVAILABLE`, `RISK_UNIT_LOT_DATA_UNAVAILABLE`

### 0.4 What's Already Built (Last Night's Work)

All of **Parts 2, 3, 4** from the prompt are implemented:
- `tagger.py` — full EDGE/RISK logic, fail-closed, reason codes ✅
- `edge_config.py` — config-driven weights/zones via env ✅
- `rule_engine.py` — base_score + EDGE boosts + rule-based adjustments + tag_contains operator ✅
- Migration 002 — `tags`, `reason_codes`, `score` columns + `ruta_boundaries` table ✅
- `test_tagger.py` — 9 test classes, all passing ✅

**What's missing / the actual build work:**
- DIF (Part 1) — not started
- UGA data unused (`future_land_use.uga` = 0/1 exists — tagger emits UNKNOWN unnecessarily)
- Discovery Engine (Part 6) — not started
- Underwriting Engine (Part 7) — `profit.py` is a partial skeleton (no carry, no financing, no sensitivity)
- DB: `deal_analysis`, `assumptions_versioned` tables — not started
- `test_scorer.py` — **BROKEN**: imports `assign_tier` from `scorer.py`, which doesn't exist

### 0.5 Data Availability Audit

| Data Field | Source | Status |
|---|---|---|
| `lot_sf` | `parcels.lot_sf` | ✅ Populated (ArcGIS `GIS_SQ_FT`) |
| `zone_code` | `parcels.zone_code` | ✅ Populated (FLU join assigns it) |
| `county` | `parcels.county` | ✅ |
| `critical areas` | `critical_areas` table + ST_Intersects | ✅ Loaded |
| `UGA status` | `future_land_use.uga` (0=outside, 1=inside) | ✅ In DB — **NOT wired to tagger yet** |
| `improvement_value` | `parcels.improvement_value` | ✅ (used for SFI + septic proxy) |
| `total_value`, `assessed_value` | `parcels.*` | ✅ |
| `last_sale_date` | `parcels.last_sale_date` | ✅ (ownership duration for SFI) |
| `last_sale_price` | `parcels.last_sale_price` | ✅ (ALS comps in profit.py) |
| `owner_name` | `parcels.owner_name` | ✅ (trust/estate detection) |
| RUTA boundary | `ruta_boundaries` table | ⚠️ Table exists, **no data** — stub |
| Transit proximity | not in schema | ❌ Stub only |
| Tax delinquency | not in schema | ❌ Stub only |
| HB1110 zones | `EDGE_HB1110_URBAN_ZONES` env var | ⚠️ Configurable, not set |
| Slope / topography | not in schema | ❌ Stub only |
| Days on market | not in schema | ❌ Stub only (DOM) |

---

## PART 1 — MIKE'S FINGERPRINT: DIF Architecture

### 1.1 Module Structure

New directory: `openclaw/analysis/dif/`

```
openclaw/analysis/dif/
├── __init__.py
├── config.py          ← DIFConfig dataclass (all weights/thresholds, env-driven)
├── engine.py          ← Composite edge_score computation; calls all components
├── components/
│   ├── yms.py         ← Yield Multiplier Score
│   ├── efi.py         ← Entitlement Friction Index
│   ├── als.py         ← Absorption Liquidity Score
│   ├── cms.py         ← Construction Margin Spread
│   └── sfi.py         ← Seller Fatigue Index
└── reason_codes.py    ← Reason code constants + formatter
```

Each component module exposes a single function:
```python
def compute_{component}(candidate: dict, config: DIFConfig, session=None) -> ComponentResult
```

Where `ComponentResult = namedtuple('ComponentResult', ['score', 'reasons', 'data_quality'])`

`data_quality` is `'full' | 'partial' | 'unavailable'` — used for fail-closed logic.

### 1.2 Component Specs

**A. YMS — Yield Multiplier Score (0–10)**

Inputs from `candidate` dict (all available):
- `lot_sf`, `zone_code` → `zoning_rules.min_lot_sf` → raw splits
- `has_critical_area_overlap` → deduction
- `potential_splits` (already computed in candidates)

Formula:
```
raw_yield = floor(lot_sf / min_lot_sf)
deduction = critical_area_overlap ? config.YMS_CRITICAL_AREA_PENALTY : 0
adjusted_yield = max(raw_yield - deduction, 0)
yms = min(adjusted_yield / config.YMS_MAX_YIELD, 1.0) * 10
```
Reason code: `"YMS: raw_yield=4, critical_area_deduction=-1, adjusted=3, score=7.5"`

Note: `potential_splits` is already in candidates — YMS should use it. Config-driven `YMS_CRITICAL_AREA_PENALTY` defaults to 1 lot.

**B. EFI — Entitlement Friction Index (0–10, moderate friction is GOOD)**

Inputs (available):
- `has_critical_area_overlap` → high wetland friction
- `improvement_value == 0` + `address is None` → access unknown
- Slope: **STUB** (no data)
- Sewer extension: **STUB**
- Political risk: **STUB**

Formula (friction accumulator, then scoring curve):
```
friction = 0
friction += critical_area_overlap ? config.EFI_WETLAND_FRICTION : 0
friction += (improvement_value == 0 and address is None) ? config.EFI_ACCESS_FRICTION : 0
# Stubs add 0 but emit STUB reason codes
friction_capped = min(friction, 10)

# Target moderate friction: score is highest at midpoint
efi = max(0, 10 - abs(friction_capped - config.EFI_TARGET_FRICTION) * config.EFI_SCALE)
```

`config.EFI_TARGET_FRICTION` defaults to 3.0 (moderate). Parcels with friction=0 (too easy, no edge) or friction≥8 (deal-killer) both score lower.

**C. ALS — Absorption Liquidity Score (0–10)**

Inputs (available via SQL):
- `parcels.last_sale_price` within 0.5 miles, same zone, last 24 months (reuse profit.py COMP_SQL)
- Target band: `$900k–$1.5M` (config: `ALS_TARGET_LOW`, `ALS_TARGET_HIGH`)
- DOM: **STUB**

Formula:
```
in_band_count = count(comps where ALS_TARGET_LOW <= price <= ALS_TARGET_HIGH)
total_comps = count(all comps)
band_ratio = in_band_count / max(total_comps, 1)

als = min((in_band_count / config.ALS_SATURATION_COUNT), 1.0) * 7.0
    + band_ratio * 3.0
# Normalized 0-10
```

Cross-county portability: `ALS_SATURATION_COUNT` config sets "what counts as liquid" per county.

**D. CMS — Construction Margin Spread (0–10)**

Inputs (available via existing `profit.py`):
- ARV from comps, dev + build cost
- Extended with: `UW_FINANCING_RATE_PCT`, `UW_CARRY_MONTHS`, `UW_FINANCING_LTV`

Formula:
```
land_cost = assessed_value
dev_cost = (COST_SHORT_PLAT_BASE + COST_ENGINEERING + COST_UTILITY) * splits
build_cost = COST_BUILD_PER_SF * TARGET_HOME_SF * splits
carry_cost = (land_cost + dev_cost) * LTV * rate * (carry_months/12)
total_cost = land_cost + dev_cost + build_cost + carry_cost
revenue = arv_per_home * splits
margin_pct = (revenue - total_cost) / revenue

cms = min(margin_pct / config.CMS_MAX_MARGIN_PCT, 1.0) * 10
```

`CMS_MAX_MARGIN_PCT` defaults to `0.30` (30% = score 10). Below 0 = score 0.

Reason: `"CMS: margin=24.3%, revenue=$3.8M, total_cost=$2.9M, carry=$87k, score=8.1"`

**E. SFI — Seller Fatigue Index (0–10)**

Inputs (available):
- `parcels.last_sale_date` → ownership years
- `parcels.owner_name` → trust/estate/family pattern match
- `parcels.improvement_value / parcels.total_value` → improvement ratio (low = land bank)
- Tax delinquency: **STUB**

Formula:
```
sfi = 0
if ownership_years >= config.SFI_MIN_YEARS:
    sfi += min(ownership_years / config.SFI_MAX_YEARS, 1.0) * 4.0
if owner_type in {TRUST, ESTATE, FAMILY}:
    sfi += config.SFI_TRUST_BONUS   # 2.0
if improvement_ratio < config.SFI_LOW_IMP_RATIO:
    sfi += config.SFI_LOW_IMP_BONUS  # 2.0
# Tax delinquency: 0 (stub) emit reason "SFI_TAX_DELINQUENCY: stub"
sfi = min(sfi, 10)
```

If `last_sale_date is None`, `data_quality = 'partial'`, use `SFI_NO_SALE_DATE_DEFAULT`.

### 1.3 Composite Score

```python
# dif/engine.py
edge_score = (
    yms_result.score * config.DIF_WEIGHT_YMS
  + als_result.score * config.DIF_WEIGHT_ALS
  + cms_result.score * config.DIF_WEIGHT_CMS
  + sfi_result.score * config.DIF_WEIGHT_SFI
  - efi_result.score * config.DIF_WEIGHT_EFI
) / config.DIF_TOTAL_WEIGHT * 100

# DIF_TOTAL_WEIGHT = sum of all weights = 13 at defaults
```

Defaults: YMS×3, ALS×3, CMS×3, SFI×2, EFI×2. All config-driven.

---

## PART 2-4 — EDGE TAGS + CONSTRAINTS GATE + SCORING (ALREADY IMPLEMENTED)

See inventory above — these are done. **Two fixes required:**

### Fix A: UGA Integration

- `future_land_use.uga = 0` → outside UGA; `uga = 1` → inside UGA. **Verified from DB.**
- Currently: tagger emits `EDGE_UGA_STATUS_UNKNOWN` because UGA status not passed in.
- Fix: `rule_engine.py:rescore_all()` joins `future_land_use` spatially for each candidate's parcel geometry → passes `uga_outside: bool | None` into `compute_tags()`.
- `tagger.py`: Accept `uga_outside: bool | None = None`.
  - `True` → confirmed outside UGA, emit LSA tag, no UNKNOWN
  - `False` → inside UGA, suppress LSA tag
  - `None` → emit `EDGE_UGA_STATUS_UNKNOWN` (backward compat)

### Fix B: Broken test_scorer.py

- Imports `assign_tier(splits, margin_pct)` from `scorer.py` — function doesn't exist.
- Rewrite against `score_to_tier(score)` + `base_score(candidate)` from `rule_engine.py`.

---

## PART 5 — DATA SOURCING STUBS

All stubs marked `# TODO(data):` and emit `STUB_DATA_UNAVAILABLE` reason code.

| Data | Module | Action |
|---|---|---|
| RUTA boundary | `openclaw/ingest/ruta_loader.py` (new) | Load from `/tmp/ruta.geojson` if present; else table stays empty |
| HB1110 zones | `EDGE_HB1110_URBAN_ZONES` env var | Already stubbed |
| Transit proximity | `openclaw/ingest/transit_loader.py` (new) | Stub file; HB1110 falls to MEDIUM weight |
| Tax delinquency | `openclaw/enrich/tax_status.py` (new) | Stub — SFI data_quality='partial' |
| Days on market | `openclaw/enrich/dom_fetcher.py` (new) | Stub — ALS uses comp volume only |
| Slope/topo | `openclaw/enrich/slope_loader.py` (new) | Stub — EFI friction uses 0 for slope term |

---

## PART 6 — DISCOVERY ENGINE

**New module:** `openclaw/discovery/engine.py`

```python
def run_discovery(county: str = None, top_n_a: int = 20, top_n_b: int = 50) -> DiscoveryResult:
    """
    1. Optional: trigger delta sync for target counties
    2. Run tagger + DIF for all candidates (or new-since-last-run)
    3. Write deal_analysis rows (assumptions_version pinned)
    4. Rank by edge_score DESC
    5. Return top N Tier-A + top N Tier-B
    6. Write JSON artifact to DISCOVERY_ARTIFACT_DIR/discovery_YYYYMMDD.json
    """
```

**Scheduler integration (main.py):**
```python
scheduler.add_job(
    run_discovery,
    "cron",
    day_of_week="sun", hour=6, minute=30,
    kwargs={"county": None}
)
```

**CLI:**
```bash
python -m openclaw.discovery.engine --county snohomish --top-a 20 --top-b 50 --json-out /tmp/discovery.json
```

**Output:**
- DB: `deal_analysis` rows
- JSON: `{tier_a: [{parcel_id, address, edge_score, tags, reasons, dif_components}...], tier_b: [...]}`
- Email: extend `notify/digest.py` with `edge_score` + top DIF reason codes

---

## PART 7 — UNDERWRITING ENGINE

**New module:** `openclaw/underwriting/engine.py`

Extends `profit.py` — does not replace it.

**Pro forma structure:**
```
ProForma:
  revenue:
    arv_per_home (from comps)
    units (potential_splits)
    total_revenue

  costs:
    land_acquisition (assessed_value)
    dev_cost = (short_plat + engineering + utility) * units
    build_cost = cost_per_sf * home_sf * units
    carry_cost = (land + dev) * LTV * annual_rate * (carry_months/12)
    financing_cost = build_cost * LTV * annual_rate * (build_months/12)
    total_cost

  margins:
    gross_profit
    margin_pct
    irr = simplified: margin / months_to_exit * 12
    months_to_exit = entitlement_months + build_months + absorption_months

  risk_class: A/B/C/D (margin thresholds)
  reasons: list[str]
  assumptions_version: str
```

**Sensitivity scenarios (config-driven):**
```python
SENSITIVITY_SCENARIOS = [
    {"label": "base",            "hard_cost_delta": 0.0,  "price_delta": 0.0,  "delay_months": 0, "rate_delta_bps": 0},
    {"label": "+10% hard costs", "hard_cost_delta": 0.10},
    {"label": "+20% hard costs", "hard_cost_delta": 0.20},
    {"label": "-5% sale price",  "price_delta": -0.05},
    {"label": "-10% sale price", "price_delta": -0.10},
    {"label": "+3mo delay",      "delay_months": 3},
    {"label": "+6mo delay",      "delay_months": 6},
    {"label": "+200bps rate",    "rate_delta_bps": 200},
]
```

All configurable via `UW_SENSITIVITY_SCENARIOS` JSON env var.

**CLI:**
```bash
python -m openclaw.underwriting.engine --tier A --top 20 --assumptions-version v1
python -m openclaw.underwriting.engine --parcel-id <uuid>
```

---

## PART 8 — DB MIGRATION PLAN

**Migration 003:** `alembic/versions/003_alpha_engine.py`

```sql
-- Table 1: deal_analysis
CREATE TABLE deal_analysis (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    parcel_id            UUID NOT NULL REFERENCES parcels(id),
    county               VARCHAR NOT NULL,
    run_date             TIMESTAMP NOT NULL DEFAULT now(),
    assumptions_version  VARCHAR NOT NULL,
    tags                 TEXT[],
    edge_score           FLOAT,
    dif_score_yms        FLOAT,
    dif_score_efi        FLOAT,
    dif_score_als        FLOAT,
    dif_score_cms        FLOAT,
    dif_score_sfi        FLOAT,
    tier                 VARCHAR(1),
    yield_estimate       INTEGER,
    absorption_score     FLOAT,
    friction_score       FLOAT,
    margin_estimate      FLOAT,
    irr_estimate         FLOAT,
    risk_class           VARCHAR(1),
    reasons              JSONB,
    underwriting_json    JSONB,
    analysis_timestamp   TIMESTAMP NOT NULL DEFAULT now()
);
CREATE INDEX idx_deal_analysis_parcel      ON deal_analysis(parcel_id);
CREATE INDEX idx_deal_analysis_run         ON deal_analysis(run_date);
CREATE INDEX idx_deal_analysis_tier        ON deal_analysis(tier);
CREATE INDEX idx_deal_analysis_edge_score  ON deal_analysis(edge_score DESC);

-- Table 2: assumptions_versioned
CREATE TABLE assumptions_versioned (
    version     VARCHAR PRIMARY KEY,
    created_at  TIMESTAMP DEFAULT now(),
    created_by  VARCHAR DEFAULT 'system',
    config_json JSONB NOT NULL,
    notes       TEXT
);
-- Seed with current defaults on migration
INSERT INTO assumptions_versioned (version, config_json, notes)
VALUES ('v1', '{}', 'Initial Alpha Engine defaults — populate from env at first run');
```

UGA status: computed at query time via `future_land_use` spatial join in `rule_engine.py`. No new column on `parcels` — reduces schema churn. (Flag for perf review on 23k candidates.)

---

## PART 9 — TESTS PLAN

### Fix existing broken test
**`tests/test_scorer.py`** — remove `assign_tier` import, rewrite against `score_to_tier` + `base_score` from `rule_engine.py`.

### New test files

**`tests/test_dif.py`** — no DB required (mock comps for ALS)

Required fixtures:
```python
FIXTURE_R5_12AC_OUTSIDE_UGA = {
    "county": "snohomish", "zone_code": "R-5",
    "lot_sf": 12 * 43560.0, "has_critical_area_overlap": False,
    "improvement_value": 10000, "total_value": 380000,
    "address": "123 Rural Rd", "owner_name": "Smith Family Trust",
    "last_sale_date": date(2001, 6, 15),  # ~24yr ownership
    "assessed_value": 380000, "potential_splits": 4,
    "uga_outside": True,
}
```

Required tests:
1. `test_yms_splits_computed_correctly`
2. `test_yms_critical_area_deduction`
3. `test_efi_moderate_friction_scores_highest`
4. `test_efi_zero_friction_scores_lower_than_moderate`
5. `test_als_comps_in_band_score_high` (mocked comps)
6. `test_als_no_comps_scores_zero`
7. `test_cms_margin_30pct_scores_10`
8. `test_cms_negative_margin_scores_zero`
9. `test_sfi_long_ownership_trust_scores_high`
10. `test_sfi_no_sale_date_partial_quality`
11. `test_composite_edge_score_ordered` (R-5/12ac/trust > B-1/5ac/corp)

**`tests/test_underwriting.py`**

1. `test_base_pro_forma_keys`
2. `test_sensitivity_count` — 8 scenarios produced
3. `test_sensitivity_hard_cost_up_reduces_margin`
4. `test_sensitivity_price_down_reduces_margin`
5. `test_sensitivity_delay_increases_carry`
6. `test_risk_class_a_requires_margin_threshold`
7. `test_assumptions_version_recorded`

**`tests/test_uga_integration.py`**

1. `test_uga_outside_resolves_lsa_without_unknown` — `uga_outside=True` → no EDGE_UGA_STATUS_UNKNOWN
2. `test_uga_inside_suppresses_lsa` — `uga_outside=False` → no EDGE_SNOCO_LSA_R5_RD_FR
3. `test_uga_none_emits_unknown` — backward compat

**`tests/test_discovery.py`**

1. `test_discovery_output_has_required_keys`
2. `test_discovery_top_n_respected`
3. `test_discovery_tier_a_sorted_by_edge_score`

---

## IMPLEMENTATION ORDER (PATCH PLAN)

| Step | Files | Depends On | Risk |
|---|---|---|---|
| 0 | Fix `test_scorer.py` | — | Low |
| 1 | `tagger.py` — add `uga_outside` param | — | Low |
| 2 | `rule_engine.py` — FLU spatial join, pass `uga_outside` | Step 1 | Medium |
| 3 | `tests/test_uga_integration.py` | Steps 1+2 | Low |
| 4 | `alembic/versions/003_alpha_engine.py` | — | Low |
| 5 | `openclaw/analysis/dif/config.py` | — | Low |
| 6 | `dif/components/yms.py` | Step 5 | Low |
| 7 | `dif/components/sfi.py` | Step 5 | Low |
| 8 | `dif/components/efi.py` | Step 5 | Low |
| 9 | `dif/components/als.py` | Step 5 | Medium (DB query) |
| 10 | `dif/components/cms.py` | Step 5, profit.py | Medium |
| 11 | `dif/engine.py` | Steps 6-10 | Low |
| 12 | `tests/test_dif.py` | Step 11 | Low |
| 13 | `openclaw/underwriting/engine.py` | Steps 10+11+4 | Medium |
| 14 | `tests/test_underwriting.py` | Step 13 | Low |
| 15 | `openclaw/discovery/engine.py` | Steps 11+13+4 | Medium |
| 16 | `tests/test_discovery.py` | Step 15 | Low |
| 17 | `main.py` — add weekly discovery job | Step 15 | Low |
| 18 | `notify/digest.py` — add edge_score + DIF reasons | Step 15 | Low |
| 19 | Stub ingest modules (RUTA, transit, etc.) | — | Low |
| 20 | README update section | all | Documentation |

---

## CONFIG PLAN

New env vars to add to `.env`:

```bash
# DIF — Developer Identity Fingerprint weights
DIF_WEIGHT_YMS=3
DIF_WEIGHT_ALS=3
DIF_WEIGHT_CMS=3
DIF_WEIGHT_SFI=2
DIF_WEIGHT_EFI=2

# YMS
DIF_YMS_CRITICAL_AREA_PENALTY=1
DIF_YMS_MAX_YIELD=10

# EFI
DIF_EFI_TARGET_FRICTION=3.0
DIF_EFI_SCALE=2.0
DIF_EFI_WETLAND_FRICTION=4.0
DIF_EFI_ACCESS_FRICTION=3.0

# ALS
DIF_ALS_TARGET_LOW=900000
DIF_ALS_TARGET_HIGH=1500000
DIF_ALS_SATURATION_COUNT=6
DIF_ALS_COMP_RADIUS_METERS=804

# CMS
DIF_CMS_MAX_MARGIN_PCT=0.30

# SFI
DIF_SFI_MIN_YEARS=10
DIF_SFI_MAX_YEARS=30
DIF_SFI_TRUST_BONUS=2.0
DIF_SFI_LOW_IMP_BONUS=2.0
DIF_SFI_LOW_IMP_RATIO=0.15
DIF_SFI_NO_SALE_DATE_DEFAULT=0.5

# Underwriting
UW_CARRY_MONTHS=12
UW_BUILD_MONTHS=8
UW_ABSORPTION_MONTHS=6
UW_FINANCING_RATE_PCT=7.5
UW_FINANCING_LTV=0.65

# Discovery
DISCOVERY_TIER_A_TOP_N=20
DISCOVERY_TIER_B_TOP_N=50
DISCOVERY_ARTIFACT_DIR=/tmp
```

`assumptions_versioned` snapshots the full config blob at run time for reproducibility.

---

## README UPDATE SECTION (Draft)

```markdown
## Alpha Engine — Mike's Fingerprint

### EDGE Tags (Snohomish County Zoning Arbitrage)

| Tag | Trigger | Score Weight |
|-----|---------|-------------|
| EDGE_SNOCO_LSA_R5_RD_FR | zone ∈ {R-5,RD,F&R}, ≥10ac, outside UGA, no access block | +35 |
| EDGE_SNOCO_RURAL_CLUSTER_BONUS | zone ∈ {R-5,RD,F&R}, ≥5ac | +15 |
| EDGE_SNOCO_RUTA_ARBITRAGE | inside RUTA boundary (data required) | +30 |
| EDGE_WA_HB1110_MIDDLE_HOUSING | zone in EDGE_HB1110_URBAN_ZONES env | +25 |
| EDGE_WA_UNIT_LOT_SUBDIVISION | zone in EDGE_UNIT_LOT_ZONES env | +20 |

### Fail-Closed Behavior
- Missing UGA data → EDGE_UGA_STATUS_UNKNOWN (not LSA tag)
- Empty RUTA table → RISK_RUTA_DATA_UNAVAILABLE
- HB1110 zones not configured → RISK_HB1110_DATA_UNAVAILABLE
- No legal access signals → RISK_ACCESS_UNKNOWN, LSA suppressed

### DIF Scoring Knobs
See env vars prefixed DIF_*, UW_* and assumptions_versioned table.

### Discovery Engine
python -m openclaw.discovery.engine --county snohomish --top-a 20

### Underwriting Engine
python -m openclaw.underwriting.engine --tier A --top 20
```

---

## RISK CONSIDERATIONS

### Data Gaps

| Risk | Impact | Mitigation |
|---|---|---|
| RUTA boundary missing | EDGE_SNOCO_RUTA_ARBITRAGE never fires | Stub in place; load from `/tmp/ruta.gpkg` when provided |
| `parcels.zone_code` null on recently ingested parcels | EDGE tags not emitted | tagger fails closed — no zone = no EDGE. Log warning in rescore_all. |
| ALS comp radius too tight in rural areas | ALS underscores rural parcels | `ALS_COMP_RADIUS_METERS` config — widen to 2000m for rural zones |
| `last_sale_date` null on ~30% of parcels | SFI partial quality | `SFI_NO_SALE_DATE_DEFAULT` config; emit reason code |
| ArcGIS `zone_code` not in parcels layer (snohomish.py comment) | zone_code null → no EDGE | Verify: `SELECT count(*) FROM parcels WHERE zone_code IS NULL AND county='snohomish'` |
| `future_land_use.uga` field semantics | Wrong UGA classification | **Verified from DB**: uga=0 rural/unincorp, uga=1 urban — confirmed from label patterns |

### False Positive Risk

- **LSA tag**: 10-acre threshold is conservative. Actual SCC 30.23.215 has nuances (road type, density credit) not modeled. Manual review required.
- **EFI curve**: Target friction = 3.0 is an assumption. Needs backtesting against Mike's historical deal decisions.
- **ALS band**: $900k–$1.5M is Mike's current market. Will need adjustment for future counties.

### Backtesting Plan (future)

Once `deal_analysis` accumulates history:
1. Export historical candidates with `edge_score`
2. Compare against `leads.status = active/dead`
3. Logistic regression: edge_score + DIF components → deal_accepted
4. Re-calibrate weights in `assumptions_versioned`

The `assumptions_version` column in `deal_analysis` ties outcomes to config snapshots — enabling this analysis later.

### Implementation Cautions

- `rule_engine.py:rescore_all()` FLU spatial join runs for every candidate on every rescore — consider caching `uga_outside` in a `candidates.uga_outside` boolean column (populated once, invalidated on geometry change) before enabling on full 23k candidate set.
- Discovery Engine must be idempotent: re-running should overwrite today's `deal_analysis` rows. Use `ON CONFLICT (parcel_id, run_date::date)` or DELETE+INSERT.
- Sensitivity scenarios: run N×8 pro forma calculations — batch in memory, single DB write at end.
