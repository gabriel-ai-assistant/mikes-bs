"""Public-record owner enrichment provider."""

from __future__ import annotations

from openclaw.db.models import EnrichmentSourceClassEnum, Lead
from openclaw.enrich.base import EnrichmentProvider

ENTITY_KEYWORDS = ("LLC", "INC", "TRUST", "CORP", "LP", "LTD", "ESTATE", "PARTNERSHIP")


def is_entity(owner_name: str | None) -> bool:
    if not owner_name:
        return False
    upper = owner_name.upper()
    return any(kw in upper for kw in ENTITY_KEYWORDS)


class PublicRecordProvider(EnrichmentProvider):
    name = "public_record"
    enabled = True
    rate_limit_per_min = 120
    source_class = EnrichmentSourceClassEnum.public_record

    async def enrich(self, lead: Lead) -> dict:
        owner_snapshot = lead.owner_snapshot or {}
        owner_name = owner_snapshot.get("name")
        mailing_address = owner_snapshot.get("mailing_address")

        if (not owner_name or not mailing_address) and lead.candidate and lead.candidate.parcel:
            owner_name = owner_name or lead.candidate.parcel.owner_name
            mailing_address = mailing_address or lead.candidate.parcel.owner_address

        data = {
            "owner_name": owner_name,
            "mailing_address": mailing_address,
            "is_entity": is_entity(owner_name),
            "source": "county_record",
        }
        status = "success" if owner_name or mailing_address else "partial"
        confidence = 0.95 if status == "success" else 0.5
        return {
            "status": status,
            "data": data,
            "confidence": confidence,
            "error_message": None,
        }
