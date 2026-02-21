# Tier Calibration Guide

## Why Tiers Were Recalibrated

When the DIF (Developer Identity Fingerprint) scoring layer was integrated into the Alpha Engine,
the base score distribution shifted significantly. Prior to DIF, scores were bounded by rule-engine
EDGE boosts (max ~80 for a high-scoring R-5 parcel with LSA + RUTA tags). With DIF, the composite
`edge_score` can now reach up to 100, reflecting market conditions, yield quality, financing margins,
and seller motivation — not just zoning arbitrage.

The old tier thresholds were calibrated against the pre-DIF scoring universe. Leaving them unchanged
would classify too many DIF-boosted candidates as Tier-A, overwhelming Mike's review capacity and
diluting the signal. The new thresholds preserve the **top ~5% of candidates as Tier-A** after DIF
adjustment.

---

## Threshold Comparison

### Old Thresholds (pre-DIF, from `TIER_CUTOFFS` in `rule_engine.py`)

| Tier | Minimum Score | Description |
|------|--------------|-------------|
| A    | ≥ 80         | High-priority lead |
| B    | ≥ 65         | Watch list |
| C    | ≥ 50         | Monitor |
| D    | ≥ 35         | Low signal |
| E    | ≥ 20         | Marginal |
| F    |  0           | Not actionable |

### New Thresholds (DIF-adjusted, `TIER_THRESHOLDS` in `.env`)

| Tier | Minimum Score | Description |
|------|--------------|-------------|
| A    | ≥ 85         | Prime target — EDGE tag + strong DIF composite |
| B    | ≥ 70         | Watch list — solid fundamentals, not yet prime |
| C    | ≥ 50         | Monitor — potential with data gaps or moderate risk |
| D    | ≥ 35         | Low signal — may improve with better data |
| E    | ≥ 20         | Marginal — not actionable now |
| F    |  0           | Not actionable |

The 5-point raise on A (80→85) and B (65→70) reflects that DIF-enhanced scores above these
thresholds represent genuinely differentiated candidates — not just zoning geometry.

---

## What Each Tier Means to a Developer

### Tier A (≥ 85) — Prime Target

A Tier-A candidate has both a qualifying EDGE tag (usually `EDGE_SNOCO_LSA_R5_RD_FR` or
`EDGE_SNOCO_RUTA_ARBITRAGE`) **and** a strong DIF composite score. This means:

- **YMS**: Meaningful yield potential (likely 3+ splits after critical-area deduction)
- **ALS**: Recent comparable sales in the target price band ($900k–$1.5M)
- **CMS**: Estimated construction margin ≥ 20%
- **SFI**: Motivated seller signals (long ownership, trust/estate, low improvement ratio)
- **EFI**: Moderate entitlement friction — not a greenfield (some process expected), not a deal-killer

These are the parcels Mike should call first. Expect **≤ 20 candidates** per weekly run.

### Tier B (≥ 70) — Watch List

Solid fundamentals but missing something: either the DIF composite is partial (stub data gaps),
the EDGE tag is lower-weight (e.g., `EDGE_SNOCO_RURAL_CLUSTER_BONUS` without LSA), or the
margin is tight. Worth tracking across runs to catch movement up to Tier-A.

### Tier C (≥ 50) — Monitor

Interesting on paper but data confidence is low or risk tags are present. May include parcels with
`RISK_ACCESS_UNKNOWN` or `RISK_RUTA_DATA_UNAVAILABLE`. Revisit when stub data fills in.

### Tier D–F (< 50) — Not Actionable Now

These candidates may have passed initial lot-size screening but lack the arbitrage signals or
market fundamentals for Mike's strategy. Leave them in the DB; they may graduate as the market
shifts or as more data layers are loaded.

---

## First-Run Warning

> ⚠️ **Expect significant B→C migration on the first DIF-integrated run.**

Before DIF, many candidates scored in the 65–79 range (old Tier-A/B). After DIF integration with
the raised thresholds, a large portion of these will shift to Tier-C. This is **expected and correct
behaviour** — the DIF delta is small for parcels where stub data dominates (low `data_confidence`),
and those candidates shouldn't be Tier-A.

**Mike should manually review all Tier-A candidates after the first DIF run.** The DIF components
in `underwriting_json` explain every score. Look for:

1. `data_confidence` < 0.6 → partial data; treat score as indicative only
2. `dif_clamped: true` → DIF wanted to move the score more than ±25 points; review the raw delta
3. Missing tags that should be present (check `reason_codes` for `RISK_*_DATA_UNAVAILABLE`)

---

## Recalibration Process

As `deal_analysis` accumulates history, tier thresholds should be recalibrated against real outcomes:

1. **Run discovery** weekly (Sunday 06:30 UTC, automatic via scheduler)
2. **Export deal_analysis** after 3–6 months of data:
   ```sql
   SELECT parcel_id, edge_score, tier, run_date, underwriting_json
   FROM deal_analysis
   ORDER BY run_date DESC;
   ```
3. **Compare `edge_score` distribution vs `leads.status` outcomes** — which score ranges
   actually converted to active leads, offers, or closed deals?
4. **Adjust `TIER_THRESHOLDS`** in `.env`:
   ```bash
   TIER_THRESHOLDS={"A": 87, "B": 72, "C": 50, "D": 35, "E": 20, "F": 0}
   ```
5. **Re-run discovery** with updated thresholds. The `assumptions_version` column preserves
   which config produced which scores — compare v1 vs v2 distributions before committing.

The `assumptions_versioned` table stores the full config blob at each run, enabling
rigorous before/after comparison as the engine matures.

---

## Config Reference

| Env Var | Default | Notes |
|---------|---------|-------|
| `TIER_THRESHOLDS` | `{"A":85,"B":70,"C":50,"D":35,"E":20,"F":0}` | JSON dict |
| `DIF_MAX_DELTA` | `25.0` | Clamps DIF contribution to ±25 points |
| `DIF_WEIGHT_YMS` | `3` | Yield Multiplier Score weight |
| `DIF_WEIGHT_ALS` | `2` | Absorption Liquidity Score weight (reduced: no DOM data) |
| `DIF_WEIGHT_CMS` | `3` | Construction Margin Spread weight |
| `DIF_WEIGHT_SFI` | `2` | Seller Fatigue Index weight |
| `DIF_WEIGHT_EFI` | `2` | Entitlement Friction Index weight (subtracted) |

See `ALPHA_ENGINE_PLAN.md` and `ALPHA_ENGINE_PLAN_DELTA.md` for full DIF architecture documentation.
