#!/bin/bash
set -euo pipefail
TASK_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TASK_BUILD_DIR="${THINGSCTL_BUILD_DIR:-$TASK_ROOT/dist}"
TASK_BRIDGE="$TASK_BUILD_DIR/ThingsCTL Bridge.app"
TASK_APP="$TASK_BUILD_DIR/Install ThingsCTL.app"
TASK_IDENTITY="${THINGSCTL_SIGN_IDENTITY:--}"
TASK_VERSION="$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["version"].split("+")[0])' "$TASK_ROOT/plugins/thingsctl/plugin.json")"
if [[ "$TASK_IDENTITY" != "-" && "$TASK_IDENTITY" != "Developer ID Application:"* ]]; then
  printf '%s\n' 'Use a Developer ID Application identity for distribution, or - for local builds.' >&2
  exit 2
fi
if [[ ! -d "$TASK_BRIDGE" || -e "$TASK_APP" ]]; then
  printf '%s\n' 'Build the bridge first, and use a fresh installer build directory.' >&2
  exit 2
fi
/usr/bin/codesign --verify --strict "$TASK_BRIDGE"
mkdir -p "$TASK_APP/Contents/MacOS" "$TASK_APP/Contents/Resources/payload"
TASK_PAYLOAD="$TASK_APP/Contents/Resources/payload"
# Copy only distribution inputs. No credentials, developer work files, logs,
# test fixtures, or personal Things data may enter the installer envelope.
python3 - "$TASK_ROOT" "$TASK_PAYLOAD" <<'PY'
import shutil
import sys
from pathlib import Path
root, target = map(Path, sys.argv[1:])
for name in (".agents", "plugins/thingsctl", "thingsctl_pkg"):
    shutil.copytree(root / name, target / name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"))
for name in ("install.sh", "uninstall.sh", "LICENSE", "scripts/install_plugin.py", "scripts/package_plugin.py",
             "docs/INSTALLATION.md", "ui/dist/things-workspace.html", "ui/THIRD-PARTY-NOTICES.txt"):
    destination = target / name
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(root / name, destination)
PY
mkdir -p "$TASK_PAYLOAD/dist"
/usr/bin/ditto "$TASK_BRIDGE" "$TASK_PAYLOAD/dist/ThingsCTL Bridge.app"
xcrun swiftc -O -target "$(uname -m)-apple-macos14.0" -framework AppKit \
  "$TASK_ROOT/bridge/ThingsCTLInstaller.swift" -o "$TASK_APP/Contents/MacOS/ThingsCTLInstaller"
cat > "$TASK_APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleExecutable</key><string>ThingsCTLInstaller</string>
<key>CFBundleIdentifier</key><string>com.kianhub.thingsctl.installer</string>
<key>CFBundleName</key><string>Install ThingsCTL</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleShortVersionString</key><string>0.1.0</string>
<key>CFBundleVersion</key><string>1</string>
<key>LSMinimumSystemVersion</key><string>14.0</string>
<key>NSAppleEventsUsageDescription</key><string>The installer restarts ThingsCTL Bridge when updating your installation.</string>
<key>NSPrincipalClass</key><string>NSApplication</string>
</dict></plist>
PLIST
/usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $TASK_VERSION" "$TASK_APP/Contents/Info.plist"
if [[ "$TASK_IDENTITY" == "-" ]]; then
  /usr/bin/codesign --force --sign - "$TASK_APP"
else
  /usr/bin/codesign --force --sign "$TASK_IDENTITY" --options runtime --timestamp \
    --entitlements "$TASK_ROOT/bridge/Release.entitlements" "$TASK_APP"
fi
/usr/bin/codesign --verify --deep --strict --verbose=2 "$TASK_APP"
printf '%s\n' "Built $TASK_APP"
