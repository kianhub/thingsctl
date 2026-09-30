"""One validation, conflict, and mutation path for every ThingsCTL surface."""

from copy import deepcopy
from datetime import date
import hashlib
import json
import os
import re
import uuid

from .demo import DemoAdapter
from .errors import ThingsError
from .host import HostClient, MUTATIONS
from .journal import OperationJournal


BUILT_IN_VIEWS = {"today", "inbox", "upcoming", "anytime", "someday", "logbook", "trash", "all"}
EDITABLE_FIELDS = ("title", "notes", "status", "when", "whenKind", "deadline", "projectId", "areaId", "tags", "listIds")
UNAVAILABLE_FIELDS = {"checklist", "checklistItems", "heading", "headingId", "evening", "reminderAt", "recurrence", "order"}
CONTROL_KEYS = {"operationId", "expectedRevision"}
TASK_EDIT_KEYS = {"title", "notes", "when", "deadline", "projectId", "areaId", "tags"}
COMMAND_KEYS = {
    "doctor": set(), "list": {"view", "offset", "limit"},
    "search": {"query", "view", "tag", "projectId", "areaId", "status", "offset", "limit", "maxScan"},
    "get": {"id"}, "show": {"id"} | CONTROL_KEYS, "add": TASK_EDIT_KEYS | {"operationId"},
    "update": TASK_EDIT_KEYS | CONTROL_KEYS | {"id"},
    "move": {"projectId", "areaId", "id"} | CONTROL_KEYS,
    "complete": {"id"} | CONTROL_KEYS, "cancel": {"id"} | CONTROL_KEYS,
    "reopen": {"id"} | CONTROL_KEYS, "trash": {"id"} | CONTROL_KEYS,
    "project_add": {"title", "notes", "areaId", "operationId"},
    "area_add": {"title", "operationId"}, "tag_add": {"title", "operationId"},
}


