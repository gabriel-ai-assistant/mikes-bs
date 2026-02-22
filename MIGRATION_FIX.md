# Alembic Migration Repair (PREP-1)

Date: 2026-02-22

## Summary
Alembic metadata drift was repaired and the revision chain is now linear with a single head.

Current status:
- `alembic current` => `009 (head)`
- `alembic heads` => `009 (head)`
- `alembic_version` table contains exactly one row: `009`

## Audit of `alembic/versions/`

| File | revision | down_revision |
|---|---|---|
| `001_initial_schema.py` | `001` | `None` |
| `002_add_candidate_tags.py` | `002` | `001` |
| `003_alpha_engine.py` | `003` | `002` |
| `004_subdivision.py` | `004` | `003` |
| `005_tax_delinquency_and_sales.py` | `005` | `004` |
| `006_learning.py` | `006` | `005` |
| `006_splits_range_arbitrage.py` | `007` | `006` |
| `008_feasibility_results.py` | `008` | `007` |
| `009_fix_block_architecture.py` | `009` | `008` |

Important finding:
- There is no duplicate revision *ID* in the current code.
- The previous problem was DB metadata drift: `alembic_version` had both `007` and `008`, which caused overlap errors.

## Backup Before Changes
Pre-fix `alembic_version` contents:

```csv
version_num
007
008
```

## Repair Actions Performed

1. Normalized `alembic_version` to one applied revision:
- Removed stale `007` row from `alembic_version`.

2. Applied the new migration with host Alembic (using DB URL pointed at `localhost:5433`):
- `alembic upgrade head` ran `008 -> 009` successfully.

3. Verified final state:
- `alembic current` shows `009 (head)`.
- `alembic heads` shows only `009 (head)`.
- `alembic_version` table has one row (`009`).

## Notes
- The Docker `web` service only bind-mounts `./openclaw`, not `./alembic`, so container-side Alembic commands can use stale migration files.
- For migration operations, run Alembic from host environment (or update Compose mounts in a future cleanup).
