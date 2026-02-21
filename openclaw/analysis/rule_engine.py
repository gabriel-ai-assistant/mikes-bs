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


def evaluate_candidate(candidate: dict, rules: list[dict]) -> tuple[str, int, bool]:
    """
    Evaluate a candidate against all rules.
    Returns: (tier, score, exclude)
    """
    # Check exclude rules first
    for rule in rules:
        if rule['action'] == 'exclude' and evaluate_rule(rule, candidate):
            return ('F', 0, True)

    # Base score
    score = base_score(candidate)

    # Apply score adjustments
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
    return (tier, score, False)


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
                p.present_use, p.owner_name, p.zone_code,
                p.lot_sf, p.assessed_value, p.improvement_value, p.total_value
            FROM candidates c
            JOIN parcels p ON c.parcel_id = p.id
        """)).mappings().all()

        logger.info(f"Re-scoring {len(rows):,} candidates")

        tier_counts = {t: 0 for t in 'ABCDEF'}
        excluded = 0
        updates = []

        for row in rows:
            candidate = dict(row)
            tier, score, exclude = evaluate_candidate(candidate, rules)
            if exclude:
                excluded += 1
                # Mark as F and flag for deletion
                updates.append({'id': str(row['candidate_id']), 'tier': 'F', 'score': 0})
            else:
                tier_counts[tier] = tier_counts.get(tier, 0) + 1
                updates.append({'id': str(row['candidate_id']), 'tier': tier, 'score': score})

        # Bulk update tiers using psycopg2 execute_values for performance
        session.execute(text(
            "ALTER TABLE candidates ADD COLUMN IF NOT EXISTS score INTEGER DEFAULT 0"
        ))
        session.commit()

        # Build bulk update via temp table approach — avoids row-by-row and cast issues
        from psycopg2.extras import execute_values
        raw_conn = session.connection().connection
        cur = raw_conn.cursor()

        execute_values(cur, """
            UPDATE candidates SET
                score_tier = v.tier::scoretierenum,
                score = v.score
            FROM (VALUES %s) AS v(id, tier, score)
            WHERE candidates.id = v.id::uuid
        """, [(u['id'], u['tier'], u['score']) for u in updates])
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
