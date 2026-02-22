# OSINT Platform — Architecture Discovery Report
*Generated 2026-02-22*

> **⚠️ Two codebases exist in the workspace:**
> - `osint-platform/` — Active lightweight platform (SQLite, no Docker, deployed)
> - `osint-temp/` — Enterprise-grade system (PostgreSQL, Redis, Celery, Docker, NOT deployed)
>
> Both are documented below. Sections are split by codebase where they differ.

---

## 1. Tech Stack Summary

### `osint-platform` (Active / Lightweight)

| Layer | Choice |
|---|---|
| **Backend** | Python 3.12 + FastAPI (async) |
| **Database** | SQLite (`data/investigations.db`) — no migrations, schema created on startup |
| **Cache** | SQLite file cache (`.osint_cache/cache.db`), TTL-based, keyed by query hash |
| **Frontend** | React 18 + Vite + TailwindCSS + Redux Toolkit + React-Leaflet + Recharts |
| **ORM** | None — raw `sqlite3` module via `InvestigationStore` wrapper class |
| **Package Manager** | pip (`pyproject.toml`); npm/yarn for frontend |
| **Background Jobs** | None — all provider queries are synchronous in request thread |
| **Deployment** | No Docker — runs bare: `uvicorn` on port 8000, Vite dev server on 5173 |

### `osint-temp` (Enterprise / Not Deployed)

| Layer | Choice |
|---|---|
| **Backend** | Python 3.12 + FastAPI (async) |
| **Database** | PostgreSQL 16 + Redis 7 + MinIO (object storage) |
| **ORM** | SQLAlchemy 2.0 (async) + Alembic (4 migrations applied) |
| **Frontend** | React 18 + Vite + TailwindCSS + Redux + React Force Graph + D3 |
| **Background Jobs** | Celery + Redis broker (4 workers, 10min task limit); Celery Beat for scheduled tasks |
| **Package Manager** | pip (`requirements.txt`); npm for frontend |
| **Deployment** | Docker Compose — 14 services: postgres, redis, minio, api, celery-worker, celery-beat, frontend + 7 OSS tool microservices |

---

## 2. File Tree (depth 2)

### `osint-platform/`
```
osint-platform/
├── osint/
│   ├── api/
│   │   ├── models.py           (Pydantic request/response schemas)
│   │   ├── routes/             (health, investigate, investigations, lookup, photos, providers)
│   │   ├── server.py           (FastAPI app factory, CORS, route registration)
│   │   └── storage.py          (InvestigationStore — SQLite wrapper)
│   ├── core/
│   │   ├── cache.py            (SQLite-backed TTL cache)
│   │   ├── client.py           (Async HTTP client with retry logic)
│   │   ├── models.py           (Pydantic unified report models)
│   │   └── rate_limiter.py     (In-memory per-provider rate limits)
│   ├── providers/              (11 provider integrations — see §6)
│   │   ├── base.py
│   │   ├── shodan.py
│   │   ├── hunter.py
│   │   ├── virustotal.py
│   │   ├── abuseipdb.py
│   │   ├── urlscan.py
│   │   ├── otx.py
│   │   ├── ipinfo.py
│   │   ├── numverify.py
│   │   ├── opencorporates.py
│   │   ├── holehe_provider.py  (subprocess: holehe)
│   │   ├── sherlock_provider.py (subprocess: sherlock)
│   │   └── maigret_provider.py (subprocess: maigret)
│   ├── aggregator.py           (Dispatches queries to multiple providers, merges results)
│   ├── cli.py                  (Click CLI — osint investigate, lookup, list)
│   └── config.py               (pydantic-settings, reads .env)
├── data/
│   ├── investigations.db       (SQLite — investigations + timeline)
│   └── photos/                 (Uploaded photo storage)
├── .osint_cache/
│   └── cache.db                (SQLite — response cache)
├── tests/
└── pyproject.toml
```

