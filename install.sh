#!/bin/sh
set -eu
REPO_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if ! command -v python3 >/dev/null 2>&1; then
  printf '%s\n' 'Python 3.9 or later is required. Install Python, then run ./install.sh again.' >&2
  exit 1
fi
exec python3 "$REPO_DIR/scripts/install_plugin.py" install "$@"
