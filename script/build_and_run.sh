#!/bin/bash
set -euo pipefail
TASK_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TASK_APP="$TASK_ROOT/dist/ThingsCTL Bridge.app"
TASK_MODE="${1:---verify}"
mkdir -p "$TASK_APP/Contents/MacOS" "$TASK_APP/Contents/Resources"
xcrun swiftc -O -framework AppKit -framework Carbon "$TASK_ROOT/bridge/ThingsCTLBridge.swift" -o "$TASK_APP/Contents/MacOS/ThingsCTLBridge"
/usr/bin/osacompile -o "$TASK_APP/Contents/Resources/Things.scpt" "$TASK_ROOT/bridge/Things.applescript"
cat > "$TASK_APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleExecutable</key><string>ThingsCTLBridge</string>
<key>CFBundleIdentifier</key><string>com.kianhub.thingsctl.bridge</string>
<key>CFBundleName</key><string>ThingsCTL Bridge</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleShortVersionString</key><string>0.1.0</string>
<key>CFBundleVersion</key><string>1</string>
<key>LSMinimumSystemVersion</key><string>14.0</string>
<key>LSUIElement</key><true/>
<key>NSAppleEventsUsageDescription</key><string>ThingsCTL reads and edits your Things tasks using the documented automation interface.</string>
<key>NSPrincipalClass</key><string>NSApplication</string>
</dict></plist>
PLIST
/usr/bin/codesign --force --sign - --identifier com.kianhub.thingsctl.bridge "$TASK_APP"
"$TASK_APP/Contents/MacOS/ThingsCTLBridge" --self-test
"$TASK_APP/Contents/MacOS/ThingsCTLBridge" --check
case "$TASK_MODE" in
  --build-only) ;;
  --debug) exec lldb -- "$TASK_APP/Contents/MacOS/ThingsCTLBridge" ;;
  --verify|run)
    pkill -x ThingsCTLBridge 2>/dev/null || true
    /usr/bin/open -gj "$TASK_APP"
    for task_attempt in $(seq 1 30); do
      if pgrep -x ThingsCTLBridge >/dev/null; then printf '%s\n' 'ThingsCTL Bridge is running'; exit 0; fi
      sleep 0.1
    done
    printf '%s\n' 'ThingsCTL Bridge did not start' >&2; exit 1 ;;
  --logs|--telemetry)
    pkill -x ThingsCTLBridge 2>/dev/null || true
    /usr/bin/open -gj "$TASK_APP"
    exec /usr/bin/log stream --info --style compact --predicate 'process == "ThingsCTLBridge"' ;;
  *) printf '%s\n' 'Usage: script/build_and_run.sh [--build-only|--verify|--debug|--logs|--telemetry]' >&2; exit 2 ;;
esac
