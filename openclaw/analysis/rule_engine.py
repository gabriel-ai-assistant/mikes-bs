"""Rule-based scoring engine for Mike's Building System.

Loads active rules from DB, evaluates them against candidate+parcel data,
returns final tier (A-F) and score (0-100).

Rule evaluation order:
1. 'exclude' rules — if any match, candidate is excluded entirely
2. 'set_tier' rules — highest priority (lowest priority number) explicit tier wins
3. 'adjust_score' rules — all matching adjustments applied to base score
4. Base score from splits + economics maps to tier if no set_tier matched
"""
import logging
from typing import Optional
from sqlalchemy import text
from openclaw.db.session import SessionLocal
from openclaw.analysis.subdivision import assess_subdivision, SUBDIVISION_SCORE_EFFECTS
from openclaw.analysis.subdivision_econ import compute_economic_margin
from openclaw.analysis.arbitrage import compute_arbitrage_depth, compute_zone_medians

logger = logging.getLogger(__name__)

# Base score weights
SPLIT_WEIGHT = 40       # 40 points max from splits
VALUE_WEIGHT = 25       # 25 points max from land value per lot
OWNER_WEIGHT = 15       # 15 points based on owner type (individual best)
FLAGS_WEIGHT = 20       # up to -20 from flags

# Tier cutoffs (score → tier)
TIER_CUTOFFS = [
    (80, 'A'),
    (65, 'B'),
    (50, 'C'),
    (35, 'D'),
    (20, 'E'),
    (0,  'F'),
]

FIELD_MAP = {
    'present_use': lambda c: (c.get('present_use') or '').lower(),
    'owner_name':  lambda c: (c.get('owner_name') or '').lower(),
    'zone_code':   lambda c: (c.get('zone_code') or '').lower(),
    'lot_sf':      lambda c: float(c.get('lot_sf') or 0),
    'has_wetland': lambda c: str(c.get('has_critical_area_overlap', False)).lower(),
    'has_ag':      lambda c: str(c.get('flagged_for_review', False)).lower(),
    'improvement_value': lambda c: float(c.get('improvement_value') or 0),
    'total_value': lambda c: float(c.get('total_value') or 0),
    # NEW: tag list for tag_contains operator
    'tags':        lambda c: c.get('tags') or [],
}


def load_rules(session) -> list[dict]:
    """Load active rules ordered by priority."""
    rows = session.execute(text("""
        SELECT id, name, field, operator, value, action, tier, score_adj, priority
        FROM scoring_rules
        WHERE active = true
        ORDER BY priority ASC, created_at ASC
    """)).mappings().all()
    return [dict(r) for r in rows]


def evaluate_rule(rule: dict, candidate: dict) -> bool:
    """Return True if rule matches this candidate."""
    field_fn = FIELD_MAP.get(rule['field'])
    if not field_fn:
        return False

    field_val = field_fn(candidate)
    rule_val = rule['value'].lower()
    op = rule['operator']

    try:
        if op == 'eq':
            return field_val == rule_val
        elif op == 'neq':
            return field_val != rule_val
        elif op == 'contains':
            return rule_val in field_val
        elif op == 'not_contains':
            return rule_val not in field_val
        elif op == 'gt':
            return float(field_val or 0) > float(rule_val)
        elif op == 'lt':
            return float(field_val or 0) < float(rule_val)
        elif op == 'gte':
            return float(field_val or 0) >= float(rule_val)
        elif op == 'lte':
            return float(field_val or 0) <= float(rule_val)
        elif op == 'tag_contains':
            return rule_val in [t.lower() for t in field_val]
    except (ValueError, TypeError):
        return False
    return False


def base_score(candidate: dict) -> int:
    """Calculate base score 0-100 from splits, value, owner type."""
    splits = candidate.get('potential_splits') or 0
    lot_sf = float(candidate.get('lot_sf') or 0)
    land_val = float(candidate.get('assessed_value') or 0)

    # Splits score (0-40): 10 splits = max
    split_score = min(splits / 10.0, 1.0) * SPLIT_WEIGHT

    # Value per lot (0-25): $200k/lot = max
    val_per_lot = (land_val / splits) if splits > 0 else 0
    value_score = min(val_per_lot / 200000.0, 1.0) * VALUE_WEIGHT

    # Owner type (0-15): individual = 15, LLC = 10, corp = 5, unknown = 7
    owner = (candidate.get('owner_name') or '').upper()
    if any(x in owner for x in ['LLC', 'INC', 'CORP', 'LTD', 'LP ']):
        owner_score = 10
    elif any(x in owner for x in ['TRUST', 'ESTATE', 'FAMILY']):
        owner_score = 12
    elif owner and not any(x in owner for x in ['ASSOCIATION', 'HOA', 'DISTRICT']):
        owner_score = 15  # individual
    else:
        owner_score = 5

    total = int(split_score + value_score + owner_score)
    return min(max(total, 0), 80)  # cap at 80 — flags/bonuses push to 100


