"""Terminal surface for the same command layer used by the plugin."""

import argparse
import json
import sys

from . import __version__
from .core import ThingsService


def _formatting(parser):
    parser.add_argument("--json", action="store_true", help="Print the structured result envelope")


def _mutation(parser, revision=True):
    parser.add_argument("--operation-id", help="A durable idempotency key; reuse only for the identical operation")
    if revision:
        parser.add_argument("--expected-revision", help="Reject changes if the task changed since this revision")
    _formatting(parser)


def _editing(parser):
    parser.add_argument("--notes", help="Set notes; an empty string clears them")
    parser.add_argument("--tag", action="append", help="Replace directly applied tags with these names; repeat for more")
    parser.add_argument("--clear-tags", action="store_true")
    schedule = parser.add_mutually_exclusive_group()
    schedule.add_argument("--when", help="today, anytime, someday, or YYYY-MM-DD")
    schedule.add_argument("--clear-when", action="store_true", help="Move to Anytime")
    deadline = parser.add_mutually_exclusive_group()
    deadline.add_argument("--deadline", help="Deadline calendar date, YYYY-MM-DD")
    deadline.add_argument("--clear-deadline", action="store_true")
    placement = parser.add_mutually_exclusive_group()
    placement.add_argument("--project", dest="projectId", help="Stable project ID")
    placement.add_argument("--area", dest="areaId", help="Stable area ID")
    placement.add_argument("--inbox", action="store_true", help="Clear project and area membership")


def build_parser():
    parser = argparse.ArgumentParser(prog="thingsctl", description="Work with Things 3 through its public macOS automation API.")
    parser.add_argument("--version", action="version", version="thingsctl " + __version__)
    parser.add_argument("--json", dest="global_json", action="store_true")
    commands = parser.add_subparsers(dest="command", required=True)
    doctor = commands.add_parser("doctor", help="Check host and automation setup without reading tasks")
    _formatting(doctor)
    listing = commands.add_parser("list", help="Read a native Things view")
    listing.add_argument("view", nargs="?", default="today")
    listing.add_argument("--offset", type=int, default=0)
    listing.add_argument("--limit", type=int, default=20)
    listing.add_argument("--no-catalog", action="store_true", help="Return task rows without rescanning projects, areas, tags, and lists")
    _formatting(listing)
    search = commands.add_parser("search", help="Search a bounded Things snapshot, reporting completeness")
    search.add_argument("query")
    search.add_argument("--view", default="all")
    search.add_argument("--tag")
    search.add_argument("--project", dest="projectId")
    search.add_argument("--area", dest="areaId")
    search.add_argument("--status", choices=("open", "completed", "canceled", "trashed"))
    search.add_argument("--offset", type=int, default=0)
    search.add_argument("--limit", type=int, default=20)
    search.add_argument("--max-scan", type=int, default=20)
    _formatting(search)
    for command in ("get", "show"):
        item = commands.add_parser(command)
        item.add_argument("id")
        _formatting(item)
    add = commands.add_parser("add", help="Create and verify a task")
    add.add_argument("title")
    _editing(add)
    _mutation(add, revision=False)
    update = commands.add_parser("update", help="Edit and verify a task")
    update.add_argument("id")
    update.add_argument("--title")
    _editing(update)
    _mutation(update)
    move = commands.add_parser("move")
    move.add_argument("id")
    destination = move.add_mutually_exclusive_group(required=True)
    destination.add_argument("--project", dest="projectId")
    destination.add_argument("--area", dest="areaId")
    destination.add_argument("--inbox", action="store_true")
    _mutation(move)
    for command in ("complete", "cancel", "reopen", "trash"):
        mutation = commands.add_parser(command)
        mutation.add_argument("id")
        _mutation(mutation)
    for kind in ("project", "area", "tag"):
        container = commands.add_parser(kind)
        operations = container.add_subparsers(dest="container_command", required=True)
        create = operations.add_parser("add")
        create.add_argument("title")
        if kind == "project":
            create.add_argument("--notes")
            create.add_argument("--area", dest="areaId")
        _mutation(create, revision=False)
    mcp = commands.add_parser("mcp", help="Run the local plugin's MCP transport")
    mcp.add_subparsers(dest="mcp_command", required=True).add_parser("serve")
    return parser


def _arguments(namespace):
    values = vars(namespace)
    args = {key: value for key, value in values.items() if key in {
        "id", "title", "notes", "view", "query", "projectId", "areaId", "deadline", "when", "status", "offset", "limit"
    } and value is not None}
    for source, target in (("operation_id", "operationId"), ("expected_revision", "expectedRevision"), ("max_scan", "maxScan")):
        if values.get(source) is not None:
            args[target] = values[source]
    if namespace.command in {"add", "update"}:
        if values.get("tag") and values.get("clear_tags"):
            return None, "Use --tag or --clear-tags, not both."
        if values.get("tag"):
            args["tags"] = values["tag"]
        if values.get("clear_tags"):
            args["tags"] = []
    elif values.get("tag") is not None:
        args["tag"] = values["tag"]
    if values.get("clear_when"):
        args["when"] = "anytime"
    if values.get("clear_deadline"):
        args["deadline"] = None
    if values.get("inbox"):
        args["projectId"] = args["areaId"] = None
    if values.get("no_catalog"):
        args["includeCatalog"] = False
    return args, None


def _human(result):
    if not result["ok"]:
        error = result["error"]
        text = "{}: {}".format(error["code"], error["message"])
        if result.get("operation"):
            text += "\nOperation {} ({})".format(result["operation"]["id"], result["operation"]["status"])
        print(text, file=sys.stderr)
        return
    if result.get("meta", {}).get("demo"):
        print("Demo data — no connection to Things.")
    data = result["data"]
    if "tasks" in data:
        for task in data["tasks"]:
            print("{}  {}  [{}]".format(task["id"], task.get("title", ""), task.get("status", "unknown")))
        if not data.get("complete", True):
            print("More results exist; this is an incomplete view. Use --offset or increase --max-scan for search.")
    elif "task" in data:
        task = data["task"]
        print("{}  {}  [{}]".format(task["id"], task.get("title", ""), task.get("status", "unknown")))
        print("Revision: " + task["revision"])
    else:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    if result.get("operation"):
        print("Operation {} ({})".format(result["operation"]["id"], result["operation"]["status"]))


def main(argv=None):
    parser = build_parser()
    namespace = parser.parse_args(argv)
    if namespace.command == "mcp":
        from .mcp_server import main as serve
        return serve()
    args, error = _arguments(namespace)
    command = namespace.command + "_add" if namespace.command in {"project", "area", "tag"} else namespace.command
    result = {"ok": False, "error": {"code": "VALIDATION_ERROR", "message": error}} if error else ThingsService().execute(command, args)
    if namespace.global_json or getattr(namespace, "json", False):
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    else:
        _human(result)
    if result["ok"]:
        return 0
    return 3 if result.get("operation", {}).get("status") == "uncertain" else 1


if __name__ == "__main__":
    sys.exit(main())
