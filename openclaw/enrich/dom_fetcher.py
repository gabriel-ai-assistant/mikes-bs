"""Days-on-Market (DOM) fetcher for Absorption Liquidity Score (ALS).

TODO(data): Integrate with MLS API (NWMLS), Redfin Data Center, or Zillow Research API.
DOM data enables recency-adjusted liquidity scoring. Until available:
- ALS uses comp volume only (no DOM weighting)
- ALS_NO_DOM reason code is always emitted
- ALS weight is reduced (2 vs 3) to reflect lower confidence
"""
import logging

logger = logging.getLogger(__name__)


def fetch_days_on_market(session=None) -> int:
    """Fetch and store Days-on-Market data for parcels in the candidate pipeline.

    Returns the number of parcels enriched with DOM data (0 until real data is provided).
    """
    # TODO(data): Connect to NWMLS, Redfin Data Center, or Zillow Research API.
    # Store median DOM by zone/radius in a dom_data table or directly on parcels.
    # ALS component will then apply recency-adjusted weighting instead of flat comp volume.
    logger.warning("DOM data not loaded — ALS uses comp volume only. ALS_NO_DOM will be emitted.")
    return 0