def score_to_tier(score: int) -> str:
    """Map numeric score to letter tier."""
    for cutoff, tier in TIER_CUTOFFS:
        if score >= cutoff:
            return tier
    return 'F'


def evaluate_candidate(candidate: dict, rules: list[dict]) -> tuple[str, int, bool, list, list]:
    """
    Evaluate a candidate against all rules.
    Returns: (tier, score, exclude, tags, reason_codes)
    """
    # Check exclude rules first
    for rule in rules:
        if rule['action'] == 'exclude' and evaluate_rule(rule, candidate):
            return ('F', 0, True, [], [])

    # Base score
    score = base_score(candidate)

    # Compute EDGE/RISK tags
    from openclaw.analysis.tagger import compute_tags
    from openclaw.analysis.edge_config import edge_config as _edge_cfg
    tags, tag_reasons = compute_tags(candidate, config=_edge_cfg, uga_outside=candidate.get('uga_outside'))
    candidate['tags'] = tags  # make tags available to rule matching below

    # Apply EDGE score boosts
    edge_boosts = {
        'EDGE_SNOCO_LSA_R5_RD_FR': _edge_cfg.weight_lsa,
        'EDGE_SNOCO_RUTA_ARBITRAGE': _edge_cfg.weight_ruta,
        'EDGE_WA_HB1110_MIDDLE_HOUSING': _edge_cfg.weight_hb1110,
        'EDGE_WA_UNIT_LOT_SUBDIVISION': _edge_cfg.weight_unit_lot,
        'EDGE_SNOCO_RURAL_CLUSTER_BONUS': _edge_cfg.weight_rural_cluster,
    }
    for tag, weight in edge_boosts.items():
        if tag in tags:
            score += weight

    # Apply RISK penalties (cap at -30 total)
    risk_tags = [t for t in tags if t.startswith('RISK_')]
    risk_penalty = max(_edge_cfg.weight_risk_penalty * len(risk_tags), -30)
    score += risk_penalty

    # Apply rule-based score adjustments
    explicit_tier = None
    for rule in rules:
        if not evaluate_rule(rule, candidate):
            continue
        if rule['action'] == 'adjust_score':
            score += (rule['score_adj'] or 0)
        elif rule['action'] == 'set_tier' and explicit_tier is None:
            # First (highest priority) set_tier rule wins
            explicit_tier = rule['tier']

    score = min(max(score, 0), 100)
    tier = explicit_tier or score_to_tier(score)

    # Collect all reason codes
    all_reasons = tag_reasons  # extend with rule-triggered reasons if needed
    return (tier, score, False, tags, all_reasons)


