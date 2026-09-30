#!/usr/bin/env python3
"""Run only after the user authorizes a disposable Things integration project.

No task list or search is read. Only objects created by this run are edited.
The fixture project and its tasks are moved to Trash, never permanently erased.
"""
import argparse
from datetime import date, timedelta
import json
import os
from pathlib import Path
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from thingsctl_pkg.core import ThingsService
from thingsctl_pkg.host import HostClient
from thingsctl_pkg.mcp_server import MCPServer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-authorized-fixtures", action="store_true",
                        help="Confirm the human authorized this disposable live test")
    parser.add_argument("--report", type=Path, default=Path("work/live-smoke.json"))
    parser.add_argument("--resume-empty-project", action="store_true", help="Reconcile this report's existing project without repeating creation")
    parser.add_argument("--resume-existing-fixture", action="store_true", help="Reuse this report's exact existing project and task after reconciliation")
    args = parser.parse_args()
    if not args.run_authorized_fixtures:
        parser.error("This creates real Things data. Obtain explicit authorization first.")
    if os.environ.get("THINGSCTL_DEMO") == "1":
        parser.error("Unset THINGSCTL_DEMO for a live integration test")
    host, service = HostClient(), ThingsService()
    task_id = None
    if args.resume_empty_project or args.resume_existing_fixture:
        report = json.loads(args.report.read_text())
        if args.resume_empty_project and (not report.get("projectId") or report.get("taskId") or report.get("cleanup") is not None or report.get("checks", [{}])[-1].get("command") != "project_add"):
            parser.error("Only a reconciled project-only report can resume; do not repeat uncertain task creation")
        if args.resume_existing_fixture and (not report.get("projectId") or not report.get("taskId") or not report.get("fixtureTitle", "").startswith("[ThingsCTL integration ")):
            parser.error("An existing fixture report with exact project and task IDs is required")
        title = report["fixtureTitle"]
        project_id = report["projectId"]
        task_id = report.get("taskId")
        report.setdefault("previousAttempts", []).append({"checks": report["checks"], "failure": report.get("failure"), "cleanup": report.get("cleanup")})
        report["checks"], report["cleanup"] = [], None
        report.pop("failure", None)
    else:
        title = "[ThingsCTL integration " + str(uuid.uuid4()) + "]"
        report = {"fixtureTitle": title, "createdAt": time.time(), "checks": [], "cleanup": None}
        project_id = None

    def save():
        args.report.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(args.report, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w") as handle:
            json.dump(report, handle, indent=2)
            handle.write("\n")

    def call(command, arguments=None):
        before = time.monotonic()
        result = service.execute(command, arguments or {})
        check = {"command": command, "ok": result["ok"], "durationSeconds": round(time.monotonic() - before, 3)}
        if "operation" in result:
            check["operationStatus"] = result["operation"]["status"]
        if not result["ok"]:
            check["error"] = result["error"]
        report["checks"].append(check)
        save()
        if not result["ok"]:
            raise RuntimeError(command + ": " + result["error"]["code"])
        if command not in {"doctor", "get"} and result.get("operation", {}).get("status") != "verified":
            raise RuntimeError("Mutation was not verified")
        return result["data"]

    try:
        doctor = call("doctor")
        if doctor.get("connected") is not True:
            raise RuntimeError("Live Things connection is not ready")
        report["thingsVersion"] = doctor.get("thingsVersion")
        report["lists"] = doctor.get("lists")
        if project_id:
            if args.resume_existing_fixture:
                restored = host.call("fixture_restore", {"id": project_id, "title": title})["project"]
                if restored.get("status") != "open":
                    raise RuntimeError("Existing fixture project was not restored")
            project = host.call("container_get", {"kind": "project", "id": project_id})["project"]
            if project.get("title") != title:
                raise RuntimeError("Reconciled fixture identity mismatch")
            report["checks"].append({"command": "reconciled_project_readback", "ok": True})
        else:
            project = call("project_add", {"title": title, "notes": "Disposable, explicitly authorized integration fixture."})["project"]
            project_id = project["id"]
        report["projectId"] = project_id
        initial_fields = {"title": "Fixture — 日本語 🥾; \"quoted\"", "notes": "Only fixture data.\nLine two.",
                          "projectId": project_id, "when": (date.today() + timedelta(days=2)).isoformat(),
                          "deadline": (date.today() + timedelta(days=4)).isoformat()}
        if task_id:
            task = call("get", {"id": task_id})["task"]
            task = call("update", {"id": task_id, "expectedRevision": task["revision"], **initial_fields})["task"]
        else:
            task = call("add", initial_fields)["task"]
        task_id = task["id"]
        report["taskId"] = task_id
        report["projectTaskAreaId"] = task.get("areaId")
        for change in [{"title": "Fixture updated", "notes": "Verified\nUnicode ✓"}, {"when": "today"}, {"deadline": None}]:
            task = call("update", {"id": task_id, "expectedRevision": task["revision"], **change})["task"]
        # Things' public Someday collection omits children of active projects.
        # Verify those start kinds only on the same detached, owned fixture.
        task = call("move", {"id": task_id, "projectId": None, "expectedRevision": task["revision"]})["task"]
        for when in ("someday", "anytime"):
            task = call("update", {"id": task_id, "expectedRevision": task["revision"], "when": when})["task"]
        task = call("move", {"id": task_id, "projectId": project_id, "expectedRevision": task["revision"]})["task"]
        for command in ("complete", "reopen", "cancel", "reopen"):
            task = call(command, {"id": task_id, "expectedRevision": task["revision"]})["task"]
        task = call("move", {"id": task_id, "projectId": None, "expectedRevision": task["revision"]})["task"]
        task = call("move", {"id": task_id, "projectId": project_id, "expectedRevision": task["revision"]})["task"]
        conflict = service.execute("update", {"id": task_id, "title": "Must not be applied", "expectedRevision": "0" * 64})
        if conflict.get("ok") or conflict.get("error", {}).get("code") != "CONFLICT":
            raise RuntimeError("Revision conflict was not rejected")
        report["checks"].append({"command": "stale_revision", "ok": True})
        rpc = MCPServer(service)
        response = rpc.handle_message({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "thingsctl_get", "arguments": {"id": task_id}}})
        if not response.get("result", {}).get("structuredContent", {}).get("ok"):
            raise RuntimeError("MCP could not read the fixture task")
        report["checks"].append({"command": "mcp_fixture_get", "ok": True})
        call("trash", {"id": task_id, "expectedRevision": task["revision"]})
        report["passed"] = True
    except Exception as error:
        report["passed"] = False
        report["failure"] = str(error)
    finally:
        if task_id:
            try:
                current = service.execute("get", {"id": task_id})
                if not current.get("ok"):
                    raise RuntimeError("Could not confirm fixture task cleanup")
                if current["data"]["task"]["status"] != "trashed":
                    cleaned_task = service.execute("trash", {"id": task_id, "expectedRevision": current["data"]["task"]["revision"]})
                    if not cleaned_task.get("ok"):
                        raise RuntimeError("Fixture task Trash verification failed")
            except Exception as error:
                report["taskCleanupError"] = str(error)
        if project_id:
            try:
                cleaned = host.call("fixture_cleanup", {"id": project_id, "title": title})
                report["cleanup"] = "trashed" if cleaned.get("cleaned") is True and not report.get("taskCleanupError") else "needs_review"
            except Exception as error:
                report["cleanup"] = "needs_review"
                report["cleanupError"] = str(error)
        save()
    print(json.dumps({"passed": report.get("passed", False), "checks": len(report["checks"]),
                      "cleanup": report["cleanup"], "report": str(args.report.resolve())}))
    return 0 if report.get("passed") and report["cleanup"] == "trashed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
