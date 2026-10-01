# Install ThingsCTL

ThingsCTL is a local macOS tool and ChatGPT/Codex plugin. Things 3 remains your task store. The CLI, MCP tools, and workspace use the same command service and the ThingsCTL Bridge.

## Requirements

- macOS 14 or newer with Things 3 installed. The implementation uses documented AppleScript automation.
- Python 3.9 or newer.
- Xcode Command Line Tools for a source build of the Swift bridge (`xcode-select --install`). The prebuilt macOS arm64 archive does not require compilation.
- A recent Codex CLI exposing `codex plugin add` and `codex plugin marketplace add`.

Source builds are ad-hoc signed with the stable identifier `com.kianhub.thingsctl.bridge` by default. The published v0.1.2 ZIP is also ad-hoc signed and not notarized. macOS may require renewing the Automation grant after a rebuild.

v0.1.3 introduces the native installer and notarization workflow. v0.1.4 adds direct bridge startup and background-item attribution. v0.1.5 fixes task lookup and workspace navigation, and removes repeated catalog/post-save reads. Signed downloads are published only after Apple accepts the submissions and the distribution checks pass.

## Install on your MacBook

Install Things 3 and a recent ChatGPT/Codex desktop app with plugin support on the MacBook. ThingsCTL uses the Things app on that Mac; signing in to the same Things Cloud account lets Things sync your tasks between Macs.

