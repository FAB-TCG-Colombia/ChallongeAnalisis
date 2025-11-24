"""Download Challonge tournaments for a given community and year into CSV."""
import argparse
import csv
import datetime as dt
import os
from typing import Dict, Iterable, List, Optional

import requests
from dotenv import load_dotenv


BASE_URL = "https://api.challonge.com/v1/tournaments.json"
DEFAULT_COMMUNITY = "fabco"
DEFAULT_TIMEOUT = 30


class ChallongeExporter:
    """Helper to fetch and save tournaments from Challonge."""

    def __init__(self, api_key: str, community: str, year: int) -> None:
        self.api_key = api_key
        self.community = community
        self.year = year

    def fetch_tournaments(self) -> List[Dict[str, Optional[str]]]:
        """Fetch tournaments for the configured community and year.

        Returns a list of tournament dictionaries already filtered by year.
        """

        page = 1
        results: List[Dict[str, Optional[str]]] = []
        params = {
            "api_key": self.api_key,
            "subdomain": self.community,
            "state": "all",
            "per_page": 200,
        }

        while True:
            params["page"] = page
            response = requests.get(BASE_URL, params=params, timeout=DEFAULT_TIMEOUT)
            response.raise_for_status()
            payload = response.json()

            if not payload:
                break

            for wrapped in payload:
                tournament = wrapped.get("tournament", {})
                if not self._is_in_year(tournament):
                    continue
                results.append(self._normalize_tournament(tournament))

            page += 1

        return results

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

    output_path = args.output or f"tournaments_{args.community}_{args.year}.csv"
    exporter = ChallongeExporter(api_key=api_key, community=args.community, year=args.year)

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
