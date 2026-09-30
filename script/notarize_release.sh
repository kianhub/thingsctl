#!/bin/bash
# Build an independently verifiable installer DMG. Credentials stay in Keychain;
# this script never accepts passwords, API key material, or certificate exports.
set -euo pipefail
TASK_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TASK_IDENTITY="${THINGSCTL_SIGN_IDENTITY:-}"
TASK_PROFILE="${THINGSCTL_NOTARY_PROFILE:-}"
if [[ "$TASK_IDENTITY" != "Developer ID Application:"* || -z "$TASK_PROFILE" ]]; then
  printf '%s\n' 'Set THINGSCTL_SIGN_IDENTITY to your Developer ID Application certificate name and THINGSCTL_NOTARY_PROFILE to a stored notarytool Keychain profile.' >&2
  exit 2
fi
if [[ "$(uname -s)" != "Darwin" ]]; then
  printf '%s\n' 'Signing and notarization require macOS.' >&2
  exit 2
fi
/usr/bin/security find-identity -v -p codesigning | python3 -c '
import sys
identity = sys.argv[1]
if not any(("\"" + identity + "\"") in line for line in sys.stdin):
    sys.exit("The requested Developer ID Application certificate and private key are not available in this Mac’s Keychain.")
' "$TASK_IDENTITY"
xcrun --find notarytool >/dev/null
xcrun --find stapler >/dev/null
TASK_VERSION="$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["version"].split("+")[0])' "$TASK_ROOT/plugins/thingsctl/plugin.json")"
TASK_ARCH="$(uname -m)"
TASK_OUTPUT="$TASK_ROOT/dist/thingsctl-v$TASK_VERSION-macos-$TASK_ARCH.dmg"
if [[ -e "$TASK_OUTPUT" ]]; then
  printf '%s\n' "Refusing to overwrite an existing release: $TASK_OUTPUT" >&2
  exit 2
fi
mkdir -p "$TASK_ROOT/dist"
TASK_STAGE="$(mktemp -d "$TASK_ROOT/dist/notarization-$TASK_VERSION.XXXXXX")"
export THINGSCTL_BUILD_DIR="$TASK_STAGE/build"
export THINGSCTL_SIGN_IDENTITY="$TASK_IDENTITY"
# Validate the stored profile before compiling, without returning its secret.
xcrun notarytool history --keychain-profile "$TASK_PROFILE" --output-format json >/dev/null

notarize() {
  local task_artifact="$1" task_label="$2" task_report="$TASK_STAGE/$2-notarization.json"
  printf '%s\n' "Submitting $task_label to Apple…"
  xcrun notarytool submit "$task_artifact" --keychain-profile "$TASK_PROFILE" \
    --wait --output-format json > "$task_report"
  python3 - "$task_report" <<'PY'
import json
import sys
from pathlib import Path
report = Path(sys.argv[1])
value = json.loads(report.read_text())
print("Notarization status: " + str(value.get("status", "unknown")))
if value.get("status") != "Accepted":
    print("Submission ID: " + str(value.get("id", "unknown")))
    sys.exit("Notarization was not accepted. Inspect " + str(report) + " and retrieve its notarytool log before retrying.")
PY
}

"$TASK_ROOT/script/build_and_run.sh" --build-only
TASK_BRIDGE="$THINGSCTL_BUILD_DIR/ThingsCTL Bridge.app"
/usr/bin/ditto -c -k --keepParent "$TASK_BRIDGE" "$TASK_STAGE/bridge.zip"
notarize "$TASK_STAGE/bridge.zip" bridge
xcrun stapler staple "$TASK_BRIDGE"
xcrun stapler validate "$TASK_BRIDGE"
/usr/sbin/spctl --assess --type execute --verbose=2 "$TASK_BRIDGE"

