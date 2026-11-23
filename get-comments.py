
import argparse
import json
import os

import requests
from dotenv import load_dotenv

from strava_token import get_valid_access_token

# Load environment variables from this project directory.
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
TOKEN_FILE = "tokens.json"
STRAVA_TOKEN_URL = os.getenv("STRAVA_TOKEN_URL", "https://www.strava.com/api/v3/oauth/token")


def fetch_activity_comments(access_token, activity_id, dump_response=False):
    headers = {'Authorization': f'Bearer {access_token}'}
    page = 1
    response = requests.get(
        f"https://www.strava.com/api/v3/activities/{activity_id}/comments",
        headers=headers,
        params={'per_page': 200, 'page': page} #, 'after_cursor': ''}
    )
    print(f"  Fetched {response}")

    if dump_response:
        print(f"Status: {response.status_code} {response.reason}")
        print("Headers:")
        for key, value in response.headers.items():
            print(f"{key}: {value}")
        print("Body:")
        print(response.text)

    response.raise_for_status()
    return response.json()


def main():
    parser = argparse.ArgumentParser(description="Fetch Strava comments for a single activity.")
    parser.add_argument("activity_id", type=int, help="Strava activity ID")
    parser.add_argument(
        "--dump-response",
        action="store_true",
        help="Print full HTTP response status, headers, and raw body",
    )
    args = parser.parse_args()

    access_token = get_valid_access_token(
        str(TOKEN_FILE),
        CLIENT_ID,
        CLIENT_SECRET,
        STRAVA_TOKEN_URL,
    )
    comments = fetch_activity_comments(
        access_token,
        args.activity_id,
        dump_response=args.dump_response,
    )
    print(json.dumps(comments, indent=2))


if __name__ == "__main__":
    main()

