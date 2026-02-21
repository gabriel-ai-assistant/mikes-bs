"""EFI — Entitlement Friction Index (0–10).

Asymmetric two-slope scoring: low friction is mildly penalized;
high friction is steeply penalized (never rewarded).

Friction sources:
  - Critical area overlap (wetlands, etc.) → 4.0
  - No improvement value AND no address (access unknown) → 3.0
  - Slope: STUB (emits SLOPE_STUBBED reason)
  - Sewer: STUB (emits SEWER_STUBBED reason)
"""

from openclaw.analysis.dif.components import ComponentResult


def compute_efi(candidate: dict, config=None) -> ComponentResult:
    """Compute Entitlement Friction Index for a candidate parcel.

    Args:
        candidate: dict with parcel data
        config: DIFConfig instance; if None, module-level dif_config is used

    Returns:
        ComponentResult(score, reasons, data_quality)
    """
    if config is None:
        from openclaw.analysis.dif.config import dif_config
        config = dif_config

    friction = 0.0

    # Critical area overlap — strong friction signal
    if candidate.get('has_critical_area_overlap'):
        friction += 4.0

    # No improvement value AND no address → access unknown, high friction
    if not candidate.get('improvement_value') and not candidate.get('address'):
        friction += 3.0

    # Stubs — emit reason codes, add 0 friction
    # (slope, sewer, political risk — data not yet available)

    friction = min(friction, 10.0)

    # Asymmetric two-slope decay formula
    if friction <= config.EFI_MILD_THRESHOLD:
        score = 10.0 - friction * config.EFI_MILD_PENALTY
    else:
        score = max(
            0.0,
            10.0
            - config.EFI_MILD_THRESHOLD * config.EFI_MILD_PENALTY
            - (friction - config.EFI_MILD_THRESHOLD) * config.EFI_STEEP_PENALTY,
        )

    reasons = [
        'SLOPE_STUBBED',
        'SEWER_STUBBED',
        f'EFI: friction={friction:.1f}, score={score:.1f}',
    ]

    return ComponentResult(score=score, reasons=reasons, data_quality='partial')