# The runtime installer deploys the bridge with shutil.copytree. Verify that
# exact path preserves the signed bundle and stapled ticket before shipping.
TASK_INSTALL_COPY="$TASK_STAGE/install-copy/ThingsCTL Bridge.app"
python3 - "$TASK_BRIDGE" "$TASK_INSTALL_COPY" <<'PY'
import shutil
import sys
from pathlib import Path
source, target = map(Path, sys.argv[1:])
target.parent.mkdir(parents=True)
shutil.copytree(source, target)
PY
/usr/bin/codesign --verify --strict --verbose=2 "$TASK_INSTALL_COPY"
xcrun stapler validate "$TASK_INSTALL_COPY"
/usr/sbin/spctl --assess --type execute --verbose=2 "$TASK_INSTALL_COPY"

# Staple the bridge before sealing the installer that contains it. Then staple
# the installer before creating its disk image, preserving every outer seal.
"$TASK_ROOT/script/build_installer.sh"
TASK_INSTALLER="$THINGSCTL_BUILD_DIR/Install ThingsCTL.app"
/usr/bin/ditto -c -k --keepParent "$TASK_INSTALLER" "$TASK_STAGE/installer.zip"
notarize "$TASK_STAGE/installer.zip" installer
xcrun stapler staple "$TASK_INSTALLER"
xcrun stapler validate "$TASK_INSTALLER"
/usr/bin/codesign --verify --deep --strict --verbose=2 "$TASK_INSTALLER"
/usr/sbin/spctl --assess --type execute --verbose=2 "$TASK_INSTALLER"

mkdir -p "$TASK_STAGE/disk-image"
/usr/bin/ditto "$TASK_INSTALLER" "$TASK_STAGE/disk-image/Install ThingsCTL.app"
cp "$TASK_ROOT/LICENSE" "$TASK_STAGE/disk-image/LICENSE.txt"
cat > "$TASK_STAGE/disk-image/Read Me.txt" <<'TEXT'
Double-click Install ThingsCTL to install in your user account.

Requires macOS 14+, Things 3, Python 3.9+, and a recent Codex CLI.
When macOS asks, allow ThingsCTL Bridge to control Things.
Refresh plugins in ChatGPT or Codex, then ask ThingsCTL to open your workspace.

Source, installation details, and recovery:
https://github.com/kianhub/thingsctl
TEXT
/usr/bin/hdiutil create -volname "ThingsCTL $TASK_VERSION" -srcfolder "$TASK_STAGE/disk-image" \
  -format UDZO "$TASK_STAGE/release.dmg"
/usr/bin/codesign --sign "$TASK_IDENTITY" --timestamp "$TASK_STAGE/release.dmg"
notarize "$TASK_STAGE/release.dmg" disk-image
xcrun stapler staple "$TASK_STAGE/release.dmg"
xcrun stapler validate "$TASK_STAGE/release.dmg"
/usr/bin/codesign --verify --strict "$TASK_STAGE/release.dmg"
/usr/sbin/spctl --assess --type open --context context:primary-signature --verbose=2 "$TASK_STAGE/release.dmg"
TASK_MOUNT="$TASK_STAGE/mounted-release"
mkdir "$TASK_MOUNT"
trap '/usr/bin/hdiutil detach "$TASK_MOUNT" >/dev/null 2>&1 || true' EXIT
/usr/bin/hdiutil attach -readonly -nobrowse -mountpoint "$TASK_MOUNT" "$TASK_STAGE/release.dmg" >/dev/null
/usr/bin/codesign --verify --deep --strict --verbose=2 "$TASK_MOUNT/Install ThingsCTL.app"
xcrun stapler validate "$TASK_MOUNT/Install ThingsCTL.app"
/usr/sbin/spctl --assess --type execute --verbose=2 "$TASK_MOUNT/Install ThingsCTL.app"
/usr/bin/hdiutil detach "$TASK_MOUNT" >/dev/null
trap - EXIT
mv "$TASK_STAGE/release.dmg" "$TASK_OUTPUT"
(cd "$TASK_ROOT/dist" && /usr/bin/shasum -a 256 "$(basename "$TASK_OUTPUT")") > "$TASK_OUTPUT.sha256"
printf '%s\n' "Signed, accepted, stapled, and verified: $TASK_OUTPUT" "Notarization reports: $TASK_STAGE"
