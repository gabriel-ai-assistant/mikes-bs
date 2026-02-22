# Feasibility Audit (Pre-Implementation)

## Scope Reviewed
- `openclaw/analysis/*` (including `dif/*` components)
- `openclaw/db/models.py`
- `openclaw/web/app.py`
- `openclaw/web/templates/*`
- `alembic/versions/*`

## Existing Analysis Stack
- `openclaw/analysis/scorer.py`: SQL-first candidate creation pipeline, provisional split estimates, wetland/ag/HOA flags.
- `openclaw/analysis/tagger.py`: primary EDGE/RISK tag producer with LSA/RUTA/HB1110/unit-lot/rural cluster logic.
- `openclaw/analysis/edge_config.py`: env-driven weights and zone-set configuration.
- `openclaw/analysis/rule_engine.py`: consumer for tags + rules + subdivision/econ/arbitrage outputs; performs global rescore and persists candidate fields.
- `openclaw/analysis/subdivision.py`: split-range estimation, frontage/width/access confidence, flags and reason codes.
- `openclaw/analysis/subdivision_econ.py`: economic margin gate with RISK tags.
- `openclaw/analysis/arbitrage.py`: arbitrage depth scoring + tags based on lot ratio/rurality/UGA/RUTA/underpricing.
- `openclaw/analysis/profit.py`: ARV and cost/profit model.
- `openclaw/analysis/dif/*`: DIF component framework (YMS/EFI/ALS/CMS/SFI) and composite delta calculator.

## Current Tag System Findings
- Tags are stored in `candidates.tags` (`TEXT[]`) and `reason_codes` (`TEXT[]`).
- Producers span `tagger.py`, `subdivision.py`, `subdivision_econ.py`, `arbitrage.py`.
- Main scoring consumer is `rule_engine.evaluate_candidate()` and bulk consumer `rescore_all()`.
- Weighting is config-driven in `edge_config.py` and environment-overridable.

## DB Schema Findings (`models.py`)
- Core entities: `Parcel`, `Candidate`, `Lead`, `ZoningRule`, `CriticalArea`, `ShorelineBuffer`, `RutaBoundary`.
- Candidate already includes arrays (`tags`, `reason_codes`, `subdivision_flags`) and subdivision/econ/arbitrage fields.
- No feasibility-results table exists yet.

## Web/API Findings (`web/app.py`)
- Existing pages: dashboard, candidates, property detail, leads, map, settings, learning.
- Existing APIs: candidates list/detail, tags, use-types, feedback, notes, rules CRUD, rescore, leads status, map points, learning actions.
- No feasibility endpoints/pages currently exist.

## Template Findings
- Rich candidate modal reused in dashboard/candidates/map/property pages.
- Property page already supports deep detail + feedback/notes.
- Candidates table shows existing subdivision and tag-derived signals.

## Migration History Findings
- `001`: core schema + enums + spatial tables.
- `002`: candidate tags/reasons + RUTA boundary.
- `003`: alpha engine tables + `candidates.uga_outside`.
- `004`: subdivision fields.
- `005`: tax delinquency + parcel sales.
- `006`: learning proposals table.
- `007` (`006_splits_range_arbitrage.py`): splits range/confidence/access mode + arbitrage/econ + `parcels.parcel_width_ft`.

## Integration Constraints Observed
- Existing scoring stack is already tag-centric and DB-backed; feasibility engine should complement, not replace.
- Existing app uses synchronous SQLAlchemy session dependency (`db()` wrapper over `get_session()`).
- Geo columns are in SRID 4326 in DB, while requested feasibility runtime CRS is EPSG:2285; reprojection is required in the new pipeline.

