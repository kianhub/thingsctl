# ThingsCTL plugin distribution

The working local plugin is `thingsctl@thingsctl-local`, installed through the managed marketplace at `~/Library/Application Support/ThingsCTL/marketplace`. Canonical source remains `plugins/thingsctl/` in this repository. Do not edit version caches.

The same package is saved privately to the personal account:

- Page: https://chatgpt.com/plugins/plugins_6abd76427a6481919ed19fc5bac9a5eb
- Backend plugin ID: `plugins_6abd76427a6481919ed19fc5bac9a5eb`
- Current account release ID: `pluginrel_6abd764364dc8191859962a5601b364b`
- Version: `0.1.1+e7388e2593a9`
- Scope: `USER`; visibility: `PRIVATE`.
- Package SHA-256: `a4517acecbf27b84b46e5fe1553316a87395c0208b641b5b3660a280967a0005`.

Private account saving provides an account plugin page and a downloadable package; it does not host the Mac automation process or make local Things available on web/mobile. The working local installation remains enabled. Account metadata and the local installed version were verified after saving.

To publish a later private update, inspect the existing account plugin files/metadata using the backend ID above, package the updated source, and update that ID with the freshly observed current release ID. Preserve its audience and identity. Do not create another account plugin. Refresh this record from the successful update result.

## App launch and verification

`thingsctl_workspace` is the global **ThingsCTL** entrypoint. `thingsctl_workspace_thread` is **ThingsCTL workspace** in a conversation panel. Both point to `ui://thingsctl/workspace.html`, prefer fullscreen, and return an initial snapshot. The host decides placement. Data-only list/get/search tools do not display an app.

On September 30, 2026, the installed MCP opener rendered a live Things-style Today workspace in the conversation side panel. Its navigation, 9 task rows, and read-only task expansion were inspected through the scoped MCP Apps browser. No task data was changed during that inspection. Global native-sidebar clicking and selected-task context were not exercised because Computer Use of the native ChatGPT window is blocked.

v0.1.1 keeps app registration stable before UI MIME capabilities are advertised, uses clear launch names, includes a workspace-launch skill, and preserves an established connection if fullscreen placement is declined. Existing MCP protocol checks and the synthetic browser workflow passed; no new tests were added.
