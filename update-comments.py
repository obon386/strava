import json
import os
import time
from datetime import datetime, timedelta, timezone

import requests
from pymongo import MongoClient
from dotenv import load_dotenv

from strava_token import get_valid_access_token

# Load environment variables from this project directory.
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
TOKEN_FILE = os.path.join(os.path.dirname(__file__), "tokens.json")
STRAVA_TOKEN_URL = os.getenv("STRAVA_TOKEN_URL", "https://www.strava.com/api/v3/oauth/token")

MONGO_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/")
MONGO_DB = os.getenv("MONGO_DB", "sport")
MONGO_ACTIVITIES_COLLECTION = os.getenv("MONGO_ACTIVITIES_COLLECTION", "activities")
MONGO_COMMENTS_COLLECTION = os.getenv("MONGO_COMMENTS_COLLECTION", "comments")

STATE_FILE = os.path.join(os.path.dirname(__file__), "comments_update_state.json")


COMMENTS_PER_PAGE = 200


def _parse_limit_pair(header_value):
    if not header_value:
        return None

    parts = [part.strip() for part in header_value.split(",")]
    if len(parts) != 2:
        return None

    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        return None


def _next_quarter_hour_utc(now_utc):
    next_minute = ((now_utc.minute // 15) + 1) * 15
    if next_minute == 60:
        return now_utc.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    return now_utc.replace(minute=next_minute, second=0, microsecond=0)


def _next_midnight_utc(now_utc):
    midnight = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight + timedelta(days=1)


def _format_rate_limit_details(response):
    headers = response.headers
    overall_limit = _parse_limit_pair(headers.get("X-RateLimit-Limit"))
    overall_usage = _parse_limit_pair(headers.get("X-RateLimit-Usage"))
    read_limit = _parse_limit_pair(headers.get("X-ReadRateLimit-Limit"))
    read_usage = _parse_limit_pair(headers.get("X-ReadRateLimit-Usage"))

    details = []
    if overall_limit and overall_usage:
        details.append(
            f"overall 15m {overall_usage[0]}/{overall_limit[0]}, daily {overall_usage[1]}/{overall_limit[1]}"
        )
    if read_limit and read_usage:
        details.append(
            f"read 15m {read_usage[0]}/{read_limit[0]}, daily {read_usage[1]}/{read_limit[1]}"
        )

    return "; ".join(details) if details else "rate-limit headers unavailable"


def _is_daily_read_limit_reached(response):
    headers = response.headers
    read_limit = _parse_limit_pair(headers.get("X-ReadRateLimit-Limit"))
    read_usage = _parse_limit_pair(headers.get("X-ReadRateLimit-Usage"))
    if read_limit and read_usage:
        return read_usage[1] >= read_limit[1]

    # Fallback when read-specific headers are unavailable.
    overall_limit = _parse_limit_pair(headers.get("X-RateLimit-Limit"))
    overall_usage = _parse_limit_pair(headers.get("X-RateLimit-Usage"))
    if overall_limit and overall_usage:
        return overall_usage[1] >= overall_limit[1]

    return False


def _seconds_until_next_quarter_hour_utc(now_utc):
    next_reset = _next_quarter_hour_utc(now_utc)
    # Add a small buffer to avoid firing at boundary-second race conditions.
    return max(1, int((next_reset - now_utc).total_seconds()) + 1)


def _raise_rate_limit_error(activity_id, response):
    now_utc = datetime.now(timezone.utc)
    next_15m_reset = _next_quarter_hour_utc(now_utc)
    next_daily_reset = _next_midnight_utc(now_utc)
    detail = _format_rate_limit_details(response)
    raise RuntimeError(
        "Strava rate limit reached while fetching comments for activity "
        f"{activity_id}. {detail}. "
        "Per Strava docs, 15-minute limits reset at :00/:15/:30/:45 UTC and daily limits reset at midnight UTC. "
        f"Next 15-minute reset: {next_15m_reset.isoformat()}, next daily reset: {next_daily_reset.isoformat()}."
    )


def _raise_daily_read_limit_error(activity_id, response):
    now_utc = datetime.now(timezone.utc)
    next_daily_reset = _next_midnight_utc(now_utc)
    detail = _format_rate_limit_details(response)
    raise RuntimeError(
        "Strava daily read limit reached while fetching comments for activity "
        f"{activity_id}. {detail}. "
        f"Daily read limits reset at midnight UTC. Next daily reset: {next_daily_reset.isoformat()}."
    )


def load_state():
    if not os.path.exists(STATE_FILE):
        return {}

    with open(STATE_FILE, "r", encoding="utf-8") as file:
        return json.load(file)


def save_state(last_attempted_activity_id):
    with open(STATE_FILE, "w", encoding="utf-8") as file:
        json.dump({"last_attempted_activity_id": last_attempted_activity_id}, file)


def clear_state():
    if os.path.exists(STATE_FILE):
        os.remove(STATE_FILE)


def fetch_activity_comments(access_token, activity_id):
    headers = {"Authorization": f"Bearer {access_token}"}
    comments = []
    page = 1

    while True:
        response = requests.get(
            f"https://www.strava.com/api/v3/activities/{activity_id}/comments",
            headers=headers,
            params={"page": page, "per_page": COMMENTS_PER_PAGE},
        )

        if response.status_code == 429:
            if _is_daily_read_limit_reached(response):
                _raise_daily_read_limit_error(activity_id, response)

            now_utc = datetime.now(timezone.utc)
            wait_seconds = _seconds_until_next_quarter_hour_utc(now_utc)
            print(
                "Activity "
                f"{activity_id}: 429 received ({_format_rate_limit_details(response)}). "
                f"Waiting {wait_seconds}s for next 15-minute reset, then retrying page {page}."
            )
            time.sleep(wait_seconds)
            continue

        response.raise_for_status()
        print(f"response: {response.status_code} \ntext: {response.json()}")
        print(f"Activity {activity_id}: {_format_rate_limit_details(response)}")

        batch = response.json()
        if not batch:
            break

        comments.extend(batch)

        # If we received less than a full page, this is the final page.
        if len(batch) < COMMENTS_PER_PAGE:
            break

        page += 1

    return comments


def get_activity_ids_missing_comments(activities_collection, comments_collection, start_from_activity_id=None):
    commented_activity_ids = set(comments_collection.distinct("activity_id"))
    activity_query = {"Activity ID": {"$exists": True}}
    if start_from_activity_id is not None:
        activity_query["Activity ID"]["$gte"] = start_from_activity_id

    cursor = activities_collection.find(
        activity_query,
        {"_id": 0, "Activity ID": 1, "Activity Date": 1},
    ).sort("Activity ID", 1)

    missing_activities = []
    for activity in cursor:
        activity_id = activity["Activity ID"]
        activity_date = activity.get("Activity Date")
        if activity_id not in commented_activity_ids:
            missing_activities.append({
                "activity_id": activity_id,
                "activity_date": activity_date,
            })

    return missing_activities


def upsert_comments(comments_collection, activity_id, comments):
    inserted_or_updated = 0
    for comment in comments:
        comment["activity_id"] = activity_id
        comments_collection.update_one(
            {"id": comment["id"]},
            {"$set": comment},
            upsert=True,
        )
        inserted_or_updated += 1

    return inserted_or_updated


def main():
    state = load_state()
    start_from_activity_id = state.get("last_attempted_activity_id")
    if start_from_activity_id is not None:
        start_from_activity_id = int(start_from_activity_id)
    if start_from_activity_id is not None:
        print(f"Resuming from last attempted activity ID: {start_from_activity_id}")

    access_token = get_valid_access_token(
        TOKEN_FILE,
        CLIENT_ID,
        CLIENT_SECRET,
        STRAVA_TOKEN_URL,
    )

    client = MongoClient(MONGO_URI)
    db = client[MONGO_DB]
    activities_collection = db[MONGO_ACTIVITIES_COLLECTION]
    comments_collection = db[MONGO_COMMENTS_COLLECTION]

    missing_activities = get_activity_ids_missing_comments(
        activities_collection,
        comments_collection,
        start_from_activity_id=start_from_activity_id,
    )

    print(f"Found {len(missing_activities)} activities with no comments in DB.")

    processed = 0
    total_comments_written = 0
    current_activity_id = None
    current_activity_date = None
    try:
        for activity_record in missing_activities:
            activity_id = activity_record["activity_id"]
            activity_date = activity_record["activity_date"]
            current_activity_id = activity_id
            current_activity_date = activity_date
            print(f"Fetching comments for activity {activity_id} (Activity Date: {activity_date})...")
            comments = fetch_activity_comments(access_token, activity_id)
            written = upsert_comments(comments_collection, activity_id, comments)
            print(
                f"Activity {activity_id} (Activity Date: {activity_date}): "
                f"fetched {len(comments)} comment(s), wrote {written}."
            )
            processed += 1
            total_comments_written += written
            time.sleep(1)

        clear_state()
        print(
            f"Done. Processed {processed} activities and wrote {total_comments_written} comments. "
            "Resume state cleared."
        )
    except Exception as error:
        # Persist the failing activity ID so the next run can continue from it.
        if current_activity_id is not None:
            save_state(current_activity_id)
            print(
                f"Failed on activity {current_activity_id} (Activity Date: {current_activity_date}). "
                f"Saved resume state. Error: {error}"
            )
        else:
            print(f"Failed before processing activities. Error: {error}")
        raise


if __name__ == "__main__":
    main()