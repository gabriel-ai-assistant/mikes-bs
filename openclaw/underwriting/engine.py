"""Underwriting Engine — Mike's Building System Alpha Engine (Stream C).

Produces full pro forma with 8 sensitivity scenarios for subdivision candidates.

IMPORTANT: The return metric here is `annualized_return_estimate`. This is NOT
a true IRR (Internal Rate of Return), which requires full discounted cash flow
timing. Reason code RETURN_PROXY_NOT_IRR is always emitted to make this clear.
"""

import argparse
import json
import logging
import os
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

class UWConfig:
    """Underwriting configuration loaded from environment variables."""

    def __init__(self):
        self.carry_months: int = int(os.getenv("UW_CARRY_MONTHS", "12"))
        self.build_months: int = int(os.getenv("UW_BUILD_MONTHS", "8"))
        self.absorption_months: int = int(os.getenv("UW_ABSORPTION_MONTHS", "6"))
        self.financing_rate_pct: float = float(os.getenv("UW_FINANCING_RATE_PCT", "7.5"))
        self.financing_ltv: float = float(os.getenv("UW_FINANCING_LTV", "0.65"))


# ---------------------------------------------------------------------------
# Sensitivity Scenarios
# ---------------------------------------------------------------------------

DEFAULT_SCENARIOS = [
    {"label": "base", "hard_cost_delta": 0.0, "price_delta": 0.0, "delay_months": 0, "rate_delta_bps": 0},
    {"label": "+10% hard costs", "hard_cost_delta": 0.10, "price_delta": 0.0, "delay_months": 0, "rate_delta_bps": 0},
    {"label": "+20% hard costs", "hard_cost_delta": 0.20, "price_delta": 0.0, "delay_months": 0, "rate_delta_bps": 0},
    {"label": "-5% sale price", "hard_cost_delta": 0.0, "price_delta": -0.05, "delay_months": 0, "rate_delta_bps": 0},
    {"label": "-10% sale price", "hard_cost_delta": 0.0, "price_delta": -0.10, "delay_months": 0, "rate_delta_bps": 0},
    {"label": "+3mo delay", "hard_cost_delta": 0.0, "price_delta": 0.0, "delay_months": 3, "rate_delta_bps": 0},
    {"label": "+6mo delay", "hard_cost_delta": 0.0, "price_delta": 0.0, "delay_months": 6, "rate_delta_bps": 0},
    {"label": "+200bps rate", "hard_cost_delta": 0.0, "price_delta": 0.0, "delay_months": 0, "rate_delta_bps": 200},
]


# ---------------------------------------------------------------------------
# Pro Forma Dataclass
# ---------------------------------------------------------------------------

@dataclass
class ProForma:
    """Full pro forma for a single subdivision candidate."""

    parcel_id: str
    assumptions_version: str

    # Cost components
    land_acquisition: float
    land_cost_source: str          # 'LAST_SALE' | 'ASSESSED'
    dev_cost: float
    build_cost: float
    carry_cost: float
    financing_cost: float
    total_cost: float

    # Revenue & profit
    total_revenue: float
    gross_profit: float
    margin_pct: float

    # Return proxy (NOT a true IRR — see RETURN_PROXY_NOT_IRR reason)
    annualized_return_estimate: float

    # Timeline
    months_to_exit: int

    # Risk classification
    risk_class: str                # 'A' | 'B' | 'C' | 'D'

    # Explainability
    reasons: list = field(default_factory=list)

    # Sensitivity scenarios (list of dicts, one per scenario)
    scenarios: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Core computation
# ---------------------------------------------------------------------------

def _classify_risk(margin_pct: float) -> str:
    """Map margin_pct to risk class A/B/C/D."""
    if margin_pct >= 0.25:
        return "A"
    elif margin_pct >= 0.15:
        return "B"
    elif margin_pct >= 0.05:
        return "C"
    else:
        return "D"


