import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main


NODE_OUTPUT_TYPES = {
    "text_generation": "text",
    "image_generation": "image",
    "video_generation": "video",
    "audio_generation": {"audio", "text"},
    "music_generation": "audio",
}


CANVAS_ROUTES = {
    "text_generation": "/api/canvas-llm",
    "image_generation": "/api/canvas-image-tasks",
    "video_generation": "/api/canvas-video",
    "audio_generation": "/api/canvas-audio",
    "music_generation": "/api/canvas-music",
}


def _sample_value(spec):
    parameter_type = str(spec.get("type") or "text").lower()
    if parameter_type == "enum":
        options = spec.get("options") or []
        return options[0] if options else "dry-run-option"
    if parameter_type == "boolean":
        return spec.get("default", False)
    if parameter_type == "integer":
        return spec.get("default", spec.get("min", 1))
    if parameter_type == "number":
        return spec.get("default", spec.get("min", 1))
    return "dry-run-value"


def _profile_fixture(profile):
    inputs = {}
    input_counts = {}
    input_roles = {}
    for key, spec in (profile.get("inputs") or {}).items():
        media_type = str(spec.get("media_type") or "text")
        minimum = max(0, int(spec.get("min") or 0))
        count = max(1 if key == "prompt" else 0, minimum)
        input_counts[key] = count
        role = str(spec.get("role") or key)
        if count:
            input_roles[role] = input_roles.get(role, 0) + count
        if media_type == "text":
            inputs[key] = "dry-run text"
        elif media_type == "image":
            inputs[key] = "asset://dry-run-image"
        elif media_type == "video":
            inputs[key] = "asset://dry-run-video"
        elif media_type == "audio":
            inputs[key] = "asset://dry-run-audio"
    parameters = {
        key: _sample_value(spec)
        for key, spec in (profile.get("parameters") or {}).items()
        if str(spec.get("level") or "optional").lower() != "advanced"
    }
    return inputs, input_counts, input_roles, parameters


