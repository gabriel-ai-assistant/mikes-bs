"""Tax delinquency enrichment for Seller Fatigue Index (SFI).

TODO(data): Query Snohomish County Treasurer public records API for delinquent parcel list.
URL: https://www.snohomishcountywa.gov/1117/Delinquent-Taxes
When loaded: adds TAX_DELINQUENT tag to candidates; SFI scoring uses real data.
Until loaded: SFI emits TAX_DELINQUENCY_STUBBED with neutral contribution.
"""
import logging

logger = logging.getLogger(__name__)


def enrich_tax_delinquency(session=None) -> int:
    """Enrich candidates with tax delinquency status from county treasurer records.

    Returns the number of delinquent parcels tagged (0 until real data is provided).
    """
    # TODO(data): Fetch delinquent parcel list from Snohomish County Treasurer API,
    # match to parcels by parcel number, and upsert TAX_DELINQUENT tag to candidates.tags.
    logger.warning("Tax delinquency data not loaded — SFI_TAX_DELINQUENCY_STUBBED will be emitted.")
    return 0
