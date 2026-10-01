"""ThingsCTL's bounded, dual-era MCP stdio server (standard library only).

The command service owns all task behavior. This layer validates tool inputs,
serves the bundled MCP App, and never executes arbitrary shell or AppleScript.
"""
from __future__ import annotations

import base64
import copy
import json
import os
import re
import stat
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any

from . import __version__

MODERN_VERSION = "2026-07-28"
LEGACY_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
META_VERSION = "io.modelcontextprotocol/protocolVersion"
META_CAPABILITIES = "io.modelcontextprotocol/clientCapabilities"
META_SERVER_INFO = "io.modelcontextprotocol/serverInfo"
UI_EXTENSION = "io.modelcontextprotocol/ui"
UI_URI = "ui://thingsctl/workspace.html"
UI_MIME = "text/html;profile=mcp-app"
VERSION = __version__
MAX_MESSAGE_BYTES = 1024 * 1024
NAVIGATION = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.33" stroke-linecap="round" stroke-linejoin="round"><rect x="2.5" y="2.5" width="15" height="15" rx="3"/><path d="m6 10 2.7 2.7L14 7.3"/></svg>'
ICON = {"src": "data:image/svg+xml;base64," + base64.b64encode(NAVIGATION.encode()).decode(), "mimeType": "image/svg+xml", "sizes": ["20x20"]}
INSTRUCTIONS = (
    "ThingsCTL operates this Mac's Things 3 through documented automation. "
    "Start with thingsctl_doctor if setup is unknown; doctor does not read tasks. "
    "Use stable item IDs and read the latest revision before changing a task. "
    "When is a start date; Deadline is separate. Unknown fields are unavailable, not empty. "
    "For tasks inside projects, start kind may be unknown. Set Anytime or Someday in Things; "
    "ThingsCTL permits Today and explicit start dates, or detaching the project before changing start kind. "
    "Reads are bounded: follow nextOffset while hasMore is true and respect completeness metadata. "
    "Mutations return verified, failed, or uncertain operations. Never automatically retry an uncertain "
    "operation with a new operationId. Use thingsctl_workspace when the user asks to open or browse the ThingsCTL app, "
    "including viewing Today with the plugin; a data-only list call does not display the app. "
    "The workspace opens as a fullscreen MCP App. "
    "Use only authorized tasks and changes; attaching task context does not authorize a mutation. "
    "This version does not expose headings, checklists, Evening, reminders, or recurrence authoring."
)


def obj(properties=None, required=()):
    value = {"type": "object", "properties": properties or {}, "additionalProperties": False}
    if required:
        value["required"] = list(required)
    return value


STRING = {"type": "string", "maxLength": 256}
ID = {"type": "string", "minLength": 1, "maxLength": 256}
NULL_ID = {"type": ["string", "null"], "maxLength": 256}
MUTATION_META = {"operationId": {"type": "string", "minLength": 1, "maxLength": 128}, "expectedRevision": ID}
TASK_FIELDS = {
    "title": {"type": "string", "minLength": 1, "maxLength": 1000},
    "notes": {"type": "string", "maxLength": 100000},
    "tags": {"type": "array", "items": {"type": "string", "minLength": 1, "maxLength": 256}, "maxItems": 100},
    "when": {"type": "string", "maxLength": 32, "description": "today, anytime, someday, or YYYY-MM-DD. Separate from Deadline. Anytime/Someday are unavailable for project tasks unless projectId is explicitly cleared in this change."},
    "deadline": {"type": ["string", "null"], "maxLength": 10, "description": "YYYY-MM-DD or null to clear the deadline."},
    "projectId": NULL_ID,
    "areaId": NULL_ID,
}
QUERY_FIELDS = {
    "view": {"type": "string", "maxLength": 256, "description": "inbox, today, upcoming, anytime, someday, logbook, trash, all, or project:<id>/area:<id>."},
    "offset": {"type": "integer", "minimum": 0, "maximum": 1000000},
    "limit": {"type": "integer", "minimum": 1, "maximum": 500},
    "includeCatalog": {"type": "boolean", "description": "Include projects, areas, tags, and built-in list metadata. Defaults to true. False omits the catalog and avoids rescanning it; retain a prior catalog in the workspace."},
}
SEARCH_FIELDS = {**{key: value for key, value in QUERY_FIELDS.items() if key != "includeCatalog"}, "projectId": ID, "areaId": ID, "tag": STRING,
                 "status": {"type": "string", "enum": ["open", "completed", "canceled", "trashed"]},
                 "maxScan": {"type": "integer", "minimum": 1, "maximum": 50000}}
