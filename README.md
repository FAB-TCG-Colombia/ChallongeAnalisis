# FAB Colombia Challonge Analyzer

This project includes a simple exporter that downloads Challonge tournaments for a community and writes them to a structured CSV file. By default, it targets the `fabco` community.

## Setup
1. Create and activate a Python 3.11+ environment.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Provide your Challonge API key (found in your Challonge account settings) securely. You can either:
   - Create a `.env` file (copy from `.env.example`) and populate `CHALLONGE_API_KEY`.
   - Or export `CHALLONGE_API_KEY` in your shell.

## Usage
Run the exporter to download tournaments for a given year:
```bash
python tournament_exporter.py --year 2024 --community fabco --output fabco_2024.csv
```

You can point to a different env file if needed:

```bash
python tournament_exporter.py --env-file /secure/path/.env
```

Flags:
- `--community` / `-c`: Challonge community subdomain to query (defaults to `fabco`).
- `--year` / `-y`: Year to filter by (defaults to the current year).
- `--output` / `-o`: Path for the CSV file (defaults to `tournaments_<community>_<year>.csv`).

The CSV will include tournament metadata such as the Challonge URL, state, participant count, and timestamps.

## Testing
Run the unit suite with:

```bash
pytest
```
