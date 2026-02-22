"""Rule-based scoring engine for Mike's Building System.

Loads active rules from DB, evaluates them against candidate+parcel data,
returns final tier (A-F) and score (0-100).

Rule evaluation order:
1. 'exclude' rules - if any match, candidate is excluded entirely
2. 'set_tier' rules - highest priority (lowest priority number) explicit tier wins
3. 'adjust_score' rules - all matching adjustments applied to base score
4. Base score from splits + economics maps to tier if no set_tier matched
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text

from openclaw.analysis.arbitrage import compute_arbitrage_depth, compute_zone_medians
from openclaw.analysis.subdivision import SUBDIVISION_SCORE_EFFECTS, assess_subdivision
from openclaw.analysis.subdivision_econ import compute_economic_margin
from openclaw.db.session import SessionLocal

logger = logging.getLogger(__name__)

# Base score weights (env-configurable)
SPLIT_WEIGHT = float(os.getenv("SPLIT_WEIGHT", "40"))
VALUE_WEIGHT = float(os.getenv("VALUE_WEIGHT", "25"))
OWNER_WEIGHT = float(os.getenv("OWNER_WEIGHT", "15"))

# Learned-rule controls
LEARNING_WEIGHT_MAX_DELTA = int(os.getenv("LEARNING_WEIGHT_MAX_DELTA", "15"))
LEARNING_WEIGHT_DECAY_HALFLIFE_DAYS = float(os.getenv("LEARNING_WEIGHT_DECAY_HALFLIFE_DAYS", "30"))
LEARNED_RULE_PREFIX = os.getenv("LEARNED_RULE_PREFIX", "LEARNED:")

# Tier cutoffs (score -> tier)
TIER_CUTOFFS = [
    (72, "A"),
    (58, "B"),
    (44, "C"),
    (30, "D"),
    (16, "E"),
    (0, "F"),
]

FIELD_MAP = {
    "present_use": lambda c: (c.get("present_use") or "").lower(),
    "owner_name": lambda c: (c.get("owner_name") or "").lower(),
    "zone_code": lambda c: (c.get("zone_code") or "").lower(),
    "lot_sf": lambda c: float(c.get("lot_sf") or 0),
    "has_wetland": lambda c: str(c.get("has_critical_area_overlap", False)).lower(),
    "has_ag": lambda c: str(c.get("flagged_for_review", False)).lower(),
    "improvement_value": lambda c: float(c.get("improvement_value") or 0),
    "total_value": lambda c: float(c.get("total_value") or 0),
    "tags": lambda c: c.get("tags") or [],
}


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(value, upper))


def _normalize_ratio(value: float, max_value: float) -> float:
    if max_value <= 0:
        return 0.0
    return _clamp(value / max_value, 0.0, 1.0)


def _owner_score_norm(owner_name: str | None) -> float:
    owner = (owner_name or "").upper()
    if any(x in owner for x in ["LLC", "INC", "CORP", "LTD", "LP "]):
        return 10.0 / 15.0
    if any(x in owner for x in ["TRUST", "ESTATE", "FAMILY"]):
        return 12.0 / 15.0
    if owner and not any(x in owner for x in ["ASSOCIATION", "HOA", "DISTRICT"]):
        return 1.0
    return 5.0 / 15.0


def _rule_is_learned(rule: dict[str, Any]) -> bool:
    name = str(rule.get("name") or "")
    return name.startswith(LEARNED_RULE_PREFIX)


def _rule_created_at_utc(rule: dict[str, Any]) -> datetime | None:
    created_at = rule.get("created_at")
    if not isinstance(created_at, datetime):
        return None
    if created_at.tzinfo is None:
        return created_at.replace(tzinfo=timezone.utc)
    return created_at.astimezone(timezone.utc)


def _learning_decay_factor(rule: dict[str, Any], now_utc: datetime) -> float:
    if not _rule_is_learned(rule):
        return 1.0
    if LEARNING_WEIGHT_DECAY_HALFLIFE_DAYS <= 0:
        return 1.0
    created_at = _rule_created_at_utc(rule)
    if created_at is None:
        return 1.0
    age_days = max((now_utc - created_at).total_seconds(), 0.0) / 86400.0
    return 0.5 ** (age_days / LEARNING_WEIGHT_DECAY_HALFLIFE_DAYS)


def _effective_rule_adjustment(rule: dict[str, Any], now_utc: datetime) -> tuple[int, float]:
    raw = int(rule.get("score_adj") or 0)
    if not _rule_is_learned(rule):
        return raw, 1.0

    bounded = int(_clamp(float(raw), -LEARNING_WEIGHT_MAX_DELTA, LEARNING_WEIGHT_MAX_DELTA))
    decay_factor = _learning_decay_factor(rule, now_utc)
    decayed = int(round(bounded * decay_factor))
    return decayed, decay_factor


def load_rules(session) -> list[dict]:
    """Load active rules ordered by priority."""
    rows = session.execute(
        text(
            """
        SELECT id, name, field, operator, value, action, tier, score_adj, priority, created_at
        FROM scoring_rules
        WHERE active = true
        ORDER BY priority ASC, created_at ASC
    """
        )
    ).mappings().all()
    return [dict(r) for r in rows]


def evaluate_rule(rule: dict, candidate: dict) -> bool:
    """Return True if rule matches this candidate."""
    field_fn = FIELD_MAP.get(rule["field"])
    if not field_fn:
        return False

    field_val = field_fn(candidate)
    rule_val = str(rule["value"]).lower()
    op = rule["operator"]

    try:
        if op == "eq":
            return field_val == rule_val
        if op == "neq":
            return field_val != rule_val
        if op == "contains":
            return rule_val in field_val
        if op == "not_contains":
            return rule_val not in field_val
        if op == "gt":
            return float(field_val or 0) > float(rule_val)
        if op == "lt":
            return float(field_val or 0) < float(rule_val)
        if op == "gte":
            return float(field_val or 0) >= float(rule_val)
        if op == "lte":
            return float(field_val or 0) <= float(rule_val)
        if op == "tag_contains":
            return rule_val in [str(t).lower() for t in field_val]
    except (ValueError, TypeError):
        return False
    return False


def compute_base_components(candidate: dict) -> dict[str, Any]:
    """Normalize base inputs to 0..1 and return weighted component contributions."""
    splits = float(candidate.get("potential_splits") or 0)
    land_val = float(candidate.get("assessed_value") or 0)

    splits_norm = _normalize_ratio(splits, 10.0)
    val_per_lot = (land_val / splits) if splits > 0 else 0.0
    value_norm = _normalize_ratio(val_per_lot, 200000.0)
    owner_norm = _owner_score_norm(candidate.get("owner_name"))

    split_score = splits_norm * SPLIT_WEIGHT
    value_score = value_norm * VALUE_WEIGHT
    owner_score = owner_norm * OWNER_WEIGHT

    base_cap = max(SPLIT_WEIGHT + VALUE_WEIGHT + OWNER_WEIGHT, 0.0)
    total = int(_clamp(float(int(split_score + value_score + owner_score)), 0.0, base_cap))

    return {
        "splits_norm": splits_norm,
        "value_norm": value_norm,
        "owner_norm": owner_norm,
        "splits": int(split_score),
        "value": int(value_score),
        "owner": int(owner_score),
        "total": total,
    }


def base_score(candidate: dict) -> int:
    """Calculate normalized base score using env-configurable component weights."""
    return compute_base_components(candidate)["total"]


def score_to_tier(score: int) -> str:
    """Map numeric score to letter tier."""
    for cutoff, tier in TIER_CUTOFFS:
        if score >= cutoff:
            return tier
    return "F"


def score_candidate(candidate: dict, rules: list[dict]) -> dict[str, Any]:
    """Evaluate candidate and return full deterministic scoring breakdown."""
    for rule in rules:
        if rule["action"] == "exclude" and evaluate_rule(rule, candidate):
            return {
                "tier": "F",
                "score": 0,
                "exclude": True,
                "tags": [],
                "reason_codes": [],
                "explicit_tier": None,
                "breakdown": {
                    "base": {"splits": 0, "value": 0, "owner": 0},
                    "edge_tags": [],
                    "risk_tags": [],
                    "dynamic_rules": [],
                    "user_vote_boost": 0,
                },
            }

    now_utc = datetime.now(timezone.utc)
    base = compute_base_components(candidate)
    score = int(base["total"])

    from openclaw.analysis.edge_config import edge_config as _edge_cfg
    from openclaw.analysis.tagger import compute_tags

    tags, tag_reasons = compute_tags(candidate, config=_edge_cfg, uga_outside=candidate.get("uga_outside"))
    candidate["tags"] = tags

    edge_boosts = {
        "EDGE_SNOCO_LSA_R5_RD_FR": _edge_cfg.weight_lsa,
        "EDGE_SNOCO_RUTA_ARBITRAGE": _edge_cfg.weight_ruta,
        "EDGE_WA_HB1110_MIDDLE_HOUSING": _edge_cfg.weight_hb1110,
        "EDGE_WA_UNIT_LOT_SUBDIVISION": _edge_cfg.weight_unit_lot,
        "EDGE_SNOCO_RURAL_CLUSTER_BONUS": _edge_cfg.weight_rural_cluster,
        "EDGE_USER_UPVOTE": _edge_cfg.weight_user_upvote,
        "EDGE_BUNDLE_SAME_OWNER": _edge_cfg.weight_bundle_same_owner,
        "EDGE_BUNDLE_ADJACENT": _edge_cfg.weight_bundle_adjacent,
    }

    edge_details: list[dict[str, Any]] = []
    bundle_tag_weights: list[tuple[str, int]] = []
    user_vote_boost = 0
    for tag, weight in edge_boosts.items():
        if tag not in tags:
            continue
        weight_int = int(weight)
        if tag.startswith("EDGE_BUNDLE_"):
            bundle_tag_weights.append((tag, weight_int))
            continue
        score += weight_int
        edge_details.append({"tag": tag, "boost": weight_int})
        if tag == "EDGE_USER_UPVOTE":
            user_vote_boost = weight_int

    if bundle_tag_weights:
        raw_bundle = sum(w for _t, w in bundle_tag_weights)
        capped_bundle = min(raw_bundle, int(_edge_cfg.bundle_score_cap))
        score += capped_bundle
        for tag, weight in bundle_tag_weights:
            applied = 0
            if raw_bundle > 0:
                applied = int(round(capped_bundle * (weight / raw_bundle)))
            edge_details.append({"tag": tag, "boost": applied, "configured_boost": weight})

    risk_tags = [t for t in tags if t.startswith("RISK_")]
    risk_details: list[dict[str, Any]] = []
    risk_cap = -30
    risk_step = int(_edge_cfg.weight_risk_penalty)
    applied_risk_total = 0
    for tag in risk_tags:
        if applied_risk_total <= risk_cap:
            break
        remaining = risk_cap - applied_risk_total
        penalty = risk_step
        if penalty < remaining:
            penalty = remaining
        score += penalty
        applied_risk_total += penalty
        risk_details.append({"tag": tag, "penalty": penalty})

    explicit_tier: str | None = None
    dynamic_rule_details: list[dict[str, Any]] = []
    for rule in rules:
        if not evaluate_rule(rule, candidate):
            continue

        if rule["action"] == "adjust_score":
            adj, decay_factor = _effective_rule_adjustment(rule, now_utc)
            if adj:
                score += adj
                dynamic_rule_details.append(
                    {
                        "rule_id": str(rule.get("id")),
                        "description": rule.get("name") or "",
                        "adjustment": adj,
                        "decay_factor": round(decay_factor, 6),
                    }
                )
        elif rule["action"] == "set_tier" and explicit_tier is None:
            explicit_tier = rule["tier"]

    score = int(_clamp(float(score), 0.0, 100.0))
    tier = explicit_tier or score_to_tier(score)

    logger.debug(
        "score_candidate candidate=%s base=%s edge=%s risk=%s rules=%s total=%s tier=%s",
        candidate.get("candidate_id") or candidate.get("id"),
        {"splits": base["splits"], "value": base["value"], "owner": base["owner"]},
        edge_details,
        risk_details,
        dynamic_rule_details,
        score,
        tier,
    )

    return {
        "tier": tier,
        "score": score,
        "exclude": False,
        "tags": tags,
        "reason_codes": tag_reasons,
        "explicit_tier": explicit_tier,
        "breakdown": {
            "base": {
                "splits": base["splits"],
                "value": base["value"],
                "owner": base["owner"],
                "normalized": {
                    "splits": round(base["splits_norm"], 6),
                    "value": round(base["value_norm"], 6),
                    "owner": round(base["owner_norm"], 6),
                },
            },
            "edge_tags": edge_details,
            "risk_tags": risk_details,
            "dynamic_rules": dynamic_rule_details,
            "user_vote_boost": user_vote_boost,
        },
    }


def evaluate_candidate(candidate: dict, rules: list[dict]) -> tuple[str, int, bool, list, list]:
    """Compatibility wrapper for existing callers."""
    scored = score_candidate(candidate, rules)
    return (
        scored["tier"],
        int(scored["score"]),
        bool(scored["exclude"]),
        list(scored["tags"]),
        list(scored["reason_codes"]),
    )


def _merge_unique(*items) -> list[str]:
    seen = set()
    merged: list[str] = []
    for group in items:
        for value in (group or []):
            if not value or value in seen:
                continue
            seen.add(value)
            merged.append(value)
    return merged


def rescore_all() -> dict:
    """Re-score all candidates using current rule set. Returns summary."""
    session = SessionLocal()
    try:
        rules = load_rules(session)
        logger.info("Loaded %d active scoring rules", len(rules))

        rows = session.execute(
            text(
                """
            SELECT
                c.id as candidate_id,
                c.potential_splits,
                c.has_critical_area_overlap,
                c.flagged_for_review,
                c.uga_outside,
                c.tags as existing_tags,
                c.reason_codes as existing_reasons,
                p.present_use, p.owner_name, p.zone_code,
                p.lot_sf, p.assessed_value, p.improvement_value, p.total_value,
                p.address, p.county, p.frontage_ft, p.parcel_width_ft, p.last_sale_price,
                COALESCE((
                    SELECT
                        COUNT(*) FILTER (WHERE cf.rating = 'up')
                        - COUNT(*) FILTER (WHERE cf.rating = 'down')
                    FROM candidate_feedback cf
                    WHERE cf.candidate_id = c.id
                ), 0) AS vote_net
            FROM candidates c
            JOIN parcels p ON c.parcel_id = p.id
        """
            )
        ).mappings().all()

        logger.info("Re-scoring %d candidates", len(rows))

        tier_counts = {t: 0 for t in "ABCDEF"}
        excluded = 0
        updates = []
        try:
            compute_zone_medians(session)
        except Exception:
            logger.exception("Zone median cache build failed; underpricing component will be skipped")

        for row in rows:
            candidate = dict(row)
            owner_name_canonical = (row.get("owner_name") or "").strip() or None
            display_text = " ".join(p for p in [row.get("address"), owner_name_canonical] if p) or None
            parcel = {
                "zone_code": row.get("zone_code"),
                "lot_sf": row.get("lot_sf"),
                "address": row.get("address"),
                "frontage_ft": row.get("frontage_ft"),
                "parcel_width_ft": row.get("parcel_width_ft"),
            }
            sub = assess_subdivision(candidate, parcel)
            candidate["potential_splits"] = sub.splits_most_likely

            scored = score_candidate(candidate, rules)
            score = int(scored["score"])
            exclude = bool(scored["exclude"])
            tags = list(scored["tags"])
            reasons = list(scored["reason_codes"])
            explicit_tier = scored["explicit_tier"]

            econ_margin, econ_tags, econ_reasons = compute_economic_margin(
                candidate,
                splits=sub.splits_most_likely,
                zone_code=row.get("zone_code") or "",
            )
            pre_arb_tags = _merge_unique(tags, sub.flags, econ_tags)
            arb_score, arb_tags, arb_reasons = compute_arbitrage_depth(candidate, tags=pre_arb_tags)

            for flag in _merge_unique(sub.flags, econ_tags, arb_tags):
                score += int(SUBDIVISION_SCORE_EFFECTS.get(flag, 0))
            score = int(_clamp(float(score), 0.0, 100.0))

            merged_tags = _merge_unique(row.get("existing_tags"), tags, sub.flags, econ_tags, arb_tags)
            merged_reasons = _merge_unique(
                row.get("existing_reasons"),
                reasons,
                sub.reasons,
                econ_reasons,
                arb_reasons,
            )

            if exclude:
                excluded += 1
                updates.append(
                    {
                        "id": str(row["candidate_id"]),
                        "tier": "F",
                        "score": 0,
                        "potential_splits": sub.splits_most_likely,
                        "tags": merged_tags,
                        "reasons": merged_reasons,
                        "sub_score": sub.score,
                        "sub_feasibility": sub.feasibility,
                        "sub_flags": sub.flags,
                        "splits_min": sub.splits_min,
                        "splits_max": sub.splits_max,
                        "splits_confidence": sub.splits_confidence,
                        "sub_access_mode": sub.access_mode,
                        "arbitrage_depth_score": arb_score,
                        "economic_margin_pct": econ_margin,
                        "owner_name_canonical": owner_name_canonical,
                        "display_text": display_text,
                    }
                )
                continue

            final_tier = explicit_tier or score_to_tier(score)
            tier_counts[final_tier] = tier_counts.get(final_tier, 0) + 1
            updates.append(
                {
                    "id": str(row["candidate_id"]),
                    "tier": final_tier,
                    "score": score,
                    "potential_splits": sub.splits_most_likely,
                    "tags": merged_tags,
                    "reasons": merged_reasons,
                    "sub_score": sub.score,
                    "sub_feasibility": sub.feasibility,
                    "sub_flags": sub.flags,
                    "splits_min": sub.splits_min,
                    "splits_max": sub.splits_max,
                    "splits_confidence": sub.splits_confidence,
                    "sub_access_mode": sub.access_mode,
                    "arbitrage_depth_score": arb_score,
                    "economic_margin_pct": econ_margin,
                    "owner_name_canonical": owner_name_canonical,
                    "display_text": display_text,
                }
            )

        session.execute(text("ALTER TABLE candidates ADD COLUMN IF NOT EXISTS score INTEGER DEFAULT 0"))
        session.execute(text("ALTER TABLE candidates ADD COLUMN IF NOT EXISTS tags TEXT[] DEFAULT '{}'"))
        session.execute(text("ALTER TABLE candidates ADD COLUMN IF NOT EXISTS reason_codes TEXT[] DEFAULT '{}'"))
        session.execute(text("ALTER TABLE candidates ADD COLUMN IF NOT EXISTS subdivisibility_score INTEGER DEFAULT 0"))
        session.execute(
            text(
                "ALTER TABLE candidates ADD COLUMN IF NOT EXISTS subdivision_feasibility VARCHAR(20) DEFAULT 'UNKNOWN'"
            )
        )
        session.execute(text("ALTER TABLE candidates ADD COLUMN IF NOT EXISTS subdivision_flags TEXT[] DEFAULT '{}'"))
        session.execute(text("ALTER TABLE candidates ADD COLUMN IF NOT EXISTS splits_min INTEGER"))
        session.execute(text("ALTER TABLE candidates ADD COLUMN IF NOT EXISTS splits_max INTEGER"))
        session.execute(text("ALTER TABLE candidates ADD COLUMN IF NOT EXISTS splits_confidence VARCHAR(10)"))
        session.execute(text("ALTER TABLE candidates ADD COLUMN IF NOT EXISTS subdivision_access_mode VARCHAR(20)"))
        session.execute(text("ALTER TABLE candidates ADD COLUMN IF NOT EXISTS arbitrage_depth_score INTEGER"))
        session.execute(text("ALTER TABLE candidates ADD COLUMN IF NOT EXISTS economic_margin_pct DOUBLE PRECISION"))
        session.execute(text("ALTER TABLE candidates ADD COLUMN IF NOT EXISTS owner_name_canonical VARCHAR"))
        session.execute(text("ALTER TABLE candidates ADD COLUMN IF NOT EXISTS display_text TEXT"))
        session.commit()

        from psycopg2.extras import execute_values

        raw_conn = session.connection().connection
        cur = raw_conn.cursor()

        execute_values(
            cur,
            """
            UPDATE candidates SET
                score_tier = v.tier::scoretierenum,
                score = v.score,
                potential_splits = v.potential_splits,
                tags = v.tags::text[],
                reason_codes = v.reasons::text[],
                subdivisibility_score = v.sub_score,
                subdivision_feasibility = v.sub_feasibility,
                subdivision_flags = v.sub_flags::text[],
                splits_min = v.splits_min,
                splits_max = v.splits_max,
                splits_confidence = v.splits_confidence,
                subdivision_access_mode = v.sub_access_mode,
                arbitrage_depth_score = v.arbitrage_depth_score,
                economic_margin_pct = v.economic_margin_pct,
                owner_name_canonical = v.owner_name_canonical,
                display_text = v.display_text
            FROM (VALUES %s) AS v(
                id, tier, score, potential_splits, tags, reasons, sub_score, sub_feasibility, sub_flags,
                splits_min, splits_max, splits_confidence, sub_access_mode, arbitrage_depth_score, economic_margin_pct,
                owner_name_canonical, display_text
            )
            WHERE candidates.id = v.id::uuid
            """,
            [
                (
                    u["id"],
                    u["tier"],
                    u["score"],
                    u["potential_splits"],
                    u["tags"],
                    u["reasons"],
                    u["sub_score"],
                    u["sub_feasibility"],
                    u["sub_flags"],
                    u["splits_min"],
                    u["splits_max"],
                    u["splits_confidence"],
                    u["sub_access_mode"],
                    u["arbitrage_depth_score"],
                    u["economic_margin_pct"],
                    u["owner_name_canonical"],
                    u["display_text"],
                )
                for u in updates
            ],
        )
        raw_conn.commit()
        cur.close()

        session.execute(text("DELETE FROM candidates WHERE score = 0 AND score_tier = 'F'::scoretierenum"))
        session.commit()

        logger.info("Re-score complete: %s, excluded: %d", tier_counts, excluded)
        return {"tiers": tier_counts, "excluded": excluded, "total": len(updates)}

    finally:
        session.close()


if __name__ == "__main__":
    import logging as _logging

    _logging.basicConfig(level=_logging.INFO)
    result = rescore_all()
    print(f"Result: {result}")
