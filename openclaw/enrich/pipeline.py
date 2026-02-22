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
from openclaw.enrich.osint_bridge import OsintProvider
from openclaw.enrich.owner import PublicRecordProvider
from openclaw.enrich.skip_trace import SkipTraceProvider

logger = logging.getLogger(__name__)

_provider_last_call_at: dict[str, float] = defaultdict(float)


def _build_providers() -> list[EnrichmentProvider]:
    providers: list[EnrichmentProvider] = [PublicRecordProvider(), SkipTraceProvider(), OsintProvider()]
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


def _owner_name_for_lead(lead: Lead) -> str | None:
    parcel = lead.candidate.parcel if lead.candidate else None
    owner_snapshot = lead.owner_snapshot or {}
    return (
        (lead.candidate.owner_name_canonical if lead.candidate else None)
        or owner_snapshot.get("name")
        or (parcel.owner_name if parcel else None)
    )


def _enrichment_expiry() -> datetime:
    return datetime.utcnow() + timedelta(days=max(1, int(settings.ENRICHMENT_RETENTION_DAYS)))


def _find_owner_dedup_lead(session, lead: Lead) -> Lead | None:
    owner_name = _owner_name_for_lead(lead)
    if not owner_name:
        return None

    return (
        session.query(Lead)
        .join(Candidate, Candidate.id == Lead.candidate_id)
        .filter(Candidate.owner_name_canonical == owner_name)
        .filter(Lead.id != lead.id)
        .filter(Lead.osint_investigation_id.isnot(None))
        .order_by(Lead.osint_queried_at.desc(), Lead.updated_at.desc())
        .first()
    )


def _map_osint_status_to_enrichment(status: str | None) -> str:
    if status == "complete":
        return "success"
    if status == "partial":
        return "partial"
    return "failed"


def _osint_to_enrichment_payload(result: dict) -> dict:
    osint_status = result.get("status")
    return {
        "status": _map_osint_status_to_enrichment(osint_status),
        "data": {
            "investigation_id": result.get("investigation_id"),
            "summary": result.get("summary"),
            "results": result.get("results") or {},
            "osint_status": osint_status,
        },
        "confidence": 1.0 if osint_status == "complete" else (0.6 if osint_status == "partial" else 0.0),
        "error_message": result.get("summary") if osint_status == "failed" else None,
    }


async def _run_osint_investigation(session, lead: Lead, provider: OsintProvider) -> dict:
    dedup_lead = _find_owner_dedup_lead(session, lead)
    if dedup_lead:
        result = {
            "investigation_id": dedup_lead.osint_investigation_id,
            "status": "complete",
            "summary": dedup_lead.osint_summary or "Reused existing owner investigation",
            "results": {"dedup_reused": True, "source_lead_id": str(dedup_lead.id)},
        }
        logger.info(
            "osint.dedup_hit",
            extra={
                "lead_id": str(lead.id),
                "owner_name": _owner_name_for_lead(lead),
                "source_lead_id": str(dedup_lead.id),
                "investigation_id": dedup_lead.osint_investigation_id,
            },
        )
    else:
        parcel = lead.candidate.parcel if lead.candidate else None
        score_tier_obj = lead.candidate.score_tier if lead.candidate else None
        score_tier = score_tier_obj.value if hasattr(score_tier_obj, "value") else str(score_tier_obj or "unknown")
        parcel_id = parcel.parcel_id if parcel and parcel.parcel_id else str(lead.candidate_id)

        result = await provider.create_investigation(
            owner_name=_owner_name_for_lead(lead) or "",
            parcel_id=parcel_id,
            score_tier=score_tier,
            address=(parcel.address if parcel else None) or (lead.owner_snapshot or {}).get("mailing_address"),
            email=lead.owner_email,
            phone=lead.owner_phone,
        )

    if result.get("investigation_id") is not None:
        lead.osint_investigation_id = result.get("investigation_id")
    lead.osint_status = result.get("status")
    lead.osint_summary = result.get("summary")
    lead.osint_queried_at = datetime.utcnow()

    return result


