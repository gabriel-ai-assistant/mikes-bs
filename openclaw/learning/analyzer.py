"""Nightly learning analyzer — reads feedback, asks Claude for scoring proposals."""
import json
import logging
import re
from collections import Counter

# anthropic import removed — using openai
from sqlalchemy import text

logger = logging.getLogger("openclaw.learning.analyzer")


# ─────────────────────────────────────────────
# Step A — Fetch feedback signal
# ─────────────────────────────────────────────

def fetch_feedback_signal(session, days: int = 7) -> dict:
    """Read candidate_feedback + candidate data for the past N days.

    Returns structured dict with:
      - downvotes / upvotes: list of candidate dicts
      - downvote_reasons: Counter of category values
      - downvoted_tags / upvoted_tags: Counters of tag co-occurrence
      - total_feedback: int
    """
    rows = session.execute(text("""
        SELECT
            cf.id            AS feedback_id,
            cf.rating,
            cf.category,
            cf.notes,
            cf.created_at,
            c.id             AS candidate_id,
            c.score          AS score_at_time,
            c.score_tier,
            c.tags,
            c.reason_codes,
            c.subdivision_flags,
            p.zone_code,
            p.present_use
        FROM candidate_feedback cf
        JOIN candidates c ON c.id = cf.candidate_id
        JOIN parcels    p ON p.id = c.parcel_id
        WHERE cf.created_at >= NOW() - INTERVAL ':days days'
    """.replace(":days days", f"{int(days)} days"))).mappings().all()

    downvotes = []
    upvotes = []
    downvote_reasons: Counter = Counter()
    downvoted_tags: Counter = Counter()
    upvoted_tags: Counter = Counter()

    for row in rows:
        r = dict(row)
        tags = list(r.get("tags") or [])
        entry = {
            "candidate_id": str(r["candidate_id"]),
            "zone_code":    r.get("zone_code"),
            "present_use":  r.get("present_use"),
            "tags":         tags,
            "reason_codes": list(r.get("reason_codes") or []),
            "subdivision_flags": list(r.get("subdivision_flags") or []),
            "category":     r.get("category"),
            "notes":        r.get("notes"),
            "score_at_time": r.get("score_at_time"),
            "score_tier":   r.get("score_tier"),
        }

        if r["rating"] == "down":
            downvotes.append(entry)
            if r.get("category"):
                downvote_reasons[r["category"]] += 1
            for tag in tags:
                downvoted_tags[tag] += 1
        else:
            upvotes.append(entry)
            for tag in tags:
                upvoted_tags[tag] += 1

    return {
        "downvotes":       downvotes,
        "upvotes":         upvotes,
        "downvote_reasons": downvote_reasons,
        "downvoted_tags":  downvoted_tags,
        "upvoted_tags":    upvoted_tags,
        "total_feedback":  len(downvotes) + len(upvotes),
    }


# ─────────────────────────────────────────────
# Step B — Build AI prompt
# ─────────────────────────────────────────────

def build_analysis_prompt(signal: dict, current_rules: list) -> str:
    """Build prompt for Claude to analyze feedback and propose rule changes."""
    return f"""You are an expert real estate scoring system tuner for Mike's Building System,
a subdivision deal-finder for Snohomish County, WA.

CURRENT SCORING RULES:
{json.dumps(current_rules, indent=2, default=str)}

FEEDBACK SIGNAL (last 7 days):
- Total feedback: {signal['total_feedback']}
- Downvotes: {len(signal['downvotes'])}
- Upvotes: {len(signal['upvotes'])}

TOP DOWNVOTE REASONS:
{json.dumps(dict(signal['downvote_reasons'].most_common(10)), indent=2)}

TAGS MOST ASSOCIATED WITH DOWNVOTES (appearing in downvoted candidates):
{json.dumps(dict(signal['downvoted_tags'].most_common(15)), indent=2)}

TAGS MOST ASSOCIATED WITH UPVOTES:
{json.dumps(dict(signal['upvoted_tags'].most_common(15)), indent=2)}

SAMPLE DOWNVOTED CANDIDATES:
{json.dumps(signal['downvotes'][:10], indent=2, default=str)}

Based on this feedback, propose specific, actionable adjustments to improve scoring accuracy.
For each proposal, provide:
1. proposal_type: one of [adjust_rule_weight, add_new_tag, add_new_risk_tag, add_exclusion_pattern]
2. description: plain English explanation
3. evidence: specific data points from the feedback that support this change
4. current_value: what exists now (rule weight, tag name, etc.) — null if new
5. proposed_value: what you recommend
6. confidence: HIGH/MEDIUM/LOW
7. estimated_impact: how many candidates this would affect

Return a JSON array of proposals only. No other text. Example:
[
  {{
    "proposal_type": "add_new_risk_tag",
    "description": "Add RISK_HOA_OWNED tag — HOA owners appear in 67% of downvotes",
    "evidence": "8 of 12 downvoted candidates had owner_name containing HOA, LLC, or ASSOCIATION",
    "current_value": null,
    "proposed_value": "RISK_HOA_OWNED: -25 pts, suppress from Tier A/B",
    "confidence": "HIGH",
    "estimated_impact": "~340 candidates would be reclassified"
  }}
]
"""


