# API Changes

This document summarizes the new and updated API endpoints added during the parcel bundle, leads, enrichment/OSINT, learning, bulk ops, export, auth, and map/feasibility phases.

## Auth Model
- Session auth uses cookies: `user_id`, `username`, `role`.
- Most API routes require an authenticated cookie. If missing, middleware redirects to `/login`.
- Auth allowlist endpoints: `/api/auth/login`, `/api/auth/logout`, `/api/auth/me`.

## Auth Endpoints
| Method | Path | Auth | Description | Request Shape | Response Shape |
|---|---|---|---|---|---|
| POST | `/api/auth/login` | No | Login and set auth cookies. Supports JSON and form body. | `{ "username": string, "password": string }` | Success: `{ "ok": true, "user": { "id": int, "username": string, "role": string } }` (JSON mode) or redirect (form mode). Failure: `401 { "error": "invalid credentials" }`. |
| POST | `/api/auth/logout` | No (best with cookie) | Clears auth cookies. | none | `{ "ok": true }` |
| GET | `/api/auth/me` | Cookie expected | Returns current user identity. | none | `{ "id": int, "username": string, "role": string }` or `401 { "error": "unauthenticated" }` |

## Candidate & Property APIs
| Method | Path | Auth | Description | Request Shape | Response Shape |
|---|---|---|---|---|---|
| GET | `/api/candidates` | Yes | Candidate list API with unified filters, paging, vote metadata, lead metadata, feasibility summary. | Query params: `q`, `tiers`, `tags_any`, `tags_none`, `tags_mode`, `use_types`, `score_min`, `score_max`, `vote`, `lead_status`, `has_bundle`, `osint_status`, `sort`, `page`, `limit`, `wetland`, `ag` | `{ total, count, page, limit, filters, candidates: [...] }` where each candidate includes id/address/owner/tier/score/vote/use/splits/tags/lead/osint/coords. |
| GET | `/api/candidates/export` | Yes | Export filtered candidates to CSV. | Query params: `format=csv`, `columns`, plus same filters as `/api/candidates` | CSV stream + headers: `X-Export-Total`, `X-Export-Limit`, `X-Export-Returned`, `X-Export-Truncated` |
| POST | `/api/candidates/bulk/vote` | Yes | Bulk vote set/clear for many candidates. | `{ "candidate_ids": [uuid], "action": "up|down|clear" }` | `{ "ok": true, "success_ids": [...], "failed": [{candidate_id,error}] }` |
| POST | `/api/candidates/bulk/tag` | Yes | Bulk add/remove tags for many candidates. | `{ "candidate_ids": [uuid], "action": "add|remove", "tags": [string] }` | `{ "ok": true, "success_ids": [...], "failed": [...] }` |
| POST | `/api/candidates/bulk/promote` | Yes | Bulk promote candidates to leads and queue enrichment. | `{ "candidate_ids": [uuid], "reason"?: string, "notes"?: string }` | `{ "ok": true, "created": [{candidate_id,lead_id}], "failed": [...] }` |
| GET | `/api/tags` | Yes | Distinct tag inventory + counts. | none | `[ { "tag": string, "count": number } ]` |
| GET | `/api/use-types` | Yes | Distinct present-use values for filters. | none | `{ "use_types": [string] }` |
| GET | `/api/candidate/{candidate_id}` | Yes | Candidate detail payload (includes bundle/subdivision/feasibility context). | Path param: `candidate_id` | Detailed candidate object; 404 on missing candidate. |
| POST | `/api/candidate/{candidate_id}/notes` | Yes | Add note to candidate. | `{ "note": string, "author"?: string }` | `{ "ok": true }` |
| GET | `/api/candidate/{candidate_id}/notes` | Yes | List recent notes for candidate. | Query: `limit` | `[ { id, note, author, created_at } ]` |
| GET | `/api/candidate/{candidate_id}/bundle` | Yes | Return stored bundle payload for candidate. | Path param | `bundle_data` object or `{}` |
| POST | `/api/candidate/{candidate_id}/detect-bundle` | Yes | Force bundle detection/recompute for candidate. | Path param | Bundle payload or `404 { "error": "candidate not found" }` |

## Voting & Scoring APIs
| Method | Path | Auth | Description | Request Shape | Response Shape |
|---|---|---|---|---|---|
| POST | `/api/candidate/{candidate_id}/feedback` | Yes | Vote endpoint (toggle/exclusive actor vote). No direct score override. | JSON: `{ "feedback_type": "thumbs_up|thumbs_down", "category"?: string, "notes"?: string }` (or query `rating=up|down`) | `{ ok, active, score, tier, thumbs_up, thumbs_down, net_votes, user_vote }` |
| GET | `/api/candidate/{candidate_id}/feedback` | Yes | Vote summary for candidate + current actor vote. | Path param | `{ thumbs_up, thumbs_down, net_votes, user_vote }` |
| GET | `/api/candidate/{candidate_id}/score-explanation` | Yes | Explain score composition and dynamic rule effects. | Path param | `{ candidate_id, total_score, tier, exclude, components, reason_codes, active_rules }` |
| GET | `/api/feedback/stats` | Yes | Aggregated feedback counts by rating/category. | none | `[ { rating, category, cnt } ]` |
| GET | `/api/rules` | Yes | List active/inactive scoring rules. | none | `[ { id, name, field, operator, value, action, tier, score_adj, priority, active } ]` |
| POST | `/api/rules` | Yes | Create scoring rule. | `{ name, field, operator, value, action, tier?, score_adj?, priority? }` | `{ "ok": true }` |
| PUT | `/api/rules/{rule_id}` | Yes | Update scoring rule. | Partial rule fields | `{ "ok": true }` or `404` |
| DELETE | `/api/rules/{rule_id}` | Yes | Delete scoring rule. | Path param | `{ "ok": true }` |
| PATCH | `/api/rules/{rule_id}/toggle` | Yes | Toggle active state of rule. | Path param | `{ "ok": true }` or `404` |
| POST | `/api/rescore` | Yes | Re-run full scoring pipeline. | none | Rescore summary payload from `rescore_all()` |
| GET | `/api/rescore/preview` | Yes | Preview tier distribution using current rules. | none | `{ preview: {A..F}, excluded, rules_active }` |