def revision_for(task):
    """Revision of exposed editable fields, preserving unavailable-vs-empty."""
    fields = task.get("availableFields")
    canonical = {}
    for key in EDITABLE_FIELDS:
        if key in task and (fields is None or key in fields):
            value = task[key]
            if key == "tags" and isinstance(value, list):
                value = sorted(({"id": tag.get("id"), "title": tag.get("title")} for tag in value),
                               key=lambda tag: (str(tag["id"]), str(tag["title"])))
            if key == "listIds" and isinstance(value, list):
                value = sorted(set(value))
            canonical[key] = value
    return hashlib.sha256(json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _date(value, name):
    if value is None:
        return value
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ThingsError("VALIDATION_ERROR", name + " must be a calendar date in YYYY-MM-DD format.")
    try:
        date.fromisoformat(value)
    except ValueError:
        raise ThingsError("VALIDATION_ERROR", name + " must be a valid calendar date.")
    return value


def _text(value, name, empty=False, max_length=100000):
    if not isinstance(value, str) or (not empty and not value.strip()) or "\x00" in value or len(value) > max_length:
        raise ThingsError("VALIDATION_ERROR", name + " must be " + ("text" if empty else "nonempty text") + ".")
    return value


def _integer(value, name, low, high):
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ThingsError("VALIDATION_ERROR", "{} must be an integer from {} to {}.".format(name, low, high))
    return value


def _validate_project_start(args, current_project=None):
    project_id = args["projectId"] if "projectId" in args else current_project
    if args.get("when") in {"anytime", "someday"} and project_id:
        raise ThingsError("UNSUPPORTED_FIELD", "Set Anytime or Someday in Things for tasks inside projects.",
                          {"fields": ["when"], "reason": "project_start_kind_unavailable"})


def _validate(command, arguments):
    if command not in COMMAND_KEYS:
        raise ThingsError("UNKNOWN_COMMAND", "Unknown ThingsCTL command.")
    if not isinstance(arguments, dict):
        raise ThingsError("VALIDATION_ERROR", "Arguments must be a JSON object.")
    args = deepcopy(arguments)
    unavailable = set(args) & UNAVAILABLE_FIELDS
    if unavailable:
        raise ThingsError("UNSUPPORTED_FIELD", "This adapter cannot safely read or edit the requested field.", {"fields": sorted(unavailable)})
    unknown = set(args) - COMMAND_KEYS[command]
    if unknown:
        raise ThingsError("VALIDATION_ERROR", "Unexpected command arguments.", {"fields": sorted(unknown)})
    for key in ("id", "projectId", "areaId"):
        if key in args and args[key] is not None:
            _text(args[key], key, max_length=256)
    if "id" in COMMAND_KEYS[command] and not args.get("id"):
        raise ThingsError("VALIDATION_ERROR", "A stable Things item ID is required.")
    if command in {"add", "project_add", "area_add", "tag_add"} and "title" not in args:
        raise ThingsError("VALIDATION_ERROR", "A title is required.")
    if "title" in args:
        _text(args["title"], "title", max_length=1000)
    if "notes" in args:
        args["notes"] = "" if args["notes"] is None else _text(args["notes"], "notes", empty=True)
    if "tags" in args:
        if not isinstance(args["tags"], list) or len(args["tags"]) > 100:
            raise ThingsError("VALIDATION_ERROR", "tags must be an array of at most 100 tag names.")
        for tag in args["tags"]:
            _text(tag, "tag", max_length=256)
            if "," in tag:
                raise ThingsError("VALIDATION_ERROR", "Tag names cannot contain commas through the AppleScript adapter.")
        args["tags"] = list(dict.fromkeys(args["tags"]))
    if "when" in args:
        if args["when"] is None:
            args["when"] = "anytime"
        if args["when"] not in ("today", "anytime", "someday"):
            _date(args["when"], "when")
    if "deadline" in args:
        _date(args["deadline"], "deadline")
    if args.get("projectId") and args.get("areaId"):
        raise ThingsError("VALIDATION_ERROR", "Choose a project or an area as the destination.")
    _validate_project_start(args)
    if "operationId" in args:
        _text(args["operationId"], "operationId", max_length=128)
    if "expectedRevision" in args:
        if not isinstance(args["expectedRevision"], str) or not re.fullmatch(r"[0-9a-f]{64}", args["expectedRevision"]):
            raise ThingsError("VALIDATION_ERROR", "expectedRevision must be a task revision returned by ThingsCTL.")
    if command == "update" and not set(args) & TASK_EDIT_KEYS:
        raise ThingsError("VALIDATION_ERROR", "Provide at least one task field to update.")
    if command == "move" and not set(args) & {"projectId", "areaId"}:
        raise ThingsError("VALIDATION_ERROR", "Provide projectId or areaId; use null to clear the destination.")
    if command in {"list", "search"}:
        view = args.setdefault("view", "all" if command == "search" else "today")
        if not isinstance(view, str) or not (view in BUILT_IN_VIEWS or re.fullmatch(r"(?:project|area):[^\x00]{1,256}", view)):
            raise ThingsError("VALIDATION_ERROR", "view must name a built-in view, project:<id>, or area:<id>.")
        _integer(args.setdefault("offset", 0), "offset", 0, 1000000)
        _integer(args.setdefault("limit", 20), "limit", 1, 500)
    if command == "search":
        _text(args.setdefault("query", ""), "query", empty=True, max_length=10000)
        if "tag" in args:
            _text(args["tag"], "tag", max_length=256)
        if "status" in args and args["status"] not in {"open", "completed", "canceled", "trashed"}:
            raise ThingsError("VALIDATION_ERROR", "status must be open, completed, canceled, or trashed.")
        _integer(args.setdefault("maxScan", 20), "maxScan", 1, 50000)
    return args


class ThingsService:
    def __init__(self, adapter=None, journal_path=None):
        self.adapter = adapter or (DemoAdapter() if os.environ.get("THINGSCTL_DEMO") == "1" else HostClient())
        self.journal_path = journal_path
        self._journal = None

    @property
    def journal(self):
        if self._journal is None:
            self._journal = OperationJournal(self.journal_path)
        return self._journal

    def _meta(self):
        return {"demo": bool(getattr(self.adapter, "demo", False)), "adapter": getattr(self.adapter, "name", "custom")}

    @staticmethod
    def _task(task):
        if not isinstance(task, dict) or not task.get("id"):
            raise ThingsError("HOST_PROTOCOL", "The adapter returned no stable task ID.")
        result = deepcopy(task)
        result["revision"] = revision_for(result)
        return result

    def execute(self, command, arguments=None):
        request_id = str(uuid.uuid4())
        operation_id, journaled, dispatched, write_returned = None, False, False, False
        command = "list" if command == "snapshot" else command
        try:
            args = _validate(command, {} if arguments is None else arguments)
            if command not in MUTATIONS:
                data = self._read(command, args)
                return {"ok": True, "requestId": request_id, "data": data, "meta": self._meta()}
            operation_id = args.get("operationId") or str(uuid.uuid4())
            inputs = {key: value for key, value in args.items() if key != "operationId"}
            digest = hashlib.sha256(json.dumps({"command": command, "arguments": inputs, "adapter": self._meta()}, ensure_ascii=False,
                                               sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
            receipt = self.journal.begin(operation_id, digest)
            if receipt is not None:
                receipt = deepcopy(receipt)
                receipt["requestId"] = request_id
                receipt.setdefault("operation", {})["replayed"] = True
                return receipt
            journaled = True
            if args.get("id"):
                before = self._task(self.adapter.call("get", {"id": args["id"]}).get("task"))
                if args.get("expectedRevision") and args["expectedRevision"] != before["revision"]:
                    raise ThingsError("CONFLICT", "This task changed in Things since you loaded it. Reload the task before saving.",
                                      {"expectedRevision": args["expectedRevision"], "actualRevision": before["revision"], "task": before})
                _validate_project_start(args, before.get("projectId"))
            host_args = {key: value for key, value in args.items() if key not in CONTROL_KEYS}
            dispatched = True
            changed = self.adapter.call(command, host_args)
            write_returned = True
            verified = self._verify(command, host_args, changed)
            result = {"ok": True, "requestId": request_id, "data": verified, "meta": self._meta(),
                      "operation": {"id": operation_id, "status": "verified"}}
            self.journal.finish(operation_id, "verified", result)
            return result
        except ThingsError as error:
            uncertain = write_returned or error.uncertain or (dispatched and error.code in {"HOST_PROTOCOL", "INVALID_RESPONSE", "VERIFICATION_FAILED", "VERIFICATION_UNAVAILABLE", "HOST_UNAVAILABLE"})
            status = "uncertain" if uncertain else "failed"
            result = {"ok": False, "requestId": request_id, "error": error.as_dict(), "meta": self._meta()}
            if operation_id:
                result["operation"] = {"id": operation_id, "status": status}
            if journaled:
                try:
                    self.journal.finish(operation_id, status, result)
                except Exception:
                    result["operation"]["status"] = "uncertain"
                    result["error"] = {"code": "JOURNAL_UNAVAILABLE", "message": "The operation receipt could not be saved. Check Things before repeating the change."}
            return result
        except Exception:
            status = "uncertain" if dispatched else "failed"
            result = {"ok": False, "requestId": request_id, "error": {"code": "INTERNAL_ERROR",
                      "message": "ThingsCTL could not finish the request." + (" Check Things before repeating this change." if dispatched else "")},
                      "meta": self._meta()}
            if operation_id:
                result["operation"] = {"id": operation_id, "status": status}
            if journaled:
                try:
                    self.journal.finish(operation_id, status, result)
                except Exception:
                    pass
            return result

    def _read(self, command, args):
        if command == "list":
            data = self._snapshot(args)
            data["tasks"] = [self._task(task) for task in data["tasks"]]
            data["complete"] = not data.get("hasMore", True) and args["offset"] == 0
            data.setdefault("view", args["view"])
            return data
        if command == "search":
            return self._search(args)
        data = deepcopy(self.adapter.call(command, {key: value for key, value in args.items() if key not in CONTROL_KEYS}))
        if command == "get":
            data["task"] = self._task(data.get("task"))
        return data

    def _snapshot(self, args):
        data = deepcopy(self.adapter.call("snapshot", args))
        if not isinstance(data, dict) or not isinstance(data.get("tasks"), list) or not isinstance(data.get("hasMore"), bool):
            raise ThingsError("HOST_PROTOCOL", "The adapter returned an incomplete snapshot envelope.")
        offset, limit = args["offset"], args["limit"]
        cursor = data.get("nextOffset")
        consumed = data.get("sourceRowsScanned")
        if consumed is None:
            consumed = cursor - offset if isinstance(cursor, int) and not isinstance(cursor, bool) else len(data["tasks"])
        if isinstance(consumed, bool) or not isinstance(consumed, int) or not len(data["tasks"]) <= consumed <= limit:
            raise ThingsError("HOST_PROTOCOL", "The adapter returned an invalid source row count.")
        if data["hasMore"]:
            if "nextOffset" not in data:
                cursor = offset + consumed
            if isinstance(cursor, bool) or not isinstance(cursor, int) or cursor != offset + consumed or consumed == 0:
                raise ThingsError("HOST_PROTOCOL", "The adapter returned a source cursor that cannot advance.")
        elif cursor is not None:
            raise ThingsError("HOST_PROTOCOL", "The adapter returned a cursor after the final source page.")
        data["sourceRowsScanned"] = consumed
        data["nextOffset"] = cursor
        return data

    def _search(self, args):
        matches, scanned, has_more, total_source, seen = [], 0, True, None, set()
        source_offset = 0
        query = args["query"].casefold()
        while has_more and scanned < args["maxScan"]:
            snapshot = self._snapshot({"view": args["view"], "offset": source_offset,
                                       "limit": min(20, args["maxScan"] - scanned)})
            tasks = snapshot["tasks"]
            total_source = snapshot.get("sourceTotal", snapshot.get("total"))
            has_more = snapshot["hasMore"]
            for task in tasks:
                if task.get("id") in seen:
                    continue
                seen.add(task.get("id"))
                tags = [tag.get("title", "") for tag in task.get("tags", [])]
                text = "\n".join([str(task.get("title", "")), str(task.get("notes", ""))] + tags).casefold()
                if query and query not in text:
                    continue
                if args.get("tag") and args["tag"].casefold() not in [tag.casefold() for tag in tags]:
                    continue
                if any(args.get(key) and task.get(key) != args[key] for key in ("projectId", "areaId", "status")):
                    continue
                matches.append(self._task(task))
            scanned += snapshot["sourceRowsScanned"]
            if has_more:
                source_offset = snapshot["nextOffset"]
        offset, limit = args["offset"], args["limit"]
        incomplete = bool(has_more)
        page = matches[offset:offset + limit]
        more_matches = offset + limit < len(matches)
        return {"tasks": page, "total": None if incomplete else len(matches),
                "matchedInScan": len(matches), "scanned": scanned, "sourceTotal": total_source,
                "offset": offset, "limit": limit, "hasMore": more_matches, "sourceHasMore": incomplete,
                "nextOffset": offset + len(page) if more_matches else None,
                "complete": not incomplete, "view": args["view"]}

    def _verify(self, command, args, changed):
        if command in {"project_add", "area_add", "tag_add"}:
            kind = command.split("_")[0]
            container = changed.get(kind)
            if not isinstance(container, dict) or not container.get("id"):
                raise ThingsError("VERIFICATION_UNAVAILABLE", "The new item's ID was not returned. Check Things before repeating the change.", uncertain=True)
            identity = {"kind": kind, "id": container["id"]}
            try:
                readback = self.adapter.call("container_get", identity)
                observed = readback.get(kind) if isinstance(readback, dict) else None
            except ThingsError as error:
                raise ThingsError("VERIFICATION_UNAVAILABLE", "The new item was created, but Things could not confirm its saved state. Check Things before repeating the change.",
                                  dict(identity, cause=error.code), uncertain=True)
            if not isinstance(observed, dict) or observed.get("id") != container["id"]:
                raise ThingsError("VERIFICATION_UNAVAILABLE", "Things returned no matching item for verification. Check Things before repeating the change.", identity, uncertain=True)
            if any(observed.get(key) != value for key, value in args.items() if key in {"title", "notes", "areaId"}):
                raise ThingsError("VERIFICATION_FAILED", "Things did not confirm the new item's fields. Check Things before repeating the change.", identity, uncertain=True)
            return {kind: deepcopy(observed)}
        task = changed.get("task")
        item_id = task.get("id") if isinstance(task, dict) else args.get("id")
        if not item_id:
            raise ThingsError("VERIFICATION_UNAVAILABLE", "Things returned no task ID for verification. Check Things before repeating the change.", uncertain=True)
        try:
            observed = self._task(self.adapter.call("get", {"id": item_id}).get("task"))
        except ThingsError as error:
            raise ThingsError("VERIFICATION_UNAVAILABLE", "The change was sent, but Things could not confirm its saved state. Check Things before repeating the change.",
                              {"id": item_id, "cause": error.code}, uncertain=True)
        expected = {key: value for key, value in args.items() if key in TASK_EDIT_KEYS}
        if "when" in expected:
            when = expected.pop("when")
            if when == "today":
                # Native Today membership is authoritative. Its activation date
                # can be missing and must never be manufactured from a deadline.
                expected["listIds"] = ["today"]
            else:
                expected["when"] = when if when not in {"anytime", "someday"} else None
                expected["whenKind"] = "someday" if when == "someday" else "scheduled" if expected["when"] else "anytime"
        if command in {"complete", "cancel", "reopen", "trash"}:
            expected["status"] = {"complete": "completed", "cancel": "canceled", "reopen": "open", "trash": "trashed"}[command]
        if command == "move" and args.get("areaId"):
            expected["projectId"] = None
        available = observed.get("availableFields")
        missing, mismatched = [], []
        for key, value in expected.items():
            if key not in observed or (available is not None and key not in available):
                missing.append(key)
                continue
            actual = observed[key]
            if key == "tags":
                actual = sorted(tag.get("title") for tag in actual)
                value = sorted(value)
            matches = isinstance(actual, list) and set(value).issubset(actual) if key == "listIds" else actual == value
            if not matches:
                mismatched.append(key)
        if missing or mismatched:
            raise ThingsError("VERIFICATION_UNAVAILABLE" if missing else "VERIFICATION_FAILED",
                              "Things did not confirm all requested fields. Check Things before repeating the change.",
                              {"id": item_id, "unavailableFields": missing, "mismatchedFields": mismatched, "task": observed}, uncertain=True)
        return {"task": observed}
