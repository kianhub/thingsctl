# Integration capabilities

Updated September 30, 2026. The bridge connects to Things 3.24 with granted Automation permission. The same disposable project/task completed the native fixture flow after fixes; both were moved to Trash. The retained Python suite has 53 tests. The table distinguishes verified native behavior from implemented but unverified paths.

## v0.1 implementation

| Capability | Implemented path | Validation and limit |
| --- | --- | --- |
| Read tasks, projects, areas, tags, and built-in lists | AppleScript → Swift bridge → shared command service | Native built-in IDs resolve, with public-name fallback. Task ID reads are verified; full personal-library browsing is not used for tests. Public collection membership may omit nested tasks. Task commands reject project IDs; bounded source cursors skip project containers without stalling on empty pages. |
| Search tasks | Bounded supported snapshots | Title, notes, tags, status, and parent filters; pagination and incomplete-result reporting are fixture tested. This is not a complete export when limits are reached. |
| Create/edit tasks | AppleScript | Title, notes, dates, project membership, and empty tag updates verified; nonempty tag assignment remains unverified. |
| Complete, cancel, reopen | AppleScript status | Implemented with read-back verification; completion, cancellation, and reopening verified on the fixture; repeating-item consequences remain unverified. |
| Move to a project or area; detach a parent | AppleScript membership | Stable parent IDs; clearing membership is explicit. Project attachment/detachment verified; area moves remain unverified. |
| Trash tasks | AppleScript delete | Task and fixture-project Trash readback verified. No bulk container deletion or Trash restore is advertised. |
| Deadline | AppleScript `due date` | Separate date-only field; set/clear and read-back code are implemented. Native set/clear round trip verified (`delete due date` clears it). |
| Start date / Anytime / Someday | AppleScript scheduling and list placement | `when` and `whenKind` remain separate from Deadline. Date/Today verified within a project, Anytime/Someday verified on the detached fixture. Project-child missing start kinds are unknown; project Anytime/Someday writes are rejected before dispatch because native readback cannot confirm them. |
| Create projects, areas, and tags | AppleScript | Project creation/readback verified on the fixture. Area/tag creation is implemented and fixture tested. General container editing/deletion is outside v0.1. |
| Reveal a task in Things | AppleScript | Opens the native item; a reveal does not change task content. Native verification pending. |
| Things-inspired workspace | Bundled React MCP App | Browser fixtures verify project navigation, rapid switches, late replies, minimal edit payloads, controls, errors/conflicts, and light/dark layouts. The full synthetic browser suite was repeated after final native semantics fixes. Installed tools are discovered, and the live MCP App side panel rendered and was inspected with Today data. Global sidebar launching and selected-task attachments remain unverified. |
| Selected task conversation context | OpenAI Extensions model-context bridge | Implemented with explicit user selection and host capability checks. Actual Codex attachment behavior remains unverified. |

Workspace navigation and pagination retain the initial project/area/tag catalog; Refresh explicitly reloads it. Scoped task reads can omit that catalog with `includeCatalog: false`. Verified saves update the visible task directly without another full snapshot. UI requests are serialized, rapid pending navigation reads are coalesced, and replies from previous views cannot replace the current list.

The task service records available fields and adapter capabilities. Unsupported fields are rejected rather than silently cleared. An interrupted or unreadable write is uncertain, and the journal prevents automatic redispatch under the same operation ID. Revision checks detect changes observed before saving; they do not provide atomic cross-app transactions.

## Unavailable fields and operations

| Capability | v0.1 status | Future documented route or gate |
| --- | --- | --- |
| Read/edit headings and checklists | Unavailable | Public AppleScript has no heading/checklist classes. A Shortcuts helper and its export/read-back behavior would need implementation and verification. |
| Project creation with headings or checklists | Unavailable | Supported URL JSON may be useful after safe verification is available. No URL mutation adapter ships in v0.1. |
| Evening placement and timed reminders | Unavailable | Documented URL/Shortcuts interfaces expose richer scheduling, but v0.1 neither reads nor edits it. |
| Recurrence-rule authoring | Unavailable | No general creation endpoint is documented in the reviewed integrations. Repeating-item changes require separate validation. |
| Inherited tags and other richer metadata | Unavailable as distinct fields | A documented Shortcuts export may distinguish applied and inherited values. Current tags represent the AppleScript adapter's direct tag strings. |
| Arbitrary manual reordering | Unavailable | Preserve native read order; prove a supported write route before adding drag reorder. |
| Rich attachment gallery | Outside v0.1 | Selected task context is implemented; Reminders-style image attachment parity is not promised. |
| Shortcuts helper | Not implemented | JSON serialization, the 500-result query limit, partitioning, latency, and update semantics are unverified. |
| URL auth-token setup | Not implemented or required | A future URL update adapter would require a Things auth token stored in Keychain. |

## Public integration references

[Things AppleScript commands](https://culturedcode.com/things/support/articles/4562654/) document the core interface. The installed public dictionary confirms the basic task/container properties and the absence of heading or checklist classes. Hidden experimental properties are excluded.

[Things URL Scheme](https://culturedcode.com/things/support/articles/2803573/) documents richer creation and updates. URL updates require a Things auth token; checklist operations have a 100-item limit. Repeating items impose restrictions on changes to scheduling and status through that interface. Launching a URL alone is not evidence that a change was saved. These routes are future possibilities rather than v0.1 features.

[Things Shortcuts actions](https://culturedcode.com/things/support/articles/9596775/) expose richer item metadata such as heading, start date, Evening, reminder date, and checklist. Find Items returns at most 500 results. The actions require Things 3.17+ and macOS 14+. No helper or proven complete export path is included in this release.

[Third-party AI tools and Things](https://culturedcode.com/things/support/articles/5510170/) identifies AppleScript, Shortcuts, the URL scheme, and Mail to Things as supported integration routes, and cautions against direct database writes or sharing Things Cloud credentials. ThingsCTL uses documented automation and excludes live database access.
