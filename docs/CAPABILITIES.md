# Integration capabilities

Reviewed September 30, 2026. The installed Things app is version 3.24. Only app metadata and its scripting dictionary were inspected; no personal task content was accessed.

The sources describe what Things exposes. Routes and release priorities below are proposed; integration behavior still needs a disposable-data proof of concept.

| Capability | Proposed route | Constraint |
| --- | --- | --- |
| Read tasks, projects, areas, tags, built-in lists | AppleScript | Preserve stable IDs and native collection order. Resolve localized list names during onboarding. |
| Create and edit basic tasks and containers | AppleScript | Core task properties, membership, tags, notes, and status. Container removal has different consequences for areas and projects. |
| Complete, cancel, reopen, move | AppleScript | Verify resulting status and membership. Repeating items need separate validation. |
| Deadline | AppleScript | `due date` represents Deadline. Schedule start dates separately. |
| Start date and basic scheduling | AppleScript `schedule`, URL Scheme | AppleScript activation date is read-only; use documented scheduling operations. |
| Evening and timed reminder | URL Scheme, optional Shortcuts | Distinct from deadline and start date. Verify through an adapter that exposes the fields. |
| Read headings and checklists | Optional Shortcuts helper | Not exposed by the public AppleScript object model. Helper export serialization is an implementation gate. |
| Create a project with headings and tasks | URL JSON | Structured creation; validate IDs and result via supported read-back. |
| Edit headings and checklists | Shortcuts or supported URL operations | Support differs by operation. URLs can replace/append checklist content; do not overwrite unread data. |
| Reveal an item or search in Things | AppleScript, URL Scheme | URL `show` and `search` navigate the native app; they do not return task data. |
| Recurrence rule authoring | Deferred | No general recurrence-rule creation endpoint is documented in the reviewed APIs. |
| Full manual reordering | Validation gate | Preserve read order; do not promise arbitrary drag reorder until a supported write path is proven. |
| Rich attachment gallery | Outside first release | Do not promise Reminders-style image attachment parity. |

AppleScript details: [Things AppleScript Commands](https://culturedcode.com/things/support/articles/4562654/). The local public dictionary also confirms no checklist or heading class. Hidden experimental properties are excluded.

URL updates require the user's Things auth token. Checklist operations allow up to 100 items. Repeating items restrict changes to when, deadline, completed, and canceled through URLs. A URL dispatch alone does not prove a saved change. [Things URL Scheme](https://culturedcode.com/things/support/articles/2803573/)

Shortcuts exposes richer item metadata, including heading, start date, evening, reminder date, and checklist. Find Items returns at most 500 results; test query partitioning and report incomplete results. These actions require Things 3.17 or newer and macOS 14 or newer. [Things Shortcuts Actions](https://culturedcode.com/things/support/articles/9596775/)

The live integration will use only documented automation. Cultured Code identifies AppleScript, Shortcuts, the URL scheme, and Mail to Things as safe routes, and warns against direct database writes and sharing Things Cloud credentials. [Third Party AI Tools and Things](https://culturedcode.com/things/support/articles/5510170/)
