from __future__ import annotations

import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from openclaw.enrich.osint_bridge import OsintProvider
from openclaw.enrich import pipeline


def _mk_lead(owner: str = "John Doe", lead_id: str = "lead-1"):
    parcel = SimpleNamespace(parcel_id="P-123", address="1 Main", owner_name=owner)
    candidate = SimpleNamespace(owner_name_canonical=owner, score_tier="A", parcel=parcel)
    lead = SimpleNamespace(
        id=lead_id,
        candidate_id="cand-1",
        candidate=candidate,
        owner_snapshot={"name": owner, "mailing_address": "PO Box"},
        owner_email=None,
        owner_phone=None,
        osint_investigation_id=None,
        osint_status=None,
        osint_summary=None,
        osint_queried_at=None,
    )
    return lead


def test_is_entity_detection():
    provider = OsintProvider()
    assert provider.is_entity("ACME LLC")
    assert provider.is_entity("NORTHWEST INC")
    assert provider.is_entity("SMITH CORP")
    assert not provider.is_entity("Jane Mary Doe")


def test_build_summary_variants():
    provider = OsintProvider()

    summary = provider._build_summary(
        {
            "emails_found": ["a@example.com", "b@example.com"],
            "social_profiles": [{"site": "x"}],
            "company_data": {"ein": "12"},
            "phone_data": {"line_type": "mobile"},
        }
    )
    assert "Emails: 2" in summary
    assert "Social: 1 profiles" in summary
    assert "Company records found" in summary
    assert "Phone intel found" in summary

    assert provider._build_summary({}) == "No significant findings"


def test_owner_dedup_reuses_investigation_id():
    first_lead = SimpleNamespace(id="lead-0", osint_investigation_id=222, osint_summary="Known intel")
    second_lead = _mk_lead(owner="Shared Owner LLC", lead_id="lead-2")
    provider = MagicMock()
    provider.create_investigation = AsyncMock()

    with patch("openclaw.enrich.pipeline._find_owner_dedup_lead", return_value=first_lead):
        result = asyncio.run(pipeline._run_osint_investigation(MagicMock(), second_lead, provider))

    assert result["investigation_id"] == 222
    assert result["status"] == "complete"
    assert second_lead.osint_investigation_id == 222
    assert second_lead.osint_status == "complete"
    assert second_lead.osint_summary == "Known intel"
    assert isinstance(second_lead.osint_queried_at, datetime)
    provider.create_investigation.assert_not_called()


def test_timeout_returns_failed_status():
    provider = OsintProvider()
    lead = _mk_lead(owner="Timeout Owner")

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value.post.side_effect = httpx.TimeoutException("slow")

    with patch("openclaw.enrich.osint_bridge.httpx.AsyncClient", return_value=mock_client):
        result = asyncio.run(
            provider.create_investigation(
                owner_name="Timeout Owner",
                parcel_id="P-123",
                score_tier="A",
                address="1 Main",
            )
        )

    assert result["status"] == "failed"
    assert result["summary"] == "Timeout"

    osint_provider = MagicMock()
    osint_provider.create_investigation = AsyncMock(return_value=result)
    with patch("openclaw.enrich.pipeline._find_owner_dedup_lead", return_value=None):
        asyncio.run(pipeline._run_osint_investigation(MagicMock(), lead, osint_provider))
    assert lead.osint_status == "failed"


def test_batch_skips_when_health_down(monkeypatch):
    monkeypatch.setattr(pipeline.settings, "OSINT_ENABLED", True)
    monkeypatch.setattr(pipeline.settings, "OSINT_BATCH_ENABLED", True)

    provider = MagicMock()
    provider.is_configured.return_value = True
    provider.check_health = AsyncMock(return_value=False)

    with patch("openclaw.enrich.pipeline.OsintProvider", return_value=provider), patch(
        "openclaw.enrich.pipeline.SessionLocal"
    ) as session_local:
        result = pipeline.run_osint_batch_backfill()

    assert result["skipped"] == "health_down"
    assert result["processed"] == 0
    session_local.assert_not_called()
