def apply_stub(component: str, reasons: list, data_quality: dict) -> None:
    reasons.append(f'{component}_STUBBED')
    data_quality[component] = 0.0

def calculate_data_confidence(data_quality: dict) -> float:
    component_weights = {'YMS': 0.2, 'EFI': 0.2, 'ALS': 0.2, 'CMS': 0.2, 'SFI': 0.2}
    total = 0.0
    for comp, weight in component_weights.items():
        conf = data_quality.get(comp, 1.0)  # 1.0 = full confidence if not tracked
        total += conf * weight
    return round(total, 3)