For a signed release, download the installer DMG from [GitHub releases](https://github.com/kianhub/thingsctl/releases), open it, and double-click **Install ThingsCTL**. The native installer runs the same user-account installation below. You do not need a Developer ID certificate or notary profile to install a signed release. A release is notarized only after Apple accepts it and the stapled tickets and Gatekeeper checks pass; the workflow's presence in source does not notarize earlier downloads.

For an Apple silicon Mac, download the [v0.1.2 macOS arm64 archive](https://github.com/kianhub/thingsctl/releases/download/v0.1.2/thingsctl-v0.1.2-macos-arm64.zip) and extract it. In Terminal, change to the extracted `thingsctl` folder, then run:

```sh
./install.sh --skip-build
```

This installs the prebuilt bridge and the local plugin. Python 3.9+ and the Codex CLI are still required; Xcode and Node.js are not required for this archive. The archive also includes **Install ThingsCTL.command**, but macOS may block that unsigned launcher. Use a signed installer DMG when available, or build from source below.

To build from the public source repository instead, including on an Intel Mac:

```sh
mkdir -p ~/Developer
cd ~/Developer
git clone https://github.com/kianhub/thingsctl.git
cd thingsctl
./install.sh
```

The source build requires Xcode Command Line Tools (`xcode-select --install`). Allow **ThingsCTL Bridge** to control Things when macOS asks, then follow the connection check below.

The installer builds the native bridge, uses the checked-in bundled workspace, stages a self-contained plugin, installs `~/Applications/ThingsCTL Bridge.app` and `~/.local/bin/thingsctl`, and registers the plugin with supported Codex CLI commands. It preserves an unrelated launcher as a backup and records ownership in `~/Library/Application Support/ThingsCTL/install-manifest.json`. Its LaunchAgent starts the signed bridge executable directly at login and associates that job with ThingsCTL Bridge. Reinstalls retain a recovery copy of the previous managed files until setup completes. It does not change Things data or macOS permission settings.

If `~/.local/bin` is absent from your shell PATH, use the full executable path or add that directory in your own shell configuration. The installer leaves shell startup files untouched.

The portable plugin ZIP contains only the plugin runtime/UI and requires a separately installed bridge. If you already installed the same plugin through a private account page, install just its local bridge and CLI from the extracted macOS archive:

```sh
./install.sh --skip-build --skip-plugin
```

Use the normal `./install.sh --skip-build` command for the GitHub distribution. `--skip-plugin` is only needed when another installation already supplies the plugin.

Useful installation options:

```sh
./install.sh --dry-run
./install.sh --skip-build
./install.sh --skip-plugin
./install.sh --no-launch-agent
```

`--skip-build` expects a native build in `dist/`. The bundled HTML in `ui/dist/` is included in the repository; end users do not need Node.js or pnpm. UI development requires Node.js and pnpm (`pnpm -C ui install && pnpm -C ui build`). `--skip-plugin` installs the bridge and CLI only. `--no-launch-agent` removes any existing installer-owned login job and skips creating a new one; the socket client can start the installed bridge on demand.

## Background startup and upgrading

v0.1.4 changes the login job from `/usr/bin/open` to `~/Applications/ThingsCTL Bridge.app/Contents/MacOS/ThingsCTLBridge` and adds `AssociatedBundleIdentifiers` for `com.kianhub.thingsctl.bridge`. The job's executable now carries the bridge app's signing identity. The installer briefly launches the bridge's bundled-resource check to register the app with Launch Services before starting the login job; that check does not read Things task data. This follows [Apple's guidance for associating helper executables with app names in System Settings](https://developer.apple.com/documentation/servicemanagement/updating-helper-executables-from-earlier-versions-of-macos).

To upgrade from an older release, run the newer native installer. It stops the previous installer-owned login job before replacing the bridge and writes the updated job while keeping the same app identifier and ownership/recovery checks. If macOS asks about background activity, allow ThingsCTL Bridge. You can review its setting in **System Settings → General → Login Items** (or **Login Items & Extensions**). Installing with `--no-launch-agent` removes the previous owned job instead of leaving it active.

## Verify connection

```sh
~/.local/bin/thingsctl doctor --json
~/.local/bin/thingsctl list today --json
```

`doctor` checks installation and connection without reading task content. The list command reads your Today tasks. When the bridge first connects to Things, macOS may ask whether **ThingsCTL Bridge** may control Things. Allow that Automation request. ThingsCTL does not need Things Cloud credentials, database access, Full Disk Access, or Accessibility permission.

In ChatGPT or Codex, refresh plugin discovery if necessary and invoke **ThingsCTL** → **Open my Things workspace**. The global **ThingsCTL** sidebar entry and **ThingsCTL workspace** conversation-panel tab expose the same interactive app. Mentioning the plugin selects its tools; the workspace opener is what displays the app. Text-only list commands remain available. Preference settings are available through the host's structured settings controls. Selected tasks can be attached to the conversation through the workspace, without sending a message automatically.

After upgrading, reopen the ThingsCTL workspace so the host loads the updated UI. If a newly installed plugin's tools are absent in an existing chat, refresh the plugin or open a fresh chat and select ThingsCTL. No installation success message alone proves that tools or the app rendered.

## MCP and portable package

For another MCP client, use this installed command:

```sh
~/.local/bin/thingsctl mcp serve
```

The checked-in `plugins/thingsctl/` source is self-contained: portable Agent Plugins 1.0 manifests, a Codex compatibility overlay, Python runtime, workspace, and licenses. The repository marketplace points to this directory, so direct marketplace installation can launch without a global CLI. The native bridge still needs `./install.sh` on the same Mac.

After changing runtime or UI source, refresh the marketplace source and build a portable package:

```sh
python3 scripts/package_plugin.py --sync-source
python3 scripts/package_plugin.py --output work/plugin/thingsctl --zip work/thingsctl-plugin.zip
```

The package contains its Python command runtime and bundled HTML. Its MCP launcher uses `${PLUGIN_ROOT}` and runs without dependencies on the repository or global `thingsctl` path. Packaging replaces generated files from canonical sources and uses a deterministic content version, so unchanged rebuilds retain the same version. Python 3.9+ and the separately installed native bridge are still required; a local plugin cannot run in web or mobile ChatGPT. Do not install by editing a Codex version cache.

## GitHub distribution

The public [GitHub repository](https://github.com/kianhub/thingsctl) and its [release downloads](https://github.com/kianhub/thingsctl/releases) distribute the source, plugin package, and prebuilt Mac archive. The installer registers the local marketplace and its sidebar app in the desktop host, using the same local distribution pattern as RemCTL. Public plugin-directory submission is not required.

Installing the plugin alone does not install or host its automation bridge. ThingsCTL Bridge and Things must run on the same Mac as the plugin. Use the installer on each Mac where you want the app available.

## Publisher signing and notarization

This section is for maintainers shipping downloads. End users do not perform these steps.

The release Mac needs a valid **Developer ID Application** certificate with its private key in Keychain, Xcode Command Line Tools, and a stored `notarytool` Keychain profile. A notary profile supplies Apple's submission credentials; it does not supply the signing certificate. Store credentials through `xcrun notarytool store-credentials notarytool` interactively, following [Apple's notarization documentation](https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution). Check available signing identities with `security find-identity -v -p codesigning`. Do not place passwords, API keys, certificate exports, or private keys in the repository.

With those prerequisites installed, run:

```sh
export THINGSCTL_SIGN_IDENTITY='Developer ID Application: Your Name (TEAMID)'
export THINGSCTL_NOTARY_PROFILE='notarytool'
./script/notarize_release.sh
```

Both environment values are references to Keychain items, not secrets. The script verifies that the exact Developer ID identity is available and that the profile authenticates before compiling. It builds for the release Mac's architecture and requires a fresh output filename. It does not publish or upload a GitHub release automatically.

The bridge is signed with hardened runtime, a secure timestamp, and the documented [Apple Events entitlement](https://developer.apple.com/documentation/BundleResources/Entitlements/com.apple.security.automation.apple-events). The native installer uses that entitlement to restart an existing bridge through the shared installer. Neither app enables App Sandbox or debugger entitlements. Local builds without `THINGSCTL_SIGN_IDENTITY` continue to use ad-hoc signing.

The script notarizes and staples the bridge before sealing it inside the installer, then notarizes and staples the installer before creating the DMG. It also copies the stapled bridge with the runtime installer's `shutil.copytree` method and checks that copy's signature, ticket, and Gatekeeper acceptance. It signs, notarizes, and staples the DMG as well. Each stage requires Apple's `Accepted` result and validates its ticket; final checks verify the signatures and Gatekeeper acceptance, including the installer inside a read-only mount of the finished DMG. Reports remain under ignored `dist/notarization-*` directories. Only the verified DMG and its SHA-256 checksum should be added to release downloads. Never describe an artifact as notarized while its submission is pending or rejected.

## Demo and supported scope

`THINGSCTL_DEMO=1` uses explicit synthetic fixtures. Use it for tests and UI previews; demo results and the workspace label their data. A failed live connection never silently substitutes demo tasks.

This release supports core task reads and changes, projects, areas, tags, separate When and Deadline fields, completion/cancellation/reopening, moves, and Trash. It excludes live database access and experimental scripting properties. Headings, checklists, Evening, timed reminders, recurrence authoring, and arbitrary reordering remain unavailable until a documented richer adapter is implemented and verified.

For tasks inside projects, a missing activation date does not prove Anytime or Someday. The workspace shows **Unspecified in Things** when documented reads cannot establish that placement and preserves it during unrelated edits. Today and explicit start dates remain supported. Anytime/Someday writes to a project task are rejected before dispatch; they are allowed when the same change explicitly detaches the task with `projectId: null`. Detach a task only when that structural move is intended. Titles, notes, tags, Deadline, status, and moves can be edited independently of an unspecified When.

Changes are journaled and read back. A result can be verified, failed, or uncertain. Keep the same operation ID when reconciling an uncertain change; do not submit a new ID and risk duplicating it. Revisions detect edits made elsewhere before save.

## Uninstall and recovery

```sh
./uninstall.sh --dry-run
./uninstall.sh
```

The uninstaller uses supported Codex removal commands and removes only installer-owned paths. It restores the prior launcher if one was preserved. It keeps task data, preference settings, the operation journal, and macOS permission grants. A pending or failed final connection check does not undo the installation or require reinstalling. The manifest records installation separately from connection readiness; rerun `thingsctl doctor --json` after granting permission or starting the bridge. If managed files have changed or an installation failed partway, the ownership manifest provides the paths and installation phase; the installer reports the error rather than claiming a complete connection.
