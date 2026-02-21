"""Owner enrichment — flags entity owners for manual skip-trace."""

import logging

from openclaw.db.models import Lead, LeadStatusEnum
from openclaw.db.session import SessionLocal

logger = logging.getLogger(__name__)

ENTITY_KEYWORDS = ("LLC", "INC", "TRUST", "CORP", "LP", "LTD")


def is_entity(owner_name: str | None) -> bool:
    """Check if owner name looks like a business entity."""
    if not owner_name:
        return False
    upper = owner_name.upper()
    return any(kw in upper for kw in ENTITY_KEYWORDS)


def enrich_candidates(candidates: list[dict]) -> int:
    """Create lead records for new candidates, flagging entities.

    Each candidate dict must have: candidate_id, parcel_id, owner_name
    Returns count of leads created.
    """
    session = SessionLocal()
    created = 0
    try:
        for c in candidates:
            entity = is_entity(c.get("owner_name"))
            lead = Lead(
                candidate_id=c["candidate_id"],
                status=LeadStatusEnum.new,
                notes="Entity owner — manual skip-trace required" if entity else None,
            )
            session.add(lead)
            created += 1

        session.commit()
        logger.info(f"Created {created} lead records")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    return created


if __name__ == "__main__":
    print("Owner enrichment — run via main orchestrator.")
