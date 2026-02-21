"""Tests for openclaw.discovery.engine.run_discovery.

All tests mock the database (SessionLocal) to avoid requiring a real DB connection.
"""
import json
import os
import uuid
from unittest.mock import MagicMock, patch

import pytest

from openclaw.discovery.engine import run_discovery


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_row(**overrides):
    """Return a minimal candidate+parcel row dict for mocking."""
    base = {
        'candidate_id': str(uuid.uuid4()),
        'parcel_id': str(uuid.uuid4()),
        'score': 70.0,
        'score_tier': 'B',
        'tags': ['EDGE_SNOCO_LSA_R5_RD_FR'],
        'uga_outside': True,
        'potential_splits': 3,
        'has_critical_area_overlap': False,
        'reason_codes': ['LSA_ELIGIBLE'],
        'address': '123 Test Rd',
        'county': 'snohomish',
        'zone_code': 'R-5',
        'lot_sf': 522720.0,
        'owner_name': 'Test Owner',
        'assessed_value': 400000,
        'improvement_value': 50000,
        'total_value': 450000,
        'last_sale_date': None,
        'last_sale_price': None,
    }
    base.update(overrides)
    return base


def _mock_session(rows):
    """Build a mock SQLAlchemy session that returns the given rows."""
    session = MagicMock()
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = [
        dict(r) for r in rows
    ]
    session.execute.return_value = mock_result
    session.commit.return_value = None
    session.rollback.return_value = None
    session.close.return_value = None
    return session


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestDiscoveryOutputKeys:
    """run_discovery output must always contain the required top-level keys."""

    def test_discovery_output_has_required_keys(self):
        session = _mock_session([])
        result = run_discovery(session=session)

        required_keys = {'run_id', 'run_date', 'assumptions_version', 'county', 'total_analyzed', 'tier_a', 'tier_b'}
        assert required_keys.issubset(result.keys()), (
            f"Missing keys: {required_keys - set(result.keys())}"
        )

    def test_discovery_total_analyzed_zero_for_empty_db(self):
        session = _mock_session([])
        result = run_discovery(session=session)
        assert result['total_analyzed'] == 0
        assert result['tier_a'] == []
        assert result['tier_b'] == []


class TestDiscoveryTopN:
    """top_n_a / top_n_b limits must be respected."""

    def test_discovery_top_n_a_respected(self):
        rows = [_make_row(score=90.0, score_tier='A') for _ in range(50)]
        session = _mock_session(rows)
        result = run_discovery(top_n_a=5, session=session)
        assert len(result['tier_a']) <= 5

    def test_discovery_top_n_b_respected(self):
        rows = [_make_row(score=75.0, score_tier='B') for _ in range(100)]
        session = _mock_session(rows)
        result = run_discovery(top_n_b=10, session=session)
        assert len(result['tier_b']) <= 10


class TestDiscoverySorting:
    """Tier-A results must be sorted by edge_score descending."""

    def test_discovery_tier_a_sorted_descending(self):
        scores = [95.0, 88.0, 91.0, 86.0, 87.0]
        rows = [_make_row(score=s, score_tier='A') for s in scores]
        session = _mock_session(rows)
        result = run_discovery(top_n_a=10, session=session)

        edge_scores = [r['edge_score'] for r in result['tier_a']]
        assert edge_scores == sorted(edge_scores, reverse=True), (
            f"Tier-A not sorted descending: {edge_scores}"
        )

    def test_discovery_tier_b_sorted_descending(self):
        scores = [79.0, 72.0, 77.0, 70.5]
        rows = [_make_row(score=s, score_tier='B') for s in scores]
        session = _mock_session(rows)
        result = run_discovery(top_n_b=10, session=session)

        edge_scores = [r['edge_score'] for r in result['tier_b']]
        assert edge_scores == sorted(edge_scores, reverse=True), (
            f"Tier-B not sorted descending: {edge_scores}"
        )


class TestDiscoveryRunId:
    """run_id must be a valid UUID4."""

    def test_discovery_run_id_is_valid_uuid(self):
        session = _mock_session([])
        result = run_discovery(session=session)
        # Should not raise
        parsed = uuid.UUID(result['run_id'])
        assert str(parsed) == result['run_id']

    def test_discovery_run_id_unique_per_run(self):
        session1 = _mock_session([])
        session2 = _mock_session([])
        r1 = run_discovery(session=session1)
        r2 = run_discovery(session=session2)
        assert r1['run_id'] != r2['run_id']


class TestDiscoveryJsonArtifact:
    """json_out parameter must produce a valid JSON file."""

    def test_discovery_json_artifact_written(self, tmp_path):
        out_path = str(tmp_path / 'test_discovery_output.json')
        rows = [_make_row(score=85.0, score_tier='A')]
        session = _mock_session(rows)

        run_discovery(json_out=out_path, session=session)

        assert os.path.exists(out_path), f"JSON artifact not written to {out_path}"
        with open(out_path) as f:
            data = json.loads(f.read())
        assert 'run_id' in data
        assert 'tier_a' in data
        assert 'tier_b' in data

    def test_discovery_json_artifact_fixed_path(self):
        """Test with the literal path from the spec."""
        out_path = '/tmp/test_discovery_output.json'
        rows = [_make_row(score=85.0, score_tier='A')]
        session = _mock_session(rows)

        run_discovery(json_out=out_path, session=session)

        assert os.path.exists(out_path), f"JSON artifact not written to {out_path}"
        with open(out_path) as f:
            data = json.loads(f.read())
        assert isinstance(data, dict)


class TestDiscoveryCountyFilter:
    """county parameter is correctly forwarded."""

    def test_discovery_county_in_output(self):
        session = _mock_session([])
        result = run_discovery(county='snohomish', session=session)
        assert result['county'] == 'snohomish'

    def test_discovery_no_county_is_none(self):
        session = _mock_session([])
        result = run_discovery(session=session)
        assert result['county'] is None


class TestDiscoveryAssumptionsVersion:
    """assumptions_version is preserved in output."""

    def test_discovery_assumptions_version_in_output(self):
        session = _mock_session([])
        result = run_discovery(assumptions_version='v2', session=session)
        assert result['assumptions_version'] == 'v2'


class TestDiscoveryCandidateShape:
    """Each candidate in tier_a/tier_b must have required fields."""

    REQUIRED_CANDIDATE_KEYS = {
        'candidate_id', 'parcel_id', 'address', 'county',
        'edge_score', 'tier', 'tags', 'top_reasons', 'dif_components'
    }

    def test_tier_a_candidate_has_required_keys(self):
        rows = [_make_row(score=90.0, score_tier='A')]
        session = _mock_session(rows)
        result = run_discovery(session=session)

        if result['tier_a']:
            candidate = result['tier_a'][0]
            assert self.REQUIRED_CANDIDATE_KEYS.issubset(candidate.keys()), (
                f"Missing candidate keys: {self.REQUIRED_CANDIDATE_KEYS - set(candidate.keys())}"
            )

    def test_tier_b_candidate_has_required_keys(self):
        rows = [_make_row(score=75.0, score_tier='B')]
        session = _mock_session(rows)
        result = run_discovery(session=session)

        if result['tier_b']:
            candidate = result['tier_b'][0]
            assert self.REQUIRED_CANDIDATE_KEYS.issubset(candidate.keys())
