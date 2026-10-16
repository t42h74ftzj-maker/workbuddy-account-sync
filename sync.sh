#!/usr/bin/env bash
# WorkBuddy account sync — double-click friendly entry (quit WorkBuddy first)
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
PY="${PYTHON:-python3}"
"$PY" "$DIR/account_sync.py" sync
