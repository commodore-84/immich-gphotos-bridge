#!/usr/bin/env python3
"""
Polls an Immich album for new assets and uploads any not-yet-synced ones
into a Google Photos album (owned by the recipient's account, created ahead of
time by setup_google_auth.py).

Run on a schedule (systemd timer) -- nightly or weekly is plenty for
~1 photo/week. Not designed to run continuously.

Env vars (see .env.example):
  IMMICH_URL, IMMICH_API_KEY, IMMICH_ALBUM_ID
  GOOGLE_AUTH_STATE_FILE   (path to auth_state.json from setup script)
  SYNCED_STATE_FILE        (path to track which asset ids are done)
  NTFY_URL                 (full topic URL, e.g. https://ntfy.yourdomain.com/immich2google)
  NTFY_TOKEN               (optional -- bearer token, if your ntfy topic
                             requires auth)
"""

import json
import os
import sys
import mimetypes
import requests
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

IMMICH_URL = os.environ["IMMICH_URL"].rstrip("/")
IMMICH_API_KEY = os.environ["IMMICH_API_KEY"]
IMMICH_ALBUM_ID = os.environ["IMMICH_ALBUM_ID"]
GOOGLE_AUTH_STATE_FILE = os.environ.get("GOOGLE_AUTH_STATE_FILE", "auth_state.json")
SYNCED_STATE_FILE = os.environ.get("SYNCED_STATE_FILE", "synced_assets.json")
NTFY_URL = os.environ.get("NTFY_URL")  # optional but recommended
NTFY_TOKEN = os.environ.get("NTFY_TOKEN")  # optional, only if your topic needs auth


def notify(message, priority="urgent", title="Immich -> Google Photos sync FAILED"):
    if not NTFY_URL:
        return
    headers = {"Title": title, "Priority": priority}
    if NTFY_TOKEN:
        headers["Authorization"] = f"Bearer {NTFY_TOKEN}"
    try:
        requests.post(
            NTFY_URL,
            data=message.encode("utf-8"),
            headers=headers,
            timeout=10,
        )
    except Exception:
        pass  # never let a notification failure crash the sync


def load_json(path, default):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default


def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def get_google_credentials(auth_state):
    creds = Credentials(
        token=None,
        refresh_token=auth_state["refresh_token"],
        client_id=auth_state["client_id"],
        client_secret=auth_state["client_secret"],
        token_uri="https://oauth2.googleapis.com/token",
    )
    creds.refresh(Request())
    return creds


def get_immich_album_assets():
    # Immich v3.0 removed the `assets` field from GET /api/albums/{id}.
    # The replacement is POST /api/search/metadata filtered by albumIds.
    resp = requests.post(
        f"{IMMICH_URL}/api/search/metadata",
        headers={"x-api-key": IMMICH_API_KEY, "Content-Type": "application/json"},
        json={"albumIds": [IMMICH_ALBUM_ID], "size": 1000},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["assets"]["items"]


def remove_from_immich_album(asset_id):
    resp = requests.delete(
        f"{IMMICH_URL}/api/albums/{IMMICH_ALBUM_ID}/assets",
        headers={"x-api-key": IMMICH_API_KEY, "Content-Type": "application/json"},
        json={"ids": [asset_id]},
        timeout=30,
    )
    resp.raise_for_status()


def download_immich_asset(asset_id):
    resp = requests.get(
        f"{IMMICH_URL}/api/assets/{asset_id}/original",
        headers={"x-api-key": IMMICH_API_KEY},
        timeout=120,
    )
    resp.raise_for_status()
    return resp.content


def upload_to_google(access_token, filename, content_bytes):
    mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    upload_resp = requests.post(
        "https://photoslibrary.googleapis.com/v1/uploads",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/octet-stream",
            "X-Goog-Upload-Content-Type": mime_type,
            "X-Goog-Upload-Protocol": "raw",
        },
        data=content_bytes,
        timeout=300,
    )
    upload_resp.raise_for_status()
    return upload_resp.text  # this is the upload token