def rescore_all() -> dict:
    """Re-score all candidates using current rule set. Returns summary."""
    session = SessionLocal()
    try:
        rules = load_rules(session)
        logger.info(f"Loaded {len(rules)} active scoring rules")

        # Load all candidates with parcel data
        rows = session.execute(text("""
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
                p.address, p.county, p.frontage_ft, p.parcel_width_ft, p.last_sale_price
            FROM candidates c
            JOIN parcels p ON c.parcel_id = p.id
        """)).mappings().all()

        logger.info(f"Re-scoring {len(rows):,} candidates")

        tier_counts = {t: 0 for t in 'ABCDEF'}
        excluded = 0
        updates = []
        try:
            compute_zone_medians(session)
        except Exception:
            logger.exception("Zone median cache build failed; underpricing component will be skipped")

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

        for row in rows:
            candidate = dict(row)
            parcel = {
                "zone_code": row.get("zone_code"),
                "lot_sf": row.get("lot_sf"),
                "address": row.get("address"),
                "frontage_ft": row.get("frontage_ft"),
                "parcel_width_ft": row.get("parcel_width_ft"),
            }
            sub = assess_subdivision(candidate, parcel)
            candidate["potential_splits"] = sub.splits_most_likely

            tier, score, exclude, tags, reasons = evaluate_candidate(candidate, rules)
            econ_margin, econ_tags, econ_reasons = compute_economic_margin(
                candidate,
                splits=sub.splits_most_likely,
                zone_code=row.get("zone_code") or "",
            )
            pre_arb_tags = _merge_unique(tags, sub.flags, econ_tags)
            arb_score, arb_tags, arb_reasons = compute_arbitrage_depth(candidate, tags=pre_arb_tags)

            for flag in _merge_unique(sub.flags, econ_tags, arb_tags):
                score += SUBDIVISION_SCORE_EFFECTS.get(flag, 0)
            score = min(max(score, 0), 100)

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
                updates.append({
                    'id': str(row['candidate_id']),
                    'tier': 'F',
                    'score': 0,
                    'potential_splits': sub.splits_most_likely,
                    'tags': merged_tags,
                    'reasons': merged_reasons,
                    'sub_score': sub.score,
                    'sub_feasibility': sub.feasibility,
                    'sub_flags': sub.flags,
                    'splits_min': sub.splits_min,
                    'splits_max': sub.splits_max,
                    'splits_confidence': sub.splits_confidence,
                    'sub_access_mode': sub.access_mode,
                    'arbitrage_depth_score': arb_score,
                    'economic_margin_pct': econ_margin,
                })
            else:
                tier = score_to_tier(score)
                tier_counts[tier] = tier_counts.get(tier, 0) + 1
                updates.append({
                    'id': str(row['candidate_id']),
                    'tier': tier,
                    'score': score,
                    'potential_splits': sub.splits_most_likely,
                    'tags': merged_tags,
                    'reasons': merged_reasons,
                    'sub_score': sub.score,
                    'sub_feasibility': sub.feasibility,
                    'sub_flags': sub.flags,
                    'splits_min': sub.splits_min,
                    'splits_max': sub.splits_max,
                    'splits_confidence': sub.splits_confidence,
                    'sub_access_mode': sub.access_mode,
                    'arbitrage_depth_score': arb_score,
                    'economic_margin_pct': econ_margin,
                })

        # Ensure columns exist
        session.execute(text(
            "ALTER TABLE candidates ADD COLUMN IF NOT EXISTS score INTEGER DEFAULT 0"
        ))
        session.execute(text(
            "ALTER TABLE candidates ADD COLUMN IF NOT EXISTS tags TEXT[] DEFAULT '{}'"
        ))
        session.execute(text(
            "ALTER TABLE candidates ADD COLUMN IF NOT EXISTS reason_codes TEXT[] DEFAULT '{}'"
        ))
        session.execute(text(
            "ALTER TABLE candidates ADD COLUMN IF NOT EXISTS subdivisibility_score INTEGER DEFAULT 0"
        ))
        session.execute(text(
            "ALTER TABLE candidates ADD COLUMN IF NOT EXISTS subdivision_feasibility VARCHAR(20) DEFAULT 'UNKNOWN'"
        ))
        session.execute(text(
            "ALTER TABLE candidates ADD COLUMN IF NOT EXISTS subdivision_flags TEXT[] DEFAULT '{}'"
        ))
        session.execute(text(
            "ALTER TABLE candidates ADD COLUMN IF NOT EXISTS splits_min INTEGER"
        ))
        session.execute(text(
            "ALTER TABLE candidates ADD COLUMN IF NOT EXISTS splits_max INTEGER"
        ))
        session.execute(text(
            "ALTER TABLE candidates ADD COLUMN IF NOT EXISTS splits_confidence VARCHAR(10)"
        ))
        session.execute(text(
            "ALTER TABLE candidates ADD COLUMN IF NOT EXISTS subdivision_access_mode VARCHAR(20)"
        ))
        session.execute(text(
            "ALTER TABLE candidates ADD COLUMN IF NOT EXISTS arbitrage_depth_score INTEGER"
        ))
        session.execute(text(
            "ALTER TABLE candidates ADD COLUMN IF NOT EXISTS economic_margin_pct DOUBLE PRECISION"
        ))
        session.commit()

        # Bulk update via psycopg2 execute_values
        from psycopg2.extras import execute_values
        raw_conn = session.connection().connection
        cur = raw_conn.cursor()

        execute_values(cur, """
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
                economic_margin_pct = v.economic_margin_pct
            FROM (VALUES %s) AS v(
                id, tier, score, potential_splits, tags, reasons, sub_score, sub_feasibility, sub_flags,
                splits_min, splits_max, splits_confidence, sub_access_mode, arbitrage_depth_score, economic_margin_pct
            )
            WHERE candidates.id = v.id::uuid
        """, [
            (
                u['id'],
                u['tier'],
                u['score'],
                u['potential_splits'],
                u['tags'],
                u['reasons'],
                u['sub_score'],
                u['sub_feasibility'],
                u['sub_flags'],
                u['splits_min'],
                u['splits_max'],
                u['splits_confidence'],
                u['sub_access_mode'],
                u['arbitrage_depth_score'],
                u['economic_margin_pct'],
            )
            for u in updates
        ])
        raw_conn.commit()
        cur.close()

        # Remove excluded candidates (score=0, tier=F from exclude rules)
        session.execute(text(
            "DELETE FROM candidates WHERE score = 0 AND score_tier = 'F'::scoretierenum"
        ))
        session.commit()

        logger.info(f"Re-score complete: {tier_counts}, excluded: {excluded}")
        return {'tiers': tier_counts, 'excluded': excluded, 'total': len(updates)}

    finally:
        session.close()


if __name__ == '__main__':
    import logging as _logging
    _logging.basicConfig(level=_logging.INFO)
    result = rescore_all()
    print(f"Result: {result}")