def compute_proforma(
    candidate: dict,
    arv_per_home: int,
    config: UWConfig,
    assumptions_version: str = "v1",
) -> ProForma:
    """Compute a full pro forma for a subdivision candidate.

    Args:
        candidate: Dict with keys: parcel_id, county, zone_code,
                   potential_splits, assessed_value, last_sale_price,
                   improvement_value, total_value.
        arv_per_home: Estimated ARV (after-repair value) per completed home, $$.
        config: UWConfig instance.
        assumptions_version: Version tag for reproducibility.

    Returns:
        ProForma dataclass.
    """
    # Import here to avoid circular import at module level
    from openclaw.config import settings

    parcel_id = str(candidate.get("parcel_id", ""))
    splits = int(candidate.get("potential_splits", 1) or 1)

    # --- Land acquisition ---
    last_sale = candidate.get("last_sale_price") or 0
    assessed = candidate.get("assessed_value") or 0

    if last_sale and last_sale > 0:
        land_acquisition = float(last_sale)
        land_cost_source = "LAST_SALE"
    else:
        land_acquisition = float(assessed)
        land_cost_source = "ASSESSED"

    # --- Development costs ---
    dev_cost_per_lot = (
        settings.COST_SHORT_PLAT_BASE
        + settings.COST_ENGINEERING_PER_LOT
        + settings.COST_UTILITY_PER_LOT
    )
    dev_cost = float(dev_cost_per_lot * splits)

    # --- Build cost ---
    build_cost = float(settings.COST_BUILD_PER_SF * settings.TARGET_HOME_SF * splits)

    # --- Timeline ---
    months_to_exit = config.carry_months + config.build_months + config.absorption_months

    # --- Carry cost (land + dev, financed at LTV) ---
    rate = config.financing_rate_pct
    ltv = config.financing_ltv
    carry_cost = (land_acquisition + dev_cost) * ltv * (rate / 100.0) * (config.carry_months / 12.0)

    # --- Financing cost (build cost, financed at LTV) ---
    financing_cost = build_cost * ltv * (rate / 100.0) * (config.build_months / 12.0)

    # --- Totals ---
    total_cost = land_acquisition + dev_cost + build_cost + carry_cost + financing_cost
    total_revenue = float(arv_per_home * splits)
    gross_profit = total_revenue - total_cost
    margin_pct = (gross_profit / total_revenue) if total_revenue > 0 else 0.0

    # --- Annualized return estimate (NOT a true IRR) ---
    if total_cost > 0 and months_to_exit > 0:
        annualized_return_estimate = (gross_profit / total_cost) / (months_to_exit / 12.0)
    else:
        annualized_return_estimate = 0.0

    # --- Risk classification ---
    risk_class = _classify_risk(margin_pct)

    # --- Reasons ---
    reasons = [
        "RETURN_PROXY_NOT_IRR",
        f"LAND_COST_SOURCE:{land_cost_source}",
        f"SPLITS:{splits}",
        f"ASSUMPTIONS_VERSION:{assumptions_version}",
    ]

    # --- Sensitivity scenarios ---
    base = ProForma(
        parcel_id=parcel_id,
        assumptions_version=assumptions_version,
        land_acquisition=land_acquisition,
        land_cost_source=land_cost_source,
        dev_cost=dev_cost,
        build_cost=build_cost,
        carry_cost=carry_cost,
        financing_cost=financing_cost,
        total_cost=total_cost,
        total_revenue=total_revenue,
        gross_profit=gross_profit,
        margin_pct=margin_pct,
        annualized_return_estimate=annualized_return_estimate,
        months_to_exit=months_to_exit,
        risk_class=risk_class,
        reasons=reasons,
        scenarios=[],
    )

    # Run all 8 sensitivity scenarios
    scenarios = [run_scenario(base, s, config) for s in DEFAULT_SCENARIOS]
    base.scenarios = scenarios

    return base


# ---------------------------------------------------------------------------
# Scenario analysis
# ---------------------------------------------------------------------------

