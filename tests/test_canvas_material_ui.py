import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class CanvasMaterialUiTests(unittest.TestCase):
    def setUp(self):
        self.canvas_html = (ROOT / "static" / "canvas.html").read_text(encoding="utf-8")
        self.smart_html = (ROOT / "static" / "smart-canvas.html").read_text(encoding="utf-8")
        self.canvas_script = (ROOT / "static" / "js" / "canvas.js").read_text(encoding="utf-8")
        self.smart_script = (ROOT / "static" / "js" / "smart-canvas.js").read_text(encoding="utf-8")

    def test_both_canvases_load_shared_material_promote_dialog(self):
        self.assertIn("/static/js/material-promote.js", self.canvas_html)
        self.assertIn("/static/js/material-promote.js", self.smart_html)

    def test_canvas_material_panels_use_current_names_and_all_media(self):
        self.assertIn("临时素材", self.canvas_script)
        self.assertIn("临时素材", self.smart_script)
        self.assertIn("输入素材", self.canvas_html)
        self.assertIn("输入素材", self.smart_html)
        self.assertNotIn("图片资产", self.canvas_html)
        self.assertNotIn("图片资产", self.smart_html)
        self.assertNotIn("filter(item => canvasAssetItemKind(item) === 'image')", self.canvas_script)
        self.assertNotIn("filter(item => assetMediaKind(item) === 'image')", self.smart_script)

    def test_canvas_media_nodes_offer_promote_action(self):
        self.assertIn("data-material-promote", self.canvas_script)
        self.assertIn("key:'promote'", self.smart_script)
        self.assertIn("MaterialPromote.open", self.canvas_script)
        self.assertIn("MaterialPromote.open", self.smart_script)

    def test_smart_canvas_material_panel_names_workflows_and_results_explicitly(self):
        self.assertIn("画布工作流", self.smart_html)
        self.assertIn("生成结果", self.smart_html)
        self.assertNotIn('data-i18n="smart.assetWorkflows">工作流</button>', self.smart_html)


if __name__ == "__main__":
    unittest.main()
