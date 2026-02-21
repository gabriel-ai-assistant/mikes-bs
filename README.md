# Mike's Building System

FastAPI + PostGIS app for finding subdivision candidates in Snohomish County, WA.

## Zoning Arbitrage Tags (EDGE/RISK System)

The scoring pipeline attaches structured tags to each candidate to capture jurisdiction-specific
development opportunities and known risk factors. Tags are stored in `candidates.tags TEXT[]`
and are additive, composable, and feed into the scoring engine.

### EDGE Tags — Opportunity Signals

| Tag | Trigger | Meaning |
|-----|---------|---------|
| `EDGE_SNOCO_LSA_R5_RD_FR` | county=snohomish, zone∈{R-5,RD,F&R}, lot≥10 acres | Eligible for Lot Size Averaging short subdivision (SCC 30.23.215 / Ord 24-058) |
| `EDGE_SNOCO_RURAL_CLUSTER_BONUS` | county=snohomish, zone∈{R-5,RD,F&R}, lot≥5 acres | Rural cluster density bonus eligible |
| `EDGE_SNOCO_RUTA_ARBITRAGE` | RUTA boundary confirmed (data stub — pending load) | Inside RUTA; improves feasible yield |
| `EDGE_WA_HB1110_MIDDLE_HOUSING` | zone∈EDGE_HB1110_URBAN_ZONES (admin-configured) | HB 1110 middle housing preemption applies |
| `EDGE_WA_UNIT_LOT_SUBDIVISION` | zone∈EDGE_UNIT_LOT_ZONES (admin-configured) | Unit lot subdivision supported for fee-simple exit |
| `EDGE_UGA_STATUS_UNKNOWN` | Always alongside LSA tag | UGA boundary data not loaded; review manually |

### RISK Tags — Constraint Signals

| Tag | Condition |
|-----|-----------|
| `RISK_ACCESS_UNKNOWN` | No address, lot < 1000 sqft, value < $5k |
| `RISK_CRITICAL_AREAS` | has_critical_area_overlap = true |
| `RISK_LOT_TOO_SMALL` | Rural zone, lot < rural cluster minimum |
| `RISK_SEPTIC_UNKNOWN` | Rural zone, no existing structure (improvement_value=0) |
| `RISK_WATER_UNKNOWN` | Rural zone, no existing structure (improvement_value=0) |
| `RISK_RUTA_DATA_UNAVAILABLE` | RUTA boundary table not loaded |
| `RISK_HB1110_DATA_UNAVAILABLE` | EDGE_HB1110_URBAN_ZONES not configured |
| `RISK_UNIT_LOT_DATA_UNAVAILABLE` | EDGE_UNIT_LOT_ZONES not configured |

### Score Weights (config-driven via env vars)

| Env Var | Default | Effect |
|---------|---------|--------|
| `EDGE_WEIGHT_LSA` | 35 | Score boost for EDGE_SNOCO_LSA_R5_RD_FR |
| `EDGE_WEIGHT_RUTA` | 30 | Score boost for EDGE_SNOCO_RUTA_ARBITRAGE |
| `EDGE_WEIGHT_HB1110` | 25 | Score boost for EDGE_WA_HB1110_MIDDLE_HOUSING |
| `EDGE_WEIGHT_UNIT_LOT` | 20 | Score boost for EDGE_WA_UNIT_LOT_SUBDIVISION |
| `EDGE_WEIGHT_RURAL_CLUSTER` | 15 | Score boost for EDGE_SNOCO_RURAL_CLUSTER_BONUS |
| `EDGE_WEIGHT_RISK_PENALTY` | -15 | Per-RISK-tag score penalty (capped at -30 total) |
| `EDGE_LSA_MIN_ACRES` | 10.0 | Minimum acres for LSA eligibility |
| `EDGE_RURAL_CLUSTER_MIN_ACRES` | 5.0 | Minimum acres for rural cluster eligibility |
| `EDGE_HB1110_URBAN_ZONES` | (empty) | Comma-separated zone codes for HB 1110 eligibility |
| `EDGE_UNIT_LOT_ZONES` | (empty) | Comma-separated zone codes for unit lot eligibility |

### Configuring HB 1110 and Unit Lot Zones

To enable HB 1110 and unit lot tags, set the env vars with the actual zone codes in your jurisdiction:

```env
EDGE_HB1110_URBAN_ZONES=RS-6,RS-8,RM-12,RM-24,MF
EDGE_UNIT_LOT_ZONES=RS-6,RS-8,RM-12
```

These tags will not fire until zones are explicitly configured (fail-closed by default).

## Alpha Engine

### EDGE Tags — Snohomish County Zoning Arbitrage

| Tag | Trigger | Score Boost |
|-----|---------|-------------|
| `EDGE_SNOCO_LSA_R5_RD_FR` | zone ∈ {R-5,RD,F&R}, ≥10ac, outside UGA, no access block | +35 |
| `EDGE_SNOCO_RURAL_CLUSTER_BONUS` | zone ∈ {R-5,RD,F&R}, ≥5ac | +15 |
| `EDGE_SNOCO_RUTA_ARBITRAGE` | inside RUTA boundary (data required) | +30 |
| `EDGE_WA_HB1110_MIDDLE_HOUSING` | zone in `EDGE_HB1110_URBAN_ZONES` env | +25 |
| `EDGE_WA_UNIT_LOT_SUBDIVISION` | zone in `EDGE_UNIT_LOT_ZONES` env | +20 |

### Fail-Closed Behavior
- UGA data unavailable → `EDGE_UGA_STATUS_UNKNOWN`, LSA tag withheld
- RUTA table empty → `RISK_RUTA_DATA_UNAVAILABLE`
- HB1110 zones not configured → `RISK_HB1110_DATA_UNAVAILABLE`
- No legal access signals → `RISK_ACCESS_UNKNOWN`, LSA suppressed

### DIF Scoring Knobs
All weights and thresholds configurable via `.env`. Key vars: `DIF_WEIGHT_YMS`, `DIF_WEIGHT_ALS`, `DIF_WEIGHT_CMS`, `DIF_WEIGHT_SFI`, `DIF_WEIGHT_EFI`, `DIF_MAX_DELTA`, `TIER_THRESHOLDS`.

### Discovery Engine
```bash
python -m openclaw.discovery.engine --county snohomish --top-a 20 --top-b 50
python -m openclaw.discovery.engine --json-out /tmp/discovery.json
```

### Underwriting Engine
```bash
python -m openclaw.underwriting.engine --tier A --top 20
python -m openclaw.underwriting.engine --parcel-id <uuid>
```

### Tier Calibration
See `docs/tier_calibration.md` for expected score distribution and recalibration process.
