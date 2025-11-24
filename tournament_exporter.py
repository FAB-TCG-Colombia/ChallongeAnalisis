"""Download Challonge tournaments for a given community and year into CSV."""
from __future__ import annotations
import argparse
import csv
import datetime as dt
import os
import time
from typing import Dict, Iterable, List, Optional

try:  # pragma: no cover - exercised indirectly in tests
    import requests
    if not hasattr(requests, "HTTPError") and hasattr(requests, "exceptions"):
        requests.HTTPError = requests.exceptions.HTTPError  # type: ignore[attr-defined]
except ModuleNotFoundError:  # pragma: no cover
    import json
    import urllib.parse
    import urllib.request
    from types import SimpleNamespace

    class _FallbackResponse:
        def __init__(self, status_code: int, text: str) -> None:
            self.status_code = status_code
            self.text = text

        def json(self) -> object:
            return json.loads(self.text)

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise _FallbackHTTPError(response=self)

    class _FallbackHTTPError(Exception):
        def __init__(self, response: _FallbackResponse):
            super().__init__("HTTP error")
            self.response = response
            self.status_code = response.status_code

    def _fallback_get(url: str, params: Dict[str, object], timeout: int):
        if params:
            query = urllib.parse.urlencode(params)
            separator = "&" if "?" in url else "?"
            url = f"{url}{separator}{query}"
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            content = resp.read().decode("utf-8")
            status = getattr(resp, "status", 200)
            return _FallbackResponse(status_code=status, text=content)

    requests = SimpleNamespace(  # type: ignore
        get=_fallback_get,
        HTTPError=_FallbackHTTPError,
        Response=_FallbackResponse,
        exceptions=SimpleNamespace(HTTPError=_FallbackHTTPError),
    )

try:  # pragma: no cover - dependency may be missing in minimal environments
    from dotenv import load_dotenv
except ModuleNotFoundError:  # pragma: no cover
    def load_dotenv(path: str) -> None:
        return None


BASE_URL = "https://api.challonge.com/v2"
DEFAULT_COMMUNITY = "fabco"
DEFAULT_TIMEOUT = 30
DEFAULT_PER_PAGE = 200


