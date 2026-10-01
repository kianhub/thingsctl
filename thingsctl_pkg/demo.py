"""Explicitly synthetic backend for development and automated tests."""

from copy import deepcopy
from datetime import date, timedelta
import uuid

from .errors import ThingsError


FIELDS = ["id", "title", "notes", "status", "when", "whenKind", "deadline", "createdAt",
          "modifiedAt", "completedAt", "canceledAt", "projectId", "areaId", "tags", "listIds"]


class DemoAdapter:
    name = "synthetic"
    demo = True

    def __init__(self):
        self.projects = [{"id": "demo-project", "title": "Autumn launch", "notes": "Synthetic project", "areaId": "demo-area"}]
        self.areas = [{"id": "demo-area", "title": "Work"}]
        self.tags = [{"id": "demo-tag", "title": "Focus"}]
        today = date.today()
        self.tasks = {}
        titles = ["Review launch brief", "Book a weekend hike", "Outline the autumn update", "Plan a quiet reading day", "Send the first draft"]
        for index, title in enumerate(titles):
            task = self._new_task({"title": title, "notes": "Fictional demo data — no connection to your Things library.",
                                   "when": "today" if index in (0, 2) else (today + timedelta(days=2)).isoformat() if index == 4 else "someday" if index == 3 else "anytime"})
            task["id"] = "demo-task-" + str(index + 1)
            if index in (0, 2, 4):
                task["projectId"], task["areaId"] = "demo-project", "demo-area"
                task["tags"] = deepcopy(self.tags)
            self.tasks[task["id"]] = task

    def _new_task(self, args):
        task = {"id": "demo-" + uuid.uuid4().hex, "title": args["title"], "notes": "", "status": "open",
                "when": None, "whenKind": "anytime", "deadline": None, "createdAt": "2026-09-30T09:00:00Z",
                "modifiedAt": "2026-09-30T09:00:00Z", "completedAt": None, "canceledAt": None,
                "projectId": None, "areaId": None, "tags": [], "availableFields": FIELDS[:]}
        self._edit(task, args)
        return task

    def _edit(self, task, args):
        for key in ("title", "notes", "deadline", "projectId", "areaId"):
            if key in args:
                task[key] = args[key]
        if args.get("areaId"):
            if not any(area["id"] == args["areaId"] for area in self.areas):
                raise ThingsError("NOT_FOUND", "The area does not exist.")
            task["projectId"] = None
        if args.get("projectId"):
            project = next((item for item in self.projects if item["id"] == args["projectId"]), None)
            if project is None:
                raise ThingsError("NOT_FOUND", "The project does not exist.")
            task["areaId"] = project.get("areaId")
        if "when" in args:
            when = args["when"]
            task["when"] = date.today().isoformat() if when == "today" else when if when not in (None, "anytime", "someday") else None
            task["whenKind"] = "scheduled" if task["when"] else "someday" if when == "someday" else "anytime"
        if "tags" in args:
            task["tags"] = []
            for title in args["tags"]:
                tag = next((item for item in self.tags if item["title"] == title), None)
                if tag is None:
                    tag = {"id": "demo-tag-" + uuid.uuid4().hex, "title": title}
                    self.tags.append(tag)
                task["tags"].append(deepcopy(tag))

    def call(self, command, args):
        if command == "doctor":
            return {"demo": True, "thingsInstalled": None, "hostRunning": True, "automation": "not-used",
                    "message": "Synthetic demo data. No connection to Things.", "capabilities": self._capabilities()}
        if command == "snapshot":
            view = args.get("view", "today")
            tasks = [self._record(task) for task in self.tasks.values() if self._in_view(task, view)]
            offset, limit = args.get("offset", 0), args.get("limit", 100)
            result = {"tasks": tasks[offset:offset + limit],
                    "total": len(tasks), "offset": offset, "limit": limit, "hasMore": offset + limit < len(tasks),
                    "capabilities": self._capabilities(), "catalogIncluded": args.get("includeCatalog", True)}
            if result["catalogIncluded"]:
                result.update({"projects": deepcopy(self.projects), "areas": deepcopy(self.areas),
                               "tags": deepcopy(self.tags), "lists": [{"id": name, "title": name.title(), "kind": "builtIn"} for name in
                                ("inbox", "today", "upcoming", "anytime", "someday", "logbook", "trash", "all")]})
            return result
        if command == "add":
            task = self._new_task(args)
            self.tasks[task["id"]] = task
            return {"task": self._record(task)}
        if command == "container_get":
            kind = args.get("kind")
            if kind not in {"project", "area", "tag"}:
                raise ThingsError("VALIDATION_ERROR", "Unknown container kind.")
            item = next((value for value in getattr(self, kind + "s") if value["id"] == args.get("id")), None)
            if item is None:
                raise ThingsError("NOT_FOUND", "The item does not exist.")
            return {kind: deepcopy(item)}
        if command in {"project_add", "area_add", "tag_add"}:
            kind = command.split("_")[0]
            item = {"id": "demo-" + kind + "-" + uuid.uuid4().hex, "title": args["title"]}
            for key in ("notes", "areaId"):
                if key in args:
                    item[key] = args[key]
            getattr(self, kind + "s").append(item)
            return {kind: deepcopy(item)}
        if command in {"get", "show", "update", "move", "complete", "cancel", "reopen", "trash"}:
            task = self.tasks.get(args.get("id"))
            if task is None:
                raise ThingsError("NOT_FOUND", "The task does not exist.")
            if command == "show":
                return {"id": task["id"], "revealed": True}
            if command in {"update", "move"}:
                self._edit(task, args)
            if command in {"complete", "cancel", "reopen", "trash"}:
                task["status"] = {"complete": "completed", "cancel": "canceled", "reopen": "open", "trash": "trashed"}[command]
                task["completedAt"] = "2026-09-30T10:00:00Z" if command == "complete" else None
                task["canceledAt"] = "2026-09-30T10:00:00Z" if command == "cancel" else None
            return {"task": self._record(task)}
        raise ThingsError("UNKNOWN_COMMAND", "Unknown backend command.")

    def _record(self, task):
        result = deepcopy(task)
        result["listIds"] = [view for view in ("inbox", "today", "upcoming", "anytime", "someday", "logbook", "trash")
                             if self._in_view(task, view)]
        return result

    @staticmethod
    def _capabilities():
        return {"availableFields": FIELDS[:], "unavailableFields": ["checklist", "heading", "evening", "reminderAt"],
                "operations": ["snapshot", "get", "add", "update", "complete", "cancel", "reopen", "move", "trash", "show", "project_add", "area_add", "tag_add"]}

    @staticmethod
    def _in_view(task, view):
        if view == "all":
            return True
        if view.startswith("project:"):
            return task["projectId"] == view.split(":", 1)[1] and task["status"] == "open"
        if view.startswith("area:"):
            return task["areaId"] == view.split(":", 1)[1] and task["status"] == "open"
        if view == "trash":
            return task["status"] == "trashed"
        if view == "logbook":
            return task["status"] in {"completed", "canceled"}
        if task["status"] != "open":
            return False
        if view == "inbox":
            return not task["projectId"] and not task["areaId"]
        if view == "today":
            return bool(task["when"] and task["when"] <= date.today().isoformat())
        if view == "upcoming":
            return bool(task["when"] and task["when"] > date.today().isoformat())
        return task["whenKind"] == view
