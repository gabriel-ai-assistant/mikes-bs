"""Lead enrichment execution pipeline."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy.orm import joinedload

from openclaw.config import settings
from openclaw.db.models import Candidate, EnrichmentResult, EnrichmentSourceClassEnum, Lead
from openclaw.db.session import SessionLocal
from openclaw.enrich.base import EnrichmentProvider
from openclaw.enrich.owner import PublicRecordProvider
from openclaw.enrich.skip_trace import SkipTraceProvider

logger = logging.getLogger(__name__)

_provider_last_call_at: dict[str, float] = defaultdict(float)


def _build_providers() -> list[EnrichmentProvider]:
    providers: list[EnrichmentProvider] = [PublicRecordProvider(), SkipTraceProvider()]
    return providers


def _to_source_class(value) -> EnrichmentSourceClassEnum:
    if isinstance(value, EnrichmentSourceClassEnum):
        return value
    try:
        return EnrichmentSourceClassEnum(str(value))
    except Exception:
        return EnrichmentSourceClassEnum.public_record


def _upsert_lead_contacts_from_result(lead: Lead, provider_name: str, payload: dict) -> None:
    if provider_name != "skip_trace":
        return
    data = payload.get("data") or {}
    phones = data.get("phones") or []
    emails = data.get("emails") or []
    if not lead.owner_phone and phones:
        lead.owner_phone = phones[0]
    if not lead.owner_email and emails:
        lead.owner_email = emails[0]


def _enrichment_expiry() -> datetime:
    return datetime.utcnow() + timedelta(days=max(1, int(settings.ENRICHMENT_RETENTION_DAYS)))


def purge_expired_enrichment(session) -> int:
    deleted = session.query(EnrichmentResult).filter(EnrichmentResult.expires_at.isnot(None), EnrichmentResult.expires_at < datetime.utcnow()).delete(synchronize_session=False)
    if deleted:
        logger.info("enrichment.purge", extra={"deleted": deleted})
    return deleted


def run_lead_enrichment(lead_id: str, triggered_by: int | None = None, provider_name: str | None = None) -> None:
    session = SessionLocal()
    try:
        if purge_expired_enrichment(session):
            session.commit()
        lead = (
            session.query(Lead)
            .options(joinedload(Lead.candidate).joinedload(Candidate.parcel))
            .filter(Lead.id == lead_id)
            .first()
        )
        if not lead:
            logger.warning("enrichment.lead_not_found", extra={"lead_id": lead_id})
            return

        providers = _build_providers()
        if provider_name:
            providers = [p for p in providers if p.name == provider_name]

        configured = [p for p in providers if p.is_configured()]
        if not configured:
            logger.info("enrichment.none_configured", extra={"lead_id": lead_id})
            return

        max_retries = max(0, min(3, int(settings.SKIP_TRACE_MAX_RETRIES)))

        for provider in configured:
            retry = 0
            interval = 60.0 / max(1, int(provider.rate_limit_per_min))
            elapsed = time.time() - _provider_last_call_at[provider.name]
            if elapsed < interval:
                time.sleep(interval - elapsed)

            started = time.perf_counter()
            result_payload: dict | None = None
            error_message = None
            while retry <= max_retries:
                try:
                    result_payload = asyncio.run(provider.enrich(lead))
                    break
                except Exception as exc:
                    error_message = str(exc)
                    retry += 1
                    if retry > max_retries:
                        break
                    backoff = min(30, 2 ** (retry - 1))
                    logger.warning(
                        "enrichment.retry",
                        extra={
                            "lead_id": str(lead.id),
                            "provider": provider.name,
                            "retry": retry,
                            "max_retries": max_retries,
                            "backoff_seconds": backoff,
                        },
                    )
                    time.sleep(backoff)

            duration_ms = int((time.perf_counter() - started) * 1000)
            _provider_last_call_at[provider.name] = time.time()

            payload = result_payload or {
                "status": "failed",
                "data": {},
                "confidence": 0.0,
                "error_message": error_message or "Provider failed",
            }
            status_value = payload.get("status", "failed")
            _upsert_lead_contacts_from_result(lead, provider.name, payload)

            row = EnrichmentResult(
                lead_id=lead.id,
                provider=provider.name,
                status=status_value,
                data=payload.get("data") or {},
                confidence=payload.get("confidence"),
                source_class=_to_source_class(getattr(provider, "source_class", EnrichmentSourceClassEnum.public_record)),
                fetched_at=datetime.utcnow(),
                expires_at=_enrichment_expiry(),
                error_message=payload.get("error_message"),
            )
            session.add(row)
            session.add(lead)
            session.commit()

            logger.info(
                "enrichment.call",
                extra={
                    "lead_id": str(lead.id),
                    "provider": provider.name,
                    "status": status_value,
                    "duration_ms": duration_ms,
                    "retries": retry,
                    "triggered_by": triggered_by,
                },
            )
    except Exception:
        session.rollback()
        logger.exception("enrichment.pipeline_error", extra={"lead_id": lead_id, "triggered_by": triggered_by})
    finally:
        session.close()
