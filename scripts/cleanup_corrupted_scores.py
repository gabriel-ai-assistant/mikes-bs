#!/usr/bin/env python3
"""Re-score candidates with potentially corrupted vote-inflated scores."""

from __future__ import annotations

import sys
from collections import Counter

from sqlalchemy import text

sys.path.insert(0, "/app")

from openclaw.analysis.rule_engine import load_rules, score_candidate
from openclaw.db.session import SessionLocal


def main() -> int:
    session = SessionLocal()
    try:
        rules = load_rules(session)
        rows = session.execute(
            text(
                """
                SELECT
                    c.id::text AS candidate_id,
                    c.score AS stored_score,
                    c.score_tier::text AS stored_tier,
                    c.potential_splits,
                    c.has_critical_area_overlap,
                    c.flagged_for_review,
                    c.uga_outside,
                    c.tags,
                    c.reason_codes,
                    p.present_use,
                    p.owner_name,
                    p.zone_code,
                    p.lot_sf,
                    p.assessed_value,
                    p.improvement_value,
                    p.total_value,
                    p.address,
                    p.county,
                    p.frontage_ft,
                    p.parcel_width_ft,
                    p.last_sale_price,
                    COALESCE((
                        SELECT
                            COUNT(*) FILTER (WHERE cf.rating = 'up')
                            - COUNT(*) FILTER (WHERE cf.rating = 'down')
                        FROM candidate_feedback cf
                        WHERE cf.candidate_id = c.id
                    ), 0) AS vote_net
                FROM candidates c
                JOIN parcels p ON p.id = c.parcel_id
                WHERE c.score >= 85
                  AND EXISTS (
                      SELECT 1
                      FROM candidate_feedback upf
                      WHERE upf.candidate_id = c.id
                        AND upf.rating = 'up'
                  )
                ORDER BY c.score DESC, c.id
                """
            )
        ).mappings().all()

        total_examined = len(rows)
        corrupted_found = 0
        rescored = 0
        before_tiers = Counter()
        after_tiers = Counter()

        for row in rows:
            candidate = dict(row)
            pipeline = score_candidate(candidate, rules)
            pipeline_score = int(pipeline["score"])
            stored_score = int(row.get("stored_score") or 0)
            if pipeline_score >= (stored_score - 10):
                continue

            pipeline_tier = str(pipeline["tier"])
            corrupted_found += 1
            before_tiers[str(row.get("stored_tier") or "?")] += 1
            after_tiers[pipeline_tier] += 1

            session.execute(
                text(
                    """
                    UPDATE candidates
                    SET score = :score,
                        score_tier = :tier::scoretierenum
                    WHERE id = :candidate_id::uuid
                    """
                ),
                {
                    "score": pipeline_score,
                    "tier": pipeline_tier,
                    "candidate_id": row["candidate_id"],
                },
            )
            rescored += 1

        session.commit()

        print(f"total_examined={total_examined}")
        print(f"corrupted_found={corrupted_found}")
        print(f"rescored={rescored}")
        print("before_tier_counts=" + ", ".join(f"{k}:{before_tiers[k]}" for k in sorted(before_tiers)) if before_tiers else "before_tier_counts=none")
        print("after_tier_counts=" + ", ".join(f"{k}:{after_tiers[k]}" for k in sorted(after_tiers)) if after_tiers else "after_tier_counts=none")
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
