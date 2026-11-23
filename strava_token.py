import json
import time

import requests


def load_token(token_file):
    with open(token_file) as file:
        return json.load(file)


def save_token(token_file, data):
    with open(token_file, "w") as file:
        json.dump(data, file)


def refresh_access_token(token_data, client_id, client_secret, token_file, token_url):
    if not client_id or not client_secret:
        raise ValueError(
            "CLIENT_ID and CLIENT_SECRET must be set in fetch-strava-activities/.env."
        )

    print("🔄 Refreshing access token...")
    response = requests.post(token_url, data={
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "refresh_token",
        "refresh_token": token_data["refresh_token"]
    })

    if response.status_code != 200:
        raise Exception(f"Failed to refresh token: {response.text}")

    new_data = response.json()
    token_data.update({
        "access_token": new_data["access_token"],
        "refresh_token": new_data["refresh_token"],
        "expires_at": new_data["expires_at"]
    })
    save_token(token_file, token_data)
    print("✅ Access token refreshed.")
    return token_data


def get_valid_access_token(token_file, client_id, client_secret, token_url):
    token_data = load_token(token_file)
    if time.time() > token_data["expires_at"]:
        token_data = refresh_access_token(
            token_data,
            client_id,
            client_secret,
            token_file,
            token_url,
        )
    return token_data["access_token"]