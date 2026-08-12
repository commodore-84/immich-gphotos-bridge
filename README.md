# Immich → Google Photos bridge

Selectively sync photos from a self-hosted [Immich](https://immich.app)
instance into a specific Google Photos account — without giving that
person Immich access, and without relying on Google's now-defunct
shared-album API.

**The general shape:** Person A self-hosts photos in Immich. Person B only
uses Google Photos and isn't going to change that. This lets Person A
curate an album of photos to share, and have it show up automatically in
Person B's Google Photos, with no manual step on Person B's side after a
one-time setup. (Person A and Person B can also be the same person, e.g.
syncing a curated Immich album into your own Google Photos as a backup
mirror.)

## How it works

```
[Immich album: "To Sync"]
        |
        |  nightly, via systemd timer
        v
[sync_immich_to_gphotos.py]  --downloads originals-->  [Google Photos album]
        |                                                (owned by Person B's
        |  removes synced asset from Immich album         Google account)
        v
[Immich album, now empty/caught-up]
```

The Immich album is the queue. A photo sitting in it hasn't synced yet.
Once synced, it's removed from the album (not deleted — just no longer a
member of that album). An empty album means fully caught up.

There is no live/webhook trigger — this polls on a schedule. At low
volume (photos added occasionally, not in bulk) a nightly run is more than
enough, and missing a scheduled run is a non-event; it just picks up
whatever's new on the next run.

## Why this approach, and not X

Some context on the constraints that shaped this design, useful if you're
adapting it:

- **Google killed programmatic album sharing in March 2025.** The
  Photos Library API's `albums.share` / `albums.join` endpoints now return
  403. An app cannot create an album and share it with another account via
  API anymore. The only way to get photos into *someone else's* library
  automatically is to hold OAuth credentials **for that person's own
  account** and upload directly into it.
- **The API can only write into albums it created itself.** You cannot
  point the API at an album someone made manually in the Google Photos app
  and add media to it. The setup script therefore creates the destination
  album programmatically as part of the one-time auth step.
- **Immich v3.0 removed the `assets` field from album-info responses.**
  If you're on Immich ≥ 3.0 (this was built/tested on 3.1.0), `GET
  /api/albums/{id}` no longer returns the assets in that album — this was
  a deliberate breaking change. The replacement is `POST
  /api/search/metadata` filtered by `albumIds`, which is what this script
  uses. If you're on an older Immich version, you'd need to revert to the
  old endpoint.

## Repo contents

| File | Purpose |
|---|---|
| `bootstrap_google_cloud.sh` | Optional. Automates the two Google Cloud steps that actually have a CLI/API (project creation, enabling the API). Everything else in Workflow A is Console-only by Google's design. |
| `setup_google_auth.py` | One-time script. Run once, on any machine with a browser, logged in as Person B's Google account. Produces `auth_state.json`. |
| `reauth_google.py` | Use this instead of `setup_google_auth.py` if you ever need to refresh the token without recreating the album (e.g. token was issued while the app was still in Testing status). |
| `sync_immich_to_gphotos.py` | The recurring sync. Runs unattended, forever, via systemd timer. |
| `test_script.sh` | Convenience wrapper — loads `.env` and runs the sync script directly, so you don't have to remember the `source .env` steps each time you want to test manually. |
| `.env.example` | Template for the config the sync script reads. |
| `immich-gphotos-sync.service` / `.timer` | systemd units for the nightly schedule. |
| `.gitignore` | Excludes all the secrets this project generates — see Security below. |

## Prerequisites

- An Immich instance, **v3.0 or newer** (for the `search/metadata` endpoint
  used here — see note above if you're on an older version).
- Person B's Google account, with the ability to complete a browser OAuth
  consent screen logged in as them (either they do it themselves, or you
  do it while they're present/on a call).
- A machine to run the recurring sync — a small LXC/VM/container is
  plenty; the job takes under a second to run and uses negligible
  resources even daily.
- Python 3.8+ wherever each script runs. Note: **Python only needs to be
  installed permanently on the machine running the recurring sync.** The
  one-time `setup_google_auth.py` step can be run anywhere (a laptop,
  Person B's own PC) and doesn't need to persist afterward — only the
  `auth_state.json` file it produces needs to be copied over.
- [ntfy](https://ntfy.sh) (or your own instance) if you want failure
  alerts — optional but recommended given this runs unattended.

## Cost

Free. Creating a Google Cloud project and enabling the Photos Library API
requires no billing account. It's quota-limited (10,000 API requests/day,
75,000 media-byte requests/day per project) rather than metered — at
occasional-photo volume you'll use a tiny fraction of that. The only
"cost" in any real sense is storage: media uploaded via the API counts
against Person B's Google account storage, at original quality.

## Workflow A — Google side (one-time, on Person B's account)

Do this while able to log into **Person B's** Google account in a
browser — either run it on their computer, or use an incognito window on
yours to force a fresh login.

0. *(Optional, scriptable)* Run `./bootstrap_google_cloud.sh` to create the
   Cloud project and enable the Photos Library API in one step. It prints
   the exact manual steps remaining below.
1. https://console.cloud.google.com → New Project.
2. **APIs & Services → Library** → enable **Google Photos Library API**.
3. Google manages OAuth setup under a separate **Google Auth Platform**
   area with its own tabs: *Branding*, *Audience*, *Data Access*,
   *Clients*. Go through them in order:
   - **Branding**: fill in app name / support email. No logo needed.
   - **Audience**: select **External**.
   - **Data Access**: add the scope
     `https://www.googleapis.com/auth/photoslibrary.appendonly`
     manually (it's not in the common-scopes picker, so look for a
     "manually add scope" option and paste the full scope URL).
   - **Clients**: Create Credentials → OAuth client ID. When asked
     **"What data will you be accessing?"**, choose **User data** (not
     "Application data" — Google Photos has no service-account/app-only
     access path). Application type: **Desktop app**. Download the
     resulting JSON, save it as `client_secret.json`.
