# Strava Activity Fetcher

Scripts in this directory fetch Strava activities and comments, export activity summaries to CSV, and read or write activity data in MongoDB.

## Setup

Use Python 3.9 or newer. From this directory, create a virtual environment and install dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Set `CLIENT_ID` and `CLIENT_SECRET` in `.env` using your Strava API application credentials. Adjust the MongoDB settings there if needed. The scripts load `.env` from this directory regardless of the current working directory. Do not commit `.env`.

The OAuth access and refresh tokens are stored in the local `tokens.json` file. `strava_token.py` refreshes the access token when it expires. This file is also excluded from Git.

## Fetch activities

Set the `AFTER` and `BEFORE` values near the top of `get-acties.py`, then run:

```powershell
python get-acties.py
```

The script writes CSV output under `results_csv` and stores activity and comment data in MongoDB.

## Fetch comments for one activity

```powershell
python get-comments.py 123456789
```

Add `--dump-response` to print the full HTTP response for troubleshooting.

## Backfill missing comments

```powershell
python update-comments.py
```

This script finds activities without comments and resumes from its saved state after an interrupted run.

## Other MongoDB utilities

- `update_activity_names.py` fills in activity names from the related database.
- `update_strava_ids.py` and `update_strava_ids_from_csv.py` match records and update Strava IDs.
- `start-mongo.sh` is a Git Bash helper; edit its MongoDB paths before use.

CSV exports, tokens, state files, logs, and temporary response files are local project data and are excluded from Git.
