import requests
import time
import os
import csv
import sys
import argparse
from datetime import datetime, timedelta
from pymongo import MongoClient
from dotenv import load_dotenv

from strava_token import get_valid_access_token

# Load environment variables from this project directory.
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

# === Config ===
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
TOKEN_FILE = os.path.join(os.path.dirname(__file__), "tokens.json")
STRAVA_TOKEN_URL = os.getenv("STRAVA_TOKEN_URL", "https://www.strava.com/api/v3/oauth/token")
STRAVA_ACTIVITIES_URL = os.getenv("STRAVA_ACTIVITIES_URL", "https://www.strava.com/api/v3/athlete/activities")
# OUTPUT_CSV_FILE will be created from the AFTER and BEFORE date range below.
OUTPUT_CSV_DIR = os.path.join(os.path.dirname(__file__), "results_csv")
MONGO_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/")
MONGO_DB = os.getenv("MONGO_DB", "sport_acties")
MONGO_COLLECTION = os.getenv("MONGO_COLLECTION", "acties")
MONGO_COMMENTS_COLLECTION = os.getenv("MONGO_COMMENTS_COLLECTION", "comments")

AFTER = None
BEFORE = None

# Build an output filename that includes the BEFORE and AFTER dates
def get_output_filename(after, before):
    after_date_str = datetime.fromtimestamp(after).strftime('%Y-%m-%d')
    before_date_str = datetime.fromtimestamp(before).strftime('%Y-%m-%d')
    return os.path.join(
        OUTPUT_CSV_DIR,
        f"result_{after_date_str}_to_{before_date_str}.csv",
    )


# === Helper functions ===

def get_latest_activity_timestamp():
    """Get the timestamp of the latest activity from MongoDB."""
    try:
        client = MongoClient(MONGO_URI)
        db = client[MONGO_DB]
        collection = db[MONGO_COLLECTION]
        
        # Find the latest activity by start_time
        latest = collection.find_one(
            sort=[("start_time", -1)]
        )
        
        if latest and "start_time" in latest:
            # Parse the start_time string and convert to timestamp
            start_time_str = latest["start_time"]
            dt = datetime.strptime(start_time_str, "%Y-%m-%d %H:%M:%S.0")
            timestamp = int(time.mktime(dt.timetuple()))
            print(f"Found latest activity at {start_time_str} (timestamp: {timestamp})")
            return timestamp
        else:
            print("No activities found in MongoDB, using default AFTER date")
            return int(time.mktime(datetime(2014, 1, 1).timetuple()))
    except Exception as e:
        print(f"Error querying MongoDB: {e}")
        return int(time.mktime(datetime(2014, 1, 1).timetuple()))


def parse_command_line_args():
    """Parse command line arguments for AFTER and BEFORE dates."""
    parser = argparse.ArgumentParser(
        description="Fetch Strava activities within a date range and save to MongoDB and CSV."
    )
    parser.add_argument(
        "--after",
        type=str,
        help="Start date in YYYY-MM-DD format or Unix timestamp. If not specified, uses latest activity from DB."
    )
    parser.add_argument(
        "--before",
        type=str,
        help="End date in YYYY-MM-DD format or Unix timestamp. Defaults to now if not specified."
    )
    
    args = parser.parse_args()
    return args


def parse_date_or_timestamp(value):
    """Convert a date string (YYYY-MM-DD) or timestamp to Unix timestamp."""
    try:
        # Try parsing as Unix timestamp first
        timestamp = int(value)
        return timestamp
    except ValueError:
        pass
    
    try:
        # Try parsing as YYYY-MM-DD format
        dt = datetime.strptime(value, "%Y-%m-%d")
        return int(time.mktime(dt.timetuple()))
    except ValueError:
        raise ValueError(f"Invalid date format: {value}. Use YYYY-MM-DD or Unix timestamp.")