class ChallongeExporter:
    """Helper to fetch and save tournaments from Challonge."""

    def __init__(
        self, api_key: str, community: str, community_id: str, year: int
    ) -> None:
        self.api_key = api_key
        self.community = community
        self.community_id = community_id
        self.year = year

    def fetch_tournaments(self) -> List[Dict[str, Optional[str]]]:
        """Fetch tournaments for the configured community and year.

        Returns a list of tournament dictionaries already filtered by year.
        """

        results: List[Dict[str, Optional[str]]] = []
        url = f"{BASE_URL}/communities/{self.community_id}/tournaments"
        page = 1
        params = {
            "api_key": self.api_key,
            "state": "all",
            "per_page": DEFAULT_PER_PAGE,
        }

        while url:
            params["page"] = page
            response = self._get_with_retry(url, params=params)
            payload = response.json()

            data = payload.get("data", []) or []
            for entry in data:
                attributes = self._extract_attributes(entry)
                if not attributes or not self._is_in_year(attributes):
                    continue
                results.append(self._normalize_tournament(attributes))

            next_page = self._next_page(payload, current_page=page)
            if next_page:
                page = next_page
            else:
                break

        return results

    def _extract_attributes(self, entry: Dict[str, object]) -> Dict[str, Optional[str]]:
        attributes = dict(entry.get("attributes", {}) or {})
        attributes.setdefault("id", entry.get("id"))
        self._merge_timestamps(attributes)

        relationships = entry.get("relationships", {}) or {}

        participants = relationships.get("participants", {}) or {}
        if not attributes.get("participants_count"):
            meta = participants.get("meta", {}) if isinstance(participants, dict) else {}
            if not meta and isinstance(participants, dict):
                links = participants.get("links", {}) or {}
                meta = links.get("meta", {})
            attributes["participants_count"] = (
                participants.get("count")
                if isinstance(participants, dict)
                else None
            ) or (meta.get("count") if isinstance(meta, dict) else None)

        return attributes

    def _is_in_year(self, tournament: Dict[str, Optional[str]]) -> bool:
        date_fields = ["started_at", "created_at"]
        for field in date_fields:
            raw_date = tournament.get(field)
            if not raw_date:
                continue
            parsed = self._parse_date(raw_date)
            if parsed and parsed.year == self.year:
                return True
        return False

    def _parse_date(self, raw_date: str) -> Optional[dt.datetime]:
        try:
            sanitized = raw_date.replace("Z", "+00:00")
            return dt.datetime.fromisoformat(sanitized)
        except ValueError:
            return None

    def _next_page(self, payload: Dict[str, object], current_page: int) -> Optional[int]:
        links = payload.get("links", {}) or {}
        meta = payload.get("meta", {}) or {}
        meta_current = meta.get("current_page", current_page)

        next_page = meta.get("next_page") or (meta_current + 1 if links.get("next") else None)
        total_pages = meta.get("total_pages")

        if next_page and (not total_pages or next_page <= total_pages):
            return next_page

        return None

    def _get_with_retry(
        self, url: str, params: Dict[str, object], max_attempts: int = 3
    ) -> requests.Response:
        http_error = getattr(requests, "HTTPError", None)
        http_error = http_error or getattr(getattr(requests, "exceptions", None), "HTTPError", None)
        last_error: Optional[Exception] = None
        for attempt in range(1, max_attempts + 1):
            response = requests.get(url, params=params, timeout=DEFAULT_TIMEOUT)
            try:
                response.raise_for_status()
                return response
            except Exception as exc:  # pragma: no cover - exercised via tests
                if http_error and not isinstance(exc, http_error):
                    raise
                last_error = exc
                status = response.status_code
                if status and 500 <= status < 600 and attempt < max_attempts:
                    time.sleep(min(2 ** (attempt - 1), 5))
                    continue
                raise

        if last_error:
            raise last_error
        raise requests.HTTPError("Unknown error while fetching tournaments")

    def _merge_timestamps(self, attributes: Dict[str, Optional[str]]) -> None:
        timestamps = attributes.get("timestamps")
        if not isinstance(timestamps, dict):
            return

        for key in ("created_at", "started_at", "completed_at", "starts_at"):
            if not attributes.get(key) and timestamps.get(key):
                attributes[key] = timestamps[key]

    def _normalize_tournament(self, tournament: Dict[str, Optional[str]]) -> Dict[str, Optional[str]]:
        return {
            "id": tournament.get("id"),
            "name": tournament.get("name"),
            "url": tournament.get("url"),
            "full_challonge_url": tournament.get("full_challonge_url"),
            "state": tournament.get("state"),
            "game_name": tournament.get("game_name"),
            "participants_count": tournament.get("participants_count"),
            "created_at": tournament.get("created_at"),
            "started_at": tournament.get("started_at"),
            "completed_at": tournament.get("completed_at"),
        }

    def write_csv(self, tournaments: Iterable[Dict[str, Optional[str]]], output_path: str) -> None:
        fieldnames = [
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
        with open(output_path, "w", newline="", encoding="utf-8") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for tournament in tournaments:
                writer.writerow(tournament)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Download Challonge tournaments for a community and year and export to CSV. "
            f"Defaults to community '{DEFAULT_COMMUNITY}'."
        )
    )
    parser.add_argument(
        "--env-file",
        default=".env",
        help="Optional path to an environment file containing CHALLONGE_API_KEY.",
    )
    parser.add_argument(
        "--community",
        "-c",
        default=DEFAULT_COMMUNITY,
        help="Challonge community subdomain to fetch tournaments for.",
    )
    parser.add_argument(
        "--community-id",
        "-i",
        default=None,
        help=(
            "Challonge community identifier for the v2 API. Falls back to "
            "CHALLONGE_COMMUNITY_ID environment variable if unset."
        ),
    )
    parser.add_argument(
        "--year",
        "-y",
        type=int,
        default=dt.date.today().year,
        help="Year to filter tournaments by (based on start or creation date).",
    )
    parser.add_argument(
        "--output",
        "-o",
        default=None,
        help="Path to write CSV output (defaults to tournaments_<community>_<year>.csv)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    api_key = load_api_key(args.env_file)

    community_id = args.community_id or os.getenv("CHALLONGE_COMMUNITY_ID")
    if not community_id:
        raise SystemExit(
            "CHALLONGE_COMMUNITY_ID is required. Provide --community-id or set it in the env."
        )

    output_path = args.output or f"tournaments_{args.community}_{args.year}.csv"
    exporter = ChallongeExporter(
        api_key=api_key,
        community=args.community,
        community_id=community_id,
        year=args.year,
    )

    tournaments = exporter.fetch_tournaments()
    exporter.write_csv(tournaments, output_path)
    print(f"Exported {len(tournaments)} tournaments to {output_path}")


def load_api_key(env_file: str = ".env") -> str:
    """Load the Challonge API key from the environment or a .env file."""

    if env_file:
        load_dotenv(env_file)
        if not os.getenv("CHALLONGE_API_KEY") and os.path.exists(env_file):
            api_key_from_file = _read_key_from_file(env_file)
            if api_key_from_file:
                os.environ["CHALLONGE_API_KEY"] = api_key_from_file

    api_key = os.getenv("CHALLONGE_API_KEY")
    if not api_key:
        raise SystemExit(
            "CHALLONGE_API_KEY is required. Set it in the environment or the provided env file."
        )
    return api_key


def _read_key_from_file(env_file: str) -> Optional[str]:
    """Lightweight parser to extract CHALLONGE_API_KEY when dotenv is unavailable."""

    try:
        with open(env_file, encoding="utf-8") as handle:
            for line in handle:
                if line.strip().startswith("CHALLONGE_API_KEY"):
                    _, _, value = line.partition("=")
                    return value.strip().strip('"').strip("'")
    except OSError:
        return None
    return None


if __name__ == "__main__":
    main()