4. **Publish the app to Production**: Audience tab → "Publish App."

   **You do not need to complete Google's verification process to do
   this**, and you can safely ignore the "Needs verification" / "In
   verification" banners Google shows afterward — those only matter if
   you want to remove the "unverified app" warning screen for large
   numbers of unrelated users, which doesn't apply here. What actually
   matters for this project is just the **publishing status**: refresh
   tokens issued while an app is in **Testing** status are hard-capped at
   a **7-day lifespan**, no matter what you do afterward — that cap isn't
   revisited retroactively. Refresh tokens issued while the app is
   already in **Production** status are not subject to that cap and last
   indefinitely (until revoked, unused for 6 months, or the account
   password changes) — regardless of whether verification was ever
   completed.

   Practical upshot: switch to Production *before* running
   `setup_google_auth.py` for the first time, so the very first token you
   generate already has the durable lifetime, rather than generating one
   token in Testing (7-day cap, permanently) and having to redo it later.
5. On whichever machine will run the browser step (needs Python + a
   browser):
   ```bash
   pip install google-auth-oauthlib google-auth requests
   ```
6. Edit `ALBUM_TITLE` in `setup_google_auth.py` to whatever you want the
   destination album called in Person B's Google Photos.
7. Put `client_secret.json` in the same folder as `setup_google_auth.py`,
   then run:
   ```bash
   python3 setup_google_auth.py
   ```
   Run this **from a terminal**, not by double-clicking — on Windows,
   double-clicking closes the console window immediately on error, before
   you can read it.
8. A browser tab opens showing **"Google hasn't verified this app."**
   This is expected — click **Advanced → Go to [app name] (unsafe) →
   Continue**. Confirm the account shown at the top is **Person B's**,
   not yours, before approving.

   This step:
   - Grants the `appendonly` scope against their account.
   - Creates the destination Google Photos album via the API (required —
     see the "why" note above).
   - Writes `auth_state.json` containing the refresh token, client
     credentials, and the new album's ID.
9. Copy `auth_state.json` to wherever Workflow B will run. Nothing else
   from this step needs to persist — `client_secret.json`, the venv, even
   Python itself can be discarded from that machine afterward.

**A few rules that keep the resulting token alive indefinitely**, worth
knowing rather than discovering the hard way:
- **6-month inactivity rule**: a refresh token dies if it goes unused for
  6 consecutive months. A nightly sync keeps it well within that.
- **Password changes**: changing Person B's Google account password
  revokes all their existing OAuth tokens, this one included — you'd need
  to re-run the setup (or `reauth_google.py`) afterward.
- **50-token cap**: repeatedly re-authenticating the same client/user
  combination more than ~50 times causes Google to silently drop the
  oldest tokens. Not a practical concern for normal use, but worth knowing
  if you're re-running the setup script frequently while testing.

## Workflow B — the recurring sync

