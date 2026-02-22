"""Mike's Building System — orchestrator entry point.

Nightly pipeline (6am UTC):
1. Delta sync — pull changed parcels from ArcGIS REST API (CORRDATE watermark)
2. Assign zone codes to new parcels via FLU spatial join
3. Score candidates (lot_sf vs zone minimum, wetland/ag flags)
4. Send email digest of new A/B tier candidates

Seed data is loaded via scripts/load_*.py — not part of the nightly run.

CLI:
    python -m openclaw.main --run-now
    python -m openclaw.main --score-only   (skip ingest, just score)
"""
import argparse
import logging
import sys

from apscheduler.schedulers.blocking import BlockingScheduler

from openclaw.analysis.scorer import run_scoring
from openclaw.discovery.engine import run_discovery
from openclaw.ingest.delta_sync import run_delta_sync
from openclaw.logging_utils import configure_logging
from openclaw.notify.digest import send_digest
from openclaw.learning.analyzer import run_nightly_learning

configure_logging(logging.INFO)
logger = logging.getLogger("openclaw.main")


def run_pipeline(score_only: bool = False):
    """Execute the nightly pipeline."""
    logger.info("=" * 60)
    logger.info("Mike's Building System — pipeline starting")
    logger.info("=" * 60)

    if not score_only:
        # Step 1: Delta sync (ArcGIS API, CORRDATE watermark)
        logger.info("Step 1/3: Delta sync from ArcGIS REST APIs")
        try:
            delta_results = run_delta_sync()
            for county, r in delta_results.items():
                logger.info(f"  {county}: fetched={r['fetched']:,}, upserted={r['upserted']:,}")
        except Exception as e:
            logger.error(f"Delta sync failed: {e} — continuing to scoring")
    else:
        logger.info("Skipping delta sync (--score-only)")

    # Step 2: Score candidates
    logger.info("Step 2/3: Scoring candidates")
    try:
        summary = run_scoring()
        total = sum(v["count"] for v in summary.values())
        logger.info(f"Scoring complete — {total:,} total candidates")
        for tier, stats in summary.items():
            logger.info(
                f"  Tier {tier}: {stats['count']:,} candidates, "
                f"{stats['total_splits']:,} splits, "
                f"{stats['wetland_flagged']} wetland flags"
            )
    except Exception as e:
        logger.error(f"Scoring failed: {e}")
        raise

    # Step 3: Send digest
    logger.info("Step 3/3: Sending digest")
    try:
        count = send_digest()
        logger.info(f"Digest sent — {count} candidates reported")
    except Exception as e:
        logger.warning(f"Digest failed (non-fatal): {e}")

    logger.info("Pipeline complete")


def main():
    parser = argparse.ArgumentParser(description="Mike's Building System")
    parser.add_argument("--run-now", action="store_true", help="Run full pipeline immediately")
    parser.add_argument("--score-only", action="store_true", help="Skip delta sync, run scoring only")
    parser.add_argument("--discover", action="store_true", help="Run weekly discovery now")
    args = parser.parse_args()

    if args.discover:
        run_discovery()
        return

    if args.run_now or args.score_only:
        run_pipeline(score_only=args.score_only)
        return

    # Scheduled mode: daily 6am UTC
    logger.info("Starting scheduler — pipeline runs daily at 06:00 UTC")
    scheduler = BlockingScheduler()
    scheduler.add_job(run_pipeline, "cron", hour=6, minute=0, kwargs={"score_only": False})
    scheduler.add_job(run_discovery, 'cron', day_of_week='sun', hour=6, minute=30, kwargs={'county': None, 'assumptions_version': 'v1'})
    scheduler.add_job(run_nightly_learning, 'cron', hour=2, minute=0, id='nightly_learning')
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped")


if __name__ == "__main__":
    main()
