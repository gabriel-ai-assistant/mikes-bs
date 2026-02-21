"""Transit stop/route data loader for HB1110 transit-adjacency scoring.

TODO(data): Download GTFS feeds from Sound Transit (soundtransit.org) and Community Transit.
Transit adjacency upgrades EDGE_WA_HB1110_MIDDLE_HOUSING from MEDIUM to HIGH weight.
"""
import logging

logger = logging.getLogger(__name__)


def load_transit_data(filepath: str, session=None) -> int:
    """Load GTFS transit stop/route data for HB1110 transit-adjacency scoring.

    Returns the number of stops/routes loaded (0 until real data is provided).
    """
    # TODO(data): Parse GTFS stops.txt and routes.txt, compute per-parcel proximity,
    # store transit_adjacent boolean on candidates or parcels table.
    logger.warning("Transit data not yet loaded — HB1110 parcels scored at MEDIUM weight.")
    return 0
