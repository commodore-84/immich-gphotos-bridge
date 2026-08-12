#!/usr/bin/env bash
# Convenience wrapper: loads .env and runs the sync script directly,
# exactly like a manual test run -- so you don't have to remember the
# `set -a; source .env; set +a` incantation every time.
#
# Run this from the same directory as sync_immich_to_gphotos.py and .env,
# or pass that directory as the first argument:
#   ./test_script.sh
#   ./test_script.sh /opt/immich-gphotos-bridge

set -euo pipefail

DIR="${1:-$(dirname "$(readlink -f "$0")")}"
cd "$DIR"

if [ ! -f ".env" ]; then
    echo "ERROR: .env not found in $DIR"
    exit 1
fi

if [ ! -f "sync_immich_to_gphotos.py" ]; then
    echo "ERROR: sync_immich_to_gphotos.py not found in $DIR"
    exit 1
fi

PYTHON_BIN="./venv/bin/python3"
if [ ! -x "$PYTHON_BIN" ]; then
    echo "No venv found at ./venv -- falling back to system python3"
    PYTHON_BIN="python3"
fi

echo "== Loading .env from $DIR =="
set -a
source .env
set +a

echo "== Running sync_immich_to_gphotos.py =="
echo
"$PYTHON_BIN" sync_immich_to_gphotos.py
EXIT_CODE=$?

echo
if [ $EXIT_CODE -eq 0 ]; then
    echo "== Done. Exit code 0 (success) =="
else
    echo "== Done. Exit code $EXIT_CODE (check output above) =="
fi
exit $EXIT_CODE