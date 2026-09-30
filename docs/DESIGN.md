# Things visual direction

Build an interface that feels at home beside Things 3. Use [Things product imagery](https://culturedcode.com/things/) as the visual reference and the interactive demo as the initial concept.

## Navigation and layout

Use a quiet gray sidebar with Inbox, Today, Upcoming, Anytime, Someday, Logbook, and Trash. Place areas and their projects below the built-in views. Use familiar colored symbols: blue inbox, yellow Today star, red calendar, teal Anytime stack, tan Someday box, green Logbook, and neutral Trash. Keep project progress understated.

The main canvas is a generous task list with system typography, subtle dividers, and wide breathing room. Use rounded square completion checkboxes. Project names and headings create structure without large cards. Today separates daytime tasks from This Evening, using a crescent. Upcoming uses dated sections.

## Task editing

Expand a selected task inline to reveal notes, checklists, tags, When, and Deadline. Notes are secondary to the title. Tags use small neutral capsules. Show date controls only where useful and keep When and Deadline distinct. Quick Entry, search, and keyboard commands should follow Things habits where feasible.

Use a compact task-result view for MCP with the same typography, checkboxes, tags, and spacing. Selected tasks can be attached to a Codex conversation once plugin integration is implemented.

## Appearance and interaction

Provide coherent light and dark appearance; preserve quiet contrast and visible keyboard focus. Reflow the sidebar into a compact navigation menu on narrow panels. Support keyboard navigation, Enter to expand, Escape to close, and Space to complete after behavior has been validated.

Keep connection status and capability details in setup or settings. Unavailable operations have a brief useful explanation. Inline changes show saving and verified completion; failures restore the prior state. Conflicts show both choices without silently overwriting native edits.

## Demo scope

`ui/things-workspace.html` is an interactive Page visualization fragment using fictional data. Navigation, expansion, and completion are demonstrations only. It does not establish that the backend supports a displayed field.
