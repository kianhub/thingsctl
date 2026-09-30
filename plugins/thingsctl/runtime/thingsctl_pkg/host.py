"""Owner-only local transport to the macOS automation host."""

import json
import os
from pathlib import Path
import plistlib
import socket
import stat
import subprocess
import sys
import time

from .errors import ThingsError


MUTATIONS = {"add", "update", "complete", "cancel", "reopen", "move", "trash",
             "project_add", "area_add", "tag_add"}


class HostClient:
    name = "applescript"
    demo = False

    def __init__(self, socket_path=None, timeout=105):
        self.autostart = socket_path is None and not os.environ.get("THINGSCTL_SOCKET") and os.environ.get("THINGSCTL_AUTOSTART") != "0"
        self.socket_path = Path(socket_path or os.environ.get("THINGSCTL_SOCKET") or
                                Path.home() / "Library/Application Support/ThingsCTL/bridge.sock")
        self.timeout = timeout

    def _start_installed_host(self):
        """Start the fixed installed app before sending any automation command."""
        if not self.autostart or sys.platform != "darwin":
            return False
        app = Path.home() / "Applications/ThingsCTL Bridge.app"
        try:
            info = app.lstat()
            if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o022:
                return False
            plist_path = app / "Contents/Info.plist"
            plist_info = plist_path.lstat()
            if not stat.S_ISREG(plist_info.st_mode) or plist_info.st_uid != os.getuid() or plist_info.st_mode & 0o022:
                return False
            with plist_path.open("rb") as handle:
                metadata = plistlib.load(handle)
            if metadata.get("CFBundleIdentifier") != "com.kianhub.thingsctl.bridge":
                return False
            executable_name = metadata.get("CFBundleExecutable")
            if not isinstance(executable_name, str) or not executable_name or Path(executable_name).name != executable_name:
                return False
            executable = app / "Contents/MacOS" / executable_name
            executable_info = executable.lstat()
            if not stat.S_ISREG(executable_info.st_mode) or executable_info.st_uid != os.getuid() or executable_info.st_mode & 0o022:
                return False
            subprocess.run(["/usr/bin/open", "-g", "-a", str(app)], check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
        except (OSError, ValueError, plistlib.InvalidFileException, subprocess.SubprocessError):
            return False
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            try:
                socket_info = self.socket_path.lstat()
                if not stat.S_ISSOCK(socket_info.st_mode) or socket_info.st_uid != os.getuid() or socket_info.st_mode & 0o077:
                    return False
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as probe:
                    probe.settimeout(0.2)
                    probe.connect(str(self.socket_path))
                return True
            except OSError:
                pass
            time.sleep(0.05)
        return False

    def call(self, command, arguments):
        try:
            info = self.socket_path.lstat()
        except FileNotFoundError:
            if not self._start_installed_host():
                raise ThingsError("HOST_UNAVAILABLE", "ThingsCTL's macOS host is not running. Run the installer, then open ThingsCTL Bridge.")
            try:
                info = self.socket_path.lstat()
            except FileNotFoundError:
                raise ThingsError("HOST_UNAVAILABLE", "ThingsCTL Bridge did not create its local socket.")
        if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ThingsError("UNSAFE_SOCKET", "The ThingsCTL host socket must belong to you and have owner-only permissions.")
        request = (json.dumps({"command": command, "arguments": arguments}, ensure_ascii=False) + "\n").encode("utf-8")
        dispatched = False
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                connection.settimeout(self.timeout)
                try:
                    connection.connect(str(self.socket_path))
                except ConnectionRefusedError:
                    if not self._start_installed_host():
                        raise
                    # No request bytes were sent on the refused connection.
                    connection.connect(str(self.socket_path))
                dispatched = True
                connection.sendall(request)
                chunks, size = [], 0
                while True:
                    chunk = connection.recv(65536)
                    if not chunk:
                        raise OSError("Host closed the connection without a response")
                    chunks.append(chunk)
                    size += len(chunk)
                    if size > 16 * 1024 * 1024:
                        raise OSError("Host response exceeded the supported size")
                    if b"\n" in chunk:
                        break
                result = json.loads(b"".join(chunks).split(b"\n", 1)[0])
        except (OSError, UnicodeError, json.JSONDecodeError):
            uncertain = dispatched and command in MUTATIONS
            raise ThingsError("MUTATION_UNCERTAIN" if uncertain else "HOST_UNAVAILABLE",
                              "The host response was interrupted. Check Things before making another change." if uncertain else
                              "Could not read a response from ThingsCTL Host. Open the host and try again.",
                              uncertain=uncertain)
        if not isinstance(result, dict) or not isinstance(result.get("ok"), bool):
            raise ThingsError("HOST_PROTOCOL", "The host returned an invalid response.", uncertain=dispatched and command in MUTATIONS)
        if not result["ok"]:
            error = result.get("error") or {}
            details = error.get("details")
            uncertain = error.get("code") in {"MUTATION_UNCERTAIN", "UNCERTAIN", "BACKEND_TIMEOUT"} or (command in MUTATIONS and error.get("code") == "INVALID_RESPONSE") or (
                isinstance(details, dict) and details.get("operationStatus") == "uncertain")
            raise ThingsError(error.get("code", "HOST_ERROR"), error.get("message", "Things rejected the command."), details, uncertain)
        if not isinstance(result.get("data"), dict):
            raise ThingsError("HOST_PROTOCOL", "The host returned no structured result.", uncertain=command in MUTATIONS)
        return result["data"]
