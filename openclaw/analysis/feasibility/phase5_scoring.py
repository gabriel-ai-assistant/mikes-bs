from __future__ import annotations

import os

from ._config import load_json
from .context import AnalysisContext


def _weight(name: str, default: float, cfg: dict) -> float:
    env_name = f"FEAS_{name.upper()}"
    if env_name in os.environ:
        try:
            return float(os.environ[env_name])
        except Exception:
            return default
    return float(cfg.get(name, default))


def run(ctx: AnalysisContext) -> AnalysisContext:
    cfg = load_json("scoring_weights.json")

    w_lot_count = _weight("lot_count", 30, cfg)
    w_constraint = _weight("constraint_penalty", -30, cfg)
    w_driveway = _weight("driveway_penalty", -20, cfg)
    w_envelope = _weight("envelope_penalty", -20, cfg)
    w_bonus_short_plat = _weight("short_plat_bonus", 10, cfg)

    best = None
    for layout in ctx.layouts:
        score = 50.0
        score += min(layout.get("lot_count", 0), 8) / 8.0 * w_lot_count

        tags = layout.get("tags", [])
        if any(t.startswith("RISK_STORMWATER") for t in tags):
            score += w_constraint
        if any(t.startswith("RISK_DRIVEWAY") for t in tags):
            score += w_driveway
        if any(t.startswith("RISK_TIGHT_BUILDING_ENVELOPE") for t in tags):
            score += w_envelope
        if "INFO_SHORT_PLAT" in tags:
            score += w_bonus_short_plat

        score = max(0.0, min(100.0, score))
        layout["score"] = round(score, 2)
        if best is None or layout["score"] > best["score"]:
            best = layout

    ctx.layouts.sort(key=lambda l: l.get("score", 0), reverse=True)
    if best:
        ctx.add_tag(f"SCORE_SUBDIVISION_FEASIBILITY:{int(best['score'])}")
        ctx.add_tag(f"SCORE_BEST_LAYOUT:{best['id']}")

    return ctx
