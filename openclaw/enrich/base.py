"""Base abstraction for lead enrichment providers."""

from __future__ import annotations

from abc import ABC, abstractmethod

from openclaw.db.models import Lead


class EnrichmentProvider(ABC):
    name: str = "base"
    enabled: bool = False
    rate_limit_per_min: int = 60

    @abstractmethod
    async def enrich(self, lead: Lead) -> dict:
        """Return a provider payload with status/data/confidence/error_message keys."""

    def is_configured(self) -> bool:
        return bool(self.enabled)