CREATE_META = {"operationId": MUTATION_META["operationId"]}
SETTINGS_DEFAULTS = {"startView": "today", "theme": "system", "density": "comfortable", "refreshSeconds": 120}
SETTINGS_SCHEMA = obj({
    "startView": {"type": "string", "title": "Open to", "enum": ["inbox", "today", "upcoming", "anytime", "someday", "logbook"]},
    "theme": {"type": "string", "title": "Appearance", "enum": ["system", "light", "dark"]},
    "density": {"type": "string", "title": "Row spacing", "enum": ["comfortable", "compact"]},
    "refreshSeconds": {"type": "integer", "title": "Refresh interval", "minimum": 15, "maximum": 300},
})


def validate(value, schema, path="arguments"):
    """Validate our small JSON Schema subset; notably bool is not an integer."""
    kind = schema.get("type")
    kinds = kind if isinstance(kind, list) else [kind]
    checks = {"object": lambda v: isinstance(v, dict), "array": lambda v: isinstance(v, list),
              "string": lambda v: isinstance(v, str), "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
              "boolean": lambda v: isinstance(v, bool), "null": lambda v: v is None}
    if kind and not any(checks.get(k, lambda v: True)(value) for k in kinds):
        raise ValueError(f"{path} must be {kind}")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{path} has an unsupported value")
    if isinstance(value, dict) and "object" in kinds:
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False and set(value) - set(properties):
            raise ValueError(f"{path} contains unsupported fields: {', '.join(sorted(set(value) - set(properties)))}")
        for key in schema.get("required", []):
            if key not in value:
                raise ValueError(f"{path}.{key} is required")
        if len(value) < schema.get("minProperties", 0):
            raise ValueError(f"{path} must contain a setting")
        for key, item in value.items():
            if key in properties:
                validate(item, properties[key], f"{path}.{key}")
    elif isinstance(value, list) and "array" in kinds:
        if len(value) > schema.get("maxItems", 500):
            raise ValueError(f"{path} has too many items")
        for index, item in enumerate(value):
            validate(item, schema.get("items", {}), f"{path}[{index}]")
    elif isinstance(value, str):
        if not schema.get("minLength", 0) <= len(value) <= schema.get("maxLength", 65536):
            raise ValueError(f"{path} has an invalid length")
    elif isinstance(value, int) and not isinstance(value, bool):
        if not schema.get("minimum", -float("inf")) <= value <= schema.get("maximum", float("inf")):
            raise ValueError(f"{path} is out of range")


def error_envelope(code, message):
    return {"ok": False, "requestId": str(uuid.uuid4()), "error": {"code": code, "message": message}}


def tool(name, title, schema, command=None, read=True, destructive=False, entrypoints=None, app_only=False, description=None):
    descriptor = {"name": name, "title": title, "description": description or title + ". Uses ThingsCTL's shared command service.",
                  "inputSchema": schema, "annotations": {"readOnlyHint": read, "destructiveHint": destructive,
                  "idempotentHint": read, "openWorldHint": False}, "command": command}
    if entrypoints:
        descriptor["entrypoints"] = entrypoints
        descriptor["icons"] = [ICON]
    descriptor["appOnly"] = app_only
    return descriptor


