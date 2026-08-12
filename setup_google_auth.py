#!/usr/bin/env python3
"""
ONE-TIME SETUP SCRIPT.

Run this on a machine with a web browser, while logged into the RECIPIENT's
Google account (Person B -- the one whose Google Photos library will
receive the synced photos) -- or ready to log into it when the browser tab
opens.

What it does:
  1. Walks through the OAuth consent flow -> gets a refresh token tied to
     his Google account with the photoslibrary.appendonly scope.
  2. Creates a NEW Google Photos album via the API (required -- the API
     can only add photos to albums it created itself, not ones made
     manually in the Google Photos app).
  3. Writes both the refresh token and the new album ID into auth_state.json.

Run this once. Copy the resulting auth_state.json to the Proxmox box
alongside sync_immich_to_gphotos.py.

Requires: pip install google-auth-oauthlib google-auth requests
"""

import json
import sys
import requests
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/photoslibrary.appendonly"]
CLIENT_SECRETS_FILE = "client_secret.json"  # downloaded from Google Cloud Console
ALBUM_TITLE = "Photos from Alex"  # <-- change to whatever you want him to see

def main():
    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, SCOPES)
    creds = flow.run_local_server(port=0)

    if not creds.refresh_token:
        print("ERROR: No refresh token returned. Revoke prior access at "
              "https://myaccount.google.com/permissions and re-run this script.")
        sys.exit(1)

    # Create the album via the API (must be app-created to allow writes later)
    resp = requests.post(
        "https://photoslibrary.googleapis.com/v1/albums",
        headers={
            "Authorization": f"Bearer {creds.token}",
            "Content-Type": "application/json",
        },
        json={"album": {"title": ALBUM_TITLE}},
    )
    resp.raise_for_status()
    album = resp.json()

    state = {
        "refresh_token": creds.refresh_token,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "album_id": album["id"],
        "album_title": ALBUM_TITLE,
    }

    with open("auth_state.json", "w") as f:
        json.dump(state, f, indent=2)

    print("\nSuccess.")
    print(f"Album created: '{ALBUM_TITLE}' (id: {album['id']})")
    print("Saved credentials + album id to auth_state.json")
    print("Copy auth_state.json to the Proxmox bridge alongside the sync script.")
    print("\nHave the recipient open Google Photos > Albums once to confirm they can see it.")

if __name__ == "__main__":
    main()