def fetch_all_activities(access_token, after, before):
    headers = {'Authorization': f'Bearer {access_token}'}
    all_activities = []
    page = 1

    while True:
        print(f"Fetching page {page}...")
        params = {
            'after': after,
            'before': before,
            'page': page,
            'per_page': 100  # max allowed by Strava
        }
        response = requests.get(STRAVA_ACTIVITIES_URL, headers=headers, params=params)
        response.raise_for_status()
        activities = response.json()
        if not activities:
            break
        all_activities.extend(activities)
        page += 1

    return all_activities

def save_activities_to_csv(activities, after, before):
    output_csv_file = get_output_filename(after, before)
    os.makedirs(OUTPUT_CSV_DIR, exist_ok=True)    
    with open(output_csv_file, mode='w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerow(['Activity ID', 'Name', 'Start Date', 'Distance (km)', 'Moving Time (hours:minutes)'])

        for activity in activities:
            print(activity)

            start_date = datetime.strptime(activity['start_date_local'], "%Y-%m" \
            "-%dT%H:%M:%SZ")
            formatted_start_date = start_date.strftime("%Y-%m-%d %H:%M")

            moving_time_seconds = activity['moving_time']
            hours = moving_time_seconds // 3600
            minutes = (moving_time_seconds % 3600) // 60
            formatted_moving_time = f"{int(hours)}h {int(minutes)}m"

            distance_km = activity['distance'] / 1000

            writer.writerow([
                activity['id'],
                activity['name'],
                formatted_start_date,
                f"{distance_km:.2f}",
                formatted_moving_time
            ])
    print(f"Saved {len(activities)} activities to {output_csv_file}")

def format_pace(pace_min_per_km):
    if pace_min_per_km is None:
        return None
    minutes = int(pace_min_per_km)
    seconds = int(round((pace_min_per_km - minutes) * 60))
    return f"{minutes}:{seconds:02d}"

def convert_strava_to_custom_format(activity):
    start = datetime.strptime(activity['start_date_local'], "%Y-%m-%dT%H:%M:%SZ")
    end = start + timedelta(seconds=activity.get('moving_time', 0))

    avg_speed_kmh = activity.get("average_speed", 0.0) * 3.6 if "average_speed" in activity else None
    max_speed_kmh = activity.get("max_speed", 0.0) * 3.6 if "max_speed" in activity else None

    pace_avg = round(60 / avg_speed_kmh, 2) if avg_speed_kmh and avg_speed_kmh > 0 else None
    pace_max = round(60 / max_speed_kmh, 2) if max_speed_kmh and max_speed_kmh > 0 else None

    return {
        "sport": activity.get("sport_type", "UNKNOWN").upper(),
        "start_time": start.strftime("%Y-%m-%d %H:%M:%S.0"),
        "end_time": end.strftime("%Y-%m-%d %H:%M:%S.0"),
        "duration_s": float(activity.get("moving_time", 0)),
        "distance_km": activity.get("distance", 0.0) / 1000,
        "calories_kcal": activity.get("calories", 0),
        "altitude_min_m": activity.get("elev_low", None),
        "altitude_max_m": activity.get("elev_high", None),
        "heart_rate_avg_bpm": activity.get("average_heartrate", None),
        "heart_rate_max_bpm": activity.get("max_heartrate", None),
        "cadence_avg_rpm": activity.get("average_cadence", None),
        "cadence_max_rpm": activity.get("max_cadence", None),
        "speed_avg_kmh": avg_speed_kmh,
        "speed_max_kmh": max_speed_kmh,
        "pace_avg": pace_avg,
        "pace_max": pace_max,
        "pace_avg_str": format_pace(pace_avg),
        "pace_max_str": format_pace(pace_max),
        "ascent": activity.get("total_elevation_gain", 0),
        "strava_id": activity["id"]
    }

def save_activities_to_mongodb(activities):
    client = MongoClient(MONGO_URI)
    db = client[MONGO_DB]
    collection = db[MONGO_COLLECTION]

    inserted = 0
    for activity in activities:
        record = convert_strava_to_custom_format(activity)
        if not collection.find_one({"start_time": record["start_time"], "sport": record["sport"]}):
            collection.insert_one(record)
            inserted += 1

    print(f"Inserted {inserted} formatted records into MongoDB ({MONGO_DB}.{MONGO_COLLECTION})")

def fetch_activity_comments(access_token, activity_id):
    headers = {'Authorization': f'Bearer {access_token}'}
    comments = []
    page = 1
    for attempt in range(5):
        response = requests.get(
            f"https://www.strava.com/api/v3/activities/{activity_id}/comments",
            headers=headers,
            params={'page': page, 'per_page': 200}
        )
        if response.status_code == 429:
            wait = 30 * (attempt + 1)
            print(f"  Rate limited, waiting {wait}s...")
            time.sleep(wait)
        else:
            response.raise_for_status()
            break
    else:
        raise Exception(f"Rate limit exceeded after 5 retries for activity {activity_id}")

    batch = response.json()
    print(f"  Fetched {batch}")
    if batch:
        comments.extend(batch)
    return comments

def fetch_activity_commentsOLD(access_token, activity_id):
    headers = {'Authorization': f'Bearer {access_token}'}
    comments = []
    page = 1
    while True:
        for attempt in range(5):
            response = requests.get(
                f"https://www.strava.com/api/v3/activities/{activity_id}/comments",
                headers=headers,
                params={'page': page, 'per_page': 200}
            )
            if response.status_code == 429:
                wait = 15 * (attempt + 1)
                print(f"  Rate limited, waiting {wait}s...")
                time.sleep(wait)
            else:
                response.raise_for_status()
                break
        else:
            raise Exception(f"Rate limit exceeded after 5 retries for activity {activity_id}")
        batch = response.json()
        print(f"  Fetched {batch}")
        if batch:
            break
        page += 1
    return comments


def save_comments_to_mongodb(activities, access_token):
    client = MongoClient(MONGO_URI)
    db = client[MONGO_DB]
    collection = db[MONGO_COMMENTS_COLLECTION]

    inserted = 0
    for activity in activities:
        activity_id = activity["id"]
        comments = fetch_activity_comments(access_token, activity_id)
        for comment in comments:
            if not collection.find_one({"id": comment["id"]}):
                comment["activity_id"] = activity_id
                collection.insert_one(comment)
                inserted += 1
        if comments:
            print(f"  Activity {activity_id}: {len(comments)} comment(s)")
        time.sleep(1)

    print(f"Inserted {inserted} comments into MongoDB ({MONGO_DB}.{MONGO_COMMENTS_COLLECTION})")


# === Main ===

def main():
    args = parse_command_line_args()
    
    # Determine AFTER and BEFORE timestamps
    if args.before:
        before = parse_date_or_timestamp(args.before)
    else:
        before = int(time.time())
    
    if args.after:
        after = parse_date_or_timestamp(args.after)
    else:
        # If no AFTER specified, get the latest activity from MongoDB
        after = get_latest_activity_timestamp()
    
    print(f"Fetching activities from {datetime.fromtimestamp(after).strftime('%Y-%m-%d %H:%M:%S')} to {datetime.fromtimestamp(before).strftime('%Y-%m-%d %H:%M:%S')}")
    
    access_token = get_valid_access_token(
        TOKEN_FILE,
        CLIENT_ID,
        CLIENT_SECRET,
        STRAVA_TOKEN_URL,
    )
    activities = fetch_all_activities(access_token, after, before)
    print(f"Fetched {len(activities)} activities.")
    save_activities_to_csv(activities, after, before)
    save_activities_to_mongodb(activities)
    # print("Fetching activity comments...")
    # save_comments_to_mongodb(activities, access_token)


if __name__ == "__main__":
    main()