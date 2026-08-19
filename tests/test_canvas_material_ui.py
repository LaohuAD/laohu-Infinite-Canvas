import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class CanvasMaterialUiTests(unittest.TestCase):
    def setUp(self):
        self.smart_html = (ROOT / "static" / "smart-canvas.html").read_text(encoding="utf-8")
        self.smart_script = (ROOT / "static" / "js" / "smart-canvas.js").read_text(encoding="utf-8")

    def test_only_smart_canvas_loads_shared_material_promote_dialog(self):
        self.assertFalse((ROOT / "static" / "canvas.html").exists())
        self.assertFalse((ROOT / "static" / "js" / "canvas.js").exists())
        self.assertFalse((ROOT / "static" / "css" / "canvas.css").exists())
        self.assertIn("/static/js/material-promote.js", self.smart_html)

    def test_smart_canvas_material_panels_use_current_names_and_all_media(self):
        self.assertIn("临时素材", self.smart_script)
        self.assertIn("输入素材", self.smart_html)
        self.assertNotIn("图片资产", self.smart_html)
        self.assertNotIn("filter(item => assetMediaKind(item) === 'image')", self.smart_script)

    def test_smart_canvas_media_nodes_offer_promote_action(self):
        self.assertIn("key:'promote'", self.smart_script)
        self.assertIn("MaterialPromote.open", self.smart_script)

    def test_smart_canvas_material_panel_names_workflows_and_results_explicitly(self):
        self.assertIn("画布工作流", self.smart_html)
        self.assertIn("生成结果", self.smart_html)
        self.assertNotIn('data-i18n="smart.assetWorkflows">工作流</button>', self.smart_html)


if __name__ == "__main__":
    unittest.main()
