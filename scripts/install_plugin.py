#!/usr/bin/env python3
"""Install ThingsCTL via supported Codex commands; never edit its plugin cache."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import plistlib
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from package_plugin import REPO, stage_plugin

BUNDLE_ID = "com.kianhub.thingsctl.bridge"
MARKETPLACE = "thingsctl-local"
SUPPORT = Path.home() / "Library/Application Support/ThingsCTL"
APP = Path.home() / "Applications/ThingsCTL Bridge.app"
BIN = Path.home() / ".local/bin/thingsctl"
AGENT = Path.home() / "Library/LaunchAgents/com.kianhub.thingsctl.bridge.plist"
MARKET_ROOT = SUPPORT / "marketplace"
MANIFEST = SUPPORT / "install-manifest.json"


def run(argv, **kwargs):
    print("→ " + " ".join(shlex.quote(str(value)) for value in argv), flush=True)
    subprocess.run([str(value) for value in argv], check=True, **kwargs)


def ensure_safe_dir(path):
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    info = path.lstat()
    if path.is_symlink() or not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o022:
        raise ValueError("Refusing a directory not owned by this user: " + str(path))


def atomic_write(path, data, mode=0o600):
    ensure_safe_dir(path.parent)
    fd, temporary = tempfile.mkstemp(prefix=".thingsctl-", dir=path.parent)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def digest_file(path):
    if path.is_symlink() or not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_digest(path):
    digest = hashlib.sha256()
    if path.is_symlink() or not path.is_dir():
        return None
    for item in sorted(path.rglob("*")):
        if item.is_symlink():
            return None
        if item.is_file():
            digest.update(str(item.relative_to(path)).encode())
            digest.update(item.read_bytes())
    return digest.hexdigest()


def quit_bridge():
    # Running check does not launch an app just to quit it. Standard Cocoa quit is supported.
    script = 'if application id "' + BUNDLE_ID + '" is running then tell application id "' + BUNDLE_ID + '" to quit'
    run(["/usr/bin/osascript", "-e", script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)


def owned_app(path):
    if path.is_symlink() or not path.is_dir():
        return False
    try:
        with (path / "Contents/Info.plist").open("rb") as handle:
            return plistlib.load(handle).get("CFBundleIdentifier") == BUNDLE_ID
    except (OSError, ValueError):
        return False


def load_manifest():
    if not MANIFEST.exists():
        return {}
    if MANIFEST.is_symlink() or MANIFEST.stat().st_uid != os.getuid():
        raise ValueError("Unsafe installation manifest")
    value = json.loads(MANIFEST.read_text())
    if value.get("name") != "thingsctl" or value.get("version") != 1:
        raise ValueError("Foreign installation manifest")
    return value


def write_manifest(value):
    atomic_write(MANIFEST, (json.dumps(value, indent=2) + "\n").encode())


def check_installation():
    """A health check never reverses a successfully published installation."""
    try:
        result = subprocess.run([str(BIN), "doctor", "--json"], capture_output=True, text=True, timeout=20)
        diagnostic = json.loads(result.stdout) if result.stdout.strip() else None
        if not isinstance(diagnostic, dict):
            raise ValueError("Invalid diagnostic response")
        data = diagnostic.get("data", {})
        if not isinstance(data, dict):
            data = {}
        automation = data.get("automation") if isinstance(data.get("automation"), str) else "unknown"
        authorized = data.get("connected") is True or automation in {"authorized", "granted"}
        unavailable = any(data.get(key) is False for key in ("connected", "hostRunning", "thingsInstalled")) or automation in {"denied", "restricted", "unavailable"}
        available = result.returncode == 0 and diagnostic.get("ok") is True and not unavailable
        if authorized and available:
            status = "ready"
            message = "The local bridge and Things Automation connection are available."
        elif available:
            status = "permission_not_verified"
            message = "The bridge is available. Your first authorized task operation may request Automation permission."
        else:
            status = "needs_attention"
            message = "Installation is complete, but the connection needs attention. Run thingsctl doctor --json for the next step."
        return {"status": status, "message": message, "diagnostic": diagnostic}
    except (ValueError, OSError, subprocess.SubprocessError):
        return {"status": "needs_attention", "message": "Installation is complete. The connection check did not respond; run thingsctl doctor --json before opening task data."}


def install(args):
    if sys.version_info < (3, 9):
        raise ValueError("Python 3.9 or later is required")
    if sys.platform != "darwin":
        raise ValueError("ThingsCTL Bridge requires macOS")
    if not args.skip_plugin and not shutil.which("codex"):
        raise ValueError("Codex CLI is missing. Install or enable the Codex CLI before installing the plugin.")
    previous = load_manifest()
    if not args.skip_plugin:
        listing = subprocess.run(["codex", "plugin", "marketplace", "list", "--json"], check=True, capture_output=True, text=True)
        for registered in json.loads(listing.stdout).get("marketplaces", []):
            if registered.get("name") == MARKETPLACE and Path(registered.get("root", "")).resolve() != MARKET_ROOT.resolve():
                raise ValueError("The thingsctl-local marketplace name already belongs to another source")
    if BIN.exists() or BIN.is_symlink():
        if previous.get("binHash") and digest_file(BIN) != previous["binHash"]:
            raise ValueError("Installed launcher was changed; preserve it before reinstalling: " + str(BIN))
        if BIN.is_dir() and not BIN.is_symlink():
            raise ValueError("A directory occupies the launcher path")
    if APP.exists() or APP.is_symlink():
        if not owned_app(APP) or not previous.get("appHash") or tree_digest(APP) != previous["appHash"]:
            raise ValueError("Existing app does not match an installer-owned build: " + str(APP))
    if AGENT.exists() and digest_file(AGENT) != previous.get("agentHash"):
        raise ValueError("A different or edited LaunchAgent occupies " + str(AGENT))
    if MARKET_ROOT.is_symlink():
        raise ValueError("Marketplace source cannot be a symlink")
    if MARKET_ROOT.exists() and not previous:
        raise ValueError("Existing marketplace has no ThingsCTL ownership manifest: " + str(MARKET_ROOT))
    if args.dry_run:
        print("Would build the native app and use the bundled workspace, stage a self-contained plugin, preserve an existing launcher,")
        print("install " + str(APP) + ", register thingsctl-local, and add thingsctl@thingsctl-local.")
        return
    if not args.skip_build:
        run([REPO / "script/build_and_run.sh", "--build-only"])
    source_app = REPO / "dist/ThingsCTL Bridge.app"
    if not owned_app(source_app):
        raise ValueError("Built bridge is missing or has the wrong bundle identity")
    if not (REPO / "ui/dist/things-workspace.html").is_file():
        raise ValueError("Bundled workspace is missing. Restore ui/dist/things-workspace.html or run pnpm -C ui build.")
    ensure_safe_dir(SUPPORT)
    ensure_safe_dir(APP.parent)
    ensure_safe_dir(BIN.parent)
    state = {**previous, "name": "thingsctl", "version": 1, "status": "staging", "repository": str(REPO),
             "app": str(APP), "bin": str(BIN), "marketplace": str(MARKET_ROOT), "python": sys.executable}
    recovery = SUPPORT / "recovery" / str(time.time_ns())
    ensure_safe_dir(recovery)
    for name, path in (("app", APP), ("marketplace", MARKET_ROOT), ("bin", BIN), ("agent", AGENT)):
        if path.is_symlink():
            (recovery / name).symlink_to(os.readlink(path))
        elif path.is_dir():
            shutil.copytree(path, recovery / name)
        elif path.is_file():
            shutil.copy2(path, recovery / name)
    atomic_write(recovery / "previous-install.json", (json.dumps(previous, indent=2) + "\n").encode())
    state["recovery"] = str(recovery)
    write_manifest(state)
    with tempfile.TemporaryDirectory(prefix="thingsctl-install-", dir=SUPPORT) as temporary:
        temporary = Path(temporary)
        plugin = temporary / "marketplace/plugins/thingsctl"
        build = stage_plugin(plugin, repo=REPO)
        marketfile = temporary / "marketplace/.agents/plugins/marketplace.json"
        marketfile.parent.mkdir(parents=True)
        shutil.copy2(REPO / ".agents/plugins/marketplace.json", marketfile)
        staged_app = temporary / "ThingsCTL Bridge.app"
        shutil.copytree(source_app, staged_app)
        # A prior tree is only replaced when this installer owns the exact destination.
        if MARKET_ROOT.exists():
            shutil.rmtree(MARKET_ROOT)
        os.replace(temporary / "marketplace", MARKET_ROOT)
        quit_bridge()
        if APP.exists():
            shutil.rmtree(APP)
        os.replace(staged_app, APP)
    if not previous.get("binHash") and (BIN.exists() or BIN.is_symlink()):
        backup = BIN.with_name("thingsctl.before-install-" + str(time.time_ns()))
        os.replace(BIN, backup)
        state["binBackup"] = str(backup)
        write_manifest(state)
    runner = MARKET_ROOT / "plugins/thingsctl/scripts/runner.py"
    launcher = "#!/bin/sh\n# Managed by ThingsCTL installer\nexec " + shlex.quote(sys.executable) + " -I " + shlex.quote(str(runner)) + ' "$@"\n'
    atomic_write(BIN, launcher.encode(), 0o755)
    state.update({"build": build, "binHash": digest_file(BIN), "appHash": tree_digest(APP), "status": "staged"})
    if not args.no_launch_agent:
        ensure_safe_dir(AGENT.parent)
        agent = {"Label": BUNDLE_ID, "ProgramArguments": ["/usr/bin/open", "-gj", str(APP)], "RunAtLoad": True}
        atomic_write(AGENT, plistlib.dumps(agent), 0o600)
        state["agentHash"] = digest_file(AGENT)
    write_manifest(state)
    if not args.skip_plugin:
        # These are the supported 0.159+ CLI flows, not hand edits to config.toml.
        run(["codex", "plugin", "marketplace", "add", MARKET_ROOT, "--json"])
        run(["codex", "plugin", "add", "thingsctl@" + MARKETPLACE, "--json"])
        state["pluginInstalled"] = True
        write_manifest(state)
    if not args.no_launch_agent:
        domain = "gui/" + str(os.getuid())
        subprocess.run(["launchctl", "bootout", domain + "/" + BUNDLE_ID], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        run(["launchctl", "bootstrap", domain, AGENT])
    run(["/usr/bin/open", "-gj", APP])
    health = check_installation()
    state["status"] = "installed"
    state["connectionStatus"] = health["status"]
    state.pop("recovery", None)
    write_manifest(state)
    shutil.rmtree(recovery)
    print("ThingsCTL installed. Refresh plugin discovery in Codex if necessary.")
    print(health["message"])
    if health.get("diagnostic"):
        print(json.dumps(health["diagnostic"], ensure_ascii=False))
    print("This development build is ad-hoc signed and not notarized; Automation permission may need renewal after rebuilding.")


def uninstall(args):
    state = load_manifest()
    if not state:
        print("No ThingsCTL installation manifest found; nothing was removed.")
        return
    if state.get("binHash") and digest_file(BIN) != state["binHash"]:
        raise ValueError("Launcher changed since installation; nothing was removed")
    if APP.exists() and (not owned_app(APP) or tree_digest(APP) != state.get("appHash")):
        raise ValueError("App contents changed; nothing was removed")
    if AGENT.exists() and digest_file(AGENT) != state.get("agentHash"):
        raise ValueError("LaunchAgent changed since installation; nothing was removed")
    if args.dry_run:
        print("Would remove ThingsCTL plugin, owned bridge, LaunchAgent, and launcher; restore prior launcher and keep settings/journal.")
        return
    if state.get("pluginInstalled"):
        if not shutil.which("codex"):
            raise ValueError("Codex CLI is required to unregister the installed plugin")
        run(["codex", "plugin", "remove", "thingsctl@" + MARKETPLACE, "--json"])
        run(["codex", "plugin", "marketplace", "remove", MARKETPLACE, "--json"])
    if AGENT.exists():
        subprocess.run(["launchctl", "bootout", "gui/" + str(os.getuid()) + "/" + BUNDLE_ID], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        AGENT.unlink()
    if APP.exists():
        quit_bridge()
        shutil.rmtree(APP)
    if BIN.exists() and state.get("binHash"):
        BIN.unlink()
    backup = Path(state["binBackup"]) if state.get("binBackup") else None
    if backup and (backup.exists() or backup.is_symlink()):
        os.replace(backup, BIN)
    if MARKET_ROOT.is_dir() and not MARKET_ROOT.is_symlink():
        shutil.rmtree(MARKET_ROOT)
    MANIFEST.unlink()
    print("ThingsCTL removed. Existing task data, settings, operation journal, and macOS permission grants were preserved.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["install", "uninstall"])
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--skip-plugin", action="store_true")
    parser.add_argument("--no-launch-agent", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        (install if args.action == "install" else uninstall)(args)
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print("ThingsCTL installation error: " + str(exc), file=sys.stderr)
        print("Any staged installation is recorded in " + str(MANIFEST) + "; inspect it before retrying.", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
