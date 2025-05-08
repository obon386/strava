import requests
import time
import json
import os
import csv
from datetime import datetime, timedelta
from pymongo import MongoClient

# === Config ===
CLIENT_ID = "157084"
CLIENT_SECRET = "6a5522f6229dbddc14e1255b5ff1c64d8e5bf63e"
REFRESH_TOKEN_FILE = "tokens.json"  # file to store tokens
STRAVA_TOKEN_URL = "https://www.strava.com/api/v3/oauth/token"
STRAVA_ACTIVITIES_URL = "https://www.strava.com/api/v3/athlete/activities"
OUTPUT_CSV_FILE = "result.csv"
MONGO_URI = "mongodb://localhost:27017/"
MONGO_DB = "sport_acties"
MONGO_COLLECTION = "acties"

AFTER = int(time.mktime(datetime(2025, 1, 1).timetuple()))
BEFORE = int(time.mktime(datetime(2025, 1, 7).timetuple()))


# === Helper functions ===

def load_tokens():
    if os.path.exists(REFRESH_TOKEN_FILE):
        with open(REFRESH_TOKEN_FILE, 'r') as f:
            return json.load(f)
    else:
        raise Exception(f"Missing {REFRESH_TOKEN_FILE}. Please authorize and save initial refresh_token.")

def save_tokens(tokens):
    with open(REFRESH_TOKEN_FILE, 'w') as f:
        json.dump(tokens, f)

def refresh_access_token(refresh_token):
    print("Refreshing access token...")
    response = requests.post(STRAVA_TOKEN_URL, data={
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token
    })
    response.raise_for_status()
    tokens = response.json()
    save_tokens({
        'access_token': tokens['access_token'],
        'refresh_token': tokens['refresh_token'],
        'expires_at': tokens['expires_at']
    })
    return tokens['access_token']

def get_access_token():
    tokens = load_tokens()
    if time.time() > tokens['expires_at']:
        # Access token expired, refresh it
        access_token = refresh_access_token(tokens['refresh_token'])
    else:
        # Access token still valid
        access_token = tokens['access_token']
    return access_token

def get_valid_access_token():
    token_data = load_token()
    if time.time() > token_data["expires_at"]:
        token_data = refresh_access_token(token_data)
    return token_data["access_token"]

def fetch_all_activities(access_token):
    headers = {'Authorization': f'Bearer {access_token}'}
    all_activities = []
    page = 1

    while True:
        print(f"Fetching page {page}...")
        params = {
            'after': AFTER,
            'before': BEFORE,
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

def save_activities_to_csv(activities):
    with open(OUTPUT_CSV_FILE, mode='w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerow(['Name', 'Start Date', 'Distance (km)', 'Moving Time (hours:minutes)'])

        for activity in activities:
            print(activity)

            start_date = datetime.strptime(activity['start_date_local'], "%Y-%m-%dT%H:%M:%SZ")
            formatted_start_date = start_date.strftime("%Y-%m-%d %H:%M")

            moving_time_seconds = activity['moving_time']
            hours = moving_time_seconds // 3600
            minutes = (moving_time_seconds % 3600) // 60
            formatted_moving_time = f"{int(hours)}h {int(minutes)}m"

            distance_km = activity['distance'] / 1000

            writer.writerow([
                activity['name'],
                formatted_start_date,
                f"{distance_km:.2f}",
                formatted_moving_time
            ])
    print(f"Saved {len(activities)} activities to {OUTPUT_CSV_FILE}")

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
        "ascent": activity.get("total_elevation_gain", 0),
        "descent": 0
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

# === Main ===

def main():
    access_token = get_access_token()
    activities = fetch_all_activities(access_token)
    print(f"Fetched {len(activities)} activities.")
    save_activities_to_csv(activities)
    save_activities_to_mongodb(activities)


if __name__ == "__main__":
    main()