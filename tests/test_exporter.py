import csv
import datetime as dt
import sys
from pathlib import Path
from typing import Any, Dict
from unittest import mock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tournament_exporter import ChallongeExporter, load_api_key


def _make_response(payload: Any) -> mock.Mock:
    response = mock.Mock()
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


def test_fetch_tournaments_filters_by_year_and_paginates(monkeypatch: pytest.MonkeyPatch) -> None:
    page_one_payload = {
        "data": [
            {
                "id": "1",
                "attributes": {
                    "name": "2024 Event",
                    "started_at": "2024-03-01T12:00:00Z",
                    "created_at": "2024-02-01T10:00:00Z",
                    "participants_count": 16,
                    "full_challonge_url": "https://challonge.com/2024-event",
                },
            },
            {
                "id": "2",
                "attributes": {
                    "name": "2023 Event",
                    "started_at": "2023-01-01T12:00:00Z",
                },
            },
        ],
        "links": {
            "next": "https://api.challonge.com/v2/communities/123/tournaments?page=2"
        },
        "meta": {"current_page": 1, "total_pages": 2},
    }
    page_two_payload = {
        "data": [
            {
                "id": "3",
                "attributes": {
                    "name": "2024 Event 2",
                    "started_at": "2024-06-01T12:00:00Z",
                },
                "relationships": {"participants": {"count": 8}},
            }
        ],
        "links": {},
        "meta": {"current_page": 2, "total_pages": 2},
    }

    calls: Dict[int, mock.Mock] = {
        1: _make_response(page_one_payload),
        2: _make_response(page_two_payload),
    }

    def fake_get(url: str, params: Dict[str, Any], timeout: int) -> mock.Mock:
        assert url.startswith("https://api.challonge.com/v2/communities/123/tournaments")
        assert params["api_key"] == "secret"
        page_number = params.get("page", 1)
        assert page_number in calls
        return calls[page_number]

    monkeypatch.setattr("requests.get", fake_get)

    exporter = ChallongeExporter(
        api_key="secret", community="fabco", community_id="123", year=2024
    )
    tournaments = exporter.fetch_tournaments()

    assert len(tournaments) == 2
    assert tournaments[0]["id"] == "1"
    assert tournaments[0]["participants_count"] == 16
    assert tournaments[1]["id"] == "3"
    assert tournaments[1]["participants_count"] == 8


def test_write_csv_includes_expected_headers(tmp_path: Path) -> None:
    exporter = ChallongeExporter(
        api_key="secret", community="fabco", community_id="123", year=2024
    )
    tournaments = [
        {
            "id": 1,
            "name": "Sample",
            "url": "sample",
            "full_challonge_url": "https://challonge.com/sample",
            "state": "complete",
            "game_name": "Game",
            "participants_count": 4,
            "created_at": "2024-01-01T00:00:00Z",
            "started_at": "2024-01-02T00:00:00Z",
            "completed_at": "2024-01-03T00:00:00Z",
        }
    ]
    output = tmp_path / "out.csv"

    exporter.write_csv(tournaments, output_path=str(output))

    with output.open(newline="", encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)
        assert reader.fieldnames == [
            "id",
            "name",
            "url",
            "full_challonge_url",
            "state",
            "game_name",
            "participants_count",
            "created_at",
            "started_at",
            "completed_at",
        ]
        rows = list(reader)
        assert rows[0]["name"] == "Sample"


def test_parse_date_handles_missing_timezone() -> None:
    exporter = ChallongeExporter(
        api_key="secret", community="fabco", community_id="123", year=2024
    )
    parsed = exporter._parse_date("2024-05-01T10:00:00")
    assert isinstance(parsed, dt.datetime)
    assert parsed.year == 2024


def test_load_api_key_prefers_env_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("CHALLONGE_API_KEY=from_env_file\n", encoding="utf-8")
    monkeypatch.delenv("CHALLONGE_API_KEY", raising=False)

    api_key = load_api_key(env_file=str(env_file))

    assert api_key == "from_env_file"