## Lead, Enrichment, OSINT, Reminder, Export APIs
| Method | Path | Auth | Description | Request Shape | Response Shape |
|---|---|---|---|---|---|
| POST | `/api/leads` | Yes | Promote candidate to lead and queue enrichment. | `{ "candidate_id": uuid, "reason"?: string, "notes"?: string }` | `{ "ok": true, "lead_id": uuid, "lead_detail_url": string }` (or `409` if active lead exists) |
| POST | `/api/leads/{lead_id}/enrich` | Yes | Queue enrichment for one lead/all providers or one provider. | Optional JSON `{ "provider"?: string }` | `{ "ok": true, "queued": true, "provider": string\|null }` |
| GET | `/api/leads/{lead_id}/osint` | Yes | Read OSINT status/summary for lead. | Path param | `{ ok, enabled, investigation_id, status, summary, queried_at, ui_url }` |
| POST | `/api/leads/{lead_id}/osint` | Yes | Trigger OSINT investigation now. | Path param | `{ ok, lead_id, investigation_id, status, summary, queried_at }` or error (`503` when disabled/unavailable). |
| DELETE | `/api/leads/{lead_id}/enrichment` | Yes | Delete enrichment rows and clear OSINT fields for lead. | Path param | `{ "ok": true, "deleted": number }` |
| POST | `/api/leads/{lead_id}/contact-log` | Yes | Append contact interaction entry. | `{ method, outcome, notes?, contacted_at? }` | `{ ok, entry: { id, method, outcome, notes, contacted_at, username } }` |
| GET | `/api/leads/{lead_id}/contact-log` | Yes | List contact history entries. | Path param | `[ { id, method, outcome, notes, contacted_at, username } ]` |
| POST | `/api/lead/{lead_id}/status` | Yes | Update lead status workflow state. | Query `status` (allowed lead statuses) | `{ "ok": true }` |
| POST | `/api/leads/{lead_id}/reminders` | Yes | Create reminder for lead follow-up. | `{ "remind_at": ISO8601, "message"?: string }` | `{ ok, id, lead_id, status, remind_at, message }` |
| POST | `/api/reminders/{reminder_id}/dismiss` | Yes | Dismiss reminder for current user. | Path param | `{ "ok": true }` |
| GET | `/api/reminders/pending` | Yes | List pending reminders for current user. | none | `[ { id, lead_id, remind_at, message, status, is_overdue, lead_address } ]` |
| GET | `/api/leads/export` | Yes | Export leads to CSV with optional status/sort/columns filters. | Query: `format=csv`, `columns`, `status`, `sort` | CSV stream + `X-Export-*` headers |

## Learning APIs
| Method | Path | Auth | Description | Request Shape | Response Shape |
|---|---|---|---|---|---|
| POST | `/api/learning/run-now` | Yes | Run learning analyzer immediately. | none | `{ "ok": true, "proposals_generated": number }` |
| POST | `/api/learning/{proposal_id}/approve` | Yes | Approve proposal and optionally apply a bounded learned rule. | Path param | `{ "ok": true, "rule_applied": bool, "applied_rule_id": uuid\|null }` |
| POST | `/api/learning/{proposal_id}/reject` | Yes | Reject proposal. | Path param | `{ "ok": true }` |

## Map & Feasibility APIs
| Method | Path | Auth | Description | Request Shape | Response Shape |
|---|---|---|---|---|---|
| GET | `/api/map/points` | Yes | GeoJSON point feed with candidate + lead/OSINT status overlay fields. | Query: `tier`, `ag_only` | `{ "type": "FeatureCollection", "features": [...] }` |
| POST | `/api/feasibility/{parcel_id}` | Yes | Queue asynchronous feasibility run for parcel. | Path param | `{ "ok": true, "job_id": parcel_id, "status": "pending" }` |
| GET | `/api/feasibility/{parcel_id}/status` | Yes | Read in-memory job state plus latest DB state. | Path param | `{ parcel_id, job, db }` |
| GET | `/api/feasibility/{parcel_id}/result` | Yes | Fetch latest feasibility result payload. | Path param | `{ status, result_json, tags, best_layout_id, best_score, created_at, completed_at }` or 404 |