def _add_enrichment_row(session, lead: Lead, provider: EnrichmentProvider, payload: dict) -> None:
    row = EnrichmentResult(
        lead_id=lead.id,
        provider=provider.name,
        status=payload.get("status", "failed"),
        data=payload.get("data") or {},
        confidence=payload.get("confidence"),
        source_class=_to_source_class(getattr(provider, "source_class", EnrichmentSourceClassEnum.public_record)),
        fetched_at=datetime.utcnow(),
        expires_at=_enrichment_expiry(),
        error_message=payload.get("error_message"),
    )
    session.add(row)


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
            provider_retries = 0 if provider.name == "osint" else max_retries
            interval = 60.0 / max(1, int(provider.rate_limit_per_min))
            elapsed = time.time() - _provider_last_call_at[provider.name]
            if elapsed < interval:
                time.sleep(interval - elapsed)

            started = time.perf_counter()
            result_payload: dict | None = None
            error_message = None
            while retry <= provider_retries:
                try:
                    if provider.name == "osint":
                        osint_result = asyncio.run(_run_osint_investigation(session, lead, provider))
                        result_payload = _osint_to_enrichment_payload(osint_result)
                    else:
                        result_payload = asyncio.run(provider.enrich(lead))
                    break
                except Exception as exc:
                    error_message = str(exc)
                    retry += 1
                    if retry > provider_retries:
                        break
                    backoff = min(30, 2 ** (retry - 1))
                    logger.warning(
                        "enrichment.retry",
                        extra={
                            "lead_id": str(lead.id),
                            "provider": provider.name,
                            "retry": retry,
                            "max_retries": provider_retries,
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
            _add_enrichment_row(session, lead, provider, payload)
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


def run_lead_osint(lead_id: str, triggered_by: int | None = None, require_health: bool = False) -> dict:
    if not settings.OSINT_ENABLED:
        return {"ok": False, "error": "OSINT is disabled"}

    session = SessionLocal()
    try:
        lead = (
            session.query(Lead)
            .options(joinedload(Lead.candidate).joinedload(Candidate.parcel))
            .filter(Lead.id == lead_id)
            .first()
        )
        if not lead:
            return {"ok": False, "error": "not found"}

        provider = OsintProvider()
        if not provider.is_configured():
            return {"ok": False, "error": "OSINT provider not configured"}

        if require_health and not asyncio.run(provider.check_health()):
            return {"ok": False, "error": "OSINT platform unavailable"}

        started = time.perf_counter()
        result = asyncio.run(_run_osint_investigation(session, lead, provider))
        payload = _osint_to_enrichment_payload(result)
        _add_enrichment_row(session, lead, provider, payload)
        session.add(lead)
        session.commit()

        logger.info(
            "osint.manual",
            extra={
                "lead_id": str(lead.id),
                "status": result.get("status"),
                "duration_ms": int((time.perf_counter() - started) * 1000),
                "triggered_by": triggered_by,
            },
        )

        return {
            "ok": True,
            "lead_id": str(lead.id),
            "investigation_id": lead.osint_investigation_id,
            "status": lead.osint_status,
            "summary": lead.osint_summary,
            "queried_at": lead.osint_queried_at.isoformat() if lead.osint_queried_at else None,
        }
    except Exception:
        session.rollback()
        logger.exception("osint.manual_error", extra={"lead_id": lead_id, "triggered_by": triggered_by})
        return {"ok": False, "error": "OSINT execution failed"}
    finally:
        session.close()


def run_osint_batch_backfill() -> dict:
    if not settings.OSINT_ENABLED or not settings.OSINT_BATCH_ENABLED:
        return {"ok": True, "skipped": "disabled", "processed": 0}

    provider = OsintProvider()
    if not provider.is_configured():
        return {"ok": True, "skipped": "not_configured", "processed": 0}

    if not asyncio.run(provider.check_health()):
        logger.warning("osint.batch.skipped.health_down")
        return {"ok": True, "skipped": "health_down", "processed": 0}

    session = SessionLocal()
    processed = 0
    try:
        batch_limit = max(1, int(settings.OSINT_BATCH_LIMIT))
        leads = (
            session.query(Lead)
            .join(Candidate, Candidate.id == Lead.candidate_id)
            .options(joinedload(Lead.candidate).joinedload(Candidate.parcel))
            .filter(Lead.osint_status.is_(None))
            .order_by(Candidate.score.desc(), Lead.created_at.asc())
            .limit(batch_limit)
            .all()
        )

        for lead in leads:
            try:
                result = asyncio.run(_run_osint_investigation(session, lead, provider))
                payload = _osint_to_enrichment_payload(result)
                _add_enrichment_row(session, lead, provider, payload)
                session.add(lead)
                session.commit()
                processed += 1
            except Exception:
                session.rollback()
                logger.exception("osint.batch.lead_error", extra={"lead_id": str(lead.id)})

        logger.info("osint.batch.completed", extra={"processed": processed, "requested": len(leads)})
        return {"ok": True, "processed": processed, "requested": len(leads)}
    finally:
        session.close()
