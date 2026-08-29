import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_node(source):
    result = subprocess.run(
        ["node", "-e", source],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


class DirectorQaRegressionTests(unittest.TestCase):
    def test_prompt_state_uses_each_models_character_limit(self):
        data = run_node("""
const d=require('./static/js/smart-director-core.js');
console.log(JSON.stringify({
  seedanceEmpty:d.promptState({inputs:{prompt:{media_type:'text',min:1,max_chars:15000}}},''),
  seedanceFull:d.promptState({inputs:{prompt:{media_type:'text',min:1,max_chars:15000}}},'x'.repeat(15000)),
  wanTooLong:d.promptState({inputs:{prompt:{media_type:'text',min:1,min_chars:5,max_chars:20000}}},'x'.repeat(20001))
}));
""")

        self.assertFalse(data["seedanceEmpty"]["valid"])
        self.assertEqual(data["seedanceEmpty"]["maxChars"], 15000)
        self.assertTrue(data["seedanceFull"]["valid"])
        self.assertEqual(data["seedanceFull"]["remaining"], 0)
        self.assertFalse(data["wanTooLong"]["valid"])
        self.assertEqual(data["wanTooLong"]["maxChars"], 20000)

    def test_connection_placement_prefers_the_selected_adjacent_boundary(self):
        data = run_node("""
const d=require('./static/js/smart-director-core.js');
const clips=[
  {id:'clip-1',type:'ordinary',startMs:0,durationMs:5000},
  {id:'clip-2',type:'ordinary',startMs:5000,durationMs:5000}
];
console.log(JSON.stringify({
  selectedFirst:d.connectionPlacement('clip-1',clips),
  selectedLast:d.connectionPlacement('clip-2',clips),
  only:d.connectionPlacement('clip-1',[clips[0]])
}));
""")

        self.assertEqual(data["selectedFirst"], {"startMs": 4500, "durationMs": 1000})
        self.assertEqual(data["selectedLast"], {"startMs": 4500, "durationMs": 1000})
        self.assertEqual(data["only"], {"startMs": 4500, "durationMs": 1000})

    def test_operation_labels_are_human_readable_in_both_languages(self):
        data = run_node("""
const d=require('./static/js/smart-director-core.js');
console.log(JSON.stringify({
  zh:d.operationLabel('multimodal_to_video','zh'),
  en:d.operationLabel('image_to_video','en'),
  compact:d.operationLabel('image_to_video','zh',true),
  fallback:d.operationLabel('custom_mode','en')
}));
""")

        self.assertEqual(data["zh"], "多模态生成视频")
        self.assertEqual(data["en"], "Image to video")
        self.assertEqual(data["compact"], "图生视频")
        self.assertEqual(data["fallback"], "Custom mode")

    def test_director_ui_wires_prompt_limits_input_capacity_and_empty_export_state(self):
        source = (ROOT / "static/js/smart-canvas.js").read_text(encoding="utf-8")

        self.assertIn("SMART_DIRECTOR_CORE.promptState", source)
        self.assertIn("data-director-prompt-count", source)
        self.assertIn("data-director-input-disabled", source)
        self.assertIn("modelSupportsInputs(profile", source)
        self.assertIn("data-director-model-search", source)
        self.assertIn("SMART_DIRECTOR_CORE.operationLabel", source)
        self.assertIn("SMART_DIRECTOR_CORE.connectionPlacement", source)
        self.assertIn("hasExportableClip", source)
        self.assertIn("generation = selected.generation", source)

    def test_unset_parameter_trigger_keeps_the_parameter_name(self):
        source = (ROOT / "static/js/smart-canvas.js").read_text(encoding="utf-8")
        renderer = source[
            source.index("function renderCapabilityParameterControl"):
            source.index("function capabilityParameterDescription")
        ]

        self.assertIn("const triggerText = unset", renderer)
        self.assertIn("? label", renderer)
        self.assertNotIn("? capabilityUiText('默认','Default')", renderer)

    def test_short_connection_clips_have_safe_hit_targets_and_new_directors_avoid_toolbar(self):
        source = (ROOT / "static/js/smart-canvas.js").read_text(encoding="utf-8")
        css = (ROOT / "static/css/smart-canvas.css").read_text(encoding="utf-8")

        self.assertIn("function directorMenuNodeOrigin", source)
        self.assertIn("directorMenuNodeOrigin(p)", source)
        self.assertIn("world.getBoundingClientRect()", source)
        self.assertIn("min-width:18px", css)
        self.assertIn(".director-connection-clip .minimax-clip-delete", css)
        self.assertIn('grid-template-areas:"provider mode" "model model"', css)

    def test_switching_generic_clips_renders_the_selected_clips_settings(self):
        source = (ROOT / "static/js/smart-canvas.js").read_text(encoding="utf-8")
        handler = source[
            source.index("const previousSegmentId = node.selectedSegmentId"):
            source.index("el.querySelectorAll('[data-minimax-trim]')")
        ]

        self.assertIn("previousSegmentId !== seg?.id", handler)
        self.assertIn("render();", handler)
        self.assertIn("data-director-rendered-segment", source)
        self.assertIn("renderedSegmentId !== node.selectedSegmentId", source)

    def test_escape_is_safe_before_the_audio_preview_exists(self):
        source = (ROOT / "static/js/smart-canvas.js").read_text(encoding="utf-8")
        closer = source[
            source.index("function closeSmartAudioPreview"):
            source.index("function openSmartMaterialPreview")
        ]

        self.assertIn("if(audio){", closer)
        self.assertNotIn("audio?.load?.();\n    audio.onloadedmetadata", closer)


if __name__ == "__main__":
    unittest.main()
