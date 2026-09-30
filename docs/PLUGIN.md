# ThingsCTL plugin distribution

ThingsCTL is an open-source local plugin distributed from [GitHub](https://github.com/kianhub/thingsctl), under the MIT license. It is not listed in the public ChatGPT plugin directory. The native bridge and Things must run on the same Mac as the plugin.

## Install on another Mac

Use the macOS arm64 archive from [Releases](https://github.com/kianhub/thingsctl/releases), or clone this repository. Run the included installer on each Mac. It installs the bridge, CLI, and managed local marketplace, then adds `thingsctl@thingsctl-local` through supported Codex commands. Each Mac uses its own local Things library and Automation grant.

The source plugin lives in `plugins/thingsctl/`; the repository marketplace is `.agents/plugins/marketplace.json`. It is self-contained, including its Python command runtime, HTML app, icons, skills, and dependency licenses. The native bridge still needs a separate local installation. See [installation](INSTALLATION.md).

## Package and update

After changing runtime, UI, or plugin source:

```sh
python3 scripts/package_plugin.py --sync-source
python3 scripts/package_plugin.py --output work/plugin/thingsctl --zip work/thingsctl-plugin.zip
```

Use a fresh staging directory for each package. Packaging synchronizes generated runtime/UI files and adds a deterministic content suffix to the plugin version. Refresh an installed plugin with `./install.sh --skip-build` when the prebuilt bridge is available, or `./install.sh` for a source build. Do not edit installed version caches.

A privately saved account copy, if used, distributes the plugin package but does not host ThingsCTL Bridge. Its private owner identifiers are not required for open-source installation. Installing a plugin package alone does not install the bridge or grant macOS Automation access.

## App launch and verification

`thingsctl_workspace` registers the global **ThingsCTL** entrypoint; `thingsctl_workspace_thread` registers **ThingsCTL workspace** in conversation panels. Both use `ui://thingsctl/workspace.html`, prefer fullscreen, and return an initial snapshot. The host decides placement. Data-only list/get/search tools do not display an app.

The installed MCP opener rendered a live Things-style Today workspace and inline task details in a conversation side panel on September 30, 2026. That inspection did not change task data. Global native-sidebar clicking and selected-task context remain unverified.

v0.1.1 made app registration stable before UI MIME capabilities are advertised, clarified launch names, added a workspace-launch skill, and preserved a connected app if fullscreen placement is declined. The existing MCP checks and synthetic browser workflow passed; no tests were added.
