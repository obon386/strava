"""
Script to update strava_id in sport_acties.acties collection
by matching start_time to sport.activities Aktivitätsdatum.

Matches acties.start_time (format: "YYYY-MM-DD HH:MM:SS.0")
to activities.Aktivitätsdatum (format: "DD-MM-YYYY, hh:mm:ss")
by date only (ignoring hour differences) and validates sport types match.
"""

import os
from pymongo import MongoClient
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from this project directory.
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

# === Config ===
MONGO_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/")
MONGO_DB = os.getenv("MONGO_DB", "sport_acties")
MONGO_COLLECTION = os.getenv("MONGO_COLLECTION", "acties")


def parse_aktivitaetsdatum_to_date(aktivitaetsdatum_str):
    """
    Parse Aktivitätsdatum string in format "DD-MM-YYYY, hh:mm:ss"
    and return date only in format "YYYY-MM-DD"
    """
    try:
        # Parse "DD-MM-YYYY, hh:mm:ss"
        dt = datetime.strptime(aktivitaetsdatum_str, "%d-%m-%Y, %H:%M:%S")
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        return None


def parse_start_time_to_date(start_time_str):
    """
    Parse start_time string in format "YYYY-MM-DD HH:MM:SS.0"
    and return date only in format "YYYY-MM-DD"
    """
    try:
        # Extract date part (before the space)
        date_part = start_time_str.split(' ')[0]
        return date_part
    except Exception:
        return None


def update_strava_ids_from_activities():
    """
    Iterates over all activities in sport_acties.acties collection,
    matches start_time (by date only) to activities.Aktivitätsdatum,
    validates that sport types match (Aktivitätsart vs sport),
    and updates the strava_id field.
    """
    client = MongoClient(MONGO_URI)
    sport_acties_db = client[MONGO_DB]
    acties_collection = sport_acties_db[MONGO_COLLECTION]
    
    sport_db = client["sport"]
    activities_collection = sport_db["activities"]
    
    updated_count = 0
    skipped_count = 0
    not_found_count = 0
    sport_mismatch_count = 0
    
    # Get all activities from sport.activities for lookup
    print("Loading activities from sport.activities...")
    all_sport_activities = list(activities_collection.find({}))
    print(f"Loaded {len(all_sport_activities)} activities from sport.activities")
    
    # Create a mapping of date to list of activities (for potential duplicates)
    date_to_activities = {}
    for activity in all_sport_activities:
        aktivitaetsdatum = activity.get("Aktivitätsdatum")
        if aktivitaetsdatum:
            normalized_date = parse_aktivitaetsdatum_to_date(aktivitaetsdatum)
            if normalized_date:
                if normalized_date not in date_to_activities:
                    date_to_activities[normalized_date] = []
                date_to_activities[normalized_date].append(activity)
    
    print(f"Created mapping with {len(date_to_activities)} unique dates\n")
    
    # Iterate over all activities in sport_acties.acties
    acties = acties_collection.find({})
    
    for acty in acties:
        start_time = acty.get("start_time")
        acty_sport = acty.get("sport")
        
        if not start_time:
            print(f"  Skipping activity (no start_time): {acty.get('_id')}")
            skipped_count += 1
            continue
        
        if not acty_sport:
            print(f"  Skipping activity (no sport type): {acty.get('_id')}")
            skipped_count += 1
            continue
        
        # Parse start_time to date only
        normalized_date = parse_start_time_to_date(start_time)
        
        if not normalized_date:
            print(f"  Skipping activity (invalid start_time): {acty.get('_id')}")
            skipped_count += 1
            continue
        
        # Look up activities by date
        matching_activities = date_to_activities.get(normalized_date, [])
        
        if not matching_activities:
            print(f"  No matching activity found for date: {normalized_date}")
            not_found_count += 1
            continue
        
        # Find best match: look for one with matching sport type
        matched_activity = None
        for sport_activity in matching_activities:
            aktivitaetsart = sport_activity.get("Aktivitätsart", "").upper()
            if aktivitaetsart == acty_sport:
                matched_activity = sport_activity
                break
        
        # If no exact sport match, use first one (with warning)
        if not matched_activity:
            print(f"  WARNING: No sport type match for {normalized_date} (acties.sport={acty_sport})")
            for sport_activity in matching_activities:
                aktivitaetsart = sport_activity.get("Aktivitätsart", "").upper()
                print(f"    Available: Aktivitätsart={aktivitaetsart}, strava_id={sport_activity.get('strava_id')}")
            sport_mismatch_count += 1
            # Use first available if you want to force update anyway
            # matched_activity = matching_activities[0]
            continue
        
        strava_id = matched_activity.get("strava_id")
        
        if not strava_id:
            print(f"  No strava_id found in sport.activities for date: {normalized_date}")
            not_found_count += 1
            continue
        
        # Update the activity in sport_acties.acties with strava_id
        result = acties_collection.update_one(
            {"_id": acty["_id"]},
            {"$set": {"strava_id": strava_id}}
        )
        
        if result.modified_count > 0:
            print(f"  Updated activity {acty.get('_id')} with strava_id: {strava_id} (date: {normalized_date})")
            updated_count += 1
        else:
            print(f"  Failed to update activity {acty.get('_id')}")
    
    print(f"\nUpdate complete:")
    print(f"  Updated: {updated_count}")
    print(f"  Skipped: {skipped_count}")
    print(f"  Not found: {not_found_count}")
    print(f"  Sport mismatch (not updated): {sport_mismatch_count}")
    client.close()


if __name__ == "__main__":
    print("Starting strava_id update by matching start_time to Aktivitätsdatum...")
    update_strava_ids_from_activities()
    print("Done!")
