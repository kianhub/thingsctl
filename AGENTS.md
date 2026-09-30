# Project guidance

This is a planning repository for a Things 3 equivalent of RemCTL. Read `docs/PLAN.md`, `docs/CAPABILITIES.md`, and `docs/DESIGN.md` before implementation.

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

This initial repository contains a plan and UI concept, not a working integration.
