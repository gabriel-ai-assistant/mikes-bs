# ALPHA ENGINE PLAN DELTA — Opus Architecture Review
## Date: 2026-02-21 | All 15 points resolved

---

## VERDICTS

### 1. UGA Integration Performance — ACCEPT
Materialize `uga_outside BOOLEAN` on `candidates` at ingestion/enrichment. Populate via `ST_Contains` batch against `future_land_use`. Rescore reads a boolean column — no spatial join in hot path. Add index on `candidates.uga_outside`.

### 2. YMS Semantics — ACCEPT WITH MODIFICATION
Always emit `YMS_HEURISTIC` reason code. Add `YMS_MAX_EFFECTIVE_LOTS = 20` config cap (prevents overscoring large parcels). Formula: `capped_yield = min(adjusted_yield, YMS_MAX_EFFECTIVE_LOTS)`. Emit `YMS_YIELD_CAPPED` when cap fires.

### 3. EFI Asymmetric Curve — ACCEPT
Replace symmetric bell curve with asymmetric two-slope decay. High friction is never rewarded:
```
if friction <= EFI_MILD_THRESHOLD:
    efi = 10 - (friction * EFI_MILD_PENALTY)
else:
    efi = max(0, 10 - EFI_MILD_THRESHOLD * EFI_MILD_PENALTY
                     - (friction - EFI_MILD_THRESHOLD) * EFI_STEEP_PENALTY)
```
Remove: `EFI_TARGET_FRICTION`, `EFI_SCALE`. Add: `EFI_MILD_THRESHOLD=3.0`, `EFI_MILD_PENALTY=0.5`, `EFI_STEEP_PENALTY=2.0`.

### 4. ALS Without DOM — ACCEPT WITH MODIFICATION
Reduce ALS composite weight: **3 → 2**. Composite denominator changes: 13 → 12.
Add time-weighted recency to comp counting:
- 0–180 days: 1.0×
- 181–365 days: 0.5×
- 366–730 days: 0.25×

Always emit `ALS_NO_DOM` reason code until DOM data is implemented.

### 5. CMS Land Cost Source — ACCEPT
Add `land_cost_source` reason code: `LAND_COST_SOURCE:ASSESSED|LAST_SALE|LIST_PRICE`.
Priority: LIST_PRICE → LAST_SALE → ASSESSED.
Add `CMS_ASSESSED_VALUE_MULTIPLIER` config dict (keyed by county, default 1.0).
Apply: `land_cost = assessed_value * multiplier[county]`.

### 6. IRR Terminology — ACCEPT
Rename everywhere:
- DB column: `irr_estimate` → `annualized_return_estimate`
- Code: `irr` → `annualized_return_proxy`
- Reason code: always emit `RETURN_PROXY_NOT_IRR`
True IRR requires cash flow timing; this is not that.

### 7. deal_analysis Schema Redundancy — ACCEPT WITH MODIFICATION
Slim the schema. Keep: `id, parcel_id, county, run_date, assumptions_version, tags, edge_score, tier, reasons JSONB, underwriting_json JSONB, analysis_timestamp, run_id UUID`.
**Remove** individual component columns: `dif_score_yms`, `dif_score_efi`, `dif_score_als`, `dif_score_cms`, `dif_score_sfi`, `yield_estimate`, `absorption_score`, `friction_score`, `margin_estimate`, `risk_class`.
Derive from `underwriting_json` when needed. Keep `tier` for fast DB filtering.

### 8. Idempotent Discovery Runs — ACCEPT
Add DB unique constraint: `UNIQUE(parcel_id, (run_date::date), assumptions_version)`.
Use `ON CONFLICT ... DO UPDATE` upsert semantics. Add `run_id UUID` for batch tracing (not uniqueness key). Reruns with same assumptions overwrite; new assumption version = new record.

### 9. DIF Score Dominance — ACCEPT
Add `DIF_MAX_DELTA = 25` config (default ±25 points).
```python
dif_delta = clamped to [-DIF_MAX_DELTA, +DIF_MAX_DELTA]
```
Emit: `DIF_DELTA_APPLIED:{value}`, `DIF_DELTA_CLAMPED_HIGH` or `DIF_DELTA_CLAMPED_LOW` when clamp fires.

### 10. Spatial Join Scalability — ACCEPT
Generalize #1: ALL spatial computations move to ingestion/enrichment phase. This includes UGA, wetland proximity, shoreline, access proximity. Scoring reads precomputed booleans/floats only. Create `openclaw/enrichment/spatial.py` for enrichment jobs.