class ConfiguredModelCapabilityMatrixTests(unittest.TestCase):
    def test_ai_money_new_llm_models_are_configured_and_dry_run_without_network(self):
        provider = next(item for item in main.load_api_providers() if item.get("id") == "ai-money")
        self.assertIn("qwen/qwen3.8-max", provider.get("chat_models") or [])
        self.assertIn("laohuaimoney/gk-4.6", provider.get("chat_models") or [])

        catalog = main.MODEL_CAPABILITY_REGISTRY.build_catalog([provider])
        models = {item["model_id"]: item for item in catalog["providers"][0]["models"]}
        qwen = models["qwen/qwen3.8-max"]
        gk = models["laohuaimoney/gk-4.6"]
        self.assertEqual(qwen["node_type"], "text_generation")
        self.assertTrue(qwen["runnable"])
        self.assertEqual(gk["inputs"]["reference"]["media_type"], "image")
        self.assertTrue(gk["runnable"])

        for model_id, input_counts, inputs, input_roles in (
            ("qwen/qwen3.8-max", {"text": 1, "image": 0}, {"prompt": "测试"}, {"prompt": 1}),
            (
                "laohuaimoney/gk-4.6",
                {"text": 1, "image": 1},
                {"prompt": "描述图片", "reference": ["asset://reference-image"]},
                {"prompt": 1, "reference": 1},
            ),
        ):
            profile = main.MODEL_CAPABILITY_REGISTRY.validate_request(
                [provider], "ai-money", model_id, "text_generation",
                input_counts=input_counts, input_roles=input_roles, parameters={},
            )
            dry_run = main.MODEL_CAPABILITY_REGISTRY.build_dry_run(
                profile, inputs=inputs, input_roles=input_roles, parameters={},
            )
            self.assertFalse(dry_run["network_requested"])
            self.assertEqual(dry_run["standard_request"]["model_id"], model_id)
            self.assertEqual(dry_run["platform_request"].get("max_tokens"), None)
            self.assertTrue(dry_run["platform_request"].get("messages"))

    def test_hidden_model_parameter_comes_from_selected_model_identity(self):
        providers = [provider for provider in main.load_api_providers() if provider.get("id") == "codex"]
        profile = main.MODEL_CAPABILITY_REGISTRY.validate_request(
            providers,
            "codex",
            "gpt-5.5",
            "text_generation",
            input_counts={"text": 1, "image": 1, "video": 0, "audio": 0},
            input_roles={"prompt": 1, "reference": 1},
            parameters={},
        )
        self.assertEqual(profile["model_id"], "gpt-5.5")
        dry_run = main.MODEL_CAPABILITY_REGISTRY.build_dry_run(
            profile,
            inputs={"prompt": "识别图片内容", "reference": ["asset://reference-image"]},
            parameters={},
            input_roles={"prompt": 1, "reference": 1},
        )
        self.assertEqual(dry_run["platform_request"]["--model"], "gpt-5.5")
        self.assertEqual(dry_run["platform_request"]["--image"], ["asset://reference-image"])

    def test_every_configured_ready_model_builds_a_no_network_request(self):
        providers = [provider for provider in main.load_api_providers() if provider.get("enabled") is not False]
        ready_count = 0
        for provider in providers:
            catalog = main.MODEL_CAPABILITY_REGISTRY.build_catalog([provider])
            runtime_provider = next(
                (item for item in catalog.get("providers", []) if item.get("id") == provider.get("id")),
                None,
            )
            if not runtime_provider:
                continue
            for profile in runtime_provider.get("models") or []:
                if not profile.get("runnable"):
                    continue
                ready_count += 1
                inputs, input_counts, input_roles, parameters = _profile_fixture(profile)
                validated = main.MODEL_CAPABILITY_REGISTRY.validate_request(
                    providers,
                    provider.get("id"),
                    profile.get("model_id"),
                    profile.get("node_type"),
                    input_counts=input_counts,
                    input_roles=input_roles,
                    parameters=parameters,
                )
                dry_run = main.MODEL_CAPABILITY_REGISTRY.build_dry_run(
                    validated,
                    inputs=inputs,
                    parameters=parameters,
                    input_roles=input_roles,
                )
                self.assertFalse(dry_run["network_requested"], profile.get("model_id"))
                self.assertEqual(dry_run["validation"], "contract_validated")
                self.assertTrue(profile.get("request_mapping"), profile.get("model_id"))
                platform = profile.get("platform") or {}
                self.assertTrue(
                    platform.get("endpoint") or platform.get("commands") or platform.get("transport"),
                    profile.get("model_id"),
                )
                self.assertIn(profile.get("node_type"), CANVAS_ROUTES)
                expected_output = NODE_OUTPUT_TYPES[profile.get("node_type")]
                if isinstance(expected_output, set):
                    self.assertIn(dry_run["result_contract"]["media_type"], expected_output, profile.get("model_id"))
                else:
                    self.assertEqual(dry_run["result_contract"]["media_type"], expected_output, profile.get("model_id"))
        self.assertGreater(ready_count, 0)

    def test_unfinished_models_are_visible_but_fail_closed(self):
        provider = next(item for item in main.load_api_providers() if item.get("id") == "ai-money")
        catalog = main.MODEL_CAPABILITY_REGISTRY.build_catalog([provider])
        models = catalog["providers"][0]["models"]
        lip_sync = next(item for item in models if item.get("model_id") == "kling-lip-sync-tts")
        self.assertEqual(lip_sync["readiness"], "adapter_missing")
        self.assertFalse(lip_sync["runnable"])
        with self.assertRaises(main.ModelCapabilityError):
            main.MODEL_CAPABILITY_REGISTRY.validate_request(
                [provider], "ai-money", "kling-lip-sync-tts", "audio_generation",
                input_counts={"prompt": 1, "source_video": 1},
                input_roles={"prompt": 1, "source_video": 1},
                parameters={},
            )


if __name__ == "__main__":
    unittest.main()
