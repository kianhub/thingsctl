import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.env = dict(os.environ, THINGSCTL_DEMO="1", THINGSCTL_JOURNAL=str(Path(self.temp.name) / "journal.sqlite3"))

    def run_cli(self, *args):
        return subprocess.run([str(ROOT / "thingsctl"), *args], cwd=str(ROOT), env=self.env,
                              text=True, capture_output=True)

    def test_update_and_clear_flags_route_to_shared_core(self):
        result = self.run_cli("update", "demo-task-1", "--title", "CLI title", "--clear-tags", "--clear-deadline", "--when", "someday", "--inbox", "--json")
        self.assertEqual(result.returncode, 0, result.stdout)
        data = json.loads(result.stdout)
        self.assertEqual(data["operation"]["status"], "verified")
        self.assertEqual(data["data"]["task"]["title"], "CLI title")
        self.assertEqual(data["data"]["task"]["tags"], [])
        self.assertEqual(data["data"]["task"]["whenKind"], "someday")

    def test_invalid_calendar_date_returns_json_error_and_nonzero_exit(self):
        result = self.run_cli("add", "A", "--deadline", "2026-02-30", "--json")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)["error"]["code"], "VALIDATION_ERROR")
        self.assertEqual(result.stderr, "")

    def test_human_errors_go_to_stderr(self):
        result = self.run_cli("get", "missing")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("NOT_FOUND", result.stderr)

    def test_duplicate_tag_and_clear_option_rejected(self):
        result = self.run_cli("add", "A", "--tag", "Focus", "--clear-tags", "--json")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)["error"]["code"], "VALIDATION_ERROR")


if __name__ == "__main__":
    unittest.main()