def run_scenario(base: ProForma, scenario: dict, config: UWConfig) -> dict:
    """Apply a single stress scenario to a base ProForma.

    Args:
        base: Base ProForma (computed at base assumptions).
        scenario: Dict with keys: label, hard_cost_delta, price_delta,
                  delay_months, rate_delta_bps.
        config: UWConfig instance (for base rate reference).

    Returns:
        Dict with label + all scenario-adjusted financial fields.
    """
    hard_cost_delta = scenario.get("hard_cost_delta", 0.0)
    price_delta = scenario.get("price_delta", 0.0)
    delay_months = scenario.get("delay_months", 0)
    rate_delta_bps = scenario.get("rate_delta_bps", 0)

    # Adjusted hard costs (dev + build, scaled together)
    hard_cost_scale = 1.0 + hard_cost_delta
    adj_dev_cost = base.dev_cost * hard_cost_scale
    adj_build_cost = base.build_cost * hard_cost_scale

    # Adjusted revenue
    adj_revenue = base.total_revenue * (1.0 + price_delta)

    # Adjusted rate (base rate + delta in basis points; 100bps = 1%)
    adj_rate = config.financing_rate_pct + (rate_delta_bps / 100.0)
    ltv = config.financing_ltv

    # Recompute carry cost with adjusted rate (base carry months + any delay)
    total_carry_months = config.carry_months + delay_months
    adj_carry_cost = (
        (base.land_acquisition + adj_dev_cost)
        * ltv
        * (adj_rate / 100.0)
        * (config.carry_months / 12.0)
    )

    # Additional delay carry: extra hold on land + dev portion
    delay_carry = (
        (base.land_acquisition + adj_dev_cost)
        * ltv
        * (adj_rate / 100.0)
        * (delay_months / 12.0)
    )

    # Recompute financing cost with adjusted rate
    adj_financing_cost = (
        adj_build_cost * ltv * (adj_rate / 100.0) * (config.build_months / 12.0)
    )

    # Total carry = base carry (adj rate) + delay carry
    total_carry = adj_carry_cost + delay_carry

    adj_total_cost = (
        base.land_acquisition
        + adj_dev_cost
        + adj_build_cost
        + total_carry
        + adj_financing_cost
    )

    adj_gross_profit = adj_revenue - adj_total_cost
    adj_margin_pct = (adj_gross_profit / adj_revenue) if adj_revenue > 0 else 0.0

    # Months to exit (extended by delay)
    adj_months_to_exit = base.months_to_exit + delay_months

    if adj_total_cost > 0 and adj_months_to_exit > 0:
        adj_annualized_return_estimate = (adj_gross_profit / adj_total_cost) / (adj_months_to_exit / 12.0)
    else:
        adj_annualized_return_estimate = 0.0

    return {
        "label": scenario.get("label", ""),
        "hard_cost_delta": hard_cost_delta,
        "price_delta": price_delta,
        "delay_months": delay_months,
        "rate_delta_bps": rate_delta_bps,
        "dev_cost": adj_dev_cost,
        "build_cost": adj_build_cost,
        "carry_cost": total_carry,
        "financing_cost": adj_financing_cost,
        "total_cost": adj_total_cost,
        "total_revenue": adj_revenue,
        "gross_profit": adj_gross_profit,
        "margin_pct": adj_margin_pct,
        "annualized_return_estimate": adj_annualized_return_estimate,
        "months_to_exit": adj_months_to_exit,
        "risk_class": _classify_risk(adj_margin_pct),
    }


# ---------------------------------------------------------------------------
# Full underwriting run (DB-backed)
# ---------------------------------------------------------------------------

