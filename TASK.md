# OpenClaw Implementation Prompt — Mikes BS App (v4)

**Phase:** Parcel Bundles + List UX + Learning Audit + Lead System + OSINT Integration (Snohomish County)
**Architecture baseline:** See `ARCHITECTURE.md` and `OSINT_ARCHITECTURE.md` (2026-02-22 discovery reports)

---

## Agent Roles & Overnight Supervision

| Agent | Runtime | Role |
|---|---|---|
| **Codex** (OpenAI) | Primary worker | Writes code, runs tests, applies diffs, commits. Does the actual implementation work across all phases. |
| **Gabriel** (Anthropic, via OpenClaw) | Overseer / Supervisor | Monitors Codex progress, checks for stuck workers, validates outputs, escalates blockers. Does NOT write code directly — orchestrates and reviews. |

### Supervision Contract (Gabriel)

Gabriel MUST check on Codex progress at regular intervals. This is critical for overnight runs where no human is available.

```
SUPERVISION LOOP (Gabriel):
  every 15 minutes:
    1. Query Codex task status
    2. If task has been running > 30 min with no commits/output:
       → Send nudge: "Status check — are you blocked? Report current phase and any errors."
    3. If task has been running > 60 min with no progress:
       → Log WARNING, capture last known state
       → Restart the task from last successful checkpoint
    4. If task errors 3x consecutively on same phase:
       → STOP, log full error context, alert Marcus via notify/digest
    5. On phase completion:
       → Validate output (files exist, tests pass, no regressions)
       → Log phase completion + duration
       → Advance to next phase
```

### Codex Checkpoint Protocol

After completing each block/sub-block, Codex MUST:
1. Run the relevant test suite and report pass/fail counts.
2. Commit with message: `[openclaw] {block}: {description}` (e.g., `[openclaw] PREP-1: fix Alembic revision chain`).
3. Write a progress marker: `echo "{BLOCK}_COMPLETE $(date -Iseconds)" >> /tmp/openclaw_progress.log`
4. If a block takes > 20 minutes, write interim heartbeats: `echo "{BLOCK}_HEARTBEAT $(date -Iseconds)" >> /tmp/openclaw_progress.log`

Gabriel reads `/tmp/openclaw_progress.log` to detect stuck workers.

### Stuck Worker Recovery

If Codex is stuck and cannot fix an issue in 10 minutes:
1. Commit current state with `[WIP]` prefix in commit message.
2. Write `BLOCKED.md` describing: which block, what error, what was tried.
3. Write `{BLOCK}_BLOCKED` to progress log.
4. Move to the next block (if dependencies allow).

Gabriel detects `_BLOCKED` markers and can reassign or escalate.

---

## 0) Mission

Implement seven feature blocks **plus** architecture fixes and OSINT integration against the **existing** FastAPI + PostgreSQL/PostGIS + Jinja2/Vanilla JS stack.

| Priority | Block | Name | Depends On |
|----------|-------|------|------------|
| -1 | **FIX** | Architecture review fixes (spatial units, owner canonicalization, enum migration, etc.) | — |
| 0 | **PREP** | Fix Alembic + decompose app.py + add ORM models for raw tables | FIX |
| 1 | **A** | Adjacent same-owner parcel bundle detection | PREP |
| 2 | **B** | External listing + tax links under property map | PREP |
| 3 | **C** | Candidates list UX overhaul (voting fix, columns, filters) | PREP |
| 4 | **D** | Deep structural audit + improvement of Learning module | PREP, C |
| 5 | **E** | Lead system extension + owner enrichment pipeline | A, C |
| 6 | **F** | Bulk operations + export | C, E |
| 7 | **G** | Lead follow-up reminders + map status overlay | E |
| 8 | **H** | OSINT owner investigation integration (consumer only) | E |

All work must be deterministic, testable, observable, schema-driven, and mobile-responsive.

---

## 1) Hard Constraints

- ❌ No schema guessing — read the actual code first.
- ❌ No new boolean fields — use enums, tags, or structured annotations.
- ❌ No scraping behind logins.
- ❌ No violating ToS of any external service.
- ❌ No bypassing privacy protections.
- ❌ No storing unlawful personal data.
- ❌ No leaking sensitive PII outside app boundaries.
- ❌ No black-box ML — all scoring must be explainable.
- ❌ No adding React, Vue, or any JS framework — stay Jinja2 + vanilla JS.
- ❌ No adding Redis or any new infrastructure services — work within existing Docker Compose topology.
- ❌ No modifying the OSINT platform codebase — OpenClaw is a consumer only (see Block H).
- ✅ Must use existing TEXT[] tag system with EDGE_*/RISK_*/INFO_* prefix convention.
- ✅ Must integrate with existing scoring pipeline (`tagger.py` → `rule_engine.py`).
- ✅ Must be legally compliant (FCRA, TCPA, state privacy laws).
- ✅ Must degrade gracefully (see §12 for degradation contracts).
- ✅ Must be mobile-responsive (touch targets ≥44px, no horizontal scroll on 375px viewport).
- ✅ Must support small team use (2–5 users, lightweight auth).

---

## 2) Stack Reference (DO NOT RE-DISCOVER)

This is already known. Do not waste time re-discovering. Use these paths directly:

```
Backend:        Python 3.12 + FastAPI + Jinja2 SSR
Database:       PostgreSQL 16 + PostGIS 3.4 (Docker)
ORM:            SQLAlchemy 2.0 + GeoAlchemy2 (sync sessions)
Migrations:     Alembic (BROKEN — see PREP block)
Background:     APScheduler (in-process) + FastAPI BackgroundTasks
Frontend:       Vanilla JS, inline per Jinja2 template, no build step
Deployment:     Docker Compose (postgis, app, web services)
Logging:        Python stdlib logging, unstructured, stdout
Caching:        In-memory dicts only (no Redis)
LLM:            OpenAI GPT-4o (learning analyzer only)

Key files:
  Models:         openclaw/db/models.py
  Session:        openclaw/db/session.py
  All routes:     openclaw/web/app.py (~1,100 lines, monolithic)
  Templates:      openclaw/web/templates/ (9 Jinja2 templates)
  Scoring:        openclaw/analysis/rule_engine.py
  Tagger:         openclaw/analysis/tagger.py + edge_config.py
  Learning:       openclaw/learning/analyzer.py
  Config:         openclaw/config.py + openclaw/config/*.json
  Skip trace:     openclaw/enrich/skip_trace.py (stubbed, not wired)
  Owner enrich:   openclaw/enrich/owner.py (Lob stubbed, not wired)
  Delta sync:     openclaw/ingest/delta_sync.py
  Feasibility:    openclaw/analysis/feasibility/ (7-phase pipeline)
  Tests:          tests/ (analysis + feasibility only, no web tests)
```

### Existing tables WITHOUT ORM models (raw SQL only):
- `scoring_rules` — field, operator, value, action, priority
- `candidate_feedback` — candidate_id, rating, category, notes
- `learning_proposals` — AI-generated proposals, status (pending/approved/rejected)
- `candidate_notes` — free-text notes per candidate
- `critical_areas`, `shoreline_buffer`, `ruta_boundaries`, `road_centerlines`, `parcel_sales`, `tax_delinquency`

### Existing Lead model (already in models.py):
```
Lead: candidate_id (FK), status (new/reviewed/outreach/active/dead),
      owner_phone, owner_email, notes, contacted_at, contact_method, outcome
```

### Existing feedback endpoint behavior (PROBLEMATIC):
`POST /api/candidate/{id}/feedback` with `rating=up` → forces `score = max(90, current+40)` → guaranteed Tier A.
This bypasses the scoring pipeline and must be fixed in Block C.

### OSINT Platform (EXTERNAL — consumer only):
```
Codebase:       osint-platform/ (separate repo, NOT part of OpenClaw)
Runtime:        Uvicorn on port 8000, same host (aidev01)
Database:       SQLite (data/investigations.db) — NOT our DB
API Base:       http://localhost:8000/api
Auth:           None (internal tool, no auth required)
Blocking:       Synchronous — provider queries run in request thread (10-60s per call)
```
OpenClaw treats this as an opaque external service. We call its HTTP API and store the investigation ID. We do NOT read its SQLite DB, modify its code, manage its deployment, or depend on its internals.

---

## 2.5) FIX Block — Architecture Review Fixes (MANDATORY BEFORE PREP)

These fixes address bugs and ambiguities discovered during architecture review. Apply these FIRST.

### FIX-A: PostGIS Distance Units Are Wrong

**Problem:** `ST_DWithin(geom4326, geom4326, 10)` interprets `10` as **degrees** (not feet) because `parcels.geometry` is EPSG:4326. This is a critical spatial bug.

**Fix:** All distance queries MUST use `::geography` cast for meter-based distance:
```sql
-- CORRECT: 3.048 meters ≈ 10 feet
ST_DWithin(a.geometry::geography, b.geometry::geography, 3.048)
```

For adjacency, prefer `ST_Touches(a.geometry, b.geometry)` first, fall back to `ST_DWithin(...::geography, ..., 3.048)` as tolerance.

**Scope:** Grep the entire codebase for `ST_DWithin` and fix every occurrence. Add a comment at each site documenting units.

### FIX-B: ArcGIS vs PostGIS Source-of-Truth for Adjacency

**Problem:** Block A mixes ArcGIS radius fetch (A1) and PostGIS adjacency (A2) without a clear data contract.

**Decision:** PostGIS is source-of-truth for geometry adjacency. The `parcels` table contains the full Snohomish County parcel fabric. ArcGIS is used ONLY for refreshing stale/missing owner attribute fields (`OWNERNAME`, `TAXPRNAME`, `MAILADDR`).

Add this data contract comment to the top of any adjacency module:
```python
# DATA CONTRACT: Adjacency operates on parcels present in the local PostGIS DB.
# ArcGIS REST is used only to refresh owner/taxpayer fields when stale or missing.
# If a neighbor parcel is missing from DB, log a warning — do NOT fetch geometry from ArcGIS.
```

### FIX-C: Canonicalize Owner Names for Bundle Matching

**Problem:** `parcels.owner_name` may be stale/incomplete. ArcGIS returns `OWNERNAME`/`TAXPRNAME` separately. Bundle matching (Block A3) depends on a reliable owner string.

**Fix:** Create a canonical owner string with a documented fallback chain:
```python
# owner_name_canonical = coalesce(
#     parcels.owner_name,           -- prefer DB (most recent delta sync)
#     arcgis.OWNERNAME,             -- fallback to ArcGIS live query
#     arcgis.TAXPRNAME              -- last resort: taxpayer name
# )
```

- Compute and store `owner_name_canonical` on the `candidates` table (new column, Alembic migration, VARCHAR).
- Store `match_basis` in `bundle_data` JSONB: `"db_owner"` | `"arcgis_owner"` | `"arcgis_taxpayer"` — so debugging shows which source was used.
- Recompute canonical name whenever owner attributes are refreshed.

### FIX-D: Tighten Fuzzy Matching Gates

**Problem:** "Levenshtein ≤ 2 or token-set ≥ 0.85" without guards will produce false positives on short or common names.

**Fix:** Add these constraints to Block A3 fuzzy matching:
- **Minimum name length:** Skip fuzzy match if `owner_name_canonical` has fewer than 6 characters.
- **ZIP gate:** If mailing ZIP is available (from ArcGIS `MAILADDR` or `parcels.owner_address`), require exact ZIP match for fuzzy-tier matches. Exact name matches bypass this gate.
- **Algorithm:** Use `rapidfuzz.fuzz.token_set_ratio`. Normalization: lowercase, strip suffixes (`LLC`, `INC`, `TRUST`, `CORP`, `ET AL`, `ETAL`), collapse whitespace.
- **Store similarity score:** Write `similarity_score` (float 0.0–1.0) into `bundle_data` JSONB for debugging and future threshold tuning.

### FIX-E: Lead Status Enum Migration — Use TEXT + CHECK

**Problem:** Postgres enums can ADD VALUE but can't cleanly drop old values. Current Lead.status enum (`new/reviewed/outreach/active/dead`) conflicts with Block E1's new statuses. Alembic is already fragile.

**Fix:** Migrate to `TEXT + CHECK` constraint (safest approach given existing Alembic issues):
```sql
-- Alembic migration:
-- 1. Convert column type
ALTER TABLE leads ALTER COLUMN status TYPE TEXT USING status::TEXT;
-- 2. Add check constraint with ALL values (old + new)
ALTER TABLE leads ADD CONSTRAINT leads_status_check
  CHECK (status IN ('new', 'researching', 'contacted', 'negotiating',
                    'closed_won', 'closed_lost', 'dead'));
-- 3. Migrate old values
UPDATE leads SET status = 'researching' WHERE status = 'reviewed';
UPDATE leads SET status = 'contacted' WHERE status = 'outreach';
UPDATE leads SET status = 'negotiating' WHERE status = 'active';
-- 4. Drop old enum type
DROP TYPE IF EXISTS leadstatus;
```

Update `Lead` model in `models.py`: replace `Enum` column with `String` + a Python-side validator. This replaces the migration plan in Block E1 — do NOT use `ALTER TYPE ... ADD VALUE` approach.

### FIX-F: SnoCo Tax URL

**Problem:** `https://snohomishcountywa.gov/654/Property-Search` may not support direct parcel prefill and the URL is fragile.

**Fix:** Use the stable landing page. In Block B's link table:
```
SnoCo Tax: https://www.snoco.org/proptax/
Display:   "Search Parcel No: {parcel_id}" (copy hint, not deep-link)
```

### FIX-G: Bundle Refresh + Invalidation Rules

Add to Block A4 bundle storage logic:
- **Recompute triggers:** On rescore, on owner attribute refresh (delta sync), or on manual `POST /api/candidate/{id}/detect-bundle`.
- **Invalidation:** If parcel geometry changes or `owner_name_canonical` changes, mark bundle as stale.
- **TTL:** Bundles older than 7 days get a `stale` flag in `bundle_data`. Still displayed but visually marked and queued for recompute on next access or nightly job.
- **`detected_at`:** Already in the A4 schema. Add `stale: boolean` to the JSONB structure.

### FIX-H: Vote → Tag Threshold

For Block C1's `EDGE_USER_UPVOTE` tag application in `tagger.py`:
- **Threshold:** Net positive votes ≥ 1 (i.e., `up_count - down_count >= 1`)
- **Window:** All-time (no time decay for MVP)
- **Weighting:** None (all users equal)
- Document these defaults in the tagger code and make the threshold configurable via `VOTE_NET_THRESHOLD` env var (default 1).

### FIX-I: Text Search Indexing Plan

For Block C3's unified filter bar `q` parameter:
- **Phase 1 (implement now):** Use `ILIKE` on a concatenated display field. Add a computed/cached column `display_text` on candidates: `address || ' ' || owner_name_canonical`. Query: `WHERE display_text ILIKE '%{q}%'`.
- **Phase 2 (implement later, when slow):** Add `pg_trgm` extension + GIN index:
```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX idx_candidates_display_trgm ON candidates USING GIN (display_text gin_trgm_ops);
```
- Do NOT implement Phase 2 now. Add a `TODO` comment with this SQL. Only escalate if query time on the candidates endpoint exceeds 200ms at current data volume.

### FIX Block Deliverables

| Fix | File(s) Touched | Verification |
|---|---|---|
| FIX-A | All files with `ST_DWithin` | `grep -rn ST_DWithin` returns zero raw-degree usages |
| FIX-B | Adjacency modules | Data contract comment present |
| FIX-C | `models.py`, tagger/bundle logic, Alembic migration | Test canonical fallback chain (DB → ArcGIS owner → ArcGIS taxpayer) |
| FIX-D | Bundle matching module | Test: 4-char name skipped, ZIP mismatch rejected on fuzzy |
| FIX-E | Alembic migration, `models.py` | Migration up/down clean, `Lead.status` is TEXT |
| FIX-F | Block B link config | Grep confirms `snoco.org/proptax` |
| FIX-G | Bundle storage module | Test TTL flag, invalidation on owner change |
| FIX-H | `tagger.py` | Test net-vote ≥1 → tag applied, 0 → tag absent |
| FIX-I | Candidate query logic | Test ILIKE on display_text returns correct results |

---

## 3) PREP Block — Fix Tech Debt Before Features

### PREP-1: Fix Alembic

**Problem:** Duplicate migration `006` (two files with revision ID `006`), volume mount gap, broken head tracking.

**Required:**
1. Audit `alembic/versions/` — list all files with their revision IDs and `down_revision` chains.
2. Resolve the duplicate 006: determine which is canonical, rename or merge the other.
3. Fix the revision chain so `alembic history` shows a clean linear sequence 001→008.
4. Verify `alembic current` matches DB state.
5. Ensure all future migrations go through Alembic (no more manual `psql` + `alembic_version` inserts).
6. Document the fix in a `MIGRATION_FIX.md`.

**⚠️ DESTRUCTIVE RISK:** Do not drop or alter existing tables. Only fix Alembic metadata. Back up `alembic_version` table contents before any changes.

### PREP-2: Decompose app.py

**Problem:** `openclaw/web/app.py` is ~1,100 lines with all routes. Adding 20+ new endpoints here is unsustainable.

**Required:**
Split into FastAPI routers:
```
openclaw/web/
  app.py              ← slim: mounts routers, middleware, startup events
  routers/
    candidates.py     ← /api/candidates, /api/candidate/{id}, /candidates (HTML)
    leads.py          ← /api/leads, /leads (HTML)
    scoring.py        ← /api/rescore, /api/rules, /api/feedback
    learning.py       ← /api/learning/*, /learning (HTML)
    map.py            ← /api/map/*
    feasibility.py    ← /api/feasibility/*
    settings.py       ← /settings (HTML), /api/rules
    auth.py           ← (new) /api/auth/*
```

**Rules:**
- Pure mechanical refactor — zero behavior changes.
- Every existing endpoint must work identically after split.
- Add a basic smoke test: hit every existing endpoint, assert non-500 response.

### PREP-3: Add ORM Models for Raw SQL Tables

Create SQLAlchemy models for:
- `ScoringRule` (maps `scoring_rules` table)
- `CandidateFeedback` (maps `candidate_feedback` table)
- `LearningProposal` (maps `learning_proposals` table)
- `CandidateNote` (maps `candidate_notes` table)

**Rules:**
- Models must match existing table schemas exactly (column names, types, constraints).
- Do NOT generate a new Alembic migration for these — the tables already exist.
- Use `__table_args__ = {'extend_existing': True}` or map to existing tables.
- Replace raw SQL queries with ORM queries where touched by subsequent feature blocks.

### PREP-4: Basic Auth (Lightweight)

**Problem:** No authentication at all. Lead PII + enrichment data needs access control.

**Implement minimal auth:**
- Add `User` table: id, username, password_hash, role (enum: admin/member/viewer), created_at.
- Password hashing via `passlib[bcrypt]`.
- Session-based auth (cookie) — fits the SSR architecture. No JWT needed.
- Login page (`/login`) + logout endpoint.
- Middleware: redirect unauthenticated requests to `/login` (except static assets).
- Seed one admin user from env vars: `ADMIN_USERNAME`, `ADMIN_PASSWORD`.
- Role enforcement:
  - **admin:** all actions + manage users + config knobs + delete enrichment data.
  - **member:** view, vote, promote leads, add enrichment, export, set reminders.
  - **viewer:** read-only.
- Default new users to `member`.

**Alembic migration required for User table.**

---

## 4) Feature Block A — Adjacent Same-Owner Parcel Bundles

**Goal:** Detect when adjacent parcels share the same owner, group them into bundles, surface in scoring + UI.

### A1) ArcGIS Parcel Query
- Use existing ArcGIS client pattern from `openclaw/ingest/delta_sync.py` and `openclaw/analysis/feasibility/api_client.py`.
- Query Snohomish County parcel layer for parcels within configurable radius of candidate parcel centroid.
- Cache responses in-memory dict with configurable TTL (default 24h), matching existing caching pattern in `arbitrage.py`.
- **Per FIX-B:** ArcGIS is used here ONLY for owner attribute refresh, NOT for geometry. Adjacency geometry comes from PostGIS.

### A2) Geometry Adjacency Detection
- **Per FIX-A:** Use PostGIS `ST_Touches` first, fall back to `ST_DWithin(a.geometry::geography, b.geometry::geography, 3.048)` (3.048m ≈ 10ft tolerance).
- Candidate parcels already have `geometry` (EPSG:4326) in the `parcels` table via GeoAlchemy2.
- Compute adjacency in a single SQL query where possible (avoid N+1).

### A3) Owner Normalization + Matching
- **Per FIX-C:** Use `owner_name_canonical` (computed with documented fallback chain) as the matching input.
- Match tiers:
  - **Exact:** normalized canonical names identical.
  - **Fuzzy:** Token-set similarity ≥ 0.85 using `rapidfuzz.fuzz.token_set_ratio` (per FIX-D: min 6 chars, ZIP gate for fuzzy tier, store similarity_score).
  - **Entity:** same registered agent or business entity link (if enrichment provides this).
- Store match tier + similarity_score on the bundle annotation.

### A4) Storage
- Add `bundle_data` JSONB column to `candidates` table (Alembic migration).
- Structure:
```json
{
  "parcels": [{"parcel_id": "...", "owner_name": "...", "lot_sf": 0, "assessed_value": 0}],
  "match_tier": "exact|fuzzy|entity",
  "match_basis": "db_owner|arcgis_owner|arcgis_taxpayer",
  "similarity_score": 0.92,
  "total_acres": 5.2,
  "total_assessed_value": 450000,
  "detected_at": "ISO8601",
  "stale": false
}
```
- **Per FIX-G:** Include `stale` flag, recompute on rescore/owner refresh, invalidate on geometry or canonical name change, 7-day TTL.
- Add tags to existing `candidates.tags` TEXT[]: `EDGE_BUNDLE_ADJACENT`, `EDGE_BUNDLE_SAME_OWNER`.
- These tags flow through existing `tagger.py` → `rule_engine.py` scoring.

### A5) Scoring Boost
- Add `EDGE_BUNDLE_ADJACENT` and `EDGE_BUNDLE_SAME_OWNER` to `edge_config.py` with configurable weights.
- Default: `EDGE_BUNDLE_SAME_OWNER` = +10, `EDGE_BUNDLE_ADJACENT` = +5.
- Cap total bundle boost at configurable max (default +15) — enforce in `rule_engine.py`.

