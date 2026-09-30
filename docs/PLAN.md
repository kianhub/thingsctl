# ThingsCTL implementation plan

Build a Things 3 equivalent of RemCTL with a CLI, a local MCP integration for AI tools, and a Things-inspired workspace inside Codex. Things remains the task store. The first release should make everyday task work reliable before expanding into richer project operations.

## Current deliverables

- Local Git repository: `/Users/kian/Developer/thingsctl`.
- Private GitHub repository: [kianhub/thingsctl](https://github.com/kianhub/thingsctl).
- Research, architecture, capability matrix, visual specification, and interactive demo concept.
- No production commands, service, or plugin are implemented yet.

## What carries over from RemCTL

Keep three coordinated surfaces and one shared behavior layer. RemCTL combines terminal commands, MCP tools, and a full Codex workspace; its UI follows Reminders. ThingsCTL should follow Things navigation, editing, and scheduling semantics. [RemCTL reference](https://github.com/viticci/remctl)

Use documented Things integrations. Core reading and task changes fit AppleScript. Richer heading and checklist work needs Shortcuts and supported URL operations. See [the capability matrix](CAPABILITIES.md) for constraints and sources.

## First release

Read Inbox, Today, Upcoming, Anytime, Someday, Logbook, projects, areas, and tags. Search supported snapshots by title, notes, tags, and membership. Create and edit tasks; change status, schedule, move, and trash tasks; reveal an item in Things. Keep stable IDs, structured JSON, bounded results, and explicit incomplete-result reporting.

Provide a Things-style Codex workspace with task rows, sidebar navigation, Quick Entry, inline notes and tags, When and Deadline controls, and selected-task conversation attachments. Headings, checklist editing, Evening, and reminders join the connected UI only when the richer adapter is proven. The demo can show the intended design in advance.

## Architecture choice

Proposed stack: Python command core and MCP server, a Swift automation host, and bundled React and TypeScript UI. Each adapter advertises field and operation capabilities. The host holds macOS Automation identity; the service verifies changes and handles uncertain outcomes. See [architecture](ARCHITECTURE.md).

## Implementation sequence

| Phase | Work | Exit criterion |
| --- | --- | --- |
| 1 Integration proof | Disposable fixture library, public AppleScript read/write, URL callbacks and auth, optional Shortcuts JSON export | Matrix of verified operations; known behavior for IDs, dates, localized lists, order, 500-item query limit, and recurrence |
| 2 Command core | Canonical model, CLI, diagnostics, adapter capability reporting, operation journal, read-back and conflicts | Supported create/edit/complete/move/trash round trip succeeds; uncertain retries cannot duplicate tasks |
| 3 AI integration | Local stdio MCP, bounded search/read, explicit mutation tools, compact task result view | AI client gets structured results and can perform a verified disposable task flow |
| 4 Codex workspace | Plugin registration, Things-style views, Quick Entry, inline editor, task attachments | Connected workspace matches Things for supported fields and makes unavailable fields clear |
| 5 Release quality | Keyboard access, light/dark and narrow layouts, performance, signing, installer, documentation | Clean install/update preserves permissions; routine task flow passes without data drift |

## Proposed command shape

These are examples for planning, not executable commands:

```sh
thingsctl doctor
thingsctl list today --json
thingsctl search "launch" --tag Work --json
thingsctl add "Review launch brief" --when today --project PROJECT_ID
thingsctl update TASK_ID --deadline 2026-10-09
thingsctl complete TASK_ID
thingsctl show TASK_ID
thingsctl mcp serve
```

## Validation and release boundaries

Start with synthetic fixtures. Live integration tests use a deliberately created disposable area/project, not the user's existing tasks. Validate separate start dates and deadlines, Evening, inherited tags, trashed/completed tasks, Unicode text, localized names, interrupted writes, native edits during save, and libraries above query limits. Test the final UI at wide and narrow widths in light and dark appearance.

Defer general recurrence creation, arbitrary manual reorder, cloud sync APIs, and Reminders-specific feature parity. Do not read/write the live database or use hidden experimental scripting properties. If Shortcuts cannot reliably export the richer model, ship the core operations and explicitly unavailable fields rather than claim full parity.

The first implementation task is the integration proof. Its result determines the exact connected UI scope and a credible implementation estimate.