### `osint-temp/`
```
osint-temp/
├── backend/
│   ├── app/
│   │   ├── api/routes/         (correlations, entities, export, graph, integrations,
│   │   │                        investigations, person, person_investigations, search)
│   │   ├── collectors/         (domain, image, network, osint_tools, person — see §6)
│   │   ├── models/             (entity, person, relationship, task — SQLAlchemy)
│   │   ├── workers/            (celery_app.py, tasks.py, tool_tasks.py)
│   │   ├── services/           (correlation, graph, export, person_profile)
│   │   ├── database.py
│   │   └── config.py
│   └── alembic/versions/       (4 migrations)
├── frontend/
│   └── src/
│       ├── pages/              (Dashboard, Entities, Graph, Investigations, PersonSearch,
│       │                        SubjectProfile, PersonProfile, InvestigationDetail, Settings, Search)
│       └── store/              (Redux slices per domain)
├── services/                   (7 dockerized OSS tools)
│   ├── maigret/
│   ├── holehe/
│   ├── sherlock/
│   ├── blackbird/
│   ├── ghunt/
│   ├── spiderfoot/
│   └── phoneinfoga/
└── docker-compose.yml
```

---

## 3. Data Model Inventory

### `osint-platform` — SQLite (no ORM)

#### `investigations` table (`osint/api/storage.py`)
Raw SQLite table, accessed via `InvestigationStore`.

| Field | Type | Notes |
|---|---|---|
| `name` | TEXT | Investigation display name |
| `status` | TEXT | active / archived |
| `subject_name` | TEXT | Primary subject |
| `aliases` | TEXT (JSON) | List of known aliases |
| `date_of_birth`, `age_range` | TEXT | |
| `location`, `address`, `nationality`, `gender` | TEXT | |
| `email`, `phone`, `ip`, `domain` | TEXT | Primary selectors |
| `company`, `employer`, `occupation`, `education` | TEXT | |
| `social_media` | TEXT (JSON) | Dict of platform → handle |
| `vehicle`, `physical_description` | TEXT | |
| `notes` | TEXT | Free text |
| `photo_ids` | TEXT (JSON) | List of uploaded photo UUIDs |
| `results` | TEXT (JSON) | Full aggregated provider results |

#### `investigation_timeline` table
| Field | Type |
|---|---|
| `investigation_id` | FK → investigations.id |
| `event_type` | TEXT (query_run / note_added / rerun / etc.) |
| `description` | TEXT |
| `data` | TEXT (JSON) |

#### Pydantic Models (`osint/core/models.py`) — response-only, not persisted separately

| Model | Purpose |
|---|---|
| `IPReport` | IP intelligence (ports, vulns, geo, reputation) |
| `DomainReport` | Domain intelligence (emails, subdomains, DNS, tech) |
| `EmailReport` | Email intelligence (deliverable, person data) |
| `URLReport` | URL scan (malicious flag, categories, screenshot) |
| `UsernameReport` | Social profile enumeration (Sherlock/Maigret) |
| `EmailAccountsReport` | Email service registration (Holehe) |
| `AggregatedReport` | Merged multi-provider result with confidence score |

No User model. No authentication.

---

### `osint-temp` — PostgreSQL (SQLAlchemy)

#### `Entity` (`backend/app/models/entity.py`)
Core graph node. Represents any OSINT data point.

| Field | Type | Notes |
|---|---|---|
| `type` | Enum | PERSON, DOMAIN, IP, EMAIL, USERNAME, PHONE, ORGANIZATION, HASH, URL, CERTIFICATE |
| `value` | String(2048) | Raw value |
| `normalized_value` | String(2048) | Type-normalized for dedup (indexed) |
| `data` | JSONB | All collected data |
| `sources` | JSONB | List of collector names |
| `confidence` | String | low / medium / high |
| `tags` | JSONB | User-defined tags (GIN indexed) |
| `investigation_id` | UUID FK → investigations | |

Relationships: `→ outgoing_relationships`, `→ incoming_relationships` (graph edges)

---

#### `PersonProfile` (`backend/app/models/person.py`)
Aggregated person record from multiple collectors.

