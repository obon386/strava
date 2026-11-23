"""
Script to update strava_id in sport_acties.acties collection
by matching start_time to CSV data from result_csv/result_2014-01-01_to_2026-10-30.csv

Matches acties.start_time (format: "YYYY-MM-DD HH:MM:SS.0")
to CSV "Start Date" (format: "YYYY-MM-DD HH:MM") using only the first 16 characters.
"""

import csv
import os
from pymongo import MongoClient
from dotenv import load_dotenv

# Load environment variables from this project directory.
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

# === Config ===
MONGO_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/")
MONGO_DB = os.getenv("MONGO_DB", "sport_acties")
MONGO_COLLECTION = os.getenv("MONGO_COLLECTION", "acties")
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_FILE = os.path.join(SCRIPT_DIR, "results_csv", "result_2014-01-01_to_2026-10-30.csv")


def normalize_start_time_to_datetime(start_time_str):
    """
    Normalize start_time string in format "YYYY-MM-DD HH:MM:SS.0"
    to "YYYY-MM-DD HH:MM" (first 16 characters)
    """
    try:
        # Extract first 16 characters: "YYYY-MM-DD HH:MM"
        return start_time_str[:16]
    except Exception:
        return None


def load_csv_data(csv_file):
    """
    Load CSV data and create a mapping of datetime to Activity ID.
    CSV format: 'Activity ID', 'Name', 'Start Date', 'Distance (km)', 'Moving Time (hours:minutes)'
    """
    datetime_to_activity_id = {}
    
    if not os.path.exists(csv_file):
        print(f"ERROR: CSV file not found: {csv_file}")
        return None
    
    print(f"Loading CSV data from: {csv_file}")
    
    try:
        with open(csv_file, mode='r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            row_count = 0
            
            for row in reader:
                activity_id = row.get('Activity ID')
                start_date = row.get('Start Date')
                
                if activity_id and start_date:
                    # Start Date is already in format "YYYY-MM-DD HH:MM"
                    datetime_key = start_date[:16]
                    datetime_to_activity_id[datetime_key] = int(activity_id)
                    row_count += 1
            
            print(f"Loaded {row_count} activities from CSV")
            return datetime_to_activity_id
    except Exception as e:
        print(f"ERROR reading CSV file: {e}")
        return None


def update_strava_ids_from_csv():
    """
    Iterates over all activities in sport_acties.acties collection,
    matches start_time (YYYY-MM-DD HH:MM) to CSV data,
    and updates the strava_id field.
    """
    # Load CSV data
    datetime_to_activity_id = load_csv_data(CSV_FILE)
    if datetime_to_activity_id is None:
        print("Failed to load CSV data. Aborting.")
        return
    
    print(f"Created mapping with {len(datetime_to_activity_id)} entries\n")
    
    client = MongoClient(MONGO_URI)
    sport_acties_db = client[MONGO_DB]
    acties_collection = sport_acties_db[MONGO_COLLECTION]
    
    updated_count = 0
    skipped_count = 0
    not_found_count = 0
    
    # Iterate over all activities in sport_acties.acties
    print("Processing activities from MongoDB...")
    acties = acties_collection.find({})
    
    for acty in acties:
        start_time = acty.get("start_time")
        
        if not start_time:
            print(f"  Skipping activity (no start_time): {acty.get('_id')}")
            skipped_count += 1
            continue
        
        # Normalize start_time to "YYYY-MM-DD HH:MM"
        normalized_datetime = normalize_start_time_to_datetime(start_time)
        
        if not normalized_datetime:
            print(f"  Skipping activity (invalid start_time): {acty.get('_id')}")
            skipped_count += 1
            continue
        
        # Look up Activity ID in CSV by datetime
        activity_id = datetime_to_activity_id.get(normalized_datetime)
        
        if not activity_id:
            print(f"  No matching activity found in CSV for: {normalized_datetime}")
            not_found_count += 1
            continue
        
        # Update the activity in sport_acties.acties with strava_id
        result = acties_collection.update_one(
            {"_id": acty["_id"]},
            {"$set": {"strava_id": activity_id}}
        )
        
        if result.modified_count > 0:
            print(f"  Updated activity {acty.get('_id')} with strava_id: {activity_id} (datetime: {normalized_datetime})")
            updated_count += 1
        else:
            print(f"  Failed to update activity {acty.get('_id')}")
    
    print(f"\nUpdate complete:")
    print(f"  Updated: {updated_count}")
    print(f"  Skipped: {skipped_count}")
    print(f"  Not found: {not_found_count}")
    client.close()


if __name__ == "__main__":
    print("Starting strava_id update from CSV file...")
    update_strava_ids_from_csv()
    print("Done!")