### A6) Map Overlay UI
- On `property.html` map: highlight bundled parcels with shared outline color.
- Add bundle summary tooltip (parcel count, total acres, match tier).
- Use existing Leaflet/map library already in `map.html`.
- Mobile: tap to expand bundle info.

### A7) API
- `GET /api/candidate/{id}/bundle` — returns bundle_data JSON.
- Bundle detection: runs as part of scoring pipeline OR as standalone `POST /api/candidate/{id}/detect-bundle`.

### A8) Tests
- Unit: owner normalization, match tier logic, scoring cap enforcement, FIX-D gates (min length, ZIP).
- Integration: mock ArcGIS response → PostGIS adjacency query → bundle annotation created → score updated.

---

## 5) Feature Block B — External Links Under Property Map

**Goal:** Show useful external links below the property map on `property.html`.

### Links:
| Link | URL Pattern |
|------|-------------|
| NWMLS | `https://www.nwmls.com/` (landing — no deep-link available) |
| Zillow | `https://www.zillow.com/homes/{url_encoded_address}_rb/` |
| Redfin | `https://www.redfin.com/search?q={url_encoded_address}` |
| SnoCo Tax | `https://www.snoco.org/proptax/` — display "Search Parcel No: {parcel_id}" as copy hint (per FIX-F: no deep-link, stable URL) |

### Implementation:
- Add link row to `property.html` template below the map div.
- Link definitions in a config dict in the router (or `config.py`), not hardcoded in template.
- "Copy address" button using Clipboard API with `document.execCommand('copy')` fallback.
- Links open in new tab (`target="_blank" rel="noopener noreferrer"`).
- Mobile: stack vertically, full-width touch targets.

### Tests:
- Unit: URL construction from address + parcel_id.

---

## 6) Feature Block C — Candidates List UX Overhaul

### C1) Fix Voting (Thumbs Up / Down)

**Current problem:** `POST /api/candidate/{id}/feedback` with `rating=up` bypasses scoring pipeline by forcing `score = max(90, current+40)` → Tier A. This creates score corruption and makes the learning module unreliable.

**Fix:**
- **Remove the score override from the feedback endpoint.** Voting must NOT directly mutate `candidates.score`.
- Votes are stored in `candidate_feedback` table (already exists).
- Votes influence scoring ONLY through the learning pipeline (`learning/analyzer.py` → proposals → approved rules).
- Add a dedicated `EDGE_USER_UPVOTE` tag (+configurable boost, default +8) that the tagger applies when a candidate has net positive votes. **Per FIX-H:** threshold is net votes ≥ 1, all-time window, no per-user weighting. Configurable via `VOTE_NET_THRESHOLD` env var.
- Mutual exclusivity: one active vote per user per candidate. New vote replaces previous.
- Toggle: clicking same vote again removes it.
- API: keep existing `POST /api/candidate/{id}/feedback` but fix the handler.

**UI (candidates.html):**
- Thumbs up / thumbs down icons in each list row.
- Filled/highlighted when active (fetch current vote state per candidate).
- Optimistic update via fetch() + DOM manipulation, rollback on failure.
- Mobile: min 44px touch targets.

**Tests:**
- Unit: vote toggle, mutual exclusivity, no score override, FIX-H threshold logic.
- Integration: vote → tag applied → rescore → score changes by configured amount (not +40/force 90).

---

### C2) Column Chooser + Ordering

**Column registry** — define in a JS object in `candidates.html` (or a separate `columns.js` file loaded by the template):
```javascript
const COLUMN_REGISTRY = [
  { key: "address", label: "Address", default: true, order: 0, sortable: true },
  { key: "score", label: "Score", default: true, order: 1, sortable: true },
  { key: "score_tier", label: "Tier", default: true, order: 2, sortable: true },
  { key: "vote", label: "Vote", default: true, order: 3, sortable: false },
  { key: "potential_splits", label: "Splits", default: true, order: 4, sortable: true },
  { key: "lot_sf", label: "Lot SF", default: false, order: 5, sortable: true },
  { key: "zone_code", label: "Zone", default: false, order: 6, sortable: true },
  { key: "subdivision_feasibility", label: "Feasibility", default: false, order: 7, sortable: true },
  { key: "economic_margin_pct", label: "Margin %", default: false, order: 8, sortable: true },
  { key: "tags", label: "Tags", default: false, order: 9, sortable: false },
  { key: "lead_status", label: "Lead Status", default: false, order: 10, sortable: true },
  { key: "has_bundle", label: "Bundle", default: false, order: 11, sortable: true },
  { key: "osint_status", label: "OSINT", default: false, order: 12, sortable: true }
];
```

**UI:**
- Gear icon in table header → dropdown panel with checkboxes + drag handles (or up/down buttons).
- "Reset to defaults" button.
- Mobile: full-screen modal instead of dropdown.

**Persistence:**
- `localStorage` keyed by user ID (once auth exists): `column_config_{user_id}`.
- Server-side persistence is a nice-to-have but not required for initial implementation.

**Tests:**
- Unit (JS): column registry merge with saved prefs, reset logic.

---

### C3) Unified Filter Bar

**Replace** the current separate tier/tag/use_type filters with a unified filter model:

```json
{
  "q": "",
  "tiers": [],
  "tags_any": [],
  "tags_none": [],
  "use_types": [],
  "score_min": null,
  "score_max": null,
  "vote": null,
  "lead_status": null,
  "has_bundle": null,
  "osint_status": null,
  "sort": { "key": "score", "dir": "desc" },
  "page": 1,
  "limit": 50
}
```

**Backend:**
- Update `GET /api/candidates` to accept all filter params.
- Backwards-compatible: existing `tier`, `tag`, `score_min`, `score_max` params still work, mapped to canonical model.
- New params: `tags_none`, `vote`, `lead_status`, `has_bundle`, `osint_status`, `q` (text search — per FIX-I: ILIKE on `display_text` for now).

**Frontend (`candidates.html`):**
- Horizontal chip-based filter bar above the table.
- Text search input, tier multi-select, tag multi-select, preset buttons ("Tier A", "Voted Up", "Has Bundle"), score range inputs.
- Filter state serialized to URL query string (shareable/bookmarkable links).
- Changing any filter resets to page 1.
- "Clear all" button.
- Mobile: collapsible filter drawer.

**Tests:**
- Unit: filter model → SQL WHERE clause generation, backwards compat mapping.
- Integration: apply filter → correct results returned.

---

## 7) Feature Block D — Deep Learning Module Audit & Improvement

### D1) Audit Phase (MUST COMPLETE BEFORE D2)

The learning module is at `openclaw/learning/analyzer.py`. It is a **hybrid system**: static tag weights (edge_config.py) + dynamic DB rules (scoring_rules) + GPT-4o-generated proposals.

**Audit must examine:**

1. **`openclaw/learning/analyzer.py`:** Map the full flow — `fetch_feedback_signal()` → `build_analysis_prompt()` → GPT-4o call → proposal parsing → storage in `learning_proposals`.
2. **`openclaw/analysis/rule_engine.py`:** How dynamic `scoring_rules` interact with static EDGE/RISK weights. Is there double-counting? Conflicting rules?
3. **`openclaw/analysis/tagger.py` + `edge_config.py`:** Are all EDGE weights calibrated? Any tags defined but never generated? Any generated but not weighted?
4. **`candidate_feedback` table:** How much feedback data exists? Distribution of up/down? Is it enough for meaningful learning?
5. **`learning_proposals` table:** How many proposals generated? Approved? Rejected? What patterns?
6. **GPT-4o prompt quality:** Is `build_analysis_prompt()` well-structured? Does it give the model enough context? Could it hallucinate invalid rules?
7. **Score distribution:** Run `SELECT score_tier, COUNT(*) FROM candidates GROUP BY score_tier` and `SELECT MIN(score), MAX(score), AVG(score), STDDEV(score) FROM candidates`. Is the distribution healthy or clustered?