| Field | Type | Notes |
|---|---|---|
| `full_name`, `first_name`, `last_name`, `normalized_name` | String | |
| `aliases` | JSONB | List of names (GIN indexed) |
| `age`, `date_of_birth`, `gender` | Mixed | |
| `current_address`, `previous_addresses` | JSONB | |
| `emails`, `phones` | JSONB | List of dicts (GIN indexed) |
| `social_profiles`, `usernames`, `websites` | JSONB | |
| `current_employer`, `current_title`, `employment_history` | JSONB | |
| `education`, `relatives`, `associates` | JSONB | |
| `court_records`, `property_records`, `breach_records` | JSONB | |
| `raw_data` | JSONB | Per-collector raw responses |
| `sources` | JSONB | Collector names used |
| `confidence_score` | Float | 0.0–1.0, computed from data completeness |

Method: `calculate_confidence()` — weighted scoring based on emails, phones, social profiles, employment, address, source corroboration count.

---

#### `Investigation` / `Task` (`backend/app/models/task.py`)
Investigation container and async task tracker.

Relationships: `→ entities` (1:many), `→ person_profiles` (1:many)

#### `Relationship` (`backend/app/models/relationship.py`)
Graph edge between two entities.

| Field | Type |
|---|---|
| `source_id` | UUID FK → entities |
| `target_id` | UUID FK → entities |
| `relation_type` | String |
| `confidence` | String |
| `data` | JSONB |

---

## 4. API Surface

### `osint-platform` API (FastAPI, port 8000)

#### Health
```
GET  /api/health          System health + provider key status
```

#### Investigation Management
```
POST   /api/investigations                Create investigation (runs query automatically)
GET    /api/investigations                List all investigations (filter by status, limit)
GET    /api/investigations/{id}           Get full investigation with results + timeline
PUT    /api/investigations/{id}           Update subject fields
POST   /api/investigations/{id}/rerun     Re-run queries against all providers
POST   /api/investigations/{id}/notes     Add timeline note
DELETE /api/investigations/{id}           Archive (soft delete)
GET    /api/investigations/{id}/timeline  Get timeline events
```

#### Query
```
POST /api/investigate     One-shot multi-provider query (no persistence)
POST /api/lookup          Quick single-value lookup
```

#### Photos
```
POST   /api/photos/upload       Upload photo to investigation
GET    /api/photos/{photo_id}   Serve photo
DELETE /api/photos/{photo_id}   Delete photo
```

#### Providers
```
GET /api/providers    List configured providers + key status
```

---

### `osint-temp` API (FastAPI, port 8002)

#### Entities (graph nodes)
```
GET    /api/entities                    List entities (filter: type, search, investigation_id)
POST   /api/entities                    Create entity
GET    /api/entities/{id}               Get entity + data
GET    /api/entities/{id}/relationships Graph relationships
PATCH  /api/entities/{id}               Update tags/notes/confidence
DELETE /api/entities/{id}               Delete entity
```

#### Investigations
```
GET    /api/investigations              List investigations
POST   /api/investigations              Create investigation
GET    /api/investigations/{id}         Get with entities
PATCH  /api/investigations/{id}         Update
DELETE /api/investigations/{id}         Delete
```

#### Person Search & Profiling
```
POST /api/person/search                  Search for person (triggers collector pipeline)
GET  /api/person/profiles                List person profiles
GET  /api/person/profile/{id}            Full profile
POST /api/person/profile/{id}/enrich     Re-enrich with additional collectors
GET  /api/person/profile/{id}/timeline   Activity timeline
DELETE /api/person/profile/{id}          Delete
GET  /api/person/collectors              List available collectors + status
```

