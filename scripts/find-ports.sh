#!/usr/bin/env bash
# Thin wrapper around find-ports.py for Unix users.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/find-ports.py" "$@"
