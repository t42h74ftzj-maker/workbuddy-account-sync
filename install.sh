#!/usr/bin/env bash
set -e
SRC="$(cd "$(dirname "$0")" && pwd)"
DST="${WORKBUDDY_CONFIG_DIR:-$HOME/.workbuddy}/skills/workbuddy-account-sync"
mkdir -p "$(dirname "$DST")"
command -v rsync >/dev/null && rsync -a --exclude .git "$SRC/" "$DST/" || { rm -rf "$DST"; cp -r "$SRC" "$DST"; }
echo "installed to: $DST"