#### Person Investigations (CRM-style)
```
GET    /api/person/investigations                          List
POST   /api/person/investigations                          Create
GET    /api/person/investigations/{id}                     Get with subjects
PATCH  /api/person/investigations/{id}                     Update
DELETE /api/person/investigations/{id}                     Delete
POST   /api/person/investigations/{id}/subjects            Add subject
GET    /api/person/subjects/{id}                           Get subject
GET    /api/person/subjects/{id}/profile                   Full enriched profile
POST   /api/person/subjects/{id}/rerun                     Re-run collectors
POST   /api/person/subjects/{id}/enrich                    Targeted enrichment
GET    /api/person/subjects/{id}/accounts                  Discovered accounts
GET    /api/person/subjects/{id}/identifiers               All IDs found
GET    /api/person/subjects/{id}/collector-runs            Collector run history
GET    /api/person/subjects/{id}/timeline                  Timeline events
GET    /api/person/subjects/{id}/locations                 Locations
GET    /api/person/subjects/{id}/records                   Public records
GET    /api/person/subjects/{id}/breaches                  Breach records
GET    /api/person/subjects/{id}/employment                Employment history
GET    /api/person/subjects/{id}/education                 Education
GET    /api/person/subjects/{id}/associates                Associates
GET    /api/person/subjects/{id}/images                    Images
GET    /api/person/subjects/{id}/dork-results              Google dork results
GET    /api/person/subjects/{id}/notes                     Notes
POST   /api/person/subjects/{id}/notes                     Add note
PATCH  /api/person/notes/{id}                             Update note
DELETE /api/person/notes/{id}                             Delete note
GET    /api/person/subjects/search                         Search subjects
GET    /api/person/subjects/{id}/export/json               Export profile JSON
GET    /api/person/subjects/{id}/export/csv                Export profile CSV
```

#### Search (async via Celery)
```
POST /api/search                  Trigger multi-collector search (returns task_id)
GET  /api/search/task/{task_id}   Poll task status + results
GET  /api/search/collectors       List all collectors
GET  /api/search/collectors/{name} Collector detail
```

#### Graph
```
POST /api/graph    Build entity relationship graph for investigation
```

#### Correlations
```
GET  /api/correlations/rules          List correlation rules
POST /api/correlations/run            Run all correlation rules
POST /api/correlations/run/{rule}     Run specific rule
```

#### Integrations (API key management)
```
GET   /api/integrations               List all integrations + status
GET   /api/integrations/stats         Enabled count + credits
GET   /api/integrations/{name}        Get integration
PATCH /api/integrations/{name}        Enable/disable
PUT   /api/integrations/{name}/credentials  Update API key
POST  /api/integrations/{name}/test   Test connection
```

#### Export
```
GET  /api/export/formats              Available formats
POST /api/export/entities/{format}    Export entities (json/csv/pdf/graphml)
POST /api/export/report               Generate investigation report
GET  /api/export/entities/json        Quick JSON export
GET  /api/export/entities/csv         Quick CSV export
```

---

## 5. Frontend Page Inventory

### `osint-platform` (React + Vite, port 5173)
*Note: No routing config found; likely SPA with tab-based navigation.*

| View | Data Source |
|---|---|
| Investigations list | `GET /api/investigations` |
| Investigation detail + results | `GET /api/investigations/{id}` |
| New investigation form | `POST /api/investigations` |
| Quick lookup | `POST /api/lookup` |
| Provider status | `GET /api/providers` |
| Map overlay (React-Leaflet) | IP geo from IPReport.geo |
| Charts (Recharts) | AggregatedReport confidence/provider breakdown |

### `osint-temp` (React + Vite)

| Page | File | Data Fetched |
|---|---|---|
| Dashboard | `Dashboard.tsx` | Investigation stats, recent activity |
| Investigations | `Investigations.tsx` | `GET /api/investigations` |
| Investigation Detail | `InvestigationDetail.tsx` | `GET /api/investigations/{id}` |
| Entity Browser | `Entities.tsx` | `GET /api/entities` (filtered) |
| Entity Graph | `Graph.tsx` | `POST /api/graph` → force-graph D3 visualization |
| Person Search | `PersonSearch.tsx` | `POST /api/person/search` |
| Person Profile | `PersonProfile.tsx` | `GET /api/person/profile/{id}` |
| Subject Profile | `SubjectProfile.tsx` | All `/api/person/subjects/{id}/*` endpoints |
| Search | `Search.tsx` | `POST /api/search` (async), polls `GET /api/search/task/{id}` |
| Settings | `Settings.tsx` | `GET/PATCH /api/integrations` — key management UI |

---

## 6. External Integrations

### `osint-platform` Providers (`osint/providers/`)

