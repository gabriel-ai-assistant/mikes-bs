import uuid
import json
import logging
from datetime import datetime
from sqlalchemy import text
from openclaw.db.session import SessionLocal
from openclaw.analysis.tagger import compute_tags

logger = logging.getLogger(__name__)


def run_discovery(county=None, top_n_a=20, top_n_b=50, json_out=None, assumptions_version='v1', session=None) -> dict:
    run_id = str(uuid.uuid4())
    run_date = datetime.utcnow()
    own_session = session is None
    if own_session:
        session = SessionLocal()
    try:
        # Query candidates + parcels
        where = "WHERE p.county = :county" if county else ""
        params = {"county": county} if county else {}
        rows = session.execute(text(f"""
            SELECT c.id as candidate_id, c.parcel_id, c.score, c.score_tier, c.tags,
                   c.uga_outside, c.potential_splits, c.has_critical_area_overlap,
                   c.reason_codes,
                   p.address, p.county, p.zone_code, p.lot_sf, p.owner_name,
                   p.assessed_value, p.improvement_value, p.total_value,
                   p.last_sale_date, p.last_sale_price
            FROM candidates c JOIN parcels p ON c.parcel_id = p.id
            {where}
        """), params).mappings().all()

        results = []
        for row in rows:
            candidate = dict(row)
            uga_outside = candidate.get('uga_outside')

            # Re-compute tags
            try:
                new_tags, new_reasons = compute_tags(candidate, uga_outside=uga_outside)
            except Exception:
                new_tags = list(candidate.get('tags') or [])
                new_reasons = list(candidate.get('reason_codes') or [])

            # Try DIF
            edge_score = float(candidate.get('score') or 0)
            dif_delta = 0.0
            dif_components = {}
            try:
                from openclaw.analysis.dif.engine import compute_dif
                dif_result = compute_dif(candidate)
                dif_delta = dif_result.delta
                dif_components = dif_result.components
                edge_score = edge_score + dif_delta
            except (ImportError, Exception):
                pass

            results.append({
                'candidate_id': str(candidate['candidate_id']),
                'parcel_id': str(candidate['parcel_id']),
                'address': candidate.get('address'),
                'county': candidate.get('county'),
                'edge_score': round(edge_score, 2),
                'tier': candidate.get('score_tier'),
                'tags': new_tags,
                'top_reasons': new_reasons[:5],
                'dif_components': dif_components,
            })

        # Upsert to deal_analysis
        try:
            for r in results:
                session.execute(text("""
                    INSERT INTO deal_analysis (parcel_id, county, run_date, run_id, assumptions_version, tags, edge_score, tier, reasons, underwriting_json)
                    VALUES (:parcel_id, :county, :run_date, :run_id, :assumptions_version, :tags, :edge_score, :tier, :reasons, :uw_json)
                    ON CONFLICT (parcel_id, (run_date::date), assumptions_version)
                    DO UPDATE SET edge_score=EXCLUDED.edge_score, tags=EXCLUDED.tags, tier=EXCLUDED.tier, run_id=EXCLUDED.run_id, underwriting_json=EXCLUDED.underwriting_json
                """), {
                    'parcel_id': r['parcel_id'], 'county': r['county'],
                    'run_date': run_date, 'run_id': run_id,
                    'assumptions_version': assumptions_version,
                    'tags': r['tags'], 'edge_score': r['edge_score'],
                    'tier': r['tier'], 'reasons': json.dumps(r['top_reasons']),
                    'uw_json': json.dumps({'dif_components': r['dif_components']}),
                })
            session.commit()
        except Exception as e:
            logger.warning(f"Could not upsert to deal_analysis (table may not exist yet): {e}")
            session.rollback()

        # Rank and filter
        sorted_results = sorted(results, key=lambda x: x['edge_score'], reverse=True)
        tier_a = [r for r in sorted_results if r['tier'] in ('A',) or r['edge_score'] >= 85][:top_n_a]
        tier_b = [r for r in sorted_results if r['tier'] in ('B',) or (70 <= r['edge_score'] < 85)][:top_n_b]

        output = {
            'run_id': run_id,
            'run_date': run_date.isoformat(),
            'assumptions_version': assumptions_version,
            'county': county,
            'total_analyzed': len(results),
            'tier_a': tier_a,
            'tier_b': tier_b,
        }

        if json_out:
            with open(json_out, 'w') as f:
                json.dump(output, f, indent=2, default=str)
            logger.info(f"Discovery artifact written to {json_out}")

        return output
    finally:
        if own_session:
            session.close()


if __name__ == '__main__':
    import argparse
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument('--county', default=None)
    parser.add_argument('--top-a', type=int, default=20, dest='top_a')
    parser.add_argument('--top-b', type=int, default=50, dest='top_b')
    parser.add_argument('--json-out', default=None, dest='json_out')
    parser.add_argument('--assumptions-version', default='v1', dest='assumptions_version')
    args = parser.parse_args()
    result = run_discovery(county=args.county, top_n_a=args.top_a, top_n_b=args.top_b,
                           json_out=args.json_out, assumptions_version=args.assumptions_version)
    print(f"Discovery complete: {result['total_analyzed']} analyzed, {len(result['tier_a'])} Tier-A, {len(result['tier_b'])} Tier-B")
