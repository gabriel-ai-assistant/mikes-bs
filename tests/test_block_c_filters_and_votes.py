from starlette.requests import Request

from openclaw.web.routers.candidates import _parse_candidate_filters
from openclaw.web.routers.scoring import _extract_actor, _vote_note_with_meta


def _request(query: str) -> Request:
    return Request({
        "type": "http",
        "method": "GET",
        "path": "/api/candidates",
        "query_string": query.encode("utf-8"),
        "headers": [],
        "client": ("127.0.0.1", 9000),
        "scheme": "http",
    })


def test_parse_candidate_filters_legacy_backcompat_mapping():
    req = _request(
        "q=foo&tier=A&use_type=Single+Family&tags=EDGE_A,RISK_B&tags_mode=all"
        "&score_min=20&score_max=80&offset=100&limit=25&has_bundle=1"
    )
    f = _parse_candidate_filters(req)

    assert f["q"] == "foo"
    assert f["tiers"] == ["A"]
    assert f["use_types"] == ["Single Family"]
    assert f["tags_any"] == ["EDGE_A", "RISK_B"]
    assert f["tags_mode"] == "all"
    assert f["score_min"] == 20.0
    assert f["score_max"] == 80.0
    assert f["limit"] == 25
    assert f["page"] == 5
    assert f["offset"] == 100
    assert f["has_bundle"] is True


def test_parse_candidate_filters_unified_lists():
    req = _request(
        "tiers=A&tiers=B&use_types=Type1&use_types=Type2&tags_any=EDGE_A&tags_none=RISK_X"
        "&vote=up&page=2&limit=50&lead_status=researching&has_bundle=0"
    )
    f = _parse_candidate_filters(req)

    assert f["tiers"] == ["A", "B"]
    assert f["use_types"] == ["Type1", "Type2"]
    assert f["tags_any"] == ["EDGE_A"]
    assert f["tags_none"] == ["RISK_X"]
    assert f["vote"] == "up"
    assert f["page"] == 2
    assert f["offset"] == 50
    assert f["lead_status"] == "researching"
    assert f["has_bundle"] is False


def test_vote_note_round_trip_extracts_actor():
    note = _vote_note_with_meta("user:42", "optional note")
    assert _extract_actor(note) == "user:42"


def test_vote_note_extract_ignores_non_vote_notes():
    assert _extract_actor("plain note") is None
