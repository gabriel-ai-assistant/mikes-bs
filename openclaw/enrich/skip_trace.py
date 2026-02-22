"""Skip-trace enrichment provider stub."""

from __future__ import annotations

from openclaw.config import settings
from openclaw.db.models import EnrichmentSourceClassEnum, Lead
from openclaw.enrich.base import EnrichmentProvider


class SkipTraceProvider(EnrichmentProvider):
    name = "skip_trace"
    enabled = bool(settings.SKIP_TRACE_ENABLED)
    rate_limit_per_min = max(1, int(settings.SKIP_TRACE_RATE_LIMIT_PER_MIN))
    source_class = EnrichmentSourceClassEnum.commercial_api

    def is_configured(self) -> bool:
        return bool(self.enabled and settings.SKIP_TRACE_API_KEY)

    async def enrich(self, lead: Lead) -> dict:
        # Placeholder while external API integration is pending.
        data = {
            "phones": [lead.owner_phone] if lead.owner_phone else [],
            "emails": [lead.owner_email] if lead.owner_email else [],
            "source": "batch_skip_tracing_stub",
        }
        if data["phones"] or data["emails"]:
            status = "partial"
            confidence = 0.4
        else:
            status = "failed"
            confidence = 0.0
        return {
            "status": status,
            "data": data,
            "confidence": confidence,
            "error_message": "Skip trace API integration pending" if status == "failed" else "Stub response",
        }