# ─────────────────────────────────────────────
# Step C — Call Claude API
# ─────────────────────────────────────────────

def run_ai_analysis(prompt: str) -> list:
    """Send prompt to an LLM and parse JSON proposals.
    
    Uses OpenAI GPT-4o (OPENAI_API_KEY env var).
    """
    try:
        import openai
        client = openai.OpenAI()  # uses OPENAI_API_KEY env var
        response = client.chat.completions.create(
            model="gpt-4o",
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        text_content = response.choices[0].message.content.strip()
    except ImportError:
        logger.error("openai package not installed")
        return []

    logger.debug("LLM raw response: %s", text_content[:500])

    # Parse JSON array — handle optional markdown fences
    match = re.search(r"\[.*\]", text_content, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError as exc:
            logger.error("Failed to parse LLM JSON: %s", exc)
    return []


# ─────────────────────────────────────────────
# Step D — Save proposals to DB
# ─────────────────────────────────────────────

ENSURE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS learning_proposals (
    id              SERIAL PRIMARY KEY,
    run_date        TIMESTAMP DEFAULT NOW(),
    proposal_type   TEXT,
    description     TEXT,
    evidence        TEXT,
    current_value   TEXT,
    proposed_value  TEXT,
    confidence      TEXT,
    estimated_impact TEXT,
    status          TEXT DEFAULT 'pending',
    reviewed_at     TIMESTAMP,
    applied_at      TIMESTAMP
);
"""


def save_proposals(proposals: list, session) -> int:
    """Save AI proposals to DB. Returns count of newly inserted rows.

    Skips exact duplicates of existing pending proposals (same description).
    """
    # Ensure table exists (belt-and-suspenders; migration should create it)
    session.execute(text(ENSURE_TABLE_SQL))

    # Fetch existing pending descriptions to deduplicate
    existing = set(
        r[0]
        for r in session.execute(
            text("SELECT description FROM learning_proposals WHERE status='pending'")
        ).all()
    )

    inserted = 0
    for p in proposals:
        desc = p.get("description", "")
        if desc in existing:
            logger.debug("Skipping duplicate proposal: %s", desc[:80])
            continue
        session.execute(
            text("""
                INSERT INTO learning_proposals
                    (proposal_type, description, evidence, current_value, proposed_value,
                     confidence, estimated_impact, status)
                VALUES
                    (:proposal_type, :description, :evidence, :current_value, :proposed_value,
                     :confidence, :estimated_impact, 'pending')
            """),
            {
                "proposal_type":   str(p.get("proposal_type") or ""),
                "description":     desc,
                "evidence":        str(p.get("evidence") or ""),
                "current_value":   str(p.get("current_value") or "") if p.get("current_value") is not None else None,
                "proposed_value":  str(p.get("proposed_value") or ""),
                "confidence":      str(p.get("confidence") or "MEDIUM"),
                "estimated_impact": str(p.get("estimated_impact") or ""),
            },
        )
        existing.add(desc)
        inserted += 1

    session.commit()
    return inserted


# ─────────────────────────────────────────────
# Step E — Main runner
# ─────────────────────────────────────────────

def run_nightly_learning(session=None) -> int:
    """Main entry point. Fetch signal, analyze, save proposals.

    Returns number of proposals saved (0 if skipped).
    """
    own_session = session is None
    if own_session:
        from openclaw.db.session import SessionLocal
        session = SessionLocal()

    try:
        signal = fetch_feedback_signal(session, days=7)
        if signal["total_feedback"] < 3:
            logger.info(
                "Not enough feedback to analyze (have %d, need at least 3). Skipping.",
                signal["total_feedback"],
            )
            return 0

        rules = session.execute(
            text("SELECT * FROM scoring_rules WHERE active = true ORDER BY priority")
        ).mappings().all()
        rules_list = [dict(r) for r in rules]

        prompt = build_analysis_prompt(signal, rules_list)
        logger.info(
            "Calling Claude for learning analysis — %d downvotes, %d upvotes",
            len(signal["downvotes"]),
            len(signal["upvotes"]),
        )
        proposals = run_ai_analysis(prompt)
        logger.info("Claude returned %d proposals", len(proposals))

        count = save_proposals(proposals, session)
        logger.info(
            "Learning run complete: %d proposals saved from %d feedback items",
            count,
            signal["total_feedback"],
        )
        return count

    except Exception as exc:
        logger.error("Learning run failed: %s", exc, exc_info=True)
        raise
    finally:
        if own_session:
            session.close()


if __name__ == "__main__":
    import logging as _logging
    _logging.basicConfig(level=_logging.INFO)
    run_nightly_learning()
