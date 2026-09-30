# ThingsCTL

A planned macOS CLI, AI integration, and Things 3 inspired workspace for Codex.

Inspired by [RemCTL](https://github.com/viticci/remctl). Things remains the source of truth; ThingsCTL uses documented AppleScript, URL Scheme, and optional Shortcuts integration. Independent project, not affiliated with Cultured Code.

## Status

Planning repository. The CLI, MCP server, native bridge, and Codex plugin are **not implemented**. The interactive UI preview uses fictional data and does not connect to Things.

## Project documents

- [Plan Page with interactive Things-style preview](https://chatgpt.com/space/page_392304e138e88191a4cf95560319d65b) — private to the Page owner.
- [Implementation plan](docs/PLAN.md)
- [Integration capabilities](docs/CAPABILITIES.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Visual direction](docs/DESIGN.md)
- [Interactive workspace concept](ui/things-workspace.html) — Page visualization fragment, with demo interactions only.

## Intended surfaces

1. `thingsctl`: human-readable and structured JSON commands.
2. A local MCP server: bounded reads, explicit changes, verified results.
3. A Codex plugin: Things-style navigation, task rows, inline editing, and selected-task conversation attachments.

## Development principles

Use documented automation. Never write the Things database, request Things Cloud credentials, or rely on hidden experimental AppleScript properties. Keep When and Deadline separate. Expose unavailable fields and operations honestly. Verify writes; never retry an uncertain creation automatically.

The repository was initialized at `/Users/kian/Developer/thingsctl`. See the plan before starting implementation.
