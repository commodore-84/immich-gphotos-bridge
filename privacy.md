# Privacy Policy

This application ("Immich Google Photos Bridge") is a personal, open-source
tool that transfers photos from a self-hosted Immich instance into a
specific Google Photos account, at the direction of that account's owner.

## What data this app accesses

This app requests the `photoslibrary.appendonly` scope from the Google
Photos Library API. This scope permits the app to:

- Upload new media items to the authorizing user's Google Photos library.
- Create albums, and add uploaded items to albums the app itself created.

This scope does **not** permit the app to read, list, download, modify, or
delete any existing content in the authorizing user's Google Photos
library. The app has no access to any Google Photos content beyond what
it uploads itself.

## What this app does with the data

Photos selected by the app's operator (via a curated album in their own
self-hosted Immich instance) are uploaded directly into the authorizing
user's Google Photos library, into a single album created for this
purpose. No data is shared with, sold to, or processed by any third party.
No analytics, tracking, or advertising is performed. All processing
happens on infrastructure controlled by the app's operator; Google's APIs
are the only third-party service involved.

## Data retention

This app does not retain copies of uploaded photos beyond what's needed to
perform the upload at the time it runs. Photos remain in the operator's
Immich instance (the source) and the authorizing user's Google Photos
library (the destination) according to those services' own retention.

## Revoking access

The authorizing user can revoke this app's access at any time via
[Google Account permissions](https://myaccount.google.com/permissions).

## Contact

Questions about this app or this policy: open an issue on the
[GitHub repository](https://github.com/yourusername/your-repo-name)
or contact [your-email@example.com].
