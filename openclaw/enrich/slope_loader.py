"""Slope/topography enrichment for Entitlement Friction Index (EFI).

TODO(data): Download USGS 1/3 arc-second DEM for Snohomish County.
Source: https://www.usgs.gov/the-national-map-data-delivery
Compute per-parcel mean slope % and store in parcels.slope_pct.
Until loaded: EFI ignores slope contribution (SLOPE_STUBBED reason code emitted).
Slope > 20% would add EFI friction = 2.0 (see EFI config).
"""
import logging

logger = logging.getLogger(__name__)


def load_slope_data(filepath: str, session=None) -> int:
    """Load USGS DEM slope data and compute per-parcel mean slope percentage.

    Returns the number of parcels enriched with slope data (0 until real data is provided).
    """
    # TODO(data): Parse USGS DEM GeoTIFF, compute per-parcel mean slope % using
    # ST_Intersects + raster aggregation (PostGIS raster or rasterio),
    # and store in parcels.slope_pct column.
    logger.warning("Slope/DEM data not loaded — EFI uses SLOPE_STUBBED with 0 slope friction.")
    return 0
