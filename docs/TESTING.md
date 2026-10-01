# Verification

Run the fixture suite without connecting to Things:

```sh
python3 -m unittest discover -s tests -v
./script/build_and_run.sh --build-only
THINGSCTL_TEST_STATIC_ONLY=1 pnpm -C ui test
```

The bridge build checks typed Apple event descriptors, Unicode/quoted text, calendar dates, and input boundaries without sending an event to Things. Python tests use synthetic adapters and mocked installation commands. UI static tests check field preservation and the self-contained bundle. The browser flow exercises project changes, rapid navigation, late host replies, minimal save payloads, catalog retention/refresh, and saving while switching views. Full UI development tests use an isolated headless browser with explicitly labeled demo data:

```sh
pnpm -C ui check
pnpm -C ui build
pnpm -C ui test
```

## Disposable live integration test

Obtain the user's explicit authorization before running this command:

```sh
python3 scripts/live_smoke.py --run-authorized-fixtures
```

The script requires a connected bridge and creates one uniquely named `[ThingsCTL integration UUID]` project and one task. It reads and edits only those item IDs. It checks Unicode text, separate start date and Deadline, Today/date placement in a project and Someday/Anytime placement on the detached fixture, completion/cancellation/reopening, parent detachment and moves, revision conflicts, an MCP task read, and Trash verification.

The native bridge has a fixture-only cleanup/restore handlers, absent from the CLI and MCP tool catalogs. It verifies the exact generated project title and ID before changing that fixture project. Task cleanup separately verifies its known ID, including after detachment. The test never empties Trash. If cleanup is unconfirmed, inspect only the named fixture project; do not repeat an uncertain creation with a fresh operation ID.

Results are saved privately to `work/live-smoke.json`. They describe fixture data and test outcomes; the script does not enumerate personal task lists or export the Things library. Native fixture-only probes also verify rejection of a project ID through a task command and advancing past a skipped project source row. Native snapshots report unknown task totals plus source counts/cursors.

A passing fixture flow does not prove inherited tag behavior, localized names, recurrence, very large snapshots, or installed host rendering.

## Plugin package

Package after runtime/UI edits:

```sh
python3 scripts/package_plugin.py --output work/plugin/thingsctl --zip work/thingsctl-plugin.zip
```

Test the package from a different working directory with `THINGSCTL_DEMO=1` and a private temporary journal. Check protocol initialization/discovery, resource reads, and a synthetic mutation. Do not treat a packaged demo test as proof of a live connection.

Installed verification includes supported Codex registration, discovery of tools and entrypoints, workspace rendering, settings, selected task attachments, and the authorized native fixture flow. See [installation](INSTALLATION.md).
