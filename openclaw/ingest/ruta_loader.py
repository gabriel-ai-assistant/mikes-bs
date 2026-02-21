"""RUTA (Rural Urban Transition Area) boundary loader.

TODO(data): Request RUTA boundary shapefile/GeoJSON from Snohomish County GIS portal.
Load into ruta_boundaries table. Until loaded, EDGE_SNOCO_RUTA_ARBITRAGE will not fire.
See: https://www.snohomishcountywa.gov/DocumentCenter/View/60604
"""
import logging

logger = logging.getLogger(__name__)


def load_ruta_boundary(filepath: str, session=None) -> int:
    """Load RUTA boundary data from a shapefile or GeoJSON into ruta_boundaries table.

    Returns the number of records loaded (0 until real data is provided).
    """
    # TODO(data): Implement GeoJSON/shapefile parsing and ST_GeomFromGeoJSON upsert
    # once boundary file is obtained from Snohomish County GIS.
    logger.warning("RUTA boundary data not yet loaded — stub only. EDGE_SNOCO_RUTA_ARBITRAGE will not fire.")
    return 0
