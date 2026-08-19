import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class AssetManagerUiTests(unittest.TestCase):
    def setUp(self):
        self.html = (ROOT / "static" / "asset-manager.html").read_text(encoding="utf-8")
        self.script = (ROOT / "static" / "js" / "asset-manager.js").read_text(encoding="utf-8")
        self.promote_script = (ROOT / "static" / "js" / "material-promote.js").read_text(encoding="utf-8")
        self.styles = (ROOT / "static" / "css" / "asset-manager.css").read_text(encoding="utf-8")

    def test_top_navigation_has_four_clear_sections(self):
        tabs = re.findall(r'data-tab="([^"]+)"[^>]*>.*?<span[^>]*>([^<]+)</span>', self.html)

        self.assertEqual(tabs, [
            ("assets", "输入素材"),
            ("workflows", "画布工作流"),
            ("prompts", "提示词库"),
            ("results", "生成结果"),
        ])

    def test_input_materials_use_unified_left_navigation(self):
        self.assertIn("let activeInputScope = 'asset';", self.script)
        self.assertIn("function renderUnifiedInputNavigation()", self.script)
        self.assertIn('data-input-scope="asset"', self.script)
        self.assertIn('data-input-scope="temporary"', self.script)
        self.assertIn("资产素材", self.script)
        self.assertIn("临时素材", self.script)
        self.assertNotIn("input-scope-switcher", self.script)
        self.assertNotIn("input-scope-switcher", self.styles)

    def test_temporary_materials_are_flat_and_can_be_promoted(self):
        navigation = self.script.split("function renderUnifiedInputNavigation(){", 1)[1].split("function updateSearchQueryFromInput", 1)[0]
        self.assertNotIn("renderLocalUploadFolderBranch", navigation)
        self.assertNotIn("renderLocalUploadSmartClassTree", navigation)
        self.assertIn("data-localup-promote", self.script)
        self.assertIn("MaterialPromote.open", self.script)

    def test_asset_cards_use_hover_cues_and_double_click_preview(self):
        self.assertIn("asset-audio-waveform", self.script)
        self.assertIn("asset-lightbox-audio", self.script)
        self.assertIn("asset-lightbox-text", self.script)
        self.assertIn("path.startsWith('/api/materials/')", self.script)
        self.assertIn("asset-card-hover-cue", self.script)
        self.assertIn("root.addEventListener('dblclick'", self.script)
        self.assertIn("function refreshAssetSelectionOnly()", self.script)
        self.assertIn("function refreshLocalSelectionOnly()", self.script)
        double_click_handler = self.script.split("root.addEventListener('dblclick'", 1)[1].split("root.addEventListener('click'", 1)[0]
        self.assertNotIn("audio,video", double_click_handler)

        temporary_card = self.script.split("function renderLocalUploadCard(item){", 1)[1].split("function renderLocalUploadDetail", 1)[0]
        asset_card = self.script.split("function renderAssetCard(item){", 1)[1].split("function renderAssetLibraryDetail", 1)[0]
        self.assertNotIn("asset-card-actions", temporary_card)
        self.assertNotIn("asset-card-actions", asset_card)

    def test_temporary_material_detail_keeps_common_actions_only(self):
        detail = self.script.split("function renderLocalUploadDetail(item){", 1)[1].split("function refreshLocalUploadSelectionOnly", 1)[0]
        self.assertIn("data-localup-preview", detail)
        self.assertIn("data-localup-download", detail)
        self.assertNotIn("data-localup-open", detail)
        self.assertNotIn("data-localup-copy", detail)

    def test_material_editing_preserves_extension_and_uses_inline_editor(self):
        self.assertIn("function materialNameParts(item)", self.script)
        self.assertIn("function beginAssetInlineRename(id)", self.script)
        self.assertIn("asset-name-extension", self.script)
        self.assertIn("asset-name-extension", self.styles)
        self.assertIn("data-localup-delete-one", self.script)
        self.assertIn("data-asset-delete", self.script)

    def test_promote_dialog_reports_errors_and_recovers(self):
        self.assertIn("data-promote-error", self.promote_script)
        self.assertIn("errorBox.textContent", self.promote_script)
        self.assertIn("saveButton.disabled = false", self.promote_script)
        self.assertIn("data-promote-add-category", self.promote_script)
        self.assertNotIn("新建分组（可选）", self.promote_script)
        self.assertIn("resultIdFromUrl", self.promote_script)
        self.assertIn("/api/results/${encodeURIComponent(entry.id)}/promote", self.promote_script)

    def test_generation_results_are_independent_and_have_five_filters(self):
        self.assertIn("apiJson('/api/results')", self.script)
        self.assertIn("apiJson('/api/results/delete'", self.script)
        for category_id, label in (
            ("all", "全部"),
            ("image", "图片"),
            ("video", "视频"),
            ("audio", "音频"),
            ("text", "文本"),
        ):
            self.assertIn(f"id:'{category_id}', name:'{label}'", self.script)
        self.assertNotIn("apiJson('/api/canvas-assets')", self.script)
        self.assertIn("source_canvas", self.script)
        self.assertIn("未记录来源", self.script)

    def test_generation_results_share_material_preview_edit_and_promote_actions(self):
        result_detail = self.script.split("function renderCanvasAssetDetail(item){", 1)[1].split("function refreshCanvasAssetSelectionOnly", 1)[0]
        self.assertIn("data-canvas-asset-preview", result_detail)
        self.assertIn("data-result-rename", result_detail)
        self.assertIn("data-result-inline-name", result_detail)
        self.assertIn("data-result-promote", result_detail)
        self.assertIn("data-text-edit", result_detail)
        self.assertIn("function beginResultInlineRename(id)", self.script)
        self.assertIn("function promoteCanvasAssetItem(id)", self.script)
        self.assertIn("function openTextContentEditor(source, id)", self.script)
        self.assertIn("function materialOverlayHost()", self.script)
        self.assertGreaterEqual(self.script.count("materialOverlayHost().appendChild(overlay)"), 2)
        self.assertIn("/api/results/${encodeURIComponent(id)}", self.script)
        self.assertIn("root.addEventListener('dblclick'", self.script)
        self.assertIn(".asset-text-editor {", self.styles)
        self.assertIn("background:var(--card)", self.styles)

    def test_default_asset_library_has_no_delete_action(self):
        self.assertIn("activeAssetLibraryId === 'default'", self.script)

    def test_skill_library_imports_markdown_through_shared_prompt_assets(self):
        main_source = (ROOT / "main.py").read_text(encoding="utf-8")

        self.assertIn("def seed_skill_library", main_source)
        self.assertIn('"kind": "skill" if', main_source)
        self.assertIn('@app.post("/api/prompt-libraries/skills/import")', main_source)
        self.assertIn('accept=".md,text/markdown,text/plain"', self.script)
        self.assertIn("data-prompt-skill-import", self.script)
        self.assertIn("new FormData()", self.script)

    def test_skill_selection_keeps_stable_id_and_runtime_snapshot(self):
        canvas_source = (ROOT / "static/js/smart-canvas.js").read_text(encoding="utf-8")

        self.assertIn("libraryKind:activeLibrary.kind", canvas_source)
        self.assertIn("textSystemSkillId", canvas_source)
        self.assertIn("textSystemSkillSnapshot", canvas_source)
        self.assertIn("skill:cloneSmartSettings(runSettings.textSystemSkillSnapshot", canvas_source)


if __name__ == "__main__":
    unittest.main()