### 11. Stub Data Handling — ACCEPT
All stubs emit `{COMPONENT}_STUBBED` reason code (e.g., `SLOPE_STUBBED`, `DOM_STUBBED`, `RUTA_STUBBED`).
Add `data_confidence` float (0.0–1.0) to `underwriting_json` output, computed from which layers have real vs. stub data. Silent neutral scoring for stubs is forbidden — confidence must reflect gaps.

### 12. Test Coverage — ACCEPT
Add `tests/test_dif_integration.py`:
- `test_high_friction_caps_total_score` — EFI steep penalty bounds final score
- `test_missing_zoning_suppresses_edge_tags` — no zone_code → no EDGE_* tags
- `test_uga_none_emits_risk_and_conservative_score`
- `test_dif_delta_clamp_high` — DIF that would exceed +25 is clamped
- `test_dif_delta_clamp_low` — negative DIF clamped at −25

### 13. Tier Stability — ACCEPT WITH MODIFICATION
Add explicit `TIER_THRESHOLDS` config: `{"A": 85, "B": 70, "C": 50, "D": 35, "E": 20, "F": 0}`.
Add `docs/tier_calibration.md` documenting expected post-DIF score distribution.
Note in migration: existing tier assignments should be re-evaluated after DIF launch (base_score + EDGE scores topped out at ~80; DIF can push to 100).

### 14. Naming Consistency — ACCEPT
Standardized naming:
- `irr_estimate` → `annualized_return_estimate`
- Internal YMS output labeled `heuristic_yield`
- DIF composite delta labeled `dif_delta` in code and reason codes
- All financial metrics use `_estimate` or `_proxy` suffix
- `edge_score` stays (DIF composite output, unambiguous in context)

### 15. Logging & Explainability — ACCEPT
`underwriting_json` must always contain this explainability structure:
```json
{
  "base_score": 45.0,
  "edge_boosts": {"EDGE_SNOCO_LSA_R5_RD_FR": 35},
  "dif_components": {"yms": 7.2, "efi": 4.1, "als": 5.5, "cms": 8.0, "sfi": 6.3},
  "dif_delta_raw": 18.4,
  "dif_delta_applied": 18.4,
  "dif_clamped": false,
  "final_score": 65.4,
  "data_confidence": 0.72,
  "reasons": [...]
}
```

---

## PLAN DELTA — File-Level Changes

### New Files
```
openclaw/analysis/dif/__init__.py
openclaw/analysis/dif/config.py          ← DIFConfig with all updated params
openclaw/analysis/dif/engine.py          ← composite + clamping + explainability struct
openclaw/analysis/dif/components/yms.py  ← heuristic_yield, cap, YMS_HEURISTIC reason
openclaw/analysis/dif/components/efi.py  ← asymmetric curve (two-slope)
openclaw/analysis/dif/components/als.py  ← recency-weighted comps, ALS_NO_DOM reason
openclaw/analysis/dif/components/cms.py  ← land_cost_source, county multiplier
openclaw/analysis/dif/components/sfi.py  ← ownership/trust/improvement, RETURN_PROXY_NOT_IRR
openclaw/analysis/dif/stubs.py           ← STUBBED reason codes, data_confidence computation
openclaw/analysis/dif/output.py          ← build_underwriting_json() structure
openclaw/enrichment/spatial.py           ← batch enrichment: UGA, wetland, access (ingestion-phase)
openclaw/discovery/engine.py             ← weekly batch, run_id, upsert semantics
openclaw/underwriting/engine.py          ← pro forma, sensitivity, annualized_return_estimate
tests/test_dif_integration.py            ← 5 new interaction/clamp tests
docs/tier_calibration.md                 ← expected score distribution post-DIF
alembic/versions/003_alpha_engine.py     ← slim deal_analysis schema (see below)
```

### Modified Files
```
openclaw/analysis/tagger.py      ← add uga_outside: bool | None param
openclaw/analysis/rule_engine.py ← read candidates.uga_outside (boolean), not spatial join
openclaw/analysis/edge_config.py ← add TIER_THRESHOLDS config
openclaw/main.py                 ← add weekly discovery job (Sunday 06:30 UTC)
openclaw/notify/digest.py        ← add edge_score + data_confidence + top DIF reasons
tests/test_scorer.py             ← fix broken assign_tier import
```

