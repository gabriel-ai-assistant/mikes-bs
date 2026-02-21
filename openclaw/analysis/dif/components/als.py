"""ALS — Absorption Liquidity Score (0–10).

Measures how liquid the local market is for homes in the target price band
($900k–$1.5M by default), using time-weighted recent comparable sales.

Requires a live DB session. Without one, returns score=0 / 'unavailable'.

Recency weighting:
  0–180 days: 1.0×
  181–365 days: 0.5×
  366–730 days: 0.25×

Always emits ALS_NO_DOM until days-on-market data is implemented.
"""

from datetime import date, timedelta

from sqlalchemy import text

from openclaw.analysis.dif.components import ComponentResult

_ALS_COMP_SQL = text("""
    SELECT
        p.last_sale_price,
        p.last_sale_date
    FROM parcels p
    WHERE p.last_sale_price IS NOT NULL
        AND p.last_sale_price > 0
        AND p.last_sale_date IS NOT NULL
        AND p.last_sale_date >= :cutoff_date
        AND p.county::text = :county
        AND p.zone_code = :zone_code
        AND ST_DWithin(
            p.geometry::geography,
            (SELECT geometry::geography FROM parcels WHERE id = :parcel_id),
            :radius_meters
        )
        AND p.id != :parcel_id
""")


def _get_recency_weight(days_since_sale: int, recency_weights) -> float:
    """Return the recency weight for a sale N days ago."""
    for lo, hi, weight in recency_weights:
        if lo <= days_since_sale <= hi:
            return weight
    return 0.0


def compute_als(candidate: dict, config=None, session=None) -> ComponentResult:
    """Compute Absorption Liquidity Score for a candidate parcel.

    Args:
        candidate: dict with parcel data (parcel_id, county, zone_code)
        config: DIFConfig instance; if None, module-level dif_config is used
        session: SQLAlchemy session; if None, returns unavailable result

    Returns:
        ComponentResult(score, reasons, data_quality)
    """
    if config is None:
        from openclaw.analysis.dif.config import dif_config
        config = dif_config

    if session is None:
        return ComponentResult(
            score=0.0,
            reasons=['ALS_NO_SESSION', 'ALS_NO_DOM'],
            data_quality='unavailable',
        )

    today = date.today()
    cutoff = today - timedelta(days=730)

    try:
        result = session.execute(
            _ALS_COMP_SQL,
            {
                'parcel_id': str(candidate.get('parcel_id', '')),
                'county': candidate.get('county', ''),
                'zone_code': candidate.get('zone_code', ''),
                'cutoff_date': cutoff,
                'radius_meters': config.ALS_COMP_RADIUS_METERS,
            }
        )
        rows = result.fetchall()
    except Exception:
        rows = []

    in_band_weighted = 0.0
    total_weighted = 0.0

    for row in rows:
        price = row[0]
        sale_date = row[1]

        if isinstance(sale_date, date):
            days_since = (today - sale_date).days
        else:
            days_since = 365  # fallback

        weight = _get_recency_weight(days_since, config.ALS_RECENCY_WEIGHTS)
        total_weighted += weight

        if config.ALS_TARGET_LOW <= price <= config.ALS_TARGET_HIGH:
            in_band_weighted += weight

    band_ratio = in_band_weighted / max(total_weighted, 0.001)
    score = min(in_band_weighted / config.ALS_SATURATION_COUNT, 1.0) * 7.0 + band_ratio * 3.0

    reasons = [
        'ALS_NO_DOM',
        f'ALS: in_band_weighted={in_band_weighted:.1f}, total={total_weighted:.1f}, score={score:.1f}',
    ]

    return ComponentResult(score=score, reasons=reasons, data_quality='partial')