def create_media_item(access_token, upload_token, description=""):
    """
    Creates the media item in the library, unfiled (no album). This never
    needs to know whether any particular album exists -- it always
    succeeds as long as the upload token is valid.
    """
    resp = requests.post(
        "https://photoslibrary.googleapis.com/v1/mediaItems:batchCreate",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json={
            "newMediaItems": [
                {
                    "description": description,
                    "simpleMediaItem": {"uploadToken": upload_token},
                }
            ],
        },
        timeout=60,
    )
    resp.raise_for_status()
    result = resp.json()["newMediaItemResults"][0]
    status = result["status"]
    if status.get("code") and status["code"] != 0:
        raise RuntimeError(f"Google rejected media item: {status}")
    return result["mediaItem"]["id"]


def add_to_album(access_token, album_id, media_item_id):
    """
    Adds an already-created media item to an album. Raises requests.HTTPError
    if the album doesn't exist -- this is the ONLY place we can detect a
    missing album, since the appendonly scope has no read/list access to
    verify albums exist ahead of time.
    """
    resp = requests.post(
        f"https://photoslibrary.googleapis.com/v1/albums/{album_id}:batchAddMediaItems",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json={"mediaItemIds": [media_item_id]},
        timeout=30,
    )
    resp.raise_for_status()


def create_album(access_token, title):
    resp = requests.post(
        "https://photoslibrary.googleapis.com/v1/albums",
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        json={"album": {"title": title}},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["id"]


def main():
    auth_state = load_json(GOOGLE_AUTH_STATE_FILE, None)
    if auth_state is None:
        raise RuntimeError(f"Missing {GOOGLE_AUTH_STATE_FILE} -- run setup_google_auth.py first")

    synced_ids = set(load_json(SYNCED_STATE_FILE, []))

    assets = get_immich_album_assets()
    new_assets = [a for a in assets if a["id"] not in synced_ids]

    if not new_assets:
        print("No new assets to sync.")
        return

    creds = get_google_credentials(auth_state)
    album_id = auth_state["album_id"]
    album_recreated_this_run = False

    uploaded = 0
    errors = []
    removal_warnings = []

    for asset in new_assets:
        asset_id = asset["id"]
        filename = asset.get("originalFileName", asset_id)
        try:
            content = download_immich_asset(asset_id)
            upload_token = upload_to_google(creds.token, filename, content)
            media_item_id = create_media_item(creds.token, upload_token)

            try:
                add_to_album(creds.token, album_id, media_item_id)
            except requests.exceptions.HTTPError:
                if album_recreated_this_run:
                    raise  # already tried recovering once this run, don't loop forever
                # Most likely cause: the album was deleted. Recreate it
                # (same title) and retry adding this one item. Not a
                # failure -- it self-healed -- but worth knowing about,
                # so it's pushed at low/default priority, not urgent.
                album_id = create_album(creds.token, auth_state["album_title"])
                auth_state["album_id"] = album_id
                save_json(GOOGLE_AUTH_STATE_FILE, auth_state)
                album_recreated_this_run = True
                notify(
                    f"Destination album '{auth_state['album_title']}' was "
                    f"missing -- recreated it automatically.",
                    priority="default",
                    title="Immich -> Google Photos sync: info",
                )
                add_to_album(creds.token, album_id, media_item_id)

            # Upload succeeded -- mark as synced immediately so a failed
            # removal below can never cause a duplicate upload later.
            synced_ids.add(asset_id)
            uploaded += 1
            save_json(SYNCED_STATE_FILE, sorted(synced_ids))

            try:
                remove_from_immich_album(asset_id)
            except Exception as re:
                # Not fatal: the photo made it to Google Photos fine, it'll
                # just linger visibly in the Immich album until you remove
                # it by hand (or the next successful run retries removal).
                removal_warnings.append(f"{filename}: uploaded ok, but couldn't "
                                         f"remove from Immich album ({re})")
        except Exception as e:
            errors.append(f"{filename}: {e}")

    if uploaded:
        print(f"Synced {uploaded} new photo(s).")
    if removal_warnings:
        msg = "Uploaded fine, but couldn't clean up the Immich album:\n" + "\n".join(removal_warnings)
        print(msg, file=sys.stderr)
        notify(msg, priority="default")
    if errors:
        msg = f"{len(errors)} photo(s) failed to sync:\n" + "\n".join(errors)
        print(msg, file=sys.stderr)
        notify(msg, priority="high")
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        notify(f"Sync script crashed: {e}", priority="urgent")
        raise