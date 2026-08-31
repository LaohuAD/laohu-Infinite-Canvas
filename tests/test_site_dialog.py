import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SiteDialogTests(unittest.TestCase):
    CURRENT_PRODUCT_FILES = (
        "static/js/api-settings.js",
        "static/js/comfyui-settings.js",
        "static/index.html",
        "static/angle.html",
        "static/enhance.html",
        "static/klein.html",
        "static/online.html",
        "static/zimage.html",
        "static/gpt-chat.html",
        "static/js/history-bulk-manager.js",
        "static/js/asset-manager.js",
    )

    def test_theme_exposes_shared_async_dialog_api(self):
        source = (ROOT / "static/js/theme.js").read_text(encoding="utf-8")

        self.assertIn("window.StudioDialog", source)
        self.assertIn("alert(message", source)
        self.assertIn("confirm(message", source)
        self.assertIn("prompt(message", source)
        self.assertIn("studio-dialog-overlay", source)
        self.assertIn("aria-modal", source)
        self.assertIn("previousFocus", source)
        self.assertIn("event.key === 'Escape'", source)
        self.assertIn("event.key === 'Tab'", source)
        self.assertIn("html.studio-theme-dark > .studio-dialog-overlay", source)
        self.assertIn("--studio-dialog-panel", source)

    def test_current_product_has_no_browser_native_dialog_calls(self):
        pattern = re.compile(r"(?<![\w.])(alert|confirm|prompt)\s*\(")
        for relative in self.CURRENT_PRODUCT_FILES:
            source = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIsNone(pattern.search(source), relative)
            self.assertNotIn("window.alert(", source, relative)
            self.assertNotIn("window.confirm(", source, relative)
            self.assertNotIn("window.prompt(", source, relative)

    def test_api_and_comfy_settings_use_shared_dialogs(self):
        api = (ROOT / "static/js/api-settings.js").read_text(encoding="utf-8")
        comfy = (ROOT / "static/js/comfyui-settings.js").read_text(encoding="utf-8")

        self.assertIn("await StudioDialog.confirm(trf('api.rhEnableUnverifiedConfirm'", api)
        self.assertIn("await StudioDialog.prompt(tr('comfy.namePrompt')", comfy)
        self.assertIn("type:'danger'", api)
        self.assertIn("type:'danger'", comfy)

    def test_home_and_legacy_generators_use_async_dialogs(self):
        home = (ROOT / "static/index.html").read_text(encoding="utf-8")
        angle = (ROOT / "static/angle.html").read_text(encoding="utf-8")

        self.assertIn("await StudioDialog.prompt(promptMsg", home)
        self.assertIn("await StudioDialog.confirm", home)
        self.assertIn("await StudioDialog.confirm", angle)

    def test_chat_history_and_assets_use_shared_dialogs(self):
        chat = (ROOT / "static/gpt-chat.html").read_text(encoding="utf-8")
        history = (ROOT / "static/js/history-bulk-manager.js").read_text(encoding="utf-8")
        assets = (ROOT / "static/js/asset-manager.js").read_text(encoding="utf-8")

        self.assertIn("await StudioDialog.confirm", chat)
        self.assertIn("await StudioDialog.confirm", history)
        self.assertIn("await StudioDialog.confirm", assets)


if __name__ == "__main__":
    unittest.main()
