# Learning Module Audit (Block D1)

Date: 2026-02-22
Scope: `openclaw/learning/analyzer.py`, `openclaw/analysis/rule_engine.py`, `openclaw/analysis/tagger.py`, `openclaw/analysis/edge_config.py`, and live DB diagnostics.

## 1) Executive Summary

No hard stop was found (data is usable and scoring can be repaired in-place), so D2 can proceed.

High-priority issues were found:
- `set_tier` rules are effectively ignored in bulk scoring (`rescore_all`) due to tier recomputation from numeric score.
- Core base-score inputs are on mixed scales before weighting (raw splits, dollars, categorical owner heuristic).
- Learning proposals are persisted/reviewed but not structurally applied with bounded, decayed effects.
- Legacy thumbs-up score inflation likely left stale high scores; pipeline re-score is needed.

## 2) Current Flow Map

### 2.1 Learning analyzer (`openclaw/learning/analyzer.py`)
- `fetch_feedback_signal()` pulls recent feedback + candidate/parcel context and aggregates counters.
- `build_analysis_prompt()` composes a GPT-4o prompt with top reasons/tags and sample downvoted cases.
- `run_ai_analysis()` calls OpenAI chat completions, regex-extracts JSON array, and parses proposals.
- `save_proposals()` inserts proposals into `learning_proposals`, deduping only by pending-description exact match.
- `run_nightly_learning()` orchestrates and skips if feedback count < 3.

Audit notes:
- SQL interval construction uses string replacement; works, but is brittle.
- Logger text still says "Claude" in places; stale naming.
- Proposal schema is free-form text; no validation for machine-applicable rule payloads.

### 2.2 Rule engine (`openclaw/analysis/rule_engine.py`)
- Loads active `scoring_rules`, evaluates exclude/set_tier/adjust_score.
- Computes base score from splits, value-per-lot, owner type.
- Applies EDGE boosts and RISK penalties from tagger outputs.
- `rescore_all()` enriches with subdivision/econ/arbitrage layers and writes back candidate fields.

Critical behavioral defect found:
- `evaluate_candidate()` computes `explicit_tier`, but `rescore_all()` discards it and always does `tier = score_to_tier(score)` in non-exclude path. This conflicts with rule semantics and can produce rule-violating tiers.

### 2.3 Tagger + edge config (`tagger.py`, `edge_config.py`)
- EDGE tags generated for LSA/RUTA/HB1110/unit-lot/rural-cluster/user-upvote.
- RISK tags generated for constraints and missing data.
- Edge weights are env-configurable.

Calibration notes:
- `EDGE_USER_UPVOTE` creates a direct score path from vote net; this is explainable but can amplify sparse feedback.
- Many high-scoring records carry broad default risk tags (`RISK_HB1110_DATA_UNAVAILABLE`, `RISK_UNIT_LOT_DATA_UNAVAILABLE`), reducing discriminative power.

## 3) Required DB Diagnostics (Executed)

### 3.1 Tier distribution
`SELECT score_tier, COUNT(*) FROM candidates GROUP BY score_tier;`

- A: 5,797
- B: 1,685
- C: 1,988
- D: 5,729
- E: 7,533
- F: 308

### 3.2 Score statistics
`SELECT MIN(score), MAX(score), ROUND(AVG(score),1), ROUND(STDDEV(score),1) FROM candidates;`

- min: 0
- max: 95
- avg: 22.1
- stddev: 17.0

### 3.3 Feedback volume
`SELECT COUNT(*) FROM candidate_feedback;`

- total feedback rows: 37

Additional split:
`SELECT rating, COUNT(*) FROM candidate_feedback GROUP BY rating ORDER BY rating;`
- down: 28
- up: 9

### 3.4 Learning proposals status
`SELECT status, COUNT(*) FROM learning_proposals GROUP BY status;`

- pending: 6
- approved: 3
- rejected: 1

## 4) Findings By Requested Category

### 4.1 Dead code / stale logic
- Learning route approval currently marks proposal approved/rejected but does not enforce structured application to scoring rules.
- Analyzer logging references "Claude" although implementation uses OpenAI GPT-4o.

### 4.2 Non-normalized inputs
- Base scoring mixes unbounded/raw numeric inputs and categorical heuristics before weighted aggregation.
- Dynamic rule adjustments are absolute point deltas with no bounded learning policy.

### 4.3 Corrupted score risk from old thumbs-up override
- Historical override behavior (`score = max(90, current+40)`) can leave stale inflated scores.
- Heuristic suspect rows (score >= 90) found: 6 candidates currently at 90–95.
- Sample IDs:
  - `9b67fd42-81c8-4ef0-a68d-01590a50586b` (95)
  - `a7ac5534-ef69-4787-a600-3402ff4aa261` (91)
  - `3e78dba0-8653-4566-8212-dc0e9d8f8898` (90)
  - `115cc88e-c971-47b8-84c1-20eda232c17d` (90)
  - `a131ed90-d0ec-4fac-91a8-de0c4fe0d1cd` (90)
  - `7ff474dd-d077-4bf8-b1a5-597a840e8505` (90)

Conclusion: best repair is full pipeline re-score of all candidates (deterministic recompute), not selective patching.

### 4.4 Conflicting rules
- Active rules include 4 `set_tier` rules and 3 `adjust_score` rules.
- Because `rescore_all()` recomputes tier from score, `set_tier` intent conflicts with persisted result.

### 4.5 Feedback-loop adequacy
- 37 total feedback rows is low signal for robust auto-learning; downvote-heavy skew (28/37) can bias rule proposals.
- Proposal dedupe by description string only is weak against semantically duplicated recommendations.

## 5) Prioritized Improvement Plan (D2)

1. Fix rule-engine consistency and determinism:
- Preserve explicit `set_tier` in persisted scoring path.
- Normalize base feature inputs to [0.0, 1.0] before weighted sum.

2. Add bounded + decayed learning adjustments:
- Env-configurable max learned delta (default ±15).
- Time-decay multiplier by half-life days (default 30) for approved-learning-derived rule adjustments.

3. Improve explainability:
- Add score explanation endpoint with component-level breakdown.

4. Repair historical corruption:
- Re-score through full pipeline to overwrite stale legacy-inflated scores.

5. Lock determinism in tests:
- Add fixture-based ranking determinism tests for same input/rules.

Estimated effort: small-to-medium (single module + router + tests + one rescore run).

## 6) Critical Blocker Decision

Critical blocker threshold ("fundamentally broken or data corrupt beyond repair") was **not** met.

Decision: proceed to D2 immediately with the above priority order.
