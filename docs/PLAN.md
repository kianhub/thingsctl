# ThingsCTL implementation and validation plan

ThingsCTL implements three surfaces for one Things command service: a CLI, a local MCP plugin, and a Things-inspired Codex workspace. Things remains the task store. The v0.1 code is present; the native disposable fixture flow and installation pass. Host tools are available, and the live MCP App rendered in the conversation side panel. Global sidebar launching and selected-task attachments remain unverified.

## Deliverables

- Public [GitHub repository](https://github.com/kianhub/thingsctl), with an MIT license.
- Python command core and CLI, bounded reads/search, operation receipts, revision checks, and mutation verification.
- Swift automation bridge and compiled AppleScript adapter using the public Things interface.
- Stdio MCP server, global and thread workspace entrypoints, structured settings, and portable local plugin manifests.
- Bundled React/TypeScript workspace, installer, uninstaller, recovery logic, and dependency notices.

The original demo is preserved in `ui/things-workspace-concept.html`. The connected app source is in `ui/src/`, with a self-contained build at `ui/dist/things-workspace.html`.

## v0.1 scope

The implemented adapter reads Inbox, Today, Upcoming, Anytime, Someday, Logbook, Trash, projects, areas, and tags. It supports bounded searches, task creation and editing, completion/cancellation/reopening, scheduling, parent moves, Trash, revealing tasks in Things, and creation of projects, areas, and tags. The fixture flow verifies task text, project membership, date/Today scheduling, Deadline set/clear, status changes, and Trash. Area/tag edits and inherited metadata remain unverified. Project-task Anytime/Someday writes are unavailable because public readback cannot confirm them; missing kinds remain unknown.

The workspace has Things-style navigation and task rows, Quick Entry, inline titles/notes/tags, separate When and Deadline controls, task IDs, pagination, search within loaded tasks, connection settings, and selected-task conversation attachments. It consumes the opener's initial result and calls the shared MCP tools for later reads and changes. Saved changes require a verified operation receipt; drafts remain visible after errors or conflicts. Uncertain writes are not automatically repeated.

Headings, checklist editing, Evening, timed reminders, recurrence authoring, arbitrary reordering, and richer Shortcuts fields remain unavailable. No Shortcuts helper or URL mutation adapter is shipped. Their appearance in an earlier concept does not imply support.

## Validation status

| Surface | Completed validation | Remaining gate |
| --- | --- | --- |
| Command core and CLI | 27 fixture tests covering validation, bounded reads, revisions, verification, and operation receipts | Native fixture flow passed; area/tag behavior remains unverified |
| MCP server | 13 tests for tool/schema behavior, structured results, resources, and plugin metadata | Installed tools are discovered and the fixture get succeeds; live workspace rendering in the side panel is verified; global sidebar launching remains unverified |
| Installer | 11 tests covering ownership, staging, supported registration commands, and recovery behavior | Installed and enabled through supported Codex commands; granted Things connection |
| Workspace | Type checks, self-contained build checks, browser interactions, conflicts/uncertainty, and light/dark layouts at 320–1024px | Full synthetic browser suite passed; the real host side panel rendered live Today data. Global sidebar launching and task attachments remain unverified |
| Native bridge | Swift build, AppleScript compilation, static validation | Granted connection and 20-check fixture flow passed; large-library/localization behavior remains unverified |

No personal task data is used as test material. The authorized integration flow reused one exact fixture project and task while fixing native semantics, then moved both to Trash. UI browser checks use synthetic demo data.

## Release gates

1. Completed: native built-in-list resolution and granted bridge Automation connection.
2. Completed: authorized disposable project/task flow for text, scheduling, Deadline set/clear, project moves, completion/cancellation/reopening, conflict rejection, MCP read, and Trash. Direct tag edits remain a separate integration check.
3. Completed installation, enabled registration, host tool discovery, and live fixture reads. The actual MCP App was opened in this conversation’s side panel and inspected with live Today data. The native ChatGPT global sidebar and selected-task context remain unverified; Computer Use of that native app is blocked, while the scoped MCP Apps surface is accessible.
4. v0.1.1 preserves app entrypoint metadata before MIME negotiation, names the global/thread launchers clearly, adds a workspace-launch skill, and keeps a successful connection when fullscreen placement is declined. Repeat relevant checks after any fixes. Record unsupported or partially verified native behaviors instead of claiming complete parity.
5. Distribute the canonical plugin ZIP and a macOS arm64 archive containing source, bundled UI/licenses, runtime, installer, and prebuilt bridge. The v0.1.2 archive is ad-hoc signed and not notarized. A native installer app and signed/stapled DMG workflow are now prepared in source; production signing and notarization remain gated on the release Mac's Developer ID certificate/private key and notarytool Keychain profile. Do not label a release notarized until all Apple acceptance, ticket, signature, and Gatekeeper checks pass.

Large-library completeness, localized list behavior, manual order, inherited tags, native edits during a save, interrupted native writes, and repeating-item behavior need focused integration evidence. Cross-app writes are not atomic transactions.

## Implemented command examples

These use the current CLI. Item placeholders must be replaced with stable IDs returned by ThingsCTL.

```sh
thingsctl doctor --json
thingsctl list today --offset 0 --limit 20 --json
thingsctl list project:PROJECT_ID --json
thingsctl search "launch" --tag Work --max-scan 20 --json
thingsctl add "Review launch brief" --when today --project PROJECT_ID --json
thingsctl update TASK_ID --notes "Review the final draft" --deadline 2026-10-09 --json
thingsctl update TASK_ID --clear-deadline --json
thingsctl complete TASK_ID --json
thingsctl show TASK_ID
thingsctl mcp serve
```

Use `--operation-id` for a durable mutation ID and `--expected-revision` for the revision returned by a prior read. Reusing an operation ID with different arguments is rejected. Install with `./install.sh`; see [installation](INSTALLATION.md) for requirements, MCP configuration, packaging, and recovery.

## Future adapters

[RemCTL](https://github.com/viticci/remctl) supplies the reference for coordinated terminal, chat, and workspace surfaces. ThingsCTL implements its own Things backend and UI.

A future documented Shortcuts adapter may add headings, checklists, Evening, reminders, and richer metadata after export serialization, query limits, and read-back are proven. Supported URL operations may complement it where their results can be verified. Do not use the live Things database or experimental properties to fill these gaps. See [capabilities](CAPABILITIES.md) and [architecture](ARCHITECTURE.md).
