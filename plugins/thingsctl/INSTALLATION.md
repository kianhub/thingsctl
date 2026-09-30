# Install ThingsCTL

ThingsCTL is a local macOS tool and Codex plugin. Things 3 remains your task store. The CLI, MCP tools, and workspace use the same command service and the ThingsCTL Bridge.

## Requirements

- macOS 14 or newer with Things 3 installed. The implementation uses documented AppleScript automation.
- Python 3.9 or newer.
- Xcode Command Line Tools for a source build of the Swift bridge (`xcode-select --install`). The prebuilt macOS arm64 archive does not require compilation.
- A recent Codex CLI exposing `codex plugin add` and `codex plugin marketplace add`.

The repository is a development build. It is ad-hoc signed with the stable identifier `com.kianhub.thingsctl.bridge`; it is not notarized. macOS may require renewing the Automation grant after a rebuild.

## Install

From the repository:

```sh
./install.sh
```

The installer builds the native bridge, uses the checked-in bundled workspace, stages a self-contained plugin, installs `~/Applications/ThingsCTL Bridge.app` and `~/.local/bin/thingsctl`, and registers the plugin with supported Codex CLI commands. It preserves an unrelated launcher as a backup and records ownership in `~/Library/Application Support/ThingsCTL/install-manifest.json`. Its LaunchAgent starts the bridge at login. Reinstalls retain a recovery copy of the previous managed files until setup completes. It does not change Things data or macOS permission settings.

If `~/.local/bin` is absent from your shell PATH, use the full executable path or add that directory in your own shell configuration. The installer leaves shell startup files untouched.

The [v0.1.0 macOS arm64 archive](https://github.com/kianhub/thingsctl/releases/tag/v0.1.0) includes a prebuilt bridge in `dist/`. Extract it and run `./install.sh --skip-build`; Python and Codex are still required. The portable plugin ZIP contains only the plugin runtime/UI, and requires a separately installed bridge.

Useful installation options:

```sh
./install.sh --dry-run
./install.sh --skip-build
./install.sh --skip-plugin
./install.sh --no-launch-agent
```

`--skip-build` expects a native build in `dist/`. The bundled HTML in `ui/dist/` is included in the repository; end users do not need Node.js or pnpm. UI development requires Node.js and pnpm (`pnpm -C ui install && pnpm -C ui build`). `--skip-plugin` installs the bridge and CLI only. `--no-launch-agent` skips login startup; the socket client can start the installed bridge on demand.

## Verify connection

```sh
~/.local/bin/thingsctl doctor --json
~/.local/bin/thingsctl list today --json
```

`doctor` checks installation and connection without reading task content. The list command reads your Today tasks. When the bridge first connects to Things, macOS may ask whether **ThingsCTL Bridge** may control Things. Allow that Automation request. ThingsCTL does not need Things Cloud credentials, database access, Full Disk Access, or Accessibility permission.

In Codex, refresh plugin discovery if necessary and invoke **ThingsCTL** → **Open my Things workspace**. The global Things entrypoint and Task workspace tab expose the same interactive view. Preference settings are available through the host's structured settings controls. Selected tasks can be attached to the conversation through the workspace, without sending a message automatically.

If a newly installed plugin's tools are absent in an existing chat, refresh the plugin or open a fresh chat and select ThingsCTL. No installation success message alone proves that tools or the app rendered.

## MCP and portable package

For another MCP client, use this installed command:

```sh
~/.local/bin/thingsctl mcp serve
```

The checked-in `plugins/thingsctl/` source is self-contained: portable Agent Plugins 1.0 manifests, a Codex compatibility overlay, Python runtime, workspace, and licenses. The repository marketplace points to this directory, so direct marketplace installation can launch without a global CLI. The native bridge still needs `./install.sh` on the same Mac.

After changing runtime or UI source, refresh the marketplace source and build a private package:

```sh
python3 scripts/package_plugin.py --sync-source
python3 scripts/package_plugin.py --output work/plugin/thingsctl --zip work/thingsctl-plugin.zip
```

The package contains its Python command runtime and bundled HTML. Its MCP launcher uses `${PLUGIN_ROOT}` and runs without dependencies on the repository or global `thingsctl` path. Packaging replaces generated files from canonical sources and uses a deterministic content version, so unchanged rebuilds retain the same version. Python 3.9+ and the separately installed native bridge are still required; a local plugin cannot run in web or mobile ChatGPT. Do not install by editing a Codex version cache.

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
