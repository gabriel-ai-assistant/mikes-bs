from datetime import datetime, timedelta

from openclaw.analysis.rule_engine import score_candidate


def _candidate() -> dict:
    return {
        "candidate_id": "00000000-0000-0000-0000-000000000001",
        "potential_splits": 6,
        "lot_sf": 261360,
        "assessed_value": 900000,
        "owner_name": "Jane Smith",
        "county": "snohomish",
        "zone_code": "R-5",
        "has_critical_area_overlap": False,
        "improvement_value": 100000,
        "total_value": 1000000,
        "address": "123 Main St",
        "vote_net": 2,
    }


def test_score_candidate_is_deterministic_for_identical_inputs():
    candidate = _candidate()
    rules = [
        {
            "id": "rule-1",
            "name": "large lot bonus",
            "field": "lot_sf",
            "operator": "gt",
            "value": "200000",
            "action": "adjust_score",
            "score_adj": 7,
            "tier": None,
            "priority": 10,
            "created_at": datetime.utcnow(),
        }
    ]

    first = score_candidate(dict(candidate), rules)
    for _ in range(5):
        nxt = score_candidate(dict(candidate), rules)
        assert nxt["score"] == first["score"]
        assert nxt["tier"] == first["tier"]
        assert nxt["breakdown"] == first["breakdown"]


def test_learned_rule_adjustment_is_bounded_to_max_delta():
    candidate = _candidate()
    rules = [
        {
            "id": "rule-learned",
            "name": "LEARNED: huge adjustment",
            "field": "lot_sf",
            "operator": "gt",
            "value": "1000",
            "action": "adjust_score",
            "score_adj": 99,
            "tier": None,
            "priority": 1,
            "created_at": datetime.utcnow(),
        }
    ]

    scored = score_candidate(dict(candidate), rules)
    dynamic = scored["breakdown"]["dynamic_rules"]
    assert dynamic
    assert dynamic[0]["adjustment"] == 15


def test_learned_rule_weight_decays_with_age():
    candidate = _candidate()
    rules = [
        {
            "id": "rule-decay",
            "name": "LEARNED: decayed",
            "field": "lot_sf",
            "operator": "gt",
            "value": "1000",
            "action": "adjust_score",
            "score_adj": 14,
            "tier": None,
            "priority": 1,
            "created_at": datetime.utcnow() - timedelta(days=30),
        }
    ]

    scored = score_candidate(dict(candidate), rules)
    dynamic = scored["breakdown"]["dynamic_rules"]
    assert dynamic
    # Default half-life is 30 days, so adjustment should be about half.
    assert dynamic[0]["adjustment"] == 7
