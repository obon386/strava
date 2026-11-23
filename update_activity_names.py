"""
Script to update activity names in sport_acties.acties collection
by fetching them from sport.activities collection.
"""

import os
from pymongo import MongoClient
from dotenv import load_dotenv

# Load environment variables from this project directory.
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

# === Config ===
MONGO_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/")
MONGO_DB = os.getenv("MONGO_DB", "sport_acties")
MONGO_COLLECTION = os.getenv("MONGO_COLLECTION", "acties")


def update_activity_names_from_sport_db():
    """
    Iterates over all activities in sport_acties.acties collection,
    fetches the activity name from sport.activities collection,
    and updates the activity record with the activity name.
    """
    client = MongoClient(MONGO_URI)
    sport_acties_db = client[MONGO_DB]
    acties_collection = sport_acties_db[MONGO_COLLECTION]
    
    sport_db = client["sport"]
    activities_collection = sport_db["activities"]
    
    updated_count = 0
    skipped_count = 0
    
    # Iterate over all activities in sport_acties.acties
    activities = acties_collection.find({})
    
    for activity in activities:
        activity_id = activity.get("strava_id")
        
        if not activity_id:
            print(f"  Skipping activity (no strava_id): {activity.get('_id')}")
            skipped_count += 1
            continue
        
        # Fetch activity name from sport.activities collection
        sport_activity = activities_collection.find_one({"Aktivitäts-ID": activity_id})
        
        if not sport_activity:
            print(f"  Activity {activity_id} not found in sport.activities")
            skipped_count += 1
            continue
        
        activity_name = sport_activity.get("Name der Aktivität")
        
        if not activity_name:
            print(f"  Activity {activity_id} has no name in sport.activities")
            skipped_count += 1
            continue
        
        # Update the activity in sport_acties.acties with the name
        result = acties_collection.update_one(
            {"_id": activity["_id"]},
            {"$set": {"activity_name": activity_name}}
        )
        
        if result.modified_count > 0:
            print(f"  Updated activity {activity_id} with name: {activity_name}")
            updated_count += 1
        else:
            print(f"  Failed to update activity {activity_id}")
    
    print(f"\nUpdate complete: {updated_count} updated, {skipped_count} skipped")
    client.close()


if __name__ == "__main__":
    print("Starting activity name update...")
    update_activity_names_from_sport_db()
    print("Done!")