MUTATION_COMMANDS = ("add", "update", "complete", "cancel", "reopen", "move", "trash", "show", "project_add", "area_add", "tag_add")
TOOLS = [
    tool("thingsctl_doctor", "Check ThingsCTL connection", obj(), "doctor"),
    tool("thingsctl_list", "List Things tasks", obj(QUERY_FIELDS), "list"),
    tool("thingsctl_search", "Search Things tasks", obj({**SEARCH_FIELDS, "query": {"type": "string", "maxLength": 512}}, ["query"]), "search"),
    tool("thingsctl_projects", "List Things projects", obj()),
    tool("thingsctl_areas", "List Things areas", obj()),
    tool("thingsctl_tags", "List Things tags", obj()),
    tool("thingsctl_get", "Get a Things task", obj({"id": ID}, ["id"]), "get"),
    tool("thingsctl_add", "Create a Things task", obj({**TASK_FIELDS, **CREATE_META}, ["title"]), "add", False),
    tool("thingsctl_update", "Update a Things task", obj({"id": ID, **TASK_FIELDS, **MUTATION_META}, ["id"]), "update", False),
    tool("thingsctl_move", "Move a Things task", obj({"id": ID, "projectId": NULL_ID, "areaId": NULL_ID, **MUTATION_META}, ["id"]), "move", False),
    tool("thingsctl_complete", "Complete a Things task", obj({"id": ID, **MUTATION_META}, ["id"]), "complete", False),
    tool("thingsctl_cancel", "Cancel a Things task", obj({"id": ID, **MUTATION_META}, ["id"]), "cancel", False),
    tool("thingsctl_reopen", "Reopen a Things task", obj({"id": ID, **MUTATION_META}, ["id"]), "reopen", False),
    tool("thingsctl_trash", "Trash a Things task", obj({"id": ID, **MUTATION_META}, ["id"]), "trash", False, True),
    tool("thingsctl_show", "Reveal a task in Things", obj({"id": ID, **MUTATION_META}, ["id"]), "show", False),
    tool("thingsctl_project_add", "Create a Things project", obj({"title": TASK_FIELDS["title"], "notes": TASK_FIELDS["notes"], "areaId": NULL_ID, **CREATE_META}, ["title"]), "project_add", False),
    tool("thingsctl_area_add", "Create a Things area", obj({"title": TASK_FIELDS["title"], **CREATE_META}, ["title"]), "area_add", False),
    tool("thingsctl_tag_add", "Create a Things tag", obj({"title": TASK_FIELDS["title"], **CREATE_META}, ["title"]), "tag_add", False),
    tool("thingsctl_workspace", "ThingsCTL", obj(), entrypoints=[{"type": "global"}], description=
         "Open the Things-style interactive app in the sidebar or beside this conversation, with live tasks and editing controls. "
         "Call this when the user asks to browse or check Things in the app, UI, sidebar, or workspace. "
         "Returns the initial task list for the app; data-only tools remain available for ordinary task queries."),
    tool("thingsctl_workspace_thread", "ThingsCTL workspace", obj(), entrypoints=[{"type": "thread"}], app_only=True),
    tool("thingsctl_workspace_snapshot", "Refresh Things workspace", obj(QUERY_FIELDS), "list", app_only=True),
    tool("thingsctl_workspace_mutate", "Apply a Things workspace change", obj({"command": {"type": "string", "enum": list(MUTATION_COMMANDS)},
         "arguments": {"type": "object"}, "operationId": MUTATION_META["operationId"], "expectedRevision": ID}, ["command", "arguments", "operationId"]), read=False, destructive=True, app_only=True),
    tool("thingsctl_settings", "Things workspace settings", obj(), app_only=True),
    tool("thingsctl_settings_read", "Read Things workspace preferences", obj(), app_only=True),
    tool("thingsctl_settings_update", "Save Things workspace preferences", obj({"set": {**SETTINGS_SCHEMA, "minProperties": 1}}, ["set"]), read=False, app_only=True),
]
TOOLS_BY_NAME = {item["name"]: item for item in TOOLS}
TOOLS_BY_NAME["thingsctl_settings_read"]["outputSchema"] = {
    "type": "object", "properties": {"schema": {"type": "object"}, "values": SETTINGS_SCHEMA, "layout": {"type": "array"}},
    "required": ["schema", "values", "layout"]}
