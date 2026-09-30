"""Installer ownership/recovery checks in temporary paths; no apps are launched."""
import argparse
import json
import plistlib
import sys
import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import install_plugin as installer
sys.path.pop(0)


class InstallationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.support = root / "support"
        self.repo = root / "repo"
        source_app = self.repo / "dist/ThingsCTL Bridge.app"
        (source_app / "Contents/MacOS").mkdir(parents=True)
        (source_app / "Contents/Info.plist").write_bytes(plistlib.dumps({"CFBundleIdentifier": installer.BUNDLE_ID}))
        (source_app / installer.BRIDGE_EXECUTABLE).write_text("fixture executable")
        (source_app / installer.BRIDGE_EXECUTABLE).chmod(0o755)
        (self.repo / "ui/dist").mkdir(parents=True)
        (self.repo / "ui/dist/things-workspace.html").write_text("fixture html")
        (self.repo / ".agents/plugins").mkdir(parents=True)
        (self.repo / ".agents/plugins/marketplace.json").write_text('{"name":"thingsctl-local","plugins":[]}')
        self.app, self.bin, self.agent = root / "apps/ThingsCTL Bridge.app", root / "bin/thingsctl", root / "agents/bridge.plist"
        self.manifest = self.support / "install-manifest.json"
        self.calls = []
        self.patches = patch.multiple(installer, SUPPORT=self.support, REPO=self.repo, APP=self.app, BIN=self.bin,
                                     AGENT=self.agent, MARKET_ROOT=self.support / "marketplace", MANIFEST=self.manifest)
        self.patches.start()
        self.addCleanup(self.patches.stop)
        self.run_patch = patch.object(installer, "run", side_effect=lambda argv, **kw: self.calls.append([str(v) for v in argv]))
        self.run_patch.start()
        self.addCleanup(self.run_patch.stop)
        self.stage_patch = patch.object(installer, "stage_plugin", side_effect=self.fake_stage)
        self.stage_patch.start()
        self.addCleanup(self.stage_patch.stop)
        self.health_patch = patch.object(installer, "check_installation", return_value={"status": "permission_not_verified", "message": "Fixture setup pending"})
        self.health_mock = self.health_patch.start()
        self.addCleanup(self.health_patch.stop)
        self.args = argparse.Namespace(skip_build=True, skip_plugin=True, no_launch_agent=True, dry_run=False)

    @staticmethod
    def fake_stage(destination, repo=None):
        (destination / "scripts").mkdir(parents=True)
        (destination / "scripts/runner.py").write_text("fixture runtime")
        (destination / ".thingsctl-package.json").write_text('{"name":"thingsctl","build":"fixture"}')
        return "fixture"

    def test_fresh_install_preserves_prior_launcher_and_uninstall_restores(self):
        self.bin.parent.mkdir()
        self.bin.write_text("prior executable")
        installer.install(self.args)
        state = json.loads(self.manifest.read_text())
        self.assertEqual(state["status"], "installed")
        self.assertTrue(installer.owned_app(self.app))
        self.assertEqual(Path(state["binBackup"]).read_text(), "prior executable")
        self.assertIn("Managed by ThingsCTL", self.bin.read_text())
        installer.uninstall(self.args)
        self.assertEqual(self.bin.read_text(), "prior executable")
        self.assertFalse(self.app.exists())
        self.assertFalse(self.manifest.exists())

    def test_reinstall_validates_owned_app_and_refuses_modification(self):
        installer.install(self.args)
        installer.install(self.args)
        state = json.loads(self.manifest.read_text())
        self.assertEqual(state["appHash"], installer.tree_digest(self.app))
        (self.app / installer.BRIDGE_EXECUTABLE).write_text("changed by user")
        with self.assertRaisesRegex(ValueError, "installer-owned"):
            installer.install(self.args)
        self.assertEqual((self.app / installer.BRIDGE_EXECUTABLE).read_text(), "changed by user")

    def test_failed_reinstall_retains_recovery_copy(self):
        installer.install(self.args)
        previous = self.bin.read_text()
        original = installer.atomic_write
        with patch.object(installer, "atomic_write", wraps=original) as atomic:
            def failing(path, data, mode=0o600):
                if path == self.bin:
                    raise OSError("fixture write failure")
                return original(path, data, mode)
            atomic.side_effect = failing
            with self.assertRaisesRegex(OSError, "fixture write failure"):
                installer.install(self.args)
        state = json.loads(self.manifest.read_text())
        recovery = Path(state["recovery"])
        self.assertEqual((recovery / "bin").read_text(), previous)
        self.assertTrue((recovery / "app/Contents/Info.plist").exists())
        self.assertTrue((recovery / "marketplace/plugins/thingsctl/scripts/runner.py").exists())

    def test_unavailable_final_doctor_keeps_installation_complete(self):
        self.health_mock.return_value = {"status": "needs_attention", "message": "Run doctor after starting the bridge"}
        installer.install(self.args)
        state = json.loads(self.manifest.read_text())
        self.assertEqual(state["status"], "installed")
        self.assertEqual(state["connectionStatus"], "needs_attention")
        self.assertNotIn("recovery", state)
        self.assertTrue(self.app.exists())
        self.assertTrue(self.bin.exists())

    def test_foreign_app_is_never_removed(self):
        self.app.mkdir(parents=True)
        (self.app / "foreign").write_text("keep")
        with self.assertRaisesRegex(ValueError, "installer-owned"):
            installer.install(self.args)
        self.assertEqual((self.app / "foreign").read_text(), "keep")
        self.assertFalse(self.manifest.exists())

    def test_missing_bundled_ui_is_actionable_without_mutation(self):
        (self.repo / "ui/dist/things-workspace.html").unlink()
        with self.assertRaisesRegex(ValueError, "pnpm -C ui build"):
            installer.install(self.args)
        self.assertFalse(self.manifest.exists())
        self.assertFalse(self.app.exists())

    def test_modified_launch_agent_is_preserved_on_uninstall(self):
        self.args.no_launch_agent = False
        with patch.object(installer.subprocess, "run"):
            installer.install(self.args)
        self.agent.write_text("foreign launch agent")
        with self.assertRaisesRegex(ValueError, "LaunchAgent changed"):
            installer.uninstall(self.args)
        self.assertEqual(self.agent.read_text(), "foreign launch agent")


class HealthCheckTests(unittest.TestCase):
    def diagnostic(self, code, value):
        with patch.object(installer.subprocess, "run", return_value=SimpleNamespace(returncode=code, stdout=json.dumps(value))):
            return installer.check_installation()

    def test_denied_permission_is_attention_even_with_successful_diagnostic(self):
        health = self.diagnostic(0, {"ok": True, "data": {"automation": "denied", "hostRunning": True}})
        self.assertEqual(health["status"], "needs_attention")

    def test_granted_permission_is_ready(self):
        health = self.diagnostic(0, {"ok": True, "data": {"automation": "granted", "hostRunning": True, "thingsInstalled": True}})
        self.assertEqual(health["status"], "ready")

    def test_metadata_only_connection_does_not_claim_tasks_verified(self):
        health = self.diagnostic(0, {"ok": True, "data": {"automation": "not-requested", "hostRunning": True, "thingsInstalled": True}})
        self.assertEqual(health["status"], "permission_not_verified")

    def test_timeout_remains_actionable(self):
        with patch.object(installer.subprocess, "run", side_effect=installer.subprocess.TimeoutExpired("fixture", 20)):
            health = installer.check_installation()
        self.assertEqual(health["status"], "needs_attention")


if __name__ == "__main__":
    unittest.main()
