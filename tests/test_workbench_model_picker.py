import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_node(script):
    result = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


class WorkbenchModelPickerTests(unittest.TestCase):
    def test_capability_candidates_cross_enabled_providers_without_display_name_merge(self):
        script = r'''
const c = require('./static/js/smart-model-capabilities.js');
const profile = (provider, model, family, variant, name='Fast') => ({
  model_id:model,
  family_id:family,
  variant_id:variant,
  variant_name:name,
  node_type:'video_generation',
  validation_mode:'strict',
  readiness:'ready',
  runnable:true,
  operation:'text_to_video',
  inputs:{prompt:{role:'prompt', media_type:'text', min:0, max:1}},
  parameters:{}
});
const catalog = {providers:[
  {id:'p1', name:'平台一', protocol:'p1', families:[{family_id:'seedance-2', display_name:'Seedance 2.0', node_type:'video_generation', variants:[profile('p1','p1-fast','seedance-2','fast')]}]},
  {id:'p2', name:'平台二', protocol:'p2', families:[{family_id:'seedance-2', display_name:'Seedance 2.0', node_type:'video_generation', variants:[profile('p2','p2-fast','seedance-2','fast')]}]},
  {id:'p3', name:'平台三', protocol:'p3', families:[{family_id:'other-seedance-2', display_name:'Seedance 2.0', node_type:'video_generation', variants:[profile('p3','p3-fast','other-seedance-2','fast')]}]}
]};
const families = c.familiesAcrossProviders(catalog, 'video_generation', {text:1}, ['p1','p2','p3'], '', {prompt:1}, {});
const merged = families.find(item => item.family_id === 'seedance-2');
const sameLabel = families.filter(item => item.display_name === 'Seedance 2.0');
console.log(JSON.stringify({
  familyCount:families.length,
  mergedProviders:merged?.provider_ids || [],
  mergedModels:(merged?.compatible_variants || []).map(item => item.model_id),
  sameLabelFamilyIds:sameLabel.map(item => item.family_id),
  variantKeys:[c.variantSelectionKey({variant_id:'mode',variant_name:'Fast'}), c.variantSelectionKey({variant_id:'mode',variant_name:'Mini'})]
}));
'''
        result = run_node(script)
        self.assertEqual(result["familyCount"], 2)
        self.assertEqual(result["mergedProviders"], ["p1", "p2"])
        self.assertEqual(result["mergedModels"], ["p1-fast", "p2-fast"])
        self.assertEqual(result["sameLabelFamilyIds"], ["seedance-2", "other-seedance-2"])
        self.assertNotEqual(result["variantKeys"][0], result["variantKeys"][1])

    def test_generation_renderers_use_family_variant_platform_order_and_one_bundle(self):
        source = (ROOT / "static/js/smart-canvas.js").read_text(encoding="utf-8")
        for function_name in (
            "function renderTextGenerationParams",
            "function renderApiParams",
            "function renderApiVideoParams",
            "function renderApiAudioParams",
            "function renderApiMusicParams",
        ):
            start = source.index(function_name)
            end = source.index("\nfunction ", start + len(function_name))
            renderer = source[start:end]
            self.assertLess(renderer.index("renderCapabilityFamilyControl"), renderer.index("renderCapabilityVariantControl"))
            self.assertLess(renderer.index("renderCapabilityVariantControl"), renderer.index("renderExecutionPlatformControl"))

        bundle_start = source.index("function renderCapabilityParameterBundleForSource")
        bundle_end = source.index("function renderCapabilityParameterBundle(", bundle_start)
        bundle = source[bundle_start:bundle_end]
        self.assertIn("markup:''", bundle)
        self.assertIn("renderCapabilitySettingsControl(orderedEntries", bundle)
        self.assertIn("orderedEntries", bundle)

    def test_parameter_popover_keeps_scroll_inside_canvas(self):
        source = (ROOT / "static/js/smart-canvas.js").read_text(encoding="utf-8")
        binding_start = source.index("function bindDynamicParams")
        binding_end = source.index("dynamicParams.querySelectorAll('[data-execution-platform-option]')", binding_start)
        bindings = source[binding_start:binding_end]
        self.assertIn("popover.addEventListener('wheel'", bindings)
        self.assertIn("event.stopPropagation()", bindings)
        self.assertIn("inCapabilitySettings", source)
        self.assertIn("requestAnimationFrame(() => positionPinnedSmartPopover(match))", source)


if __name__ == "__main__":
    unittest.main()