TOOLS_BY_NAME["thingsctl_settings_update"]["outputSchema"] = obj({"values": SETTINGS_SCHEMA}, ["values"])
COMMAND_SCHEMAS = {item["command"]: item["inputSchema"] for item in TOOLS if item.get("command")}


class RPCError(Exception):
    def __init__(self, code, message, data=None):
        self.code, self.message, self.data = code, message, data


class MCPServer:
    def __init__(self, service=None, ui_path=None, settings_path=None):
        if service is None:
            from .core import ThingsService
            service = ThingsService()
        self.service = service
        self.legacy_capabilities = {}
        self.legacy_version = LEGACY_VERSIONS[0]
        root = Path(os.environ.get("THINGSCTL_PLUGIN_ROOT", Path(__file__).resolve().parents[1]))
        candidates = [root / "ui/workspace.html", root / "ui/dist/things-workspace.html", root / "plugins/thingsctl/ui/workspace.html"]
        self.ui_path = Path(ui_path) if ui_path else next((p for p in candidates if p.is_file()), candidates[0])
        self.settings_path = Path(settings_path) if settings_path else Path.home() / "Library/Application Support/ThingsCTL/settings.json"

    def identity(self):
        return {"name": "thingsctl", "title": "ThingsCTL", "version": VERSION,
                "websiteUrl": "https://github.com/kianhub/thingsctl", "icons": [ICON]}

    def capabilities(self):
        return {"tools": {"listChanged": False}, "resources": {"listChanged": False, "subscribe": False},
                "extensions": {UI_EXTENSION: {}, "openai/settings": {"readTool": "thingsctl_settings_read", "updateTool": "thingsctl_settings_update"}}}

    def settings(self):
        values = dict(SETTINGS_DEFAULTS)
        if self.settings_path.exists() or self.settings_path.is_symlink():
            info = self.settings_path.lstat()
            if stat.S_ISLNK(info.st_mode) or info.st_uid != os.getuid() or not stat.S_ISREG(info.st_mode):
                raise ValueError("Settings file is not owned by this user")
            loaded = json.loads(self.settings_path.read_text(encoding="utf-8"))
            validate(loaded, SETTINGS_SCHEMA, "settings")
            values.update(loaded)
        return {"schema": SETTINGS_SCHEMA, "values": values,
                "layout": [{"kind": "group", "title": "Workspace", "items": [{"kind": "property", "property": key} for key in values]}]}

    def save_settings(self, values):
        updated = {**self.settings()["values"], **values}
        parent = self.settings_path.parent
        parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if parent.is_symlink() or parent.stat().st_uid != os.getuid():
            raise ValueError("Settings directory is not owned by this user")
        fd, temporary = tempfile.mkstemp(prefix=".settings-", dir=parent)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(updated, handle)
            os.replace(temporary, self.settings_path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return {"values": updated}

    def ui_meta(self):
        return {"ui": {"resourceUri": UI_URI, "visibility": ["model", "app"]}}

    def descriptor(self, item, legacy):
        result = {key: copy.deepcopy(value) for key, value in item.items() if key not in {"command", "entrypoints", "appOnly"}}
        meta = {}
        # Keep registration stable during host discovery, before UI capabilities
        # may be advertised. Hosts choose rendering; every opener retains a text
        # result, and app-only tools retain their visibility on every transport.
        if item["name"] in {"thingsctl_workspace", "thingsctl_workspace_thread", "thingsctl_settings"}:
            meta = self.ui_meta()
            if legacy:
                meta["openai/outputTemplate"] = UI_URI
        elif item.get("appOnly"):
            meta["ui"] = {"visibility": ["app"]}
        if item.get("appOnly") and "ui" in meta:
            meta["ui"]["visibility"] = ["app"]
        if item.get("entrypoints"):
            meta["openai/ui"] = {"entrypoints": item["entrypoints"]}
        if meta:
            result["_meta"] = meta
        return result

    def call_tool(self, name, arguments):
        item = TOOLS_BY_NAME.get(name)
        if item is None:
            raise RPCError(-32602, "Unknown tool")
        try:
            validate(arguments, item["inputSchema"])
            if name in {"thingsctl_workspace", "thingsctl_workspace_thread"}:
                response = self.service.execute("list", {"view": self.settings()["values"]["startView"], "limit": 20})
                response.setdefault("meta", {})["settings"] = self.settings()["values"]
            elif name in {"thingsctl_projects", "thingsctl_areas", "thingsctl_tags"}:
                response = self.service.execute("list", {"view": "today", "limit": 1})
                if response.get("ok"):
                    collection = name.removeprefix("thingsctl_")
                    if collection not in response.get("data", {}):
                        raise ValueError("Things did not provide the requested catalogue")
                    response["data"] = {collection: response["data"][collection]}
            elif name == "thingsctl_settings":
                response = {"ok": True, "requestId": str(uuid.uuid4()), "data": {"settings": self.settings()["values"], "mode": "settings"}}
            elif name == "thingsctl_settings_read":
                response = self.settings()
            elif name == "thingsctl_settings_update":
                response = self.save_settings(arguments["set"])
            elif name == "thingsctl_workspace_mutate":
                command = arguments["command"]
                merged = dict(arguments["arguments"])
                for key in ("operationId", "expectedRevision"):
                    if key in arguments:
                        if key in merged and merged[key] != arguments[key]:
                            raise ValueError(f"Conflicting {key}")
                        merged[key] = arguments[key]
                validate(merged, COMMAND_SCHEMAS[command])
                response = self.service.execute(command, merged)
            else:
                response = self.service.execute(item["command"], arguments)
        except (ValueError, OSError, json.JSONDecodeError) as exc:
            response = error_envelope("INVALID_ARGUMENT", str(exc))
        return {"content": [{"type": "text", "text": json.dumps(response, ensure_ascii=False)}],
                "structuredContent": response, "isError": response.get("ok") is False}

    def resource(self):
        if not self.ui_path.is_file():
            raise RPCError(-32002, "Workspace is not built. Run ./script/build_and_run.sh --build-only.")
        policy = {"csp": {"connectDomains": [], "resourceDomains": []}, "prefersBorder": False}
        return {"contents": [{"uri": UI_URI, "mimeType": UI_MIME, "text": self.ui_path.read_text(encoding="utf-8"),
                "_meta": {"ui": policy, "openai/ui": {"availableDisplayModes": ["fullscreen"], "preferredDisplayMode": "fullscreen"},
                          "openai/widgetCSP": {"connect_domains": [], "resource_domains": []}}}]}

    def dispatch(self, method, params, modern, caps):
        if method == "server/discover":
            return {"supportedVersions": [MODERN_VERSION], "capabilities": self.capabilities(), "instructions": INSTRUCTIONS,
                    "_meta": {META_SERVER_INFO: self.identity()}, "ttlMs": 3600000, "cacheScope": "public"}
        if method == "initialize":
            if modern:
                raise RPCError(-32601, "initialize uses legacy semantics; use server/discover for 2026-07-28")
            requested = params.get("protocolVersion")
            self.legacy_version = requested if requested in LEGACY_VERSIONS else LEGACY_VERSIONS[0]
            self.legacy_capabilities = params.get("capabilities", {})
            return {"protocolVersion": self.legacy_version, "capabilities": self.capabilities(), "serverInfo": self.identity(), "instructions": INSTRUCTIONS}
        if method == "ping":
            return {}
        if method == "tools/list":
            return {"tools": [self.descriptor(item, not modern) for item in TOOLS]}
        if method == "tools/call":
            arguments = params.get("arguments", {})
            result = self.call_tool(params.get("name"), arguments)
            if params.get("name") in {"thingsctl_workspace", "thingsctl_workspace_thread", "thingsctl_settings"}:
                result["_meta"] = self.ui_meta()
                if not modern:
                    result["_meta"]["openai/outputTemplate"] = UI_URI
            return result
        if method == "resources/list":
            return {"resources": [{"uri": UI_URI, "name": "things-workspace", "title": "Things workspace", "mimeType": UI_MIME}]}
        if method == "resources/templates/list":
            return {"resourceTemplates": []}
        if method == "resources/read":
            if params.get("uri") != UI_URI:
                raise RPCError(-32002, "Unknown resource")
            return self.resource()
        raise RPCError(-32601, "Method not found")

    def handle_message(self, message):
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0" or not isinstance(message.get("method"), str):
            return self.rpc_error(None, -32600, "Invalid Request")
        if "id" not in message:
            return None
        request_id = message["id"]
        if not isinstance(request_id, (str, int)) or isinstance(request_id, bool):
            return self.rpc_error(None, -32600, "Invalid request ID")
        params = message.get("params", {})
        if not isinstance(params, dict):
            return self.rpc_error(request_id, -32602, "params must be an object")
        meta = params.get("_meta", {})
        if not isinstance(meta, dict):
            return self.rpc_error(request_id, -32602, "_meta must be an object")
        method = message["method"]
        modern = method == "server/discover" or META_VERSION in meta or META_CAPABILITIES in meta
        caps = meta.get(META_CAPABILITIES, {}) if modern else self.legacy_capabilities
        try:
            if modern:
                requested = meta.get(META_VERSION, MODERN_VERSION if method == "server/discover" else None)
                if requested != MODERN_VERSION:
                    raise RPCError(-32022, "Unsupported protocol version", {"supported": [MODERN_VERSION, *LEGACY_VERSIONS], "requested": requested})
                if method != "server/discover" and (META_VERSION not in meta or META_CAPABILITIES not in meta):
                    raise RPCError(-32602, "Modern requests require protocolVersion and clientCapabilities in params._meta")
                if not isinstance(caps, dict):
                    raise RPCError(-32602, "clientCapabilities must be an object")
            result = self.dispatch(method, params, modern, caps)
            if modern:
                result["resultType"] = "complete"
                result.setdefault("_meta", {}).setdefault(META_SERVER_INFO, self.identity())
            return {"jsonrpc": "2.0", "id": request_id, "result": result}
        except RPCError as exc:
            return self.rpc_error(request_id, exc.code, exc.message, exc.data)
        except Exception:
            # Do not leak task contents, auth values, paths, or Python tracebacks to a client.
            return self.rpc_error(request_id, -32603, "ThingsCTL could not complete this request. Run thingsctl_doctor.")

    @staticmethod
    def rpc_error(request_id, code, message, data=None):
        error = {"code": code, "message": message}
        if data is not None:
            error["data"] = data
        return {"jsonrpc": "2.0", "id": request_id, "error": error}


def main():
    server = MCPServer()
    stream = sys.stdin.buffer
    while True:
        line = stream.readline(MAX_MESSAGE_BYTES + 1)
        if not line:
            return
        if len(line) > MAX_MESSAGE_BYTES:
            while line and not line.endswith(b"\n"):
                line = stream.readline(MAX_MESSAGE_BYTES + 1)
            response = MCPServer.rpc_error(None, -32600, "Request exceeds 1 MiB")
        else:
            try:
                response = server.handle_message(json.loads(line))
            except (UnicodeDecodeError, json.JSONDecodeError):
                response = MCPServer.rpc_error(None, -32700, "Parse error")
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