| Provider | File | Input Type | Credentials |
|---|---|---|---|
| **Shodan** | `shodan.py` | IP | `SHODAN_API_KEY` env |
| **Hunter.io** | `hunter.py` | Domain, Email | `HUNTER_API_KEY` env |
| **VirusTotal** | `virustotal.py` | IP, Domain, URL | `VIRUSTOTAL_API_KEY` env |
| **AbuseIPDB** | `abuseipdb.py` | IP | `ABUSEIPDB_API_KEY` env |
| **URLScan.io** | `urlscan.py` | URL | `URLSCAN_API_KEY` env |
| **OTX (AlienVault)** | `otx.py` | IP, Domain | `OTX_API_KEY` env |
| **IPInfo** | `ipinfo.py` | IP | `IPINFO_TOKEN` env |
| **Numverify** | `numverify.py` | Phone | `NUMVERIFY_API_KEY` env |
| **OpenCorporates** | `opencorporates.py` | Company | `OPENCORPORATES_API_KEY` env |
| **Holehe** | `holehe_provider.py` | Email | None (subprocess) |
| **Sherlock** | `sherlock_provider.py` | Username | None (subprocess) |
| **Maigret** | `maigret_provider.py` | Username | None (subprocess) |

All providers extend `base.py` `BaseProvider`. Credentials loaded via `config.py` pydantic-settings (`.env` file). `config.has_key(provider)` used to skip unconfigured providers.

Cache: All HTTP responses cached in `.osint_cache/cache.db` (SQLite) with configurable TTL (`CACHE_DEFAULT_TTL=3600`).

### `osint-temp` Collectors

#### API Collectors (`backend/app/collectors/`)

| Collector | File | Type |
|---|---|---|
| **Shodan** | `network/shodan.py` | IP/network |
| **Censys** | `network/censys.py` | IP/certificate |
| **AbuseIPDB** | `network/abuseipdb.py` | IP |
| **IPInfo** | `network/ipinfo.py` | IP |
| **SecurityTrails** | `domain/securitytrails.py` | Domain/DNS |
| **WHOIS** | `domain/whois.py` | Domain |
| **DNS** | `domain/dns.py` | Domain |
| **crt.sh** | `domain/crtsh.py` | Domain certificates |
| **Wayback Machine** | `domain/wayback.py` | Domain/URL history |
| **HIBP** | `person/hibp.py` | Email breach |
| **Dehashed** | `person/dehashed.py` | Email/phone breach |
| **Hunter.io** | (via person) | Email |
| **FullContact** | `person/fullcontact.py` | Email/phone person |
| **PeopleDataLabs** | `person/peopledatalabs.py` | Person enrichment |
| **LeakCheck** | `person/leakcheck.py` | Email/phone breach |
| **IntelligenceX** | `person/intelligence_x.py` | Multi-type |
| **Gravatar** | `person/gravatar.py` | Email |
| **LinkedIn** | `person/linkedin.py` | Person (scrape) |
| **Court records** | `person/court_records.py` | Name |
| **Business filings** | `person/business_filings.py` | Name/company |

#### Dockerized OSS Tool Services (`services/`)

| Tool | Port | Purpose |
|---|---|---|
| **Maigret** | 8000 | Username → 2500+ sites social enumeration |
| **Holehe** | 8000 | Email → registered service discovery |
| **Sherlock** | 8000 | Username → social profile finder |
| **Blackbird** | 8000 | Username/email → social enumeration |
| **GHunt** | 8000 | Google account OSINT |
| **SpiderFoot** | 5001 | Multi-source automated OSINT |
| **PhoneInfoga** | 8000 | Phone number OSINT |

All wrapped as FastAPI microservices; `celery_app.workers.tool_tasks` dispatches to them asynchronously.

---

## 7. Scoring / Learning Pipeline

### `osint-platform` — Confidence Scoring
No ML. Simple heuristic aggregation in `AggregatedReport.merge_confidence()`:
- Collects `reputation_score` (0.0–1.0) from providers that return one (Shodan, AbuseIPDB, VirusTotal, URLScan)
- Collects `confidence` (0–100) from providers that return it (Hunter)
- Returns the mean of all available scores
- No feedback loop, no weight updates, no persistence of scoring logic

### `osint-temp` — Confidence Scoring
More sophisticated, still no ML:

