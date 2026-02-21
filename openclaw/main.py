"""Mike's Building System — orchestrator entry point.

Run order:
1. Ingest all three counties (parallel async)
2. Run candidacy + scoring SQL
3. Run profit model on new candidates
4. Run owner enrichment on new candidates
5. Insert/update candidates + leads tables
6. Send digest email of new A/B tier candidates

Schedule: daily at 6am via APScheduler.
CLI: python -m openclaw.main --run-now
"""

import argparse
import asyncio
import logging
import sys

from apscheduler.schedulers.blocking import BlockingScheduler

from openclaw.analysis.scorer import find_candidates, assign_tier
from openclaw.analysis.profit import calculate_profit
from openclaw.db.models import Candidate, ScoreTierEnum
from openclaw.db.session import SessionLocal
from openclaw.enrich.owner import enrich_candidates
from openclaw.ingest.king import KingCountyAgent
from openclaw.ingest.snohomish import SnohomishCountyAgent
from openclaw.ingest.skagit import SkagitCountyAgent
from openclaw.notify.digest import send_digest

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("openclaw.main")


async def run_ingest():
    """Run all county ingest agents in parallel."""
    agents = [KingCountyAgent(), SnohomishCountyAgent(), SkagitCountyAgent()]
    results = []
    for agent in agents:
        try:
            result = await agent.run()
            results.append(result)
        except NotImplementedError as e:
            logger.warning(f"Skipping {agent.county.value}: {e}")
        except Exception as e:
            logger.error(f"Ingest failed for {agent.county.value}: {e}")
    return results


def run_pipeline():
    """Execute the full pipeline synchronously."""
    logger.info("=" * 60)
    logger.info("Mike's Building System — pipeline starting")
    logger.info("=" * 60)

    # Step 1: Ingest
    logger.info("Step 1/6: Ingesting county parcel data")
    ingest_results = asyncio.run(run_ingest())
    for r in ingest_results:
        logger.info(f"  {r}")

    # Step 2: Find candidates
    logger.info("Step 2/6: Running candidate scoring query")
    raw_candidates = find_candidates()
    if not raw_candidates:
        logger.info("No new candidates found — pipeline complete")
        return

    # Step 3: Profit model
    logger.info(f"Step 3/6: Running profit model on {len(raw_candidates)} candidates")
    enriched = []
    for c in raw_candidates:
        profit = calculate_profit(c)
        tier = assign_tier(c["potential_splits"], profit["estimated_margin_pct"])
        enriched.append({**c, **profit, "score_tier": tier})

    # Step 4 & 5: Insert candidates + create leads with owner enrichment
    logger.info("Step 4-5/6: Inserting candidates and creating leads")
    session = SessionLocal()
    lead_inputs = []
    try:
        for e in enriched:
            candidate = Candidate(
                parcel_id=e["parcel_id"],
                score_tier=ScoreTierEnum[e["score_tier"]],
                potential_splits=e["potential_splits"],
                estimated_land_value=e["estimated_land_value"],
                estimated_dev_cost=e["estimated_dev_cost"],
                estimated_build_cost=e["estimated_build_cost"],
                estimated_arv=e["estimated_arv"],
                estimated_profit=e["estimated_profit"],
                estimated_margin_pct=e["estimated_margin_pct"],
                flagged_for_review=e.get("flagged_for_review", False),
            )
            session.add(candidate)
            session.flush()  # get the ID
            lead_inputs.append({
                "candidate_id": candidate.id,
                "parcel_id": e["parcel_id"],
                "owner_name": e.get("owner_name"),
            })
        session.commit()
        logger.info(f"Inserted {len(enriched)} candidate records")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    # Owner enrichment + lead creation
    enrich_candidates(lead_inputs)

    # Step 6: Digest
    logger.info("Step 6/6: Sending digest")
    count = send_digest()
    logger.info(f"Digest: {count} candidates reported")
    logger.info("Pipeline complete")


def main():
    parser = argparse.ArgumentParser(description="Mike's Building System")
    parser.add_argument("--run-now", action="store_true", help="Run pipeline immediately")
    args = parser.parse_args()

    if args.run_now:
        run_pipeline()
        return

    # Schedule daily at 6am UTC
    logger.info("Starting scheduler — daily run at 06:00 UTC")
    scheduler = BlockingScheduler()
    scheduler.add_job(run_pipeline, "cron", hour=6, minute=0)
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped")


if __name__ == "__main__":
    main()