### Migration 003 Schema (deal_analysis — slimmed)
```sql
CREATE TABLE deal_analysis (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    parcel_id                UUID NOT NULL REFERENCES parcels(id),
    county                   VARCHAR NOT NULL,
    run_date                 TIMESTAMP NOT NULL DEFAULT now(),
    run_id                   UUID,
    assumptions_version      VARCHAR NOT NULL,
    tags                     TEXT[],
    edge_score               FLOAT,
    tier                     VARCHAR(1),
    annualized_return_estimate FLOAT,      -- renamed from irr_estimate
    reasons                  JSONB,
    underwriting_json        JSONB,         -- contains full explainability struct
    analysis_timestamp       TIMESTAMP NOT NULL DEFAULT now(),
    CONSTRAINT uq_deal_parcel_date_version
        UNIQUE (parcel_id, (run_date::date), assumptions_version)
);
CREATE INDEX idx_deal_analysis_parcel     ON deal_analysis(parcel_id);
CREATE INDEX idx_deal_analysis_run        ON deal_analysis(run_date);
CREATE INDEX idx_deal_analysis_tier       ON deal_analysis(tier);
CREATE INDEX idx_deal_analysis_edge_score ON deal_analysis(edge_score DESC);

-- Materialize UGA on candidates (spatial enrichment, run once + on new ingestion)
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS uga_outside BOOLEAN;
CREATE INDEX IF NOT EXISTS idx_candidates_uga ON candidates(uga_outside);
```

### Updated DIFConfig (key param changes)
```python
# YMS
YMS_MAX_EFFECTIVE_LOTS: int = 20        # NEW cap
# EFI — REPLACES symmetric curve
EFI_MILD_THRESHOLD: float = 3.0
EFI_MILD_PENALTY: float = 0.5
EFI_STEEP_PENALTY: float = 2.0
# REMOVED: EFI_TARGET_FRICTION, EFI_SCALE
# ALS
ALS_WEIGHT: int = 2                     # REDUCED from 3
# composite denominator changes 13 → 12
# CMS
CMS_ASSESSED_VALUE_MULTIPLIER: dict = {"default": 1.0}   # NEW
# DIF integration
DIF_MAX_DELTA: float = 25.0             # NEW clamp
# Tier thresholds (NEW — explicit)
TIER_THRESHOLDS: dict = {"A": 85, "B": 70, "C": 50, "D": 35, "E": 20, "F": 0}
```

### Updated Composite Formula
```python
# OLD: (YMS*3 + ALS*3 + CMS*3 + SFI*2 - EFI*2) / 13 * 100
# NEW: (YMS*3 + ALS*2 + CMS*3 + SFI*2 - EFI*2) / 12 * 100
#
# Then clamp delta to ±DIF_MAX_DELTA before adding to base_score
```

---

## UPDATED IMPLEMENTATION ORDER

| Step | Files | Change From Original |
|---|---|---|
| 0 | Fix `test_scorer.py` | Unchanged |
| 1 | `tagger.py` — `uga_outside` param | Unchanged |
| 2 | `enrichment/spatial.py` — batch UGA populate (NOT in rescore) | **Changed**: moved to enrichment |
| 3 | `rule_engine.py` — read `candidates.uga_outside` boolean | **Changed**: no spatial join |
| 4 | `tests/test_uga_integration.py` | Unchanged |
| 5 | Migration 003 (slim schema + uga_outside on candidates) | **Changed**: slimmed columns, renamed field, unique constraint |
| 6 | `dif/config.py` — full updated params | **Changed**: asymmetric EFI, ALS weight=2, cap, clamp, tier thresholds |
| 7 | `dif/components/yms.py` — heuristic_yield, cap | **Changed**: add cap + reason code |
| 8 | `dif/components/efi.py` — asymmetric curve | **Changed**: two-slope decay |
| 9 | `dif/components/als.py` — recency weights, ALS_NO_DOM | **Changed**: recency weighting |
| 10 | `dif/components/cms.py` — land_cost_source, multiplier | **Changed**: source priority + multiplier |
| 11 | `dif/components/sfi.py` | Minor: add RETURN_PROXY_NOT_IRR |
| 12 | `dif/stubs.py` — stub reason codes + data_confidence | **New file** |
| 13 | `dif/output.py` — build_underwriting_json() | **New file** |
| 14 | `dif/engine.py` — composite + clamp + explainability | **Changed**: clamp, new formula |
| 15 | `tests/test_dif.py` | Unchanged |
| 16 | `tests/test_dif_integration.py` | **New file** |
| 17 | `underwriting/engine.py` — annualized_return_estimate | **Changed**: renamed field |
| 18 | `tests/test_underwriting.py` | Unchanged |
| 19 | `discovery/engine.py` — run_id, upsert | **Changed**: idempotency |
| 20 | `tests/test_discovery.py` | Unchanged |
| 21 | `main.py` — weekly job | Unchanged |
| 22 | `notify/digest.py` — edge_score + confidence | Unchanged |
| 23 | Stub ingest modules | Unchanged |
| 24 | `docs/tier_calibration.md` | **New file** |
| 25 | README update | Unchanged |
