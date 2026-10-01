import hashlib
import json
import os
from pathlib import Path
import plistlib
import socket
import tempfile
import threading
import unittest
from unittest.mock import patch

from thingsctl_pkg.core import ThingsService, revision_for
from thingsctl_pkg.demo import DemoAdapter
from thingsctl_pkg.errors import ThingsError
from thingsctl_pkg.host import HostClient


class RecordingAdapter(DemoAdapter):
    def __init__(self):
        super().__init__()
        self.calls = []

    def call(self, command, args):
        self.calls.append((command, args))
        return super().call(command, args)


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "operations.sqlite3"
        self.adapter = RecordingAdapter()
        self.service = ThingsService(self.adapter, self.path)
        self.task_id = "demo-task-1"

    def assert_ok(self, result):
        self.assertTrue(result["ok"], result)
        return result["data"]

    def test_doctor_does_not_read_tasks_or_create_journal(self):
        data = self.assert_ok(self.service.execute("doctor"))
        self.assertTrue(data["demo"])
        self.assertEqual(self.adapter.calls, [("doctor", {})])
        self.assertFalse(self.path.exists())

    def test_list_reports_bounded_completeness_and_revisions(self):
        original = self.adapter.call
        def source_page(command, args):
            result = original(command, args)
            if command == "snapshot":
                # The native collection includes a project before this task.
                result["tasks"] = result["tasks"][:1] if args["offset"] == 0 else []
                result.update(total=None, sourceTotal=5, sourceRowsScanned=2 if args["offset"] == 0 else 1,
                              nextOffset=2 if args["offset"] == 0 else None)
            return result
        self.adapter.call = source_page
        data = self.assert_ok(self.service.execute("list", {"view": "all", "limit": 2}))
        self.assertEqual(len(data["tasks"]), 1)
        self.assertTrue(data["hasMore"])
        self.assertFalse(data["complete"])
        self.assertEqual(data["nextOffset"], 2)
        self.assertEqual(data["sourceRowsScanned"], 2)
        self.assertIsNone(data["total"])
        self.assertRegex(data["tasks"][0]["revision"], r"^[a-f0-9]{64}$")
        data = self.assert_ok(self.service.execute("snapshot", {"view": "all", "offset": 4, "limit": 2}))
        self.assertEqual(data["tasks"], [])
        self.assertFalse(data["complete"])
        self.assertFalse(data["hasMore"])

    def test_revision_preserves_unknown_and_ignores_order_of_tags(self):
        base = {"title": "A", "tags": [{"id": "2", "title": "B"}, {"id": "1", "title": "A"}]}
        other = dict(base, tags=list(reversed(base["tags"])))
        self.assertEqual(revision_for(base), revision_for(other))
        self.assertNotEqual(revision_for(base), revision_for(dict(base, notes="")))
        self.assertEqual(revision_for(base), revision_for(dict(base, notes="", availableFields=["title", "tags"])))

    def test_revision_detects_native_today_membership_without_collection_order(self):
        task = {"title": "A", "when": None, "listIds": ["today", "anytime"]}
        self.assertEqual(revision_for(task), revision_for(dict(task, listIds=["anytime", "today"])))
        self.assertNotEqual(revision_for(task), revision_for(dict(task, listIds=["anytime"])))

    def test_today_placement_verifies_native_membership_with_unknown_start(self):
        original = self.adapter.call
        def no_activation_date(command, args):
            result = original(command, args)
            if command == "get":
                result["task"]["when"] = None
            return result
        self.adapter.call = no_activation_date
        result = self.service.execute("update", {"id": self.task_id, "when": "today"})
        self.assertEqual(result["operation"]["status"], "verified")
        self.assertIsNone(self.assert_ok(result)["task"]["when"])
        self.assertIn("today", result["data"]["task"]["listIds"])

    def test_today_start_date_alone_cannot_verify_native_placement(self):
        original = self.adapter.call
        def no_today_membership(command, args):
            result = original(command, args)
            if command == "get":
                result["task"]["listIds"] = ["anytime"]
            return result
        self.adapter.call = no_today_membership
        result = self.service.execute("update", {"id": self.task_id, "when": "today"})
        self.assertEqual(result["operation"]["status"], "uncertain")
        self.assertEqual(result["error"]["details"]["mismatchedFields"], ["listIds"])

    def test_create_verifies_schedule_separate_from_deadline_and_unicode(self):
        original = self.adapter.call
        def native_receipt(command, args):
            result = original(command, args)
            if command == "add":
                # The bridge returns identity after writing; the core reads
                # the authoritative task independently for verification.
                return {"task": {"id": result["task"]["id"]}}
            return result
        self.adapter.call = native_receipt
        result = self.service.execute("add", {"title": 'Plan café 🏔 "quoted"', "notes": 'do shell script "no"\nSecond line',
                                               "when": "2026-10-07", "deadline": "2026-10-09", "tags": ["Focus", "Focus"],
                                               "operationId": "create-dates"})
        task = self.assert_ok(result)["task"]
        self.assertEqual(task["when"], "2026-10-07")
        self.assertEqual(task["deadline"], "2026-10-09")
        self.assertEqual(task["whenKind"], "scheduled")
        self.assertEqual(task["notes"], 'do shell script "no"\nSecond line')
        self.assertEqual(result["operation"]["status"], "verified")
        self.assertEqual([command for command, _ in self.adapter.calls], ["add", "get"])
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_unreadable_optional_fields_do_not_block_text_or_allow_clearing_unknowns(self):
        original = self.adapter.call
        def partial_read(command, args):
            result = original(command, args)
            if command == "get":
                for field in ("tags", "deadline", "when", "whenKind"):
                    result["task"].pop(field, None)
                    result["task"]["availableFields"].remove(field)
                result["task"]["fieldErrors"] = {"tags": -1700, "deadline": -1700}
            return result
        self.adapter.call = partial_read
        edited = self.service.execute("update", {"id": self.task_id, "title": "Readable title", "notes": "Readable notes"})
        self.assert_ok(edited)
        self.assertEqual(edited["operation"]["status"], "verified")
        self.adapter.calls.clear()
        for changes in ({"tags": []}, {"deadline": None}, {"when": "2026-10-12"}):
            result = self.service.execute("update", dict(changes, id=self.task_id))
            self.assertEqual(result["error"]["code"], "UNSUPPORTED_FIELD")
            self.assertEqual(result["operation"]["status"], "failed")
        self.assertTrue(all(command == "get" for command, _ in self.adapter.calls))
        today = self.service.execute("update", {"id": self.task_id, "when": "today"})
        self.assert_ok(today)

        # A project task can expose its empty start date without exposing
        # its inherited scheduling kind. An explicit date is still editable.
        self.adapter.tasks[self.task_id].update(projectId="demo-project", when=None)
        def project_read(command, args):
            result = original(command, args)
            if command == "get" and result["task"]["when"] is None:
                result["task"].pop("whenKind", None)
                result["task"]["availableFields"].remove("whenKind")
            return result
        self.adapter.call = project_read
        scheduled = self.service.execute("update", {"id": self.task_id, "when": "2026-10-12"})
        self.assert_ok(scheduled)
        self.assertEqual(scheduled["operation"]["status"], "verified")
        self.assertEqual(scheduled["data"]["task"]["whenKind"], "scheduled")

    def test_identical_operation_id_replays_without_duplicate_even_after_restart(self):
        args = {"title": "One task", "operationId": "one-create"}
        first = self.service.execute("add", args)
        count = len(self.adapter.tasks)
        restarted = ThingsService(self.adapter, self.path)
        second = restarted.execute("add", args)
        self.assert_ok(second)
        self.assertEqual(first["data"], second["data"])
        self.assertTrue(second["operation"]["replayed"])
        self.assertEqual(len(self.adapter.tasks), count)
        self.assertEqual(sum(command == "add" for command, _ in self.adapter.calls), 1)
        rejected = restarted.execute("add", dict(args, title="Different task"))
        self.assertEqual(rejected["error"]["code"], "OPERATION_ID_REUSED")
        self.assertEqual(len(self.adapter.tasks), count)

    def test_conflict_returns_current_task_before_any_mutation(self):
        revision = self.assert_ok(self.service.execute("get", {"id": self.task_id}))["task"]["revision"]
        self.adapter.tasks[self.task_id]["title"] = "Changed in Things"
        result = self.service.execute("update", {"id": self.task_id, "title": "Stale save", "expectedRevision": revision})
        self.assertEqual(result["error"]["code"], "CONFLICT")
        self.assertEqual(result["error"]["details"]["task"]["title"], "Changed in Things")
        self.assertEqual(result["operation"]["status"], "failed")
        self.assertNotIn("update", [command for command, _ in self.adapter.calls])

    def test_create_timeout_is_uncertain_and_identical_retry_never_dispatches(self):
        original = self.adapter.call
        def timed_out(command, args):
            result = original(command, args)
            if command == "add":
                raise ThingsError("MUTATION_UNCERTAIN", "Interrupted response.", uncertain=True)
            return result
        self.adapter.call = timed_out
        args = {"title": "Already sent", "operationId": "uncertain-create"}
        first = self.service.execute("add", args)
        second = self.service.execute("add", args)
        self.assertFalse(first["ok"])
        self.assertEqual(first["operation"]["status"], "uncertain")
        self.assertTrue(second["operation"]["replayed"])
        self.assertEqual(sum(command == "add" for command, _ in self.adapter.calls), 1)

    def test_invalid_native_response_after_creation_is_uncertain(self):
        original = self.adapter.call
        def invalid_response(command, args):
            result = original(command, args)
            if command == "add":
                raise ThingsError("INVALID_RESPONSE", "Things returned an unexpected result")
            return result
        self.adapter.call = invalid_response
        result = self.service.execute("add", {"title": "Already created", "operationId": "invalid-create-response"})
        self.assertFalse(result["ok"])
        self.assertEqual(result["operation"]["status"], "uncertain")

    def test_pending_receipt_after_process_interruption_blocks_dispatch(self):
        args = {"title": "Interrupted", "operationId": "pending-create"}
        digest = hashlib.sha256(json.dumps({"command": "add", "arguments": {"title": "Interrupted"}, "adapter": self.service._meta()},
                                           sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        self.service.journal.begin("pending-create", digest)
        result = self.service.execute("add", args)
        self.assertEqual(result["operation"]["status"], "uncertain")
        self.assertEqual(self.adapter.calls, [])

    def test_demo_operation_receipt_cannot_be_replayed_as_a_native_change(self):
        args = {"title": "Demo only", "operationId": "adapter-specific"}
        self.assert_ok(self.service.execute("add", args))
        native = RecordingAdapter()
        native.demo = False
        native.name = "applescript"
        result = ThingsService(native, self.path).execute("add", args)
        self.assertEqual(result["error"]["code"], "OPERATION_ID_REUSED")
        self.assertFalse(result["meta"]["demo"])
        self.assertEqual(native.calls, [])

    def test_readback_failure_is_uncertain_not_success(self):
        original = self.adapter.call
        def incorrect(command, args):
            result = original(command, args)
            if command == "get" and any(name == "update" for name, _ in self.adapter.calls):
                result["task"]["deadline"] = None
            return result
        self.adapter.call = incorrect
        result = self.service.execute("update", {"id": self.task_id, "deadline": "2026-10-09"})
        self.assertEqual(result["error"]["code"], "VERIFICATION_FAILED")
        self.assertEqual(result["operation"]["status"], "uncertain")
        self.assertEqual(result["error"]["details"]["mismatchedFields"], ["deadline"])

    def test_missing_schedule_kind_rejects_before_writing(self):
        original = self.adapter.call
        def limited(command, args):
            result = original(command, args)
            if command == "get":
                result["task"].pop("whenKind")
                result["task"]["availableFields"].remove("whenKind")
            return result
        self.adapter.call = limited
        result = self.service.execute("update", {"id": "demo-task-2", "when": "someday"})
        self.assertEqual(result["error"]["code"], "UNSUPPORTED_FIELD")
        self.assertEqual(result["operation"]["status"], "failed")
        self.assertNotIn("update", [command for command, _ in self.adapter.calls])

    def test_validation_and_unavailable_fields_never_dispatch(self):
        cases = [("add", {"title": ""}), ("add", {"title": "A", "deadline": "2026-02-30"}),
                 ("add", {"title": "A", "when": "2026-10-01T18:00:00Z"}),
                 ("update", {"id": self.task_id}), ("update", {"id": self.task_id, "checklist": []}),
                 ("list", {"limit": True}), ("move", {"id": self.task_id, "projectId": "a", "areaId": "b"}),
                 ("update", {"id": self.task_id, "notes": "N", "expectedRevision": "wrong"}),
                 ("add", {"title": "A", "tags": ["One, Two"]}), ("add", {"title": "A" * 1001})]
        for command, args in cases:
            result = self.service.execute(command, args)
            self.assertFalse(result["ok"], result)
        self.assertEqual(self.adapter.calls, [])
        self.assertFalse(self.path.exists())

    def test_clear_fields_preserves_unmentioned_deadline(self):
        self.adapter.tasks[self.task_id]["deadline"] = "2026-10-09"
        task = self.assert_ok(self.service.execute("update", {"id": self.task_id, "notes": None, "tags": [], "when": None, "projectId": None}))["task"]
        self.assertEqual(task["notes"], "")
        self.assertEqual(task["tags"], [])
        self.assertEqual(task["whenKind"], "anytime")
        self.assertEqual(task["deadline"], "2026-10-09")

    def test_search_truncation_filters_and_pagination_are_explicit(self):
        original = self.adapter.call
        def source_page(command, args):
            if command != "snapshot":
                return original(command, args)
            result = original(command, dict(args, offset=0, limit=500))
            # A full source page can contain only project containers. Search
            # must consume that page and continue using the native cursor.
            source = [None] * 20 + result["tasks"]
            offset, limit = args["offset"], args["limit"]
            page = source[offset:offset + limit]
            has_more = offset + len(page) < len(source)
            result.update(tasks=[task for task in page if task is not None], total=None,
                          sourceTotal=len(source), sourceRowsScanned=len(page), hasMore=has_more,
                          nextOffset=offset + len(page) if has_more else None)
            return result
        self.adapter.call = source_page
        truncated = self.assert_ok(self.service.execute("search", {"query": "", "maxScan": 2}))
        self.assertFalse(truncated["complete"])
        self.assertIsNone(truncated["total"])
        self.assertEqual(truncated["scanned"], 2)
        self.assertEqual(truncated["tasks"], [])
        self.assertFalse(truncated["hasMore"])
        self.assertTrue(truncated["sourceHasMore"])
        result = self.assert_ok(self.service.execute("search", {"query": "FICTIONAL", "tag": "focus", "limit": 1, "offset": 1, "maxScan": 40}))
        self.assertTrue(result["complete"])
        self.assertEqual(result["total"], 3)
        self.assertEqual(len(result["tasks"]), 1)
        self.assertTrue(result["hasMore"])
        self.assertEqual(result["scanned"], result["sourceTotal"])

    def test_symlink_journal_rejected(self):
        target = Path(self.temp.name) / "target"
        target.touch()
        self.path.symlink_to(target)
        result = self.service.execute("add", {"title": "A"})
        self.assertEqual(result["error"]["code"], "UNSAFE_JOURNAL")
        self.assertEqual(self.adapter.calls, [])


class HostTests(unittest.TestCase):
    def setUp(self):
        # macOS Unix sockets need a short pathname.
        self.temp = tempfile.TemporaryDirectory(dir="/tmp")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "bridge.sock"

    def serve_once(self, response):
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(str(self.path))
        os.chmod(self.path, 0o600)
        server.listen(1)
        request = []
        def serve():
            try:
                with server.accept()[0] as connection:
                    request.append(json.loads(connection.recv(65536)))
                    if response is not None:
                        connection.sendall(json.dumps(response).encode() + b"\n")
            finally:
                server.close()
        worker = threading.Thread(target=serve)
        worker.start()
        self.addCleanup(worker.join, 2)
        return request

    def test_structured_transport_preserves_text(self):
        request = self.serve_once({"ok": True, "data": {"task": {"id": "id"}}})
        data = HostClient(self.path).call("add", {"title": 'Text "quoted" 🏔', "notes": "line one\nline two"})
        self.assertEqual(data["task"]["id"], "id")
        self.assertEqual(request[0]["arguments"]["notes"], "line one\nline two")

    def test_interrupted_creation_is_uncertain(self):
        self.serve_once(None)
        with self.assertRaises(ThingsError) as caught:
            HostClient(self.path).call("add", {"title": "One"})
        self.assertTrue(caught.exception.uncertain)

    def test_unsafe_socket_rejected_before_connection(self):
        self.path.touch()
        with self.assertRaises(ThingsError) as caught:
            HostClient(self.path).call("doctor", {})
        self.assertEqual(caught.exception.code, "UNSAFE_SOCKET")

    def test_autostart_rejects_foreign_or_writable_bundles(self):
        app = Path(self.temp.name) / "Applications/ThingsCTL Bridge.app"
        (app / "Contents/MacOS").mkdir(parents=True)
        executable = app / "Contents/MacOS/ThingsCTLBridge"
        executable.touch()
        executable.chmod(0o700)
        metadata = app / "Contents/Info.plist"
        metadata.write_bytes(plistlib.dumps({"CFBundleIdentifier": "other.app", "CFBundleExecutable": "ThingsCTLBridge"}))
        client = HostClient(self.path)
        client.autostart = True
        with patch("thingsctl_pkg.host.Path.home", return_value=Path(self.temp.name)), \
                patch("thingsctl_pkg.host.sys.platform", "darwin"), \
                patch("thingsctl_pkg.host.subprocess.run") as launch:
            self.assertFalse(client._start_installed_host())
            metadata.write_bytes(plistlib.dumps({"CFBundleIdentifier": "com.kianhub.thingsctl.bridge", "CFBundleExecutable": "ThingsCTLBridge"}))
            executable.chmod(0o777)
            self.assertFalse(client._start_installed_host())
            launch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
