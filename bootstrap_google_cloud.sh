#!/usr/bin/env bash
# Automates the parts of Workflow A that Google actually exposes via API/CLI.
#
# What this DOES automate:
#   - Creating the Google Cloud project
#   - Enabling the Photos Library API
#
# What this CANNOT automate (Google doesn't expose these via API for a
# personal/consumer project -- you still do these by hand in the Console):
#   - OAuth consent screen setup (Branding / Data Access tabs)
#   - Adding the appendonly scope
#   - Creating the OAuth Client ID itself
#   - Switching the app to Production
#
# Requires: gcloud CLI installed and authenticated (`gcloud auth login`).

set -euo pipefail

PROJECT_ID="${1:-immich-gphotos-bridge-$(date +%s)}"

echo "Creating project: $PROJECT_ID"
gcloud projects create "$PROJECT_ID" --name="Immich Google Photos Bridge"

echo "Setting as active project"
gcloud config set project "$PROJECT_ID"

echo "Enabling Photos Library API"
gcloud services enable photoslibrary.googleapis.com --project="$PROJECT_ID"

cat <<EOF

Done with the scriptable part. Project '$PROJECT_ID' is created and the
Photos Library API is enabled.

You still need to do the following manually in the Console (no API exists
for these on a personal project) -- go to:

  https://console.cloud.google.com/auth/overview?project=$PROJECT_ID

1. Branding tab      -> fill in app name / support email (no logo needed)
2. Audience tab      -> select "External"
3. Data Access tab   -> manually add scope:
                        https://www.googleapis.com/auth/photoslibrary.appendonly
4. Clients tab       -> Create Credentials -> OAuth client ID
                        -> "What data will you be accessing?" -> User data
                        -> Application type -> Desktop app
                        -> download the JSON as client_secret.json
5. Audience tab      -> "Publish App" to switch from Testing to Production.
                        You do NOT need to complete Google's verification --
                        ignore the "needs verification" banner. You'll see
                        an "unverified app" warning during login; click
                        Advanced -> Go to [app name] (unsafe) -> continue.
                        This is expected and fine for a personal-use app.

Then continue with setup_google_auth.py using the downloaded client_secret.json.
EOF