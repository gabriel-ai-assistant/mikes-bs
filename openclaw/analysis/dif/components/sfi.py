"""SFI — Seller Fatigue Index (0–10).

Estimates seller motivation based on:
  - Long ownership duration (≥ SFI_MIN_YEARS → score contribution up to 4.0)
  - Owner is a trust/estate/family entity → +SFI_TRUST_BONUS
  - Low improvement ratio (land bank / underutilized) → +SFI_LOW_IMP_BONUS
  - Tax delinquency: STUB (emits TAX_DELINQUENCY_STUBBED)

data_quality is 'full' when last_sale_date is known, 'partial' otherwise.
"""

from datetime import date

from openclaw.analysis.dif.components import ComponentResult

_TRUST_PATTERNS = ['TRUST', 'ESTATE', 'FAMILY', 'HEIR', 'PROBATE', 'HEIRS']


def compute_sfi(candidate: dict, config=None) -> ComponentResult:
    """Compute Seller Fatigue Index for a candidate parcel.

    Args:
        candidate: dict with parcel data
        config: DIFConfig instance; if None, module-level dif_config is used

    Returns:
        ComponentResult(score, reasons, data_quality)
    """
    if config is None:
        from openclaw.analysis.dif.config import dif_config
        config = dif_config

    today = date.today()

    # ── Ownership duration ────────────────────────────────────────────────
    last_sale_date = candidate.get('last_sale_date')
    if last_sale_date is not None:
        ownership_years = (today - last_sale_date).days / 365.25
        dq = 'full'
    else:
        ownership_years = None
        dq = 'partial'

    # ── Owner type ────────────────────────────────────────────────────────
    owner = (candidate.get('owner_name') or '').upper()
    is_trust = any(pattern in owner for pattern in _TRUST_PATTERNS)

    # ── Improvement ratio ─────────────────────────────────────────────────
    imp_val = float(candidate.get('improvement_value') or 0)
    tot_val = float(candidate.get('total_value') or 1)
    imp_ratio = imp_val / tot_val

    # ── Score accumulation ────────────────────────────────────────────────
    score = 0.0

    if ownership_years is not None and ownership_years >= config.SFI_MIN_YEARS:
        score += min(ownership_years / config.SFI_MAX_YEARS, 1.0) * 4.0
    elif ownership_years is None:
        # Partial quality — use conservative default contribution
        score += config.SFI_NO_SALE_DATE_DEFAULT * 4.0

    if is_trust:
        score += config.SFI_TRUST_BONUS

    if imp_ratio < config.SFI_LOW_IMP_RATIO:
        score += config.SFI_LOW_IMP_BONUS

    score = min(score, 10.0)

    reasons = [
        'TAX_DELINQUENCY_STUBBED',
        f'SFI: ownership_years={ownership_years}, is_trust={is_trust}, imp_ratio={imp_ratio:.2f}, score={score:.1f}',
    ]

    return ComponentResult(score=score, reasons=reasons, data_quality=dq)
