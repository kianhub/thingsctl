#!/usr/bin/env python3
"""Build a self-contained local plugin source or private ZIP, without installing."""
from __future__ import annotations
import argparse
import hashlib
import json
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
GENERATED_PLUGIN_FILES = ("runtime", "ui", "LICENSE", "INSTALLATION.md", "THIRD-PARTY-NOTICES.txt", ".thingsctl-package.json")


def copy_tree(source, destination, exclude_roots=()):
    for path in source.rglob("*"):
        relative = path.relative_to(source)
        if relative.parts[0] in exclude_roots:
            continue
        if path.is_symlink():
            raise ValueError("Plugin packages cannot contain symlinks: " + str(path))
        if "__pycache__" in relative.parts or path.suffix == ".pyc" or ".DS_Store" in relative.parts:
            continue
        target = destination / relative
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif path.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)


def stage_plugin(destination, repo=REPO):
    destination = Path(destination)
    for source in (repo / "plugins/thingsctl", repo / "thingsctl_pkg", repo / "ui"):
        if destination.resolve() == source.resolve() or source.resolve() in destination.resolve().parents:
            raise ValueError("Stage the plugin outside its source directories: " + str(destination))
    if destination.exists():
        raise ValueError("Staging destination already exists: " + str(destination))
    destination.mkdir(parents=True)
    # The source plugin also ships generated files for direct marketplace installs.
    # Always replace those files from their canonical sources, so removed runtime
    # modules and stale workspace bundles cannot survive a subsequent package.
    copy_tree(repo / "plugins/thingsctl", destination, GENERATED_PLUGIN_FILES)
    copy_tree(repo / "thingsctl_pkg", destination / "runtime/thingsctl_pkg")
    ui = repo / "ui/dist/things-workspace.html"
    if not ui.is_file():
        raise ValueError("Bundled workspace missing: ui/dist/things-workspace.html. Restore the checked-in bundle or rebuild it with pnpm -C ui build.")
    (destination / "ui").mkdir(exist_ok=True)
    shutil.copy2(ui, destination / "ui/workspace.html")
    shutil.copy2(repo / "LICENSE", destination / "LICENSE")
    notices = repo / "ui/THIRD-PARTY-NOTICES.txt"
    if notices.is_file():
        shutil.copy2(notices, destination / "THIRD-PARTY-NOTICES.txt")
    docs = repo / "docs/INSTALLATION.md"
    if docs.is_file():
        shutil.copy2(docs, destination / "INSTALLATION.md")
    manifests = (destination / "plugin.json", destination / ".codex-plugin/plugin.json")
    # Normalize build metadata before hashing, including when packaging an already
    # synchronized source plugin. Otherwise every repeat would change the version.
    for manifest in manifests:
        value = json.loads(manifest.read_text())
        value["version"] = value["version"].split("+")[0]
        manifest.write_text(json.dumps(value, indent=2) + "\n")
    digest = hashlib.sha256()
    for path in sorted(destination.rglob("*")):
        if path.is_file():
            digest.update(str(path.relative_to(destination)).encode())
            digest.update(path.read_bytes())
    build = digest.hexdigest()[:12]
    for manifest in manifests:
        value = json.loads(manifest.read_text())
        value["version"] = value["version"].split("+")[0] + "+" + build
        manifest.write_text(json.dumps(value, indent=2) + "\n")
    required = ("runtime/thingsctl_pkg/core.py", "runtime/thingsctl_pkg/cli.py", "runtime/thingsctl_pkg/mcp_server.py",
                "scripts/run-mcp", "ui/workspace.html", "plugin.json", "mcp.json", ".codex-plugin/plugin.json")
    for filename in required:
        if not (destination / filename).is_file():
            raise ValueError("Missing packaged entrypoint: " + filename)
    (destination / ".thingsctl-package.json").write_text(json.dumps({"name": "thingsctl", "build": build}, indent=2) + "\n")
    return build


def sync_plugin_source(repo=REPO):
    """Refresh the self-contained marketplace source from canonical runtime/UI."""
    source = repo / "plugins/thingsctl"
    with tempfile.TemporaryDirectory(prefix="thingsctl-sync-", dir=repo / "plugins") as directory:
        staged = Path(directory) / "thingsctl"
        build = stage_plugin(staged, repo=repo)
        for name in GENERATED_PLUGIN_FILES:
            target = source / name
            if target.is_symlink():
                raise ValueError("Refusing to replace symlink in plugin source: " + str(target))
            if target.is_dir():
                shutil.rmtree(target)
            elif target.exists():
                target.unlink()
            generated = staged / name
            if generated.is_dir():
                copy_tree(generated, target)
            elif generated.is_file():
                shutil.copy2(generated, target)
        for name in ("plugin.json", ".codex-plugin/plugin.json"):
            shutil.copy2(staged / name, source / name)
    return build


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Fresh destination directory for the plugin")
    parser.add_argument("--sync-source", action="store_true", help="Refresh plugins/thingsctl for direct marketplace installation")
    parser.add_argument("--zip", dest="archive", type=Path, help="Write a private plugin ZIP outside the plugin directory")
    args = parser.parse_args()
    if not args.output and not args.sync_source:
        parser.error("Use --output or --sync-source")
    if args.archive and not args.output:
        parser.error("--zip requires --output")
    if args.archive and (args.output.resolve() == args.archive.resolve() or args.output.resolve() in args.archive.resolve().parents):
        parser.error("Write the archive outside its plugin directory")
    build = sync_plugin_source() if args.sync_source else None
    if args.output:
        build = stage_plugin(args.output)
    if args.archive:
        args.archive.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(args.archive, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(args.output.rglob("*")):
                if path.is_file():
                    entry = zipfile.ZipInfo("thingsctl/" + path.relative_to(args.output).as_posix(), (1980, 1, 1, 0, 0, 0))
                    entry.compress_type = zipfile.ZIP_DEFLATED
                    entry.create_system = 3
                    entry.external_attr = (0o100755 if path.stat().st_mode & 0o111 else 0o100644) << 16
                    archive.writestr(entry, path.read_bytes())
    print(json.dumps({"plugin": str((args.output or REPO / "plugins/thingsctl").resolve()), "build": build, "archive": str(args.archive.resolve()) if args.archive else None}))


if __name__ == "__main__":
    main()
