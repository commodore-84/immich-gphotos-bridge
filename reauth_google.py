#!/usr/bin/env python3
"""
Re-authentication script -- use this INSTEAD of setup_google_auth.py when
you just need a fresh refresh token (e.g. the old one expired because it
was issued while the app was still in "Testing" status). This does NOT
create a new album; it reuses the existing album_id from your current
auth_state.json.

Run this on a machine with a browser, logged in as the recipient's
Google account -- same as the original setup.

Requires: pip install google-auth-oauthlib google-auth
"""

import json
import sys
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/photoslibrary.appendonly"]
CLIENT_SECRETS_FILE = "client_secret.json"
EXISTING_AUTH_STATE_FILE = "auth_state.json"  # the one with the expired token

def main():
    try:
        with open(EXISTING_AUTH_STATE_FILE) as f:
            existing_state = json.load(f)
    except FileNotFoundError:
        print(f"ERROR: {EXISTING_AUTH_STATE_FILE} not found. If you don't have "
              "an existing album_id to preserve, use setup_google_auth.py instead.")
        sys.exit(1)

    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, SCOPES)
    creds = flow.run_local_server(port=0)

    if not creds.refresh_token:
        print("ERROR: No refresh token returned. Revoke prior access at "
              "https://myaccount.google.com/permissions and re-run this script.")
        sys.exit(1)

    new_state = {
        "refresh_token": creds.refresh_token,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "album_id": existing_state["album_id"],       # reuse, don't recreate
        "album_title": existing_state["album_title"],
    }

    with open(EXISTING_AUTH_STATE_FILE, "w") as f:
        json.dump(new_state, f, indent=2)

    print("\nSuccess. Refresh token renewed.")
    print(f"Existing album preserved: '{new_state['album_title']}' "
          f"(id: {new_state['album_id']})")
    print(f"Updated {EXISTING_AUTH_STATE_FILE} -- copy it back to the sync "
          "server, replacing the old one.")

if __name__ == "__main__":
    main()