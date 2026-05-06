#!/usr/bin/env bash
# Thin wrapper around build-dongle.py for Unix users.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/build-dongle.py" "$@"
