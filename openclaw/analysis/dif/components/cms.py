"""CMS — Construction Margin Spread (0–10).

Estimates the project gross margin accounting for:
  - Land cost (priority: LIST_PRICE → LAST_SALE → ASSESSED)
  - Dev cost (short plat + engineering + utility per lot)
  - Build cost (cost per SF × target home SF × splits)
  - Carry cost (financing on land + dev over carry months)
  - Revenue (ARV from comps if session available; else assessed × 2.5 fallback)

Always emits RETURN_PROXY_NOT_IRR — this is not a true IRR computation.
"""

from openclaw.analysis.dif.components import ComponentResult


def compute_cms(candidate: dict, config=None, session=None) -> ComponentResult:
    """Compute Construction Margin Spread for a candidate parcel.

    Args:
        candidate: dict with parcel data
        config: DIFConfig instance; if None, module-level dif_config is used
        session: SQLAlchemy session for ARV comp lookup (optional)

    Returns:
        ComponentResult(score, reasons, data_quality)
    """
    if config is None:
        from openclaw.analysis.dif.config import dif_config
        config = dif_config

    from openclaw.config import settings

    # ── Land cost with source priority ────────────────────────────────────
    county = candidate.get('county', '')
    multiplier = config.CMS_ASSESSED_VALUE_MULTIPLIER.get(
        county,
        config.CMS_ASSESSED_VALUE_MULTIPLIER.get('default', 1.0),
    )
    assessed_value = float(candidate.get('assessed_value') or 0)

    land_cost = None
    source = 'NONE'

    for priority in config.CMS_LAND_COST_PRIORITY:
        if priority == 'LIST_PRICE':
            # Stub — list price data not yet available
            pass
        elif priority == 'LAST_SALE':
            last_sale_price = candidate.get('last_sale_price')
            if last_sale_price and float(last_sale_price) > 0:
                land_cost = float(last_sale_price)
                source = 'LAST_SALE'
                break
        elif priority == 'ASSESSED':
            if assessed_value > 0:
                land_cost = assessed_value * multiplier
                source = 'ASSESSED'
                break

    if land_cost is None or land_cost <= 0:
        land_cost = assessed_value * multiplier
        source = 'ASSESSED'

    # ── Splits ────────────────────────────────────────────────────────────
    splits = max(candidate.get('potential_splits', 1) or 1, 1)

    # ── Costs ─────────────────────────────────────────────────────────────
    dev_cost = (
        settings.COST_SHORT_PLAT_BASE
        + settings.COST_ENGINEERING_PER_LOT
        + settings.COST_UTILITY_PER_LOT
    ) * splits

    build_cost = settings.COST_BUILD_PER_SF * settings.TARGET_HOME_SF * splits

    # ── Revenue (ARV) ─────────────────────────────────────────────────────
    if session is not None:
        try:
            from openclaw.analysis.profit import estimate_arv
            arv_per_home, _ = estimate_arv(
                session,
                str(candidate.get('parcel_id', '')),
                candidate.get('county', ''),
                candidate.get('zone_code', ''),
                int(assessed_value),
            )
            revenue = float(arv_per_home) * splits
        except Exception:
            revenue = assessed_value * 2.5 * splits
    else:
        # Fallback: no comps, use assessed × 2.5
        revenue = assessed_value * 2.5 * splits

    # ── Carry cost ────────────────────────────────────────────────────────
    carry_cost = (
        (land_cost + dev_cost)
        * config.CMS_FINANCING_LTV
        * (config.CMS_FINANCING_RATE_PCT / 100.0)
        * (config.CMS_CARRY_MONTHS / 12.0)
    )

    # ── Margin ────────────────────────────────────────────────────────────
    total_cost = land_cost + dev_cost + build_cost + carry_cost
    margin_pct = (revenue - total_cost) / revenue if revenue > 0 else 0.0

    score = max(0.0, min(margin_pct / config.CMS_MAX_MARGIN_PCT, 1.0)) * 10.0

    reasons = [
        f'LAND_COST_SOURCE:{source}',
        'RETURN_PROXY_NOT_IRR',
        f'CMS: margin={margin_pct:.1%}, score={score:.1f}',
    ]

    data_quality = 'full' if session is not None else 'partial'

    return ComponentResult(score=score, reasons=reasons, data_quality=data_quality)
