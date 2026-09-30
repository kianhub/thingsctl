# Project guidance

This repository implements a v0.1 Things 3 equivalent of RemCTL with a shared command core, CLI, local MCP plugin, native automation bridge, and Things-inspired workspace. Read `docs/PLAN.md`, `docs/CAPABILITIES.md`, and `docs/DESIGN.md` before making changes.

Keep CLI, MCP, and workspace behavior behind one shared command layer. Things 3 is the source of truth.

- Use documented Things AppleScript, URL Scheme, and Shortcuts APIs.
- Do not read or write the live Things database, use private experimental properties, or request Things Cloud credentials.
- Do not inspect or change the user's personal tasks just to test. Use fixtures, then explicitly authorized disposable integration data.
- Store any Things URL auth token in macOS Keychain; redact it from diagnostics, URLs, model context, and logs.
- Treat start date, evening placement, reminder time, and deadline as distinct fields.
- Unavailable metadata must remain unknown, not empty. Do not claim a complete export if a query is truncated.
- Use stable item IDs; keep operation IDs and read-back verification for changes. Do not automatically repeat uncertain operations.
- Follow Things visual conventions in `docs/DESIGN.md` and the demo concept. Keep technical details out of the task workspace.
- Label every simulated interface as demo data until it is connected.
- Do not copy upstream RemCTL source without reviewing its license and retaining required attribution.

The retained 51-test suite, native build, and authorized disposable fixture flow pass. The plugin is installed with a granted Things connection, and its MCP tools are available in the host. Native workspace rendering and conversation attachments remain unverified because Computer Use blocks the ChatGPT app; consult `docs/PLAN.md` for current evidence. Keep the original demo clearly separate from the connected workspace.
