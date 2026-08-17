import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import main
from project_storage import ProjectStorage


class CanvasResultIndependenceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.storage = ProjectStorage(self.root)
        self.storage.ensure_layout()
        self.canvases = self.root / "data" / "canvases"
        self.canvases.mkdir(parents=True, exist_ok=True)
        self.patches = [
            patch.object(main, "PROJECT_STORAGE", self.storage),
            patch.object(main, "CANVAS_DIR", str(self.canvases)),
        ]
        for active_patch in self.patches:
            active_patch.start()

    def tearDown(self):
        for active_patch in reversed(self.patches):
            active_patch.stop()
        self.temp.cleanup()

    def create_canvas_and_result(self, canvas_id):
        source = self.root / "生成结果.png"
        source.write_bytes(b"independent-result")
        result = self.storage.store_result_file(source, source.name)
        canvas = {
            "id": canvas_id,
            "title": "测试画布",
            "nodes": [{"id": "node", "images": [{"url": result["url"]}]}],
            "connections": [],
            "logs": [{"id": "log", "outputs": [result["url"]]}],
            "updated_at": 1,
        }
        (self.canvases / f"{canvas_id}.json").write_text(
            json.dumps(canvas, ensure_ascii=False),
            encoding="utf-8",
        )
        return result

    async def test_soft_delete_canvas_keeps_generation_result(self):
        result = self.create_canvas_and_result("soft-delete")

        await main.delete_canvas("soft-delete")

        self.assertIsNotNone(self.storage.result_path(result["id"]))
        stored = json.loads((self.canvases / "soft-delete.json").read_text(encoding="utf-8"))
        self.assertTrue(stored["deleted_at"])

    async def test_purge_canvas_keeps_generation_result(self):
        result = self.create_canvas_and_result("purge")

        await main.purge_canvas("purge")

        self.assertFalse((self.canvases / "purge.json").exists())
        self.assertIsNotNone(self.storage.result_path(result["id"]))
        self.assertEqual(len(self.storage.list_results()), 1)


if __name__ == "__main__":
    unittest.main()
