from collections import namedtuple

DIFResult = namedtuple('DIFResult', ['score', 'delta', 'components', 'reasons', 'data_confidence'])


def compute_dif(candidate: dict, config=None, session=None) -> DIFResult:
    from openclaw.analysis.dif.config import DIFConfig, dif_config
    from openclaw.analysis.dif.components.yms import compute_yms
    from openclaw.analysis.dif.components.efi import compute_efi
    from openclaw.analysis.dif.components.als import compute_als
    from openclaw.analysis.dif.components.cms import compute_cms
    from openclaw.analysis.dif.components.sfi import compute_sfi
    from openclaw.analysis.dif.stubs import calculate_data_confidence

    if config is None:
        config = dif_config

    yms = compute_yms(candidate, config)
    efi = compute_efi(candidate, config)
    als = compute_als(candidate, config, session)
    cms = compute_cms(candidate, config, session)
    sfi = compute_sfi(candidate, config)

    composite = (
        yms.score * config.DIF_WEIGHT_YMS
        + als.score * config.DIF_WEIGHT_ALS
        + cms.score * config.DIF_WEIGHT_CMS
        + sfi.score * config.DIF_WEIGHT_SFI
        - efi.score * config.DIF_WEIGHT_EFI
    ) / 12 * 100

    dif_delta_raw = composite - 50.0
    dif_delta = dif_delta_raw
    clamped = False
    all_reasons = []
    for r in [yms.reasons, efi.reasons, als.reasons, cms.reasons, sfi.reasons]:
        all_reasons.extend(r)

    if dif_delta > config.DIF_MAX_DELTA:
        dif_delta = config.DIF_MAX_DELTA
        clamped = True
        all_reasons.append('DIF_DELTA_CLAMPED_HIGH')
    elif dif_delta < -config.DIF_MAX_DELTA:
        dif_delta = -config.DIF_MAX_DELTA
        clamped = True
        all_reasons.append('DIF_DELTA_CLAMPED_LOW')

    all_reasons.append(f'DIF_DELTA_APPLIED:{dif_delta:.1f}')

    data_quality = {
        'YMS': 1.0 if yms.data_quality == 'full' else 0.5 if yms.data_quality == 'partial' else 0.0,
        'EFI': 1.0 if efi.data_quality == 'full' else 0.5 if efi.data_quality == 'partial' else 0.0,
        'ALS': 1.0 if als.data_quality == 'full' else 0.5 if als.data_quality == 'partial' else 0.0,
        'CMS': 1.0 if cms.data_quality == 'full' else 0.5 if cms.data_quality == 'partial' else 0.0,
        'SFI': 1.0 if sfi.data_quality == 'full' else 0.5 if sfi.data_quality == 'partial' else 0.0,
    }
    data_confidence = calculate_data_confidence(data_quality)

    components = {'yms': yms.score, 'efi': efi.score, 'als': als.score, 'cms': cms.score, 'sfi': sfi.score}
    return DIFResult(score=composite, delta=dif_delta, components=components, reasons=all_reasons, data_confidence=data_confidence)