**`PersonProfile.calculate_confidence()`** — weighted completeness score:
```
+0.10  has full_name
+0.05–0.15  verified emails (more = higher)
+0.05–0.10  phones
+0.03–0.15  social profiles (per profile, capped)
+0.05–0.10  employment history
+0.05–0.20  multiple sources corroborate (capped at 0.20)
+0.10       current_address present
= confidence_score (0.0–1.0)
```

**Entity confidence** — set per-collector: `low / medium / high` string, not computed.

**Correlation engine** (`backend/app/services/correlation.py`):
- Runs pattern-matching rules against the entity graph
- Links entities that share identifiers (same email → same person, etc.)
- Rules are static code, not user-configurable

**No feedback loop. No dynamic weight updates. No ML model.**

---

## 8. Caching + Logging

### `osint-platform`

| Layer | Mechanism | Detail |
|---|---|---|
| **API response cache** | SQLite (`.osint_cache/cache.db`) | TTL-based, keyed by `md5(url+params)`. Default TTL 3600s, configurable via `CACHE_DEFAULT_TTL` env |
| **Rate limiting** | In-memory dict | Per-provider configurable limits in `core/rate_limiter.py`. Resets on process restart |
| **HTTP client** | `httpx.AsyncClient` | Retry with exponential backoff (`core/client.py`) |
| **Logging** | Python stdlib `logging` | Unstructured, INFO level, stdout |

### `osint-temp`

| Layer | Mechanism | Detail |
|---|---|---|
| **Task results** | Redis (db 2) | Celery result backend, TTL driven by Celery config |
| **Celery broker** | Redis (db 1) | Task queue |
| **Session/rate** | Redis (db 0) | Rate limiting, session state |
| **Object storage** | MinIO | Photos, exported reports, large result blobs |
| **DB query cache** | None explicit | PostgreSQL built-in buffer cache only |
| **Logging** | Python stdlib `logging` | Unstructured, per-module `getLogger(__name__)` |
| **Celery monitoring** | Celery task state in Redis | `PENDING → STARTED → SUCCESS/FAILURE`; frontend polls `/api/search/task/{id}` |

---

## 9. Deployment Status

| Codebase | Status | Notes |
|---|---|---|
| `osint-platform` | **Active** — processes running locally | No reverse proxy, port 8000 direct; no systemd service defined |
| `osint-temp` | **Not deployed** — Docker Compose exists but not started | Requires: `docker compose up -d`; needs all env vars in `.env` |

---

## 10. API Keys — Current Status

From `MEMORY.md` / `.osint-keys.env`:

| Provider | Status |
|---|---|
| Shodan | ✅ Have key |
| Hunter.io | ✅ Have key |
| OTX (AlienVault) | Free signup needed |
| AbuseIPDB | Free signup needed |
| VirusTotal | Free signup needed |
| URLScan | Free signup needed |
| IPInfo | Free signup needed |
| NumVerify | Free signup needed |
| OpenCorporates | Free signup needed |
| HIBP | Paid only |
| Dehashed | Paid only |
| IntelligenceX | Paid only |
| SecurityTrails | Paid only |
| PeopleDataLabs | Paid only |
| FullContact | Paid only |
| Censys | Paid only |

---

## 11. Notable Gaps / Tech Debt

1. **`osint-platform` has no API authentication** — any network-accessible process can call it
2. **`osint-platform` SQLite is not concurrent-safe** at high load (WAL mode helps but has limits)
3. **`osint-temp` is not deployed** — 14 Docker services, 4 Alembic migrations ready but never started; MinIO object storage unused
4. **No deduplication across investigations** in `osint-platform` — same email queried twice = two separate DB rows
5. **Subprocess providers (Sherlock, Holehe, Maigret)** in `osint-platform` spawn child processes synchronously, blocking the request thread
6. **`osint-temp` correlation rules are hard-coded** — no UI to add/modify rules; requires code deploy
7. **No export in `osint-platform`** — results exist in SQLite `results` JSON column only; no PDF/CSV/report generation
8. **No unified deployment** — the two codebases solve similar problems with different architectures and have no shared code; consolidation decision pending
