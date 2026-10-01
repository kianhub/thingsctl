"""Protocol and input-boundary checks; all task data is synthetic."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from thingsctl_pkg.mcp_server import MCPServer, META_VERSION, META_CAPABILITIES, UI_EXTENSION, UI_URI
from thingsctl_pkg.core import ThingsService
from thingsctl_pkg.demo import DemoAdapter


class FakeService:
    def __init__(self):
        self.calls = []

    def execute(self, command, arguments=None):
        self.calls.append((command, copy.deepcopy(arguments or {})))
        if command == "doctor":
            return {"ok": True, "requestId": "fixture", "data": {"connected": False, "demo": True}, "meta": {"demo": True}}
        if command == "list":
            return {"ok": True, "requestId": "fixture", "data": {"tasks": [], "projects": [], "areas": [], "tags": [], "lists": [], "capabilities": {}, "hasMore": False}, "meta": {"demo": True}}
        return {"ok": True, "requestId": "fixture", "data": {"task": {"id": "fixture-task", "title": "Synthetic task", "revision": "r2"}}, "operation": {"id": arguments.get("operationId"), "status": "verified"}, "meta": {"demo": True}}


class MCPTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.ui = self.root / "workspace.html"
        self.ui.write_text("<!doctype html><html><body>Fixture workspace</body></html>")
        self.service = FakeService()
        self.server = MCPServer(self.service, self.ui, self.root / "settings.json")

    def tearDown(self):
        self.directory.cleanup()

    def request(self, method, params=None, modern=False):
        params = dict(params or {})
        if modern:
            params["_meta"] = {META_VERSION: "2026-07-28", META_CAPABILITIES: {"extensions": {UI_EXTENSION: {"mimeTypes": ["text/html;profile=mcp-app"]}}}}
        return self.server.handle_message({"jsonrpc": "2.0", "id": 1, "method": method, "params": params})

    def test_legacy_initialize_and_discovery_are_harmless(self):
        result = self.request("initialize", {"protocolVersion": "2025-11-25", "capabilities": {}})["result"]
        self.assertEqual(result["protocolVersion"], "2025-11-25")
        self.assertNotIn("resultType", result)
        self.assertIn("openai/settings", result["capabilities"]["extensions"])
        self.request("tools/list")
        self.request("resources/list")
        self.assertIsNone(self.server.handle_message({"jsonrpc": "2.0", "method": "notifications/initialized"}))
        self.assertEqual(self.service.calls, [])

    def test_modern_discover_is_harmless(self):
        result = self.request("server/discover", modern=True)["result"]
        self.assertEqual(result["resultType"], "complete")
        self.assertEqual(result["supportedVersions"], ["2026-07-28"])
        self.request("tools/list", modern=True)
        self.assertEqual(self.service.calls, [])

    def test_modern_requires_metadata_and_rejects_unsupported_revision(self):
        result = self.request("tools/list", {"_meta": {META_VERSION: "1900-01-01", META_CAPABILITIES: {}}})
        self.assertEqual(result["error"]["code"], -32022)
        result = self.request("tools/list", {"_meta": {META_VERSION: "2026-07-28"}})
        self.assertEqual(result["error"]["code"], -32602)

    def test_app_registration_survives_discovery_without_ui_mime_types(self):
        for capabilities in ({}, {"extensions": {UI_EXTENSION: {}}}):
            result = self.request("tools/list", {"_meta": {META_VERSION: "2026-07-28", META_CAPABILITIES: capabilities}})
            tools = {tool["name"]: tool for tool in result["result"]["tools"]}
            opener = tools["thingsctl_workspace"]["_meta"]
            self.assertEqual(opener["ui"]["resourceUri"], UI_URI)
            self.assertEqual(opener["openai/ui"]["entrypoints"], [{"type": "global"}])
            panel = tools["thingsctl_workspace_thread"]["_meta"]
            self.assertEqual(panel["openai/ui"]["entrypoints"], [{"type": "thread"}])
            self.assertEqual(panel["ui"]["visibility"], ["app"])
            self.assertEqual(tools["thingsctl_workspace_mutate"]["_meta"]["ui"]["visibility"], ["app"])
            self.assertNotIn("_meta", tools["thingsctl_list"])
        self.assertEqual(self.service.calls, [])

    def test_resource_reads_are_bounded_to_the_workspace(self):
        content = self.request("resources/read", {"uri": UI_URI}, modern=True)["result"]["contents"][0]
        self.assertIn("Fixture workspace", content["text"])
        self.assertEqual(content["mimeType"], "text/html;profile=mcp-app")
        self.assertEqual(self.request("resources/read", {"uri": "file:///etc/passwd"})["error"]["code"], -32002)

    def test_doctor_does_not_trigger_snapshot(self):
        value = self.request("tools/call", {"name": "thingsctl_doctor", "arguments": {}})["result"]
        self.assertTrue(value["structuredContent"]["ok"])
        self.assertEqual(self.service.calls, [("doctor", {})])

    def test_project_navigation_can_skip_catalog_without_resetting_its_scope(self):
        class CatalogAdapter(DemoAdapter):
            def __init__(self):
                super().__init__()
                self.catalog_scans = 0
                self.calls = []
            def call(self, command, arguments):
                self.calls.append((command, copy.deepcopy(arguments)))
                if command == "snapshot" and arguments.get("includeCatalog", True):
                    self.catalog_scans += 1
                return super().call(command, arguments)
        adapter = CatalogAdapter()
        adapter.projects.append({"id": "different-project", "title": "A different project", "areaId": None})
        adapter.tasks["demo-task-2"]["projectId"] = "different-project"
        self.server.service = ThingsService(adapter, self.root / "journal.sqlite3")
        first = self.request("tools/call", {"name": "thingsctl_workspace_snapshot", "arguments": {"view": "today"}})["result"]["structuredContent"]
        self.assertTrue(first["ok"])
        self.assertIn("projects", first["data"])
        second = self.request("tools/call", {"name": "thingsctl_workspace_snapshot", "arguments": {
            "view": "project:different-project", "includeCatalog": False}})["result"]["structuredContent"]
        self.assertTrue(second["ok"])
        self.assertEqual([task["id"] for task in second["data"]["tasks"]], ["demo-task-2"])
        self.assertEqual(second["data"]["view"], "project:different-project")
        self.assertFalse(second["data"]["catalogIncluded"])
        self.assertNotIn("projects", second["data"])
        self.assertNotIn("areas", second["data"])
        search = self.request("tools/call", {"name": "thingsctl_search", "arguments": {"query": "fictional", "maxScan": 40}})["result"]
        self.assertFalse(search["isError"])
        self.assertEqual(adapter.catalog_scans, 1)
        self.assertFalse(adapter.calls[-1][1]["includeCatalog"])

    def test_unknown_fields_and_commands_never_reach_service(self):
        for name, args in [
            ("thingsctl_doctor", {"shell": "touch /tmp/not-allowed"}),
            ("thingsctl_workspace_snapshot", {"limit": True}),
            ("thingsctl_workspace_mutate", {"command": "shell", "arguments": {}, "operationId": "op"}),
            ("thingsctl_workspace_mutate", {"command": "update", "arguments": {"id": "task", "auth-token": "never"}, "operationId": "op"}),
            ("thingsctl_add", {"title": "Fixture", "checklist": ["unsupported"]}),
        ]:
            result = self.request("tools/call", {"name": name, "arguments": args})["result"]
            self.assertTrue(result["isError"])
            self.assertEqual(result["structuredContent"]["error"]["code"], "INVALID_ARGUMENT")
        self.assertEqual(self.service.calls, [])

    def test_workspace_mutation_preserves_revision_and_operation_id(self):
        result = self.request("tools/call", {"name": "thingsctl_workspace_mutate", "arguments": {
            "command": "update", "arguments": {"id": "fixture-task", "title": "Changed"}, "operationId": "op1", "expectedRevision": "r1"}})["result"]
        self.assertFalse(result["isError"])
        self.assertEqual(self.service.calls[-1], ("update", {"id": "fixture-task", "title": "Changed", "operationId": "op1", "expectedRevision": "r1"}))
        self.assertEqual(result["structuredContent"]["operation"]["status"], "verified")

    def test_conflicting_nested_operation_is_rejected(self):
        result = self.request("tools/call", {"name": "thingsctl_workspace_mutate", "arguments": {
            "command": "complete", "arguments": {"id": "fixture-task", "operationId": "nested"}, "operationId": "outer"}})["result"]
        self.assertTrue(result["isError"])
        self.assertEqual(self.service.calls, [])

    def test_workspace_opener_returns_initial_snapshot_once(self):
        result = self.request("tools/call", {"name": "thingsctl_workspace", "arguments": {},
                                             "_meta": {META_VERSION: "2026-07-28", META_CAPABILITIES: {}}})["result"]
        self.assertTrue(result["structuredContent"]["meta"]["demo"])
        self.assertEqual(len(self.service.calls), 1)
        self.assertEqual(self.service.calls[0][0], "list")
        self.assertEqual(result["_meta"]["ui"]["resourceUri"], UI_URI)

    def test_structured_settings_are_persisted_and_bounded(self):
        result = self.request("tools/call", {"name": "thingsctl_settings_update", "arguments": {"set": {"theme": "dark", "startView": "inbox"}}})["result"]
        self.assertEqual(result["structuredContent"]["values"]["theme"], "dark")
        self.assertEqual(self.server.settings()["values"]["startView"], "inbox")
        self.assertEqual(self.root.joinpath("settings.json").stat().st_mode & 0o777, 0o600)
        result = self.request("tools/call", {"name": "thingsctl_settings_update", "arguments": {"set": {"refreshSeconds": 1}}})["result"]
        self.assertTrue(result["isError"])
        self.assertEqual(self.service.calls, [])

    def test_symlink_settings_are_refused(self):
        foreign = self.root / "foreign.json"
        foreign.write_text('{"theme":"dark"}')
        (self.root / "settings.json").symlink_to(foreign)
        result = self.request("tools/call", {"name": "thingsctl_settings_update", "arguments": {"set": {"theme": "light"}}})["result"]
        self.assertTrue(result["isError"])
        self.assertEqual(foreign.read_text(), '{"theme":"dark"}')

    def test_invalid_requests_are_errors(self):
        for message in (None, [], {"jsonrpc": "1.0", "id": 1, "method": "ping"}, {"jsonrpc": "2.0", "id": True, "method": "ping"}):
            self.assertEqual(self.server.handle_message(message)["error"]["code"], -32600)


if __name__ == "__main__":
    unittest.main()
