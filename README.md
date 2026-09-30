# ThingsCTL

A macOS CLI, local MCP plugin, and Things 3 inspired workspace for Codex. Inspired by [RemCTL](https://github.com/viticci/remctl), with the same command service behind terminal, chat, and workspace actions. Independent project; not affiliated with Cultured Code.

Things is the task store. The v0.1 implementation uses its documented AppleScript interface through a small native automation bridge. It does not access the Things database or require Things Cloud credentials.

## Status

The CLI, shared command service, native Swift bridge, local MCP plugin, installer, and bundled Things-style workspace are implemented. The authorized disposable fixture flow passes against Things 3.24: Unicode editing, scheduling, Deadline set/clear, parent moves, completion, cancellation, reopening, conflict rejection, MCP reads, and Trash verification. The fixture project and task were moved to Trash afterward.

The retained Python suite has 51 tests: 27 for the core/host/CLI, 13 for MCP, and 11 for installation. Redundant happy-path and literal-value assertions have been removed. UI verification uses synthetic fixtures. Actual installation and host tool discovery are verified; native workspace rendering and conversation attachments remain unverified because Computer Use blocks ChatGPT’s native window. The development bridge is ad-hoc signed and not notarized.

Synthetic results are clearly marked as demo data. A failed live connection never falls back to fictional tasks.

## Install

With Things 3, Python 3.9+, Xcode Command Line Tools, and a recent Codex CLI installed:

```sh
./install.sh
```

For the prebuilt macOS arm64 archive from [v0.1.0](https://github.com/kianhub/thingsctl/releases/tag/v0.1.0), use `./install.sh --skip-build`. It includes the bridge and needs no Swift build tools.

The installer builds the bridge, installs the `thingsctl` launcher, stages the local plugin, and registers it through supported Codex CLI commands. The bundled HTML removes the need for Node.js on an end-user installation. Allow **ThingsCTL Bridge** to control Things when macOS asks for Automation access. See [installation, permissions, packaging, and recovery](docs/INSTALLATION.md).

Open the plugin's **Things** entrypoint or **Task workspace** tab in Codex. The workspace includes native list navigation, areas and projects, Quick Entry, inline editing, When and Deadline controls, selected-task conversation attachments, and connection settings. The plugin is installed and enabled on the development Mac. Host rendering and attachment behavior remain unverified; browser fixture tests do not establish that integration.

## Commands

These commands are implemented. `TASK_ID` and `PROJECT_ID` refer to IDs returned by ThingsCTL; the examples operate on the connected local Things app.

```sh
thingsctl doctor --json
thingsctl list today --limit 20 --json
thingsctl search "launch" --tag Work --json
thingsctl get TASK_ID --json
thingsctl add "Review launch brief" --when today --project PROJECT_ID --json
thingsctl update TASK_ID --deadline 2026-10-09 --json
thingsctl complete TASK_ID --json
thingsctl show TASK_ID
thingsctl mcp serve
```

`list` supports Inbox, Today, Upcoming, Anytime, Someday, Logbook, Trash, and project or area views. `search` reports bounded results and completeness. Other commands include cancel, reopen, move, trash, and creation of projects, areas, and tags. Use `thingsctl --help` and the relevant subcommand's `--help` for options.

Writes carry operation IDs, compare revisions when supplied, and use read-back verification. Results distinguish verified, failed, and uncertain operations. An uncertain operation is not automatically repeated; retain its ID while checking the current task.

## Scope

The implemented AppleScript adapter covers titles, notes, directly applied tags, status, project/area membership, start dates, and deadlines. When and Deadline remain separate fields. The fixture flow verifies task text, status, project moves, scheduling, and Deadline changes; direct tag edits and area/tag creation are implemented but have not had a live round trip.

AppleScript omits active-project children from its Someday collection. Missing start kinds stay unknown; Anytime/Someday changes for tasks inside projects are rejected before writing. Today and date scheduling remain available. Set project-task Anytime/Someday in Things until a documented richer adapter is added. Built-in collections preserve the public automation interface’s membership; they are not promised to flatten every nested task.

List pages and default search scans consume at most 20 source rows, skipping project containers. Source cursors advance even when a page returns no tasks. Native total task count remains unknown until a complete bounded traversal. Search reports incomplete results when the scan bound is reached; higher scans are explicit. Automatic workspace refresh waits 120 seconds and avoids overlapping loads.

Headings, checklists, Evening, timed reminders, recurrence authoring, arbitrary reordering, richer Shortcuts metadata, and a Shortcuts helper are unavailable. No URL Scheme mutation adapter or URL auth-token setup is included in v0.1. The plugin provides selected task context, rather than a Reminders-style attachment gallery.

## Project documents

- [GitHub repository](https://github.com/kianhub/thingsctl)
- [Private plan Page with the original interactive preview](https://chatgpt.com/space/page_392304e138e88191a4cf95560319d65b)
- [Implementation and validation plan](docs/PLAN.md)
- [Integration capabilities](docs/CAPABILITIES.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Visual direction](docs/DESIGN.md)
- [Original workspace concept](ui/things-workspace-concept.html), using fictional data

The repository lives at `/Users/kian/Developer/thingsctl`. Production workspace source is in `ui/src/`; its self-contained build is `ui/dist/things-workspace.html`. Full licenses for bundled dependencies are in `ui/THIRD-PARTY-NOTICES.txt`.