def run_underwriting(
    parcel_ids=None,
    tier: str = "A",
    top: int = 20,
    assumptions_version: str = "v1",
    session=None,
) -> list:
    """Run underwriting for a set of candidates.

    Args:
        parcel_ids: Optional list of specific parcel UUIDs to underwrite.
                    If None, queries top candidates by tier.
        tier: Score tier filter ('A', 'B', etc.).
        top: Maximum number of candidates to process.
        assumptions_version: Version tag for reproducibility.
        session: Optional SQLAlchemy session. If provided, upserts results
                 to deal_analysis table.

    Returns:
        List of ProForma instances.
    """
    from sqlalchemy import text as sa_text
    from openclaw.analysis.profit import estimate_arv

    config = UWConfig()

    # Build query
    if parcel_ids:
        parcel_id_list = ", ".join(f"'{pid}'" for pid in parcel_ids)
        query = sa_text(f"""
            SELECT c.parcel_id, c.county, c.zone_code, c.potential_splits,
                   p.assessed_value, p.last_sale_price, p.improvement_value,
                   p.total_value, c.score_tier
            FROM candidates c
            JOIN parcels p ON p.id = c.parcel_id
            WHERE c.parcel_id IN ({parcel_id_list})
            LIMIT :top
        """)
        params = {"top": top}
    else:
        query = sa_text("""
            SELECT c.parcel_id, c.county, c.zone_code, c.potential_splits,
                   p.assessed_value, p.last_sale_price, p.improvement_value,
                   p.total_value, c.score_tier
            FROM candidates c
            JOIN parcels p ON p.id = c.parcel_id
            WHERE c.score_tier = :tier
            ORDER BY c.score DESC
            LIMIT :top
        """)
        params = {"tier": tier, "top": top}

    need_close = False
    if session is None:
        from openclaw.db.session import SessionLocal
        session = SessionLocal()
        need_close = True

    results = []
    try:
        rows = session.execute(query, params).fetchall()

        for row in rows:
            candidate = {
                "parcel_id": row[0],
                "county": row[1],
                "zone_code": row[2],
                "potential_splits": row[3],
                "assessed_value": row[4],
                "last_sale_price": row[5],
                "improvement_value": row[6],
                "total_value": row[7],
            }

            # Estimate ARV via comp query
            arv_per_home, _is_estimated = estimate_arv(
                session,
                str(candidate["parcel_id"]),
                candidate["county"],
                candidate.get("zone_code", ""),
                candidate.get("assessed_value", 0),
            )

            pf = compute_proforma(
                candidate=candidate,
                arv_per_home=arv_per_home,
                config=config,
                assumptions_version=assumptions_version,
            )

            # Upsert to deal_analysis if session provided
            if session is not None:
                upsert = sa_text("""
                    INSERT INTO deal_analysis (
                        parcel_id, county, assumptions_version,
                        annualized_return_estimate, risk_class,
                        tier, reasons, underwriting_json
                    ) VALUES (
                        :parcel_id, :county, :assumptions_version,
                        :annualized_return_estimate, :risk_class,
                        :tier, :reasons, :underwriting_json
                    )
                    ON CONFLICT (parcel_id, (run_date::date), assumptions_version)
                    DO UPDATE SET
                        annualized_return_estimate = EXCLUDED.annualized_return_estimate,
                        risk_class = EXCLUDED.risk_class,
                        reasons = EXCLUDED.reasons,
                        underwriting_json = EXCLUDED.underwriting_json,
                        analysis_timestamp = now()
                """)
                try:
                    session.execute(upsert, {
                        "parcel_id": str(pf.parcel_id),
                        "county": candidate.get("county", ""),
                        "assumptions_version": assumptions_version,
                        "annualized_return_estimate": pf.annualized_return_estimate,
                        "risk_class": pf.risk_class,
                        "tier": str(row[8]) if row[8] else None,
                        "reasons": json.dumps(pf.reasons),
                        "underwriting_json": json.dumps(asdict(pf)),
                    })
                    session.commit()
                except Exception as e:
                    logger.warning(f"Upsert failed for {pf.parcel_id}: {e}")
                    session.rollback()

            results.append(pf)

    finally:
        if need_close:
            session.close()

    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _proforma_to_dict(pf: ProForma) -> dict:
    """Serialize ProForma to JSON-serializable dict."""
    return asdict(pf)


def main():
    parser = argparse.ArgumentParser(
        description="Underwriting Engine — Mike's Building System Alpha Engine"
    )
    parser.add_argument(
        "--tier",
        default="A",
        choices=["A", "B", "C", "D"],
        help="Score tier to underwrite (default: A)",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=20,
        help="Maximum number of candidates (default: 20)",
    )
    parser.add_argument(
        "--parcel-id",
        dest="parcel_ids",
        nargs="+",
        default=None,
        help="Specific parcel UUIDs to underwrite (overrides --tier / --top filter)",
    )
    parser.add_argument(
        "--assumptions-version",
        default="v1",
        help="Assumptions version tag for reproducibility (default: v1)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    results = run_underwriting(
        parcel_ids=args.parcel_ids,
        tier=args.tier,
        top=args.top,
        assumptions_version=args.assumptions_version,
    )

    output = [_proforma_to_dict(pf) for pf in results]
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