1. In Immich, create an API key with **exactly** these permissions:

   | Permission | Used for |
   |---|---|
   | `asset.read` | Required by `POST /api/search/metadata` (the endpoint that lists what's in the album — see v3.0 note above) |
   | `asset.download` | `GET /api/assets/{id}/original` — downloading the file to re-upload to Google |
   | `albumAsset.delete` | `DELETE /api/albums/{id}/assets` — removing a synced asset from the album |

2. Find the source album's ID: `GET /api/albums` with your key, match by
   name.
3. On the machine that will run the sync:
   ```bash
   mkdir -p /opt/immich-gphotos-bridge && cd /opt/immich-gphotos-bridge
   # place sync_immich_to_gphotos.py and auth_state.json (from Workflow A) here
   python3 -m venv venv
   ./venv/bin/pip install requests google-auth
   cp .env.example .env   # then fill in real values, see below
   ```
4. `.env` values:
   ```bash
   IMMICH_URL=http://192.168.x.x:2283      # internal address, avoids any
                                            # reverse-proxy/CDN weirdness
   IMMICH_API_KEY=your-immich-api-key
   IMMICH_ALBUM_ID=uuid-of-the-source-album
   GOOGLE_AUTH_STATE_FILE=/opt/immich-gphotos-bridge/auth_state.json
   SYNCED_STATE_FILE=/opt/immich-gphotos-bridge/synced_assets.json
   NTFY_URL=https://ntfy.sh/your-private-topic
   ```
5. **Test manually before scheduling anything:**
   ```bash
   ./test_script.sh
   ```
   (Or, without the wrapper: `set -a; source .env; set +a` then
   `./venv/bin/python3 sync_immich_to_gphotos.py`.)

   Put exactly one test photo in the source album first. Confirm it
   disappears from the Immich album and appears in the Google Photos
   album on Person B's account.
6. Install the systemd units (edit the paths inside them first if you're
   not using `/opt/immich-gphotos-bridge`):
   ```bash
   cp immich-gphotos-sync.service immich-gphotos-sync.timer /etc/systemd/system/
   systemctl daemon-reload
   systemctl enable --now immich-gphotos-sync.timer
   systemctl list-timers immich-gphotos-sync.timer   # confirm it's scheduled
   ```
7. Sanity check the unit itself (not just the bare script) runs cleanly
   under systemd's environment:
   ```bash
   systemctl start immich-gphotos-sync.service
   journalctl -u immich-gphotos-sync.service -n 30
   ```

## Re-authenticating (if the token ever needs replacing)

If the token in `auth_state.json` ever stops working (password change on
Person B's account, manual revocation, or a token generated before you
switched to Production), use `reauth_google.py` — not
`setup_google_auth.py` — to fix it:

1. Run it on a machine with a browser (same constraint as the original
   setup — it opens a local server and launches your browser to Google's
   consent screen), logged in as **Person B**.
2. You'll see **"Google hasn't verified this app"** again — this happens
   *every time* you go through the consent flow, not just the first time,
   since it's tied to the app's verification status rather than being a
   one-time first-run warning. This is expected and fine for a
   personal-use app. Click **Advanced → Go to [app name] (unsafe) →
   Continue**.
3. This generates a **new** `auth_state.json`, reusing the existing
   `album_id` so no duplicate album gets created.
4. Copy that new `auth_state.json` over to wherever the sync script runs
   (the container/source machine), replacing the old one.

As long as the app is in Production status when you do this (not
Testing), the resulting token should last indefinitely and you shouldn't
need to repeat this unless one of the triggers above happens again.

## Day to day

Add a photo to the source album whenever you want it shared. The timer
picks it up on its next scheduled run, uploads it, and clears it from the
album. Silence from ntfy means it's working; you'll get a push on any
failure, and a lower-priority push if a photo uploads successfully but the
album-cleanup step fails (rare — just means the photo lingers visibly in
the Immich album until the next run retries cleanup; it will not be
double-uploaded in the meantime, since a local state file tracks
already-synced asset IDs as a backstop).

## Security notes (important if you're forking/publishing this)

- **`auth_state.json` is a credential, not a config file.** It contains a
  live refresh token that can act on Person B's Google account (within
  the `appendonly` scope — upload/create only, not read or delete their
  existing library). Never commit it. The included `.gitignore` excludes
  it, `.env`, `synced_assets.json`, and `client_secret.json` — double
  check none of these end up in a commit before pushing to a public repo.
- Same goes for the Immich API key in `.env`.
- The scope used (`photoslibrary.appendonly`) is deliberately
  narrow — it cannot read, list, or delete anything already in Person B's
  library, only add new items and manage items it created.
- Anyone who discovers your OAuth client and completes the consent flow
  would only be authorizing *their own* Google account against this app —
  not gaining access to Person B's photos. The refresh token that matters
  is the one already generated for Person B's account, which stays under
  your control.

## Troubleshooting

- **Album shows `assetCount: 1` but the sync says "no new assets."** You're
  likely hitting the Immich v3.0 API change described above. Confirm your
  Immich version, and confirm the script is using `POST
  /api/search/metadata`, not the old `GET /api/albums/{id}` assets field.
- **Refresh token stops working after ~7 days, even though the app now
  shows "In production."** The token was generated while the app was
  still in Testing — that cap is fixed at issuance and isn't fixed
  retroactively by switching status later. Run `reauth_google.py` to
  generate a fresh one now that the app is in Production; it'll last
  indefinitely from that point.
- **403 from Immich.** Almost always a missing permission on the API key
  — check against the table in Workflow B, step 1.
- **Photo uploads to Google fine but doesn't disappear from Immich.** The
  album-cleanup call failed after a successful upload — check `journalctl`
  for the specific error; it's logged as a warning, not a hard failure,
  and won't cause a duplicate upload on the next run.
- **The destination album was deleted in Google Photos.** The
  `appendonly` scope has no read access, so the script can't proactively
  check whether the album still exists — instead, media items are
  created unfiled first (always succeeds), then a separate call attempts
  to add the item to the album. If *that* call fails, the script treats
  it as "album's gone," recreates it under the same title, updates
  `auth_state.json` with the new ID, and retries adding the item — no
  manual intervention needed, and no re-download/re-upload required since
  the media item already exists at that point. You'll get a
  normal-priority ntfy notice when this happens, and you (or Person B)
  will need to find the album again in Google Photos, since it's a new
  album object with a new share/view state rather than the original.