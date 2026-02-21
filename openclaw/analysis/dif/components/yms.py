"""YMS — Yield Multiplier Score (0–10).

Measures how many developable lots a parcel can yield relative to max expected yield.
Uses pre-computed potential_splits from candidates table (no re-computation here).
"""

from openclaw.analysis.dif.components import ComponentResult


def compute_yms(candidate: dict, config=None) -> ComponentResult:
    """Compute Yield Multiplier Score for a candidate parcel.

    Args:
        candidate: dict with parcel data (potential_splits, has_critical_area_overlap, zone_code)
        config: DIFConfig instance; if None, module-level dif_config is used

    Returns:
        ComponentResult(score, reasons, data_quality)
    """
    if config is None:
        from openclaw.analysis.dif.config import dif_config
        config = dif_config

    raw_yield = candidate.get('potential_splits', 0)
    deduction = config.YMS_CRITICAL_AREA_PENALTY if candidate.get('has_critical_area_overlap') else 0
    adjusted = max(raw_yield - deduction, 0)
    capped = min(adjusted, config.YMS_MAX_EFFECTIVE_LOTS)
    score = min(capped / config.YMS_MAX_YIELD, 1.0) * 10

    reasons = [
        'YMS_HEURISTIC',
        f'YMS: raw={raw_yield}, adjusted={adjusted}, capped={capped}, score={score:.1f}',
    ]

    if adjusted > config.YMS_MAX_EFFECTIVE_LOTS:
        reasons.append('YMS_YIELD_CAPPED')

    data_quality = 'partial' if not candidate.get('zone_code') else 'full'

    return ComponentResult(score=score, reasons=reasons, data_quality=data_quality)
