def build_underwriting_json(base_score, edge_boosts, dif_components, dif_delta_raw,
                             dif_delta_applied, dif_clamped, final_score,
                             data_confidence, reasons) -> dict:
    return {
        "base_score": round(float(base_score), 2),
        "edge_boosts": edge_boosts,
        "dif_components": {k: round(float(v), 2) for k, v in dif_components.items()},
        "dif_delta_raw": round(float(dif_delta_raw), 2),
        "dif_delta_applied": round(float(dif_delta_applied), 2),
        "dif_clamped": bool(dif_clamped),
        "final_score": round(float(final_score), 2),
        "data_confidence": round(float(data_confidence), 3),
        "reasons": list(reasons),
    }
