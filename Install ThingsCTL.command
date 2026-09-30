#!/bin/sh
set -eu

TASK_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
TASK_BRIDGE="$TASK_ROOT/dist/ThingsCTL Bridge.app/Contents/MacOS/ThingsCTLBridge"

if [ -x "$TASK_BRIDGE" ]; then
  "$TASK_ROOT/install.sh" --skip-build "$@"
else
  "$TASK_ROOT/install.sh" "$@"
fi

printf '\n%s\n' 'ThingsCTL setup finished. Open ThingsCTL in ChatGPT or Codex and allow its Things Automation request if prompted.'
if [ -t 0 ]; then
  printf '%s' 'Press Return to close this window. '
  IFS= read -r TASK_REPLY || true
fi
