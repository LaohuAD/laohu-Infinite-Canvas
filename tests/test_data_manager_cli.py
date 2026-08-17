import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "data_manager.py"


class DataManagerCliTests(unittest.TestCase):
    def run_cli(self, project_root, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(project_root), *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_status_outputs_machine_readable_summary(self):
        with tempfile.TemporaryDirectory() as temp:
            result = self.run_cli(temp, "status", "--json")

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["materials"], 0)
        self.assertEqual(payload["results"], 0)
        self.assertEqual(payload["root"], str(Path(temp).resolve()))

    def test_backup_and_restore_round_trip(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            canvas = root / "data" / "canvases" / "one.json"
            canvas.parent.mkdir(parents=True)
            canvas.write_text('{"title":"原始"}', encoding="utf-8")

            backup = self.run_cli(root, "backup", "--json")
            self.assertEqual(backup.returncode, 0, backup.stderr)
            archive = Path(json.loads(backup.stdout)["path"])
            canvas.write_text('{"title":"修改后"}', encoding="utf-8")

            restored = self.run_cli(root, "restore", str(archive), "--json")

            self.assertEqual(restored.returncode, 0, restored.stderr)
            self.assertEqual(json.loads(canvas.read_text(encoding="utf-8"))["title"], "原始")
            self.assertTrue(json.loads(restored.stdout)["safety_backup"])


if __name__ == "__main__":
    unittest.main()
