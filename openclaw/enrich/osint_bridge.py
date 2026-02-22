"""Bridge to external OSINT platform (consumer-only integration)."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from openclaw.config import settings
from openclaw.db.models import EnrichmentSourceClassEnum, Lead
from openclaw.enrich.base import EnrichmentProvider

logger = logging.getLogger(__name__)

ENTITY_KEYWORDS = (
    "LLC",
    "INC",
    "CORP",
    "TRUST",
    "LTD",
    "LP",
    "PARTNERSHIP",
    "ESTATE",
    "ET AL",
    "ETAL",
)


class OsintProvider(EnrichmentProvider):
    """Consumer bridge for creating owner investigations via OSINT HTTP API."""

    name = "osint"
    enabled = bool(settings.OSINT_ENABLED)
    rate_limit_per_min = 1
    source_class = EnrichmentSourceClassEnum.osint

    def __init__(self) -> None:
        self.enabled = bool(settings.OSINT_ENABLED)
        self.base_url = (settings.OSINT_BASE_URL or "http://localhost:8450/api").strip().rstrip("/")
        self.timeout_seconds = max(5, int(settings.OSINT_TIMEOUT_SECONDS))

    def is_configured(self) -> bool:
        return bool(self.enabled and self.base_url)

    def is_entity(self, owner_name: str | None) -> bool:
        if not owner_name:
            return False
        upper = owner_name.upper()
        return any(keyword in upper for keyword in ENTITY_KEYWORDS)

    def _build_summary(self, results: dict[str, Any] | None) -> str:
        if not isinstance(results, dict) or not results:
            return "No significant findings"

        parts: list[str] = []

        emails = results.get("emails_found") or results.get("emails")
        if isinstance(emails, list) and emails:
            parts.append(f"Emails: {len(emails)}")

        social_profiles = results.get("social_profiles") or results.get("profiles")
        if isinstance(social_profiles, list) and social_profiles:
            parts.append(f"Social: {len(social_profiles)} profiles")

        company_data = results.get("company_data") or results.get("business_records")
        if company_data:
            parts.append("Company records found")

        phone_data = results.get("phone_data") or results.get("phones")
        if phone_data:
            parts.append("Phone intel found")

        return " | ".join(parts) if parts else "No significant findings"

    def _fail_result(self, reason: str) -> dict[str, Any]:
        return {
            "investigation_id": None,
            "status": "failed",
            "summary": reason,
            "results": {},
        }

    async def check_health(self) -> bool:
        if not self.is_configured():
            return False
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self.base_url}/health")
            if resp.status_code != 200:
                return False
            payload = resp.json()
            return payload.get("status") == "ok" if isinstance(payload, dict) else True
        except Exception:
            return False

    async def create_investigation(
        self,
        owner_name: str,
        parcel_id: str,
        score_tier: str,
        address: str | None = None,
        email: str | None = None,
        phone: str | None = None,
    ) -> dict[str, Any]:
        owner_name = (owner_name or "").strip()
        if not owner_name:
            return self._fail_result("Missing owner name")

        payload: dict[str, Any] = {
            "name": f"Owner: {owner_name} - Parcel {parcel_id}",
            "subject_name": owner_name,
            "notes": f"Auto-created by OpenClaw for parcel {parcel_id}, tier {score_tier}",
        }
        if address:
            payload["address"] = address
        if email:
            payload["email"] = email
        if phone:
            payload["phone"] = phone
        if self.is_entity(owner_name):
            payload["company"] = owner_name

        try:
            async with httpx.AsyncClient(timeout=float(self.timeout_seconds)) as client:
                resp = await client.post(f"{self.base_url}/investigations", json=payload)
                resp.raise_for_status()
            data = resp.json() if resp.content else {}
            if not isinstance(data, dict):
                data = {}

            results = data.get("results") if isinstance(data.get("results"), dict) else {}
            investigation_id = data.get("id")
            if not investigation_id:
                return self._fail_result("Missing investigation id")

            return {
                "investigation_id": investigation_id,
                "status": "complete" if results else "partial",
                "summary": self._build_summary(results),
                "results": results,
            }
        except httpx.TimeoutException:
            logger.warning("osint.timeout", extra={"owner_name": owner_name, "parcel_id": parcel_id})
            return self._fail_result("Timeout")
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code if exc.response is not None else "unknown"
            logger.error("osint.http_error", extra={"owner_name": owner_name, "status_code": status_code})
            return self._fail_result(f"HTTP {status_code}")
        except Exception as exc:
            logger.error("osint.unexpected_error", extra={"owner_name": owner_name, "error": str(exc)})
            return self._fail_result(str(exc))

    async def enrich(self, lead: Lead) -> dict[str, Any]:
        parcel = lead.candidate.parcel if lead.candidate else None
        owner_name = (
            (lead.candidate.owner_name_canonical if lead.candidate else None)
            or (lead.owner_snapshot or {}).get("name")
            or (parcel.owner_name if parcel else None)
            or ""
        )
        parcel_id = parcel.parcel_id if parcel and parcel.parcel_id else str(lead.candidate_id)
        score_tier_obj = lead.candidate.score_tier if lead.candidate else None
        score_tier = score_tier_obj.value if hasattr(score_tier_obj, "value") else str(score_tier_obj or "unknown")
        address = (parcel.address if parcel else None) or (lead.owner_snapshot or {}).get("mailing_address")

        result = await self.create_investigation(
            owner_name=owner_name,
            parcel_id=parcel_id,
            score_tier=score_tier,
            address=address,
            email=lead.owner_email,
            phone=lead.owner_phone,
        )

        status_map = {"complete": "success", "partial": "partial", "failed": "failed"}
        mapped_status = status_map.get(result.get("status"), "failed")
        confidence = 1.0 if result.get("status") == "complete" else (0.6 if result.get("status") == "partial" else 0.0)

        return {
            "status": mapped_status,
            "data": {
                "investigation_id": result.get("investigation_id"),
                "summary": result.get("summary"),
                "results": result.get("results") or {},
                "osint_status": result.get("status"),
            },
            "confidence": confidence,
            "error_message": result.get("summary") if result.get("status") == "failed" else None,
        }