**Identify issues:**
- Dead code or unused tag definitions.
- Non-normalized inputs (some features 0-1, others 0-100, others 0-1000+).
- The thumbs-up score override (being fixed in C1) — how much has it corrupted existing data?
- Missing feedback loops (user signals that should influence ranking but don't).
- Approved proposals that conflict with each other.
- Performance: how long does the nightly cron take?

**Output:**
- Structured audit report (markdown).
- Prioritized improvement plan with estimated effort.
- Baseline score distribution stats.
- List of corrupted scores from the thumbs-up override (candidates where score was manually inflated).

**⚠️ Stop and present the audit report. Do not proceed to D2 without approval.**

---

### D2) Improvement Phase

Based on audit findings, implement:

- **Normalize all scoring inputs** to 0.0–1.0 range before applying weights in `rule_engine.py`.
- **Make base score weights configurable** via env vars (currently `SPLIT_WEIGHT=40`, `VALUE_WEIGHT=25`, `OWNER_WEIGHT=15` are hardcoded in `rule_engine.py`).
- **Bound learned weight adjustments** — when an approved proposal creates a scoring_rule, cap the `adjust_score` value (configurable max delta, default ±15).
- **Add feature contribution logging:** when scoring runs, log per-candidate feature contributions at DEBUG level.
- **Add "Why this rank?" API endpoint:** `GET /api/candidate/{id}/score-explanation` returning:
```json
{
  "total_score": 82,
  "tier": "A",
  "components": {
    "base": { "splits": 32, "value": 18, "owner": 12 },
    "edge_tags": [
      { "tag": "EDGE_SNOCO_LSA_R5_RD_FR", "boost": 35 },
      { "tag": "EDGE_BUNDLE_SAME_OWNER", "boost": 10 }
    ],
    "risk_tags": [
      { "tag": "RISK_STEEP_SLOPE", "penalty": -8 }
    ],
    "dynamic_rules": [
      { "rule_id": 5, "description": "lot_sf > 20000 → +5", "adjustment": 5 }
    ],
    "user_vote_boost": 8
  },
  "reason_codes": ["..."]
}
```
- **Fix corrupted scores:** Identify candidates with score overrides from old thumbs-up behavior, re-score them through the pipeline.
- **Add ranking determinism tests:** same inputs → same scores (fixture-based).
- **Add weight decay** on learned rules (configurable half-life, default 30 days) — old approved proposals lose influence over time.

---

## 8) Feature Block E — Lead System Extension + Owner Enrichment

### E1) Extend Existing Lead Model

The `Lead` model already exists in `models.py` with: `candidate_id, status (new/reviewed/outreach/active/dead), owner_phone, owner_email, notes, contacted_at, contact_method, outcome`.

**Extend it (Alembic migration):**

Add columns:
- `owner_snapshot` JSONB — name + mailing address from county records at promotion time.
- `reason` TEXT — why promoted.
- `score_at_promotion` INTEGER — score snapshot.
- `bundle_snapshot` JSONB (nullable) — bundle_data at promotion time.
- `promoted_by` INTEGER FK → users (once auth exists).
- `promoted_at` TIMESTAMP.
- `osint_investigation_id` INTEGER (nullable) — FK to OSINT platform investigation (external reference, not a DB FK).
- `osint_status` TEXT (nullable) — `pending` | `complete` | `partial` | `failed`.
- `osint_queried_at` TIMESTAMP (nullable).
- `osint_summary` TEXT (nullable) — one-line key findings from OSINT.

**Status enum migration:** Handled by FIX-E (TEXT + CHECK). The new values are: `new / researching / contacted / negotiating / closed_won / closed_lost / dead`. Old value mapping:
- `reviewed` → `researching`
- `outreach` → `contacted`
- `active` → `negotiating`
- `dead` → `dead` (unchanged)
- `new` → `new` (unchanged)

### E2) Lead Promotion Flow

**UI:**
- "Promote to Lead" button on `property.html` detail page.
- Button also available as action in candidates list rows.
- Confirmation modal (vanilla JS) showing: address, current score, bundle info, text input for reason.
- No duplicate leads for same candidate unless previous lead is `dead` or `closed_lost`.

**API:** `POST /api/leads` with body:
```json
{
  "candidate_id": "...",
  "reason": "Large bundled lot, motivated seller signals",
  "notes": ""
}
```

Endpoint snapshots current score, owner info, and bundle data automatically.
**After promotion:** Triggers OSINT investigation (Block H) as a background task.

### E3) Enrichment Provider Abstraction

**New table (Alembic migration):**
```
enrichment_results:
  id              SERIAL PK
  lead_id         FK → leads
  provider        VARCHAR (e.g., "skip_trace", "business_filings", "osint_platform")
  status          ENUM (pending/running/success/partial/failed)
  data            JSONB
  confidence      FLOAT (0.0–1.0)
  source_class    ENUM (public_record/commercial_api/business_filing/osint)
  fetched_at      TIMESTAMP
  expires_at      TIMESTAMP (nullable)
  error_message   TEXT (nullable)
```

**New ORM model:** `EnrichmentResult` in `models.py`.

**Provider interface** — create `openclaw/enrich/base.py`:
```python
class EnrichmentProvider(ABC):
    name: str
    enabled: bool  # from config/env
    rate_limit_per_min: int

    @abstractmethod
    async def enrich(self, lead: Lead) -> EnrichmentResult: ...

    def is_configured(self) -> bool: ...
```

**Wire existing stubs:**
- `openclaw/enrich/skip_trace.py` → implement `SkipTraceProvider(EnrichmentProvider)`.
- `openclaw/enrich/owner.py` → implement `PublicRecordProvider(EnrichmentProvider)` (county data already available).

**Additional providers** (implement interface, enable via config):
- Business filings (WA Secretary of State API — public).
- Social profile search (public profiles only, no login, no scraping).
- OSINT platform (Block H — `OsintProvider(EnrichmentProvider)`).

**Allowed enrichment fields:** additional mailing addresses, phone numbers, email addresses, business entity links, related parcels, corporate filings, public social profile URLs.

**Must NOT store:** scraped private content, protected category data, inferred sensitive attributes.

### E4) Enrichment Pipeline

- Triggered on lead promotion (automatic) and via "Re-enrich" button (manual).
- Runs as `BackgroundTasks` (matching existing feasibility pattern).
- Rate-limited per provider (configurable).
- Each external call logged: provider, lead_id, status, duration, retries.
- Provider enable/disable via env vars (e.g., `SKIP_TRACE_ENABLED=true`, `SKIP_TRACE_API_KEY=...`).
- Retry: configurable max retries (default 3) with exponential backoff.
- If no providers configured → enrichment section shows "No providers configured."

### E5) Lead Detail UI

Extend `leads.html` (or create `lead_detail.html`) to show:

1. **Header:** Address, status badge, score at promotion, promoted_by, promoted_at.
2. **Owner identity:** Name, mailing address from owner_snapshot.
3. **Enrichment results:** Grouped by provider, each with:
   - Confidence bar (color-coded).
   - Source classification label.
   - Expandable raw data.
   - "Re-enrich" button per provider.
4. **OSINT section:** Status badge (✅ Complete | ⚠️ Partial | ❌ Failed | ⏳ Pending), summary line, link to OSINT platform UI: `http://aidev01:8000/investigations/{osint_investigation_id}` (opens in new tab), "Run OSINT" button for manual trigger.
5. **Contact log:** Timestamped entries (method, outcome, notes). Add contact log entries via inline form.
6. **Notes:** Free-text with timestamps (use existing `candidate_notes` pattern or add `lead_notes`).
7. **Status progression:** Visual horizontal stepper showing current status + history.

**Mobile:** Single-column, collapsible sections, sticky status header.

### E6) Contact Log Table

**New table (Alembic migration):**
```
lead_contact_log:
  id              SERIAL PK
  lead_id         FK → leads
  user_id         FK → users
  method          ENUM (phone/email/mail/in_person/other)
  outcome         ENUM (no_answer/voicemail/spoke/email_sent/letter_sent/meeting/other)
  notes           TEXT
  contacted_at    TIMESTAMP
```

### E7) Compliance & Safeguards

- All enrichment goes through the provider interface — no direct external calls.
- OSINT platform calls go through `OsintProvider` (Block H) — same interface.
- UI labels distinguish public record vs. commercial data vs. OSINT.
- Audit log: every enrichment call logged with who triggered it, when, which provider, result.
- `DELETE /api/leads/{id}/enrichment` — removes all enrichment data for a lead.
- Data retention config: `ENRICHMENT_RETENTION_DAYS` env var (default 365).
- If no provider configured → feature works without enrichment.

---

## 9) Feature Block F — Bulk Operations + Export

### F1) Bulk Selection

- Checkbox column in candidates list.
- Select: individual, all on page, all matching current filter.
- Bulk action toolbar (appears when ≥1 selected):
  - **Bulk vote** (up / down / clear).
  - **Bulk tag** (add / remove tags).
  - **Bulk promote to lead** (shared reason prompt).
- Implement as batch API calls (POST with array of IDs) or sequential single-item calls with progress indicator.
- Optimistic UI with rollback on partial failure — show which items failed.
- Mobile: long-press to enter selection mode.

### F2) CSV/Excel Export

- Export button on candidates list and leads list.
- Exports current filtered/sorted view (not full dataset).
- Format: CSV (default). XLSX only if `openpyxl` is already a dependency; otherwise CSV only.
- Columns match user's current column configuration.
- For leads: include enrichment summary fields (phone, email if available) + OSINT summary.
- Large exports (>1000 rows): stream response with `StreamingResponse`.
- **PII warning:** Confirmation dialog when exporting leads with enrichment data.

**API:**
- `GET /api/candidates/export?format=csv&{current_filters}` → returns file download.
- `GET /api/leads/export?format=csv` → returns file download.

### Tests:
- Unit: export formatting, filter-to-query translation.
- Integration: filter → export → file contains correct rows + columns.

---

## 10) Feature Block G — Lead Reminders + Map Status Overlay

### G1) Follow-Up Reminders

**New table (Alembic migration):**
```
reminders:
  id              SERIAL PK
  lead_id         FK → leads
  user_id         FK → users
  remind_at       TIMESTAMP
  message         TEXT
  status          ENUM (pending/sent/dismissed)
  created_at      TIMESTAMP
```

**UI:**
- "Set reminder" button on lead detail page.
- Date/time picker (native HTML `<input type="datetime-local">`) + optional note.
- Dashboard widget or notification badge showing pending/overdue reminders.
- Overdue reminders highlighted in red.

**Delivery:**
- In-app: poll `/api/reminders/pending` on page load (no websockets — keep it simple).
- Email: use existing SMTP config in `openclaw/notify/digest.py` if `SMTP_HOST` is set.
- No SMS.

**APScheduler job:** Check for due reminders every 5 minutes (configurable), send email notifications, update status to `sent`.

### G2) Map Pins by Lead Status

On `map.html`:
- Color-code pins by lead status:
  - No lead: gray (default).
  - New: blue.
  - Researching: yellow.
  - Contacted: orange.
  - Negotiating: purple.
  - Closed won: green.
  - Closed lost / Dead: red.
- Filter checkboxes in map legend to show/hide by status.
- Bundle outlines remain visible when status coloring is active.
- Mobile: legend collapsible, pin tap shows status + address.

**API:** Extend `GET /api/map/points` to include `lead_status` and `osint_status` in GeoJSON properties (LEFT JOIN leads on candidate).

### Tests:
- Unit: reminder scheduling, overdue detection.
- Snapshot: map point GeoJSON includes correct lead_status.

---

## 10.5) Feature Block H — OSINT Owner Investigation (Consumer Only)

### Boundary Contract

**OpenClaw is a consumer of the OSINT platform. We do NOT:**
- ❌ Modify any file in the `osint-platform/` codebase.
- ❌ Read or write to `osint-platform/data/investigations.db` directly.
- ❌ Manage, restart, or deploy the OSINT platform process.
- ❌ Depend on OSINT platform internals (table schemas, provider implementations, cache structure).
- ❌ Import any Python module from `osint-platform/`.

**OpenClaw ONLY:**
- ✅ Calls the OSINT platform's HTTP API at `http://localhost:8000/api`.
- ✅ Stores the returned `investigation_id` as an opaque external reference.
- ✅ Links to the OSINT platform's UI for detailed results.
- ✅ Treats the OSINT platform as an opaque enrichment provider that may be down, slow, or unavailable.

### OSINT API Contract (read-only reference — do NOT implement these, they already exist)

```
POST /api/investigations                 Create investigation + auto-run provider queries
     Request:  { name, subject_name, address?, email?, phone?, company?, notes? }
     Response: { id, name, status, subject_name, results, ... }
     Timing:   Synchronous — 10-60 seconds (providers run in request thread)

GET  /api/investigations/{id}            Get full investigation with results + timeline
GET  /api/investigations                 List investigations
POST /api/investigations/{id}/rerun      Re-run all provider queries
GET  /api/health                         Health check + provider key status
```

### Implementation: `openclaw/enrich/osint_bridge.py` (NEW FILE)

This module implements `OsintProvider(EnrichmentProvider)` from Block E3.

```python
"""
Bridge to local OSINT platform for owner background investigation.
OSINT platform is an EXTERNAL service at http://localhost:8000.
We are a consumer only — see Block H boundary contract.
"""
import httpx
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

OSINT_BASE_URL = "http://localhost:8000/api"  # Configurable via OSINT_BASE_URL env var
OSINT_TIMEOUT = 90  # seconds — providers are synchronous and slow

ENTITY_KEYWORDS = {"LLC", "INC", "CORP", "TRUST", "LTD", "LP",
                   "PARTNERSHIP", "ESTATE", "ET AL", "ETAL"}


def is_entity(owner_name: str) -> bool:
    """Detect if owner name is a business entity vs a person."""
    upper = owner_name.upper()
    return any(kw in upper for kw in ENTITY_KEYWORDS)


async def create_investigation(
    owner_name: str,
    parcel_id: str,
    score_tier: str,
    address: str | None = None,
    email: str | None = None,
    phone: str | None = None,
) -> dict:
    """
    Create an OSINT investigation for a parcel owner.
    Returns: { investigation_id: int|None, status: str, summary: str, results: dict }
    """
    payload = {
        "name": f"Owner: {owner_name} — Parcel {parcel_id}",
        "subject_name": owner_name,
        "notes": f"Auto-created by OpenClaw for parcel {parcel_id}, tier {score_tier}",
    }
    if address:
        payload["address"] = address
    if email:
        payload["email"] = email
    if phone:
        payload["phone"] = phone
    if is_entity(owner_name):
        payload["company"] = owner_name

    try:
        async with httpx.AsyncClient(timeout=OSINT_TIMEOUT) as client:
            resp = await client.post(f"{OSINT_BASE_URL}/investigations", json=payload)
            resp.raise_for_status()
            data = resp.json()

        return {
            "investigation_id": data.get("id"),
            "status": "complete" if data.get("results") else "partial",
            "summary": _build_summary(data.get("results", {})),
            "results": data.get("results", {}),
        }
    except httpx.TimeoutException:
        logger.warning("OSINT timeout for owner=%s parcel=%s", owner_name, parcel_id)
        return _fail_result("Timeout — OSINT providers too slow")
    except httpx.HTTPStatusError as e:
        logger.error("OSINT HTTP %s for owner=%s", e.response.status_code, owner_name)
        return _fail_result(f"HTTP {e.response.status_code}")
    except Exception as e:
        logger.error("OSINT unexpected error for owner=%s: %s", owner_name, e)
        return _fail_result(str(e))


async def check_health() -> bool:
    """Check if OSINT platform is reachable. Returns True if healthy."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{OSINT_BASE_URL}/health")
            return resp.status_code == 200
    except Exception:
        return False


def _fail_result(reason: str) -> dict:
    return {"investigation_id": None, "status": "failed", "summary": reason, "results": {}}


def _build_summary(results: dict) -> str:
    """Extract key findings into a one-line summary for lead notes."""
    parts = []
    # Keys depend on AggregatedReport structure from osint-platform
    if results.get("emails_found"):
        parts.append(f"Emails: {len(results['emails_found'])}")
    if results.get("social_profiles"):
        parts.append(f"Social: {len(results['social_profiles'])} profiles")
    if results.get("company_data"):
        parts.append("Company records found")
    if results.get("phone_data"):
        parts.append("Phone intel found")
    return " | ".join(parts) if parts else "No significant findings"
```

### Trigger Points

1. **On lead promotion (Block E2):** After `POST /api/leads` creates the lead, fire a `BackgroundTasks` call to `create_investigation()`. Update lead's `osint_*` columns with results. Non-blocking — lead creation succeeds even if OSINT fails.

2. **Nightly batch backfill:** APScheduler job to process leads where `osint_status IS NULL`:
   - First: `check_health()` — skip entire batch if OSINT platform is down.
   - Rate limit: max 20 investigations per batch (configurable via `OSINT_BATCH_LIMIT` env var).
   - Order by candidate score DESC (highest-priority leads first).
   - Sequential calls (OSINT platform uses SQLite — not concurrent-safe at high load).

3. **Manual trigger:** "Run OSINT" button on lead detail page → `POST /api/leads/{id}/osint` → calls `create_investigation()` and updates lead.

### Owner Deduplication

Before creating a new OSINT investigation:
1. Check if another lead with the same `owner_name_canonical` already has `osint_investigation_id IS NOT NULL`.
2. If yes, reuse that `osint_investigation_id` — set it on the current lead, copy `osint_summary`, set `osint_status = 'complete'`.
3. If no, create a new investigation.

This avoids duplicate OSINT queries for the same owner across multiple parcels.

### API Endpoints (OpenClaw side)

```
POST /api/leads/{id}/osint              Trigger OSINT investigation for a lead (manual)
GET  /api/leads/{id}/osint              Get OSINT status + summary for a lead
```

### Config Knobs

```bash
OSINT_ENABLED=true                      # Master toggle — if false, all OSINT calls skipped
OSINT_BASE_URL=http://localhost:8000/api
OSINT_TIMEOUT_SECONDS=90
OSINT_BATCH_LIMIT=20                    # Max investigations per nightly batch
OSINT_BATCH_ENABLED=true                # Enable/disable nightly batch
```

### Degradation

| Failure | Behavior |
|---------|----------|
| OSINT platform down | `check_health()` returns false → skip batch, log warning. Manual trigger returns error message to UI. Lead pipeline unaffected. |
| OSINT timeout (>90s) | Mark `osint_status = 'failed'`, `osint_summary = 'Timeout'`. Show retry button on lead detail. |
| OSINT returns partial results | Mark `osint_status = 'partial'`. Display what's available. |
| `OSINT_ENABLED=false` | OSINT section hidden in UI. No background jobs. No API calls. |

### Tests

- Unit: `is_entity()` detection, `_build_summary()` extraction, owner dedup logic, health check.
- Integration (mocked): mock `httpx` responses → verify lead columns updated correctly, verify dedup across leads.
- Degradation: mock timeout → verify `osint_status = 'failed'`, mock 500 → verify retry logic, mock health down → verify batch skipped.

---

## 11) Degradation Contracts

| Dependency | Failure Mode | Behavior |
|------------|-------------|----------|
| ArcGIS (bundle detection) | Timeout / 5xx | Use cached result if available; else show "Bundle data unavailable" banner. Never block page load. |
| ArcGIS (delta sync) | Timeout / 5xx | Log warning, skip sync cycle. Data stays at last-known state. |
| Enrichment provider | Timeout / 5xx / rate limit | Mark enrichment_result as `failed` with error_message. Show retry button on UI. Lead detail page loads normally. |
| Enrichment provider | Not configured | Show "No enrichment providers configured" in enrichment section. Lead works fully without enrichment. |
| OSINT platform | Down / timeout / error | See Block H degradation table. Lead pipeline fully functional without OSINT. |
| OSINT platform | `OSINT_ENABLED=false` | OSINT section hidden entirely. Zero API calls. |
| OpenAI GPT-4o | Timeout / error | Learning proposal generation skipped for this cycle. Log error. `/learning` page shows "Analysis unavailable — will retry next cycle." |
| Scoring pipeline | Error | Serve last-known score. Log error. Show "Score may be stale" indicator on candidate. |
| SMTP | Not configured / error | Reminders still created and shown in-app. Email delivery silently skipped. Log warning. |
| PostgreSQL | Slow query (>5s) | FastAPI request timeout. Return 504 with message. |

---

## 12) Observability

### Structured Logging Upgrade

**Current state:** Python stdlib `logging`, unstructured plain text.

**Improvement:** Switch to `structlog` (or add a JSON formatter to stdlib logging) for structured log output. This is a low-effort change that enables future Loki/Promtail integration (already deployed on aidev01 per architecture doc).

Format: `{"timestamp": "...", "level": "...", "module": "...", "event": "...", "data": {...}}`

### Log Events:
- **Bundle detection:** candidates processed, neighbors found, matches by tier, cache hit rate.
- **Enrichment:** provider, lead_id, status, duration, retries, error.
- **OSINT:** investigation created/failed/skipped, owner dedup hit, batch size, health check result.
- **Lead events:** promotion, status change, enrichment trigger, OSINT trigger, contact log entry.
- **Learning:** proposal generated, approved, rejected, nightly run duration.
- **Voting:** candidate_id, user_id, vote value.
- **Filters:** filter params used (no PII — log filter keys, not values).
- **Bulk ops:** operation type, count, success/failure count.
- **Export:** format, row count, user_id.
- **Auth:** login, logout, failed login attempt.

### Metrics (log-based, no Prometheus yet):
- Avg neighbors found per candidate (bundle detection).
- Vote counts per day.
- Enrichment success rate by provider (including OSINT).
- OSINT: investigations created per day, dedup hit rate, avg response time, failure rate.
- Score distribution stats after each rescore.
- Lead pipeline conversion rates.
- Reminder completion rate.

---

## 13) Testing

### Existing test coverage: `tests/` covers analysis + feasibility only.

### New tests required:

| Category | Scope |
|----------|-------|
| **Smoke** | Hit every existing + new endpoint, assert non-500. FastAPI TestClient. |
| **Unit** | Owner normalization, canonical fallback chain (FIX-C), fuzzy gates (FIX-D), match tiers, vote toggle/exclusivity, vote threshold (FIX-H), filter model → SQL, score explanation, column registry, export formatting, reminder scheduling, URL construction (external links), OSINT entity detection, OSINT summary builder, OSINT owner dedup |
| **Integration** | ArcGIS → bundle (mocked), enrichment pipeline (mocked providers), OSINT bridge (mocked httpx), vote → tag → rescore, lead promotion → snapshot + enrichment + OSINT trigger, bulk operations, filter → export |
| **Ranking determinism** | Same inputs → same scores (fixtures). Learning weight bounded. |
| **Audit stability** | Pre/post learning refactor: score distribution within acceptable variance |
| **API contract** | All new endpoints return correct shapes, error cases return proper error responses |
| **Auth** | Login/logout, role enforcement, unauthenticated redirect |
| **Degradation** | OSINT down → lead still works, enrichment timeout → retry button shown, ArcGIS down → cached bundle served |

Use `pytest` + `httpx` AsyncClient (or FastAPI TestClient) for web layer tests. Match existing test conventions in `tests/`.

---

## 14) Config Knobs

All via env vars (matching existing pattern in `config.py` + `edge_config.py`):

```bash
# PREP — Auth
ADMIN_USERNAME=admin
ADMIN_PASSWORD=changeme

# Block A — Bundles
BUNDLE_ADJACENCY_TOLERANCE_FT=10
BUNDLE_SEARCH_RADIUS_FT=500
EDGE_WEIGHT_BUNDLE_SAME_OWNER=10
EDGE_WEIGHT_BUNDLE_ADJACENT=5
BUNDLE_SCORE_CAP=15
BUNDLE_CACHE_TTL_HOURS=24
BUNDLE_MAX_NEIGHBORS=50

# Block C — Voting
EDGE_WEIGHT_USER_UPVOTE=8
VOTE_NET_THRESHOLD=1

# Block D — Learning
LEARNING_WEIGHT_MAX_DELTA=15
LEARNING_WEIGHT_DECAY_HALFLIFE_DAYS=30
SCORE_STALENESS_THRESHOLD_HOURS=6
# Base score weights (currently hardcoded in rule_engine.py)
SPLIT_WEIGHT=40
VALUE_WEIGHT=25
OWNER_WEIGHT=15

# Block E — Enrichment
SKIP_TRACE_ENABLED=false
SKIP_TRACE_API_KEY=
SKIP_TRACE_RATE_LIMIT_PER_MIN=10
SKIP_TRACE_MAX_RETRIES=3
BUSINESS_FILINGS_ENABLED=false
ENRICHMENT_RETENTION_DAYS=365

# Block G — Reminders
REMINDER_CHECK_INTERVAL_MIN=5
REMINDER_EMAIL_ENABLED=false

# Block H — OSINT (consumer only)
OSINT_ENABLED=true
OSINT_BASE_URL=http://localhost:8000/api
OSINT_TIMEOUT_SECONDS=90
OSINT_BATCH_LIMIT=20
OSINT_BATCH_ENABLED=true

# General
EXPORT_MAX_ROWS=10000
```

---

## 15) Execution Order

**Strictly follow this order. Each "STOP" point requires presenting output and waiting for approval.**

```
0.  FIX block: Architecture review fixes (A–I)    → STOP: confirm all fixes applied, grep verifications pass
1.  PREP-1: Fix Alembic                           → STOP: present MIGRATION_FIX.md
2.  PREP-2: Decompose app.py into routers          → STOP: confirm all endpoints still work
3.  PREP-3: Add ORM models for raw SQL tables       → (no stop, continue)
4.  PREP-4: Basic auth                             → STOP: confirm login works
5.  Block A: Bundle detection                       → (no stop)
6.  Block B: External links                         → (no stop)
7.  Block C: Voting fix + columns + filters         → STOP: confirm list UX works
8.  Block D1: Learning audit                        → STOP: present audit report
9.  Block D2: Learning improvements                 → STOP: confirm scoring still works
10. Block E: Lead extension + enrichment             → STOP: confirm lead flow works
11. Block F: Bulk ops + export                       → (no stop)
12. Block G: Reminders + map overlay                 → (no stop)
13. Block H: OSINT integration                       → STOP: confirm OSINT calls work (mocked or live)
14. Observability pass (§12)                         → (no stop)
15. Test pass (§13) — fill gaps, run full suite     → STOP: present test results
16. Update .env.example with all new env vars
17. Write API_CHANGES.md documenting all new/changed endpoints
```

Codex writes checkpoint markers after each step per the Checkpoint Protocol above. Gabriel monitors progress and escalates stuck workers.

---

## 16) Deliverables Checklist

- [ ] FIX-A through FIX-I applied and verified
- [ ] MIGRATION_FIX.md (Alembic repair documentation)
- [ ] Router decomposition (app.py → routers/)
- [ ] ORM models for scoring_rules, candidate_feedback, learning_proposals, candidate_notes
- [ ] Auth system (User model, login, session, role enforcement)
- [ ] Bundle detection engine + tests
- [ ] External link integration (with FIX-F SnoCo URL)
- [ ] Voting fix (remove score override) + EDGE_USER_UPVOTE tag (with FIX-H threshold)
- [ ] Column chooser + localStorage persistence
- [ ] Unified filter bar + backwards compat (with FIX-I text search)
- [ ] Learning module audit report
- [ ] Learning module refactor + score explanation endpoint
- [ ] Corrupted score cleanup (from old thumbs-up override)
- [ ] Lead model extension (new columns, status via FIX-E TEXT+CHECK, OSINT columns)
- [ ] Lead promotion flow + snapshots + OSINT trigger
- [ ] Enrichment provider abstraction + pipeline (including OsintProvider)
- [ ] Skip trace provider wired
- [ ] Lead detail UI (enrichment, OSINT section, contact log, status stepper)
- [ ] Contact log table + UI
- [ ] Bulk operations (vote, tag, promote)
- [ ] CSV export (candidates + leads, including OSINT summary)
- [ ] Reminder system + APScheduler job
- [ ] Map pin status overlay
- [ ] OSINT bridge module (`osint_bridge.py`) + owner dedup + batch backfill
- [ ] OSINT health check + degradation handling
- [ ] Structured logging upgrade (with OSINT events)
- [ ] Full test suite passing (with OSINT mocked tests)
- [ ] Updated .env.example (with OSINT config knobs)
- [ ] API_CHANGES.md

---

## 17) Implementation Defaults (If Ambiguous)

- Prefer structured JSONB annotations over flat TEXT[] tags for complex data (bundles, snapshots).
- Keep enrichment modular and optional — the app must work with zero providers configured.
- Keep learning explainable — no updates that can't be traced to a feedback signal.
- Fail safely — never block page loads or ranking.
- Mobile-first for new UI components.
- Use the existing pattern when one exists (e.g., BackgroundTasks for async work, in-memory caching, TEXT[] for tags).
- When adding vanilla JS: keep it in the relevant template or a single loaded .js file per page. No build step.
- All new Jinja2 templates should extend the existing base template pattern.
- **OSINT is external:** Treat `osint-platform` exactly like you'd treat any third-party API. If it changes, only `osint_bridge.py` needs to adapt. No other OpenClaw module should know or care about OSINT internals.