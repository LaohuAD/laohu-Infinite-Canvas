import asyncio
import copy
import json
import time
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from studio_hypit_models import create_hypit_models_router


def catalog():
    return {
        "schema_version": 1,
        "providers": [
            {
                "id": "provider-a",
                "name": "Provider A",
                "protocol": "openai",
                "models": [
                    {
                        "model_id": "text-1",
                        "node_type": "text_generation",
                        "family_id": "text-family",
                        "runnable": True,
                        "readiness": "ready",
                        "validation_mode": "strict",
                        "parameters": {"temperature": {"type": "number", "min": 0, "max": 2}},
                        "inputs": {
                            "prompt": {"media_type": "text", "min": 1, "max": 1},
                            "reference": {"media_type": "image", "min": 0, "max": 2},
                        },
                    },
                    {
                        "model_id": "image-1",
                        "node_type": "image_generation",
                        "family_id": "image-family",
                        "runnable": True,
                        "readiness": "ready",
                        "validation_mode": "strict",
                        "parameters": {"count": {"type": "integer", "min": 1, "max": 2}},
                        "inputs": {"prompt": {"media_type": "text", "min": 1, "max": 1}},
                    },
                    {
                        "model_id": "image-2",
                        "node_type": "image_generation",
                        "family_id": "image-family",
                        "runnable": True,
                        "readiness": "ready",
                        "validation_mode": "strict",
                        "parameters": {"count": {"type": "integer", "min": 1, "max": 2}},
                        "inputs": {"prompt": {"media_type": "text", "min": 1, "max": 1}},
                    },
                    {
                        "model_id": "video-1",
                        "node_type": "video_generation",
                        "family_id": "video-family",
                        "runnable": True,
                        "readiness": "ready",
                        "validation_mode": "strict",
                        "parameters": {"duration": {"type": "integer", "min": 1, "max": 10}},
                        "inputs": {"prompt": {"media_type": "text", "min": 1, "max": 1}},
                    },
                    {
                        "model_id": "voice-1",
                        "node_type": "audio_generation",
                        "family_id": "voice-family",
                        "runnable": True,
                        "readiness": "ready",
                        "validation_mode": "strict",
                        "parameters": {"speaker": {"type": "text"}},
                        "inputs": {"prompt": {"media_type": "text", "min": 1, "max": 1}},
                    },
                ],
            },
            {
                "id": "runninghub",
                "name": "RunningHub",
                "protocol": "runninghub",
                "regions": [
                    {"region": "global", "enabled": True},
                    {"region": "cn", "enabled": True},
                ],
                "models": [
                    {
                        "model_id": "shared-image",
                        "node_type": "image_generation",
                        "family_id": "shared-image-family",
                        "runnable": True,
                        "readiness": "ready",
                        "validation_mode": "strict",
                        "regions": ["global", "cn"],
                        "region_profiles": {
                            "global": {
                                "model_id": "shared-image",
                                "node_type": "image_generation",
                                "family_id": "shared-image-family",
                                "runnable": True,
                                "readiness": "ready",
                                "validation_mode": "strict",
                                "parameters": {"count": {"type": "integer", "min": 1, "max": 1}},
                                "inputs": {"prompt": {"media_type": "text", "min": 1, "max": 1}},
                            },
                            "cn": {
                                "model_id": "shared-image",
                                "node_type": "image_generation",
                                "family_id": "shared-image-family",
                                "runnable": True,
                                "readiness": "ready",
                                "validation_mode": "strict",
                                "parameters": {"count": {"type": "integer", "min": 1, "max": 2}},
                                "inputs": {"prompt": {"media_type": "text", "min": 1, "max": 1}},
                            },
                        },
                        "parameters": {"count": {"type": "integer", "min": 1, "max": 4}},
                        "inputs": {"prompt": {"media_type": "text", "min": 1, "max": 1}},
                    },
                ],
            },
        ],
    }


class HypitModelsTests(unittest.TestCase):
    def setUp(self):
        self.root = Path("cache/hypit-tests") / f"case-{time.time_ns()}"
        self.root.mkdir(parents=True, exist_ok=True)
        self.projects = {"project-a": {"id": "project-a"}, "project-b": {"id": "project-b"}}
        self.calls = []
        self.fail_generation = False

        def get_project(project_id, module):
            self.assertEqual(module, "hypit")
            if project_id not in self.projects:
                raise KeyError(project_id)
            return copy.deepcopy(self.projects[project_id])

        def get_capabilities():
            return copy.deepcopy(catalog())

        async def validate(request):
            self.calls.append(("validate", copy.deepcopy(request)))
            return {"validation": "ok", "model": request["model"]}

        async def generate(request):
            self.calls.append(("generate", copy.deepcopy(request)))
            await asyncio.sleep(0)
            if self.fail_generation:
                raise RuntimeError("simulated generation failure")
            return {"images": [{"url": "/api/results/result-a.png"}], "model": request["model"]}

        self.app = FastAPI()
        self.app.include_router(
            create_hypit_models_router(
                self.root,
                get_project,
                get_capabilities,
                validate,
                generate,
            )
        )

    def tearDown(self):
        import shutil

        shutil.rmtree(self.root, ignore_errors=True)

    def wait_for_status(self, client, project_id, request_id, expected):
        for _ in range(100):
            response = client.get(
                f"/api/studio/hypit/models/projects/{project_id}/requests/{request_id}"
            )
            self.assertEqual(response.status_code, 200, response.text)
            value = response.json()
            if value["status"] == expected:
                return value
            time.sleep(0.01)
        self.fail(f"request did not reach {expected}: {value}")

    def test_module_settings_are_shared_and_binding_is_compatibility_read(self):
        with TestClient(self.app) as client:
            initial = client.get("/api/studio/hypit/models/settings")
            self.assertEqual(initial.status_code, 200, initial.text)
            self.assertNotIn("api_key", initial.text.lower())
            self.assertEqual(initial.json()["defaults"]["image"]["provider"], "")
            self.assertEqual(initial.json()["revision"], 1)

            saved = client.put(
                "/api/studio/hypit/models/settings",
                json={
                    "expected_revision": initial.json()["revision"],
                    "defaults": {
                        "image": {
                            "provider": "provider-a",
                            "model": "image-1",
                            "parameters": {"count": 1},
                        },
                        "voice": {
                            "provider": "provider-a",
                            "model": "voice-1",
                            "parameters": {"speaker": "Narrator"},
                        },
                    }
                },
            )
            self.assertEqual(saved.status_code, 200, saved.text)
            self.assertNotIn("api_key", saved.text.lower())
            self.assertEqual(saved.json()["revision"], 2)

            first = client.get(
                "/api/studio/hypit/models/projects/project-a/binding"
            )
            self.assertEqual(first.status_code, 200, first.text)
            self.assertEqual(first.json()["defaults"]["image"]["model"], "image-1")
            self.assertEqual(first.json()["revision"], saved.json()["revision"])
            self.assertEqual(first.json()["source"], "module_settings")

            legacy_path = self.root / "data" / "hypit_bindings" / "project-a.json"
            legacy_path.parent.mkdir(parents=True, exist_ok=True)
            legacy_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "project_id": "project-a",
                        "defaults": {"image": {"provider": "provider-a", "model": "image-1", "parameters": {}}},
                        "revision": 1,
                    }
                ),
                encoding="utf-8",
            )

            changed = client.put(
                "/api/studio/hypit/models/settings",
                json={
                    "expected_revision": saved.json()["revision"],
                    "defaults": {
                        "image": {
                            "provider": "provider-a",
                            "model": "image-2",
                            "parameters": {},
                        }
                    }
                },
            )
            self.assertEqual(changed.status_code, 200, changed.text)
            pinned = client.get(
                "/api/studio/hypit/models/projects/project-a/binding"
            )
            self.assertEqual(pinned.status_code, 200, pinned.text)
            self.assertEqual(pinned.json()["defaults"]["image"]["model"], "image-2")
            self.assertEqual(pinned.json()["revision"], changed.json()["revision"])
            self.assertEqual(json.loads(legacy_path.read_text(encoding="utf-8"))["defaults"]["image"]["model"], "image-1")

            stale_settings = client.put(
                "/api/studio/hypit/models/settings",
                json={
                    "expected_revision": saved.json()["revision"],
                    "defaults": {"image": {"provider": "provider-a", "model": "image-1", "parameters": {}}},
                },
            )
            self.assertEqual(stale_settings.status_code, 409, stale_settings.text)

    def test_project_binding_update_rejects_stale_revision(self):
        with TestClient(self.app) as client:
            url = '/api/studio/hypit/models/projects/project-a/binding'
            initial = client.get(url).json()
            payload = {'expected_revision': initial['revision'], 'defaults': {
                'image': {'provider': 'provider-a', 'model': 'image-1', 'parameters': {'count': 1}}}}
            updated = client.put(url, json=payload)
            self.assertEqual(updated.status_code, 200, updated.text)
            self.assertEqual(updated.json()['revision'], initial['revision'] + 1)
            self.assertEqual(client.put(url, json=payload).status_code, 409)
            self.assertEqual(client.get(url).json()['defaults']['image']['model'], 'image-1')
            other = client.get('/api/studio/hypit/models/projects/project-b/binding').json()
            self.assertEqual(other['defaults']['image']['model'], 'image-1')
            self.assertEqual(other['revision'], updated.json()['revision'])

    def test_only_enabled_model_ids_are_accepted(self):
        with TestClient(self.app) as client:
            response = client.put(
                "/api/studio/hypit/models/settings",
                json={
                    "defaults": {
                        "image": {
                            "provider": "provider-a",
                            "model": "not-enabled",
                            "parameters": {},
                        }
                    }
                },
            )
            self.assertEqual(response.status_code, 400)
            self.assertIn("启用", response.text)

    def test_runninghub_region_is_saved_projected_and_required_when_ambiguous(self):
        with TestClient(self.app) as client:
            setup = client.put(
                "/api/studio/hypit/models/settings",
                json={
                    "defaults": {
                        "image": {
                            "provider": "runninghub",
                            "model": "shared-image",
                            "region": "cn",
                            "parameters": {"count": 2},
                        }
                    }
                },
            )
            self.assertEqual(setup.status_code, 200, setup.text)
            self.assertEqual(setup.json()["defaults"]["image"]["region"], "cn")

            payload = {
                "request_id": "runninghub-cn",
                "capability": {"module": {"name": "@laohu/studio-models", "version": "1"}, "name": "image-generation"},
                "constraints": {"kind": "image", "prompt": "a red fox"},
            }
            submitted = client.post(
                "/api/studio/hypit/models/projects/project-a/requests", json=payload
            )
            self.assertEqual(submitted.status_code, 200, submitted.text)
            self.wait_for_status(client, "project-a", "runninghub-cn", "succeeded")
            validate_request = [call[1] for call in self.calls if call[0] == "validate"][-1]
            generate_request = [call[1] for call in self.calls if call[0] == "generate"][-1]
            self.assertEqual(validate_request["region"], "cn")
            self.assertEqual(generate_request["region"], "cn")

            ambiguous = client.put(
                "/api/studio/hypit/models/settings",
                json={
                    "defaults": {
                        "image": {
                            "provider": "runninghub",
                            "model": "shared-image",
                            "parameters": {"count": 1},
                        }
                    }
                },
            )
            self.assertEqual(ambiguous.status_code, 400, ambiguous.text)
            self.assertIn("region", ambiguous.text.lower())

            explicit_global = client.post(
                "/api/studio/hypit/models/projects/project-a/requests",
                json={
                    **payload,
                    "request_id": "runninghub-global",
                    "constraints": {
                        "kind": "image",
                        "prompt": "a blue fox",
                        "region": "global",
                        "parameters": {"count": 1},
                    },
                },
            )
            self.assertEqual(explicit_global.status_code, 200, explicit_global.text)
            self.wait_for_status(client, "project-a", "runninghub-global", "succeeded")
            explicit_request = [call[1] for call in self.calls if call[0] == "validate"][-1]
            self.assertEqual(explicit_request["region"], "global")

    def test_native_projection_keeps_media_roles_and_rejects_music(self):
        with TestClient(self.app) as client:
            setup = client.put(
                "/api/studio/hypit/models/settings",
                json={
                    "defaults": {
                        "video": {
                            "provider": "provider-a",
                            "model": "video-1",
                            "parameters": {"duration": 5},
                        }
                    }
                },
            )
            self.assertEqual(setup.status_code, 200, setup.text)
            payload = {
                "request_id": "typed-media",
                "capability": {"module": {"name": "@laohu/studio-models", "version": "1"}, "name": "video-generation"},
                "constraints": {
                    "kind": "video",
                    "prompt": "a fox walks",
                    "inputs": {
                        "reference": ["data:image/png;base64,AA=="],
                        "source_video": ["data:video/mp4;base64,AA=="],
                        "reference_audio": ["data:audio/wav;base64,AA=="],
                    },
                },
            }
            submitted = client.post(
                "/api/studio/hypit/models/projects/project-a/requests", json=payload
            )
            self.assertEqual(submitted.status_code, 200, submitted.text)
            self.wait_for_status(client, "project-a", "typed-media", "succeeded")
            projected = [call[1] for call in self.calls if call[0] == "validate"][-1]
            self.assertEqual(projected["inputs"]["reference"], ["data:image/png;base64,AA=="])
            self.assertEqual(projected["inputs"]["source_video"], ["data:video/mp4;base64,AA=="])
            self.assertEqual(projected["inputs"]["reference_audio"], ["data:audio/wav;base64,AA=="])

            unsupported = client.post(
                "/api/studio/hypit/models/projects/project-a/requests",
                json={
                    **payload,
                    "request_id": "music-request",
                    "capability": {"module": {"name": "@laohu/studio-models", "version": "1"}, "name": "music-generation"},
                    "constraints": {"kind": "music", "prompt": "music"},
                },
            )
            self.assertEqual(unsupported.status_code, 400, unsupported.text)
            self.assertIn("支持", unsupported.text)

    def test_request_id_is_idempotent_cross_project_isolated_and_failure_is_not_retried(self):
        with TestClient(self.app) as client:
            setup = client.put(
                "/api/studio/hypit/models/settings",
                json={
                    "defaults": {
                        "image": {
                            "provider": "provider-a",
                            "model": "image-1",
                            "parameters": {"count": 1},
                        }
                    }
                },
            )
            self.assertEqual(setup.status_code, 200)

            payload = {
                "request_id": "same-request",
                "capability": {"module": {"name": "@laohu/studio-models", "version": "1"}, "name": "image-generation"},
                "constraints": {"kind": "image", "prompt": "a red fox"},
            }
            first = client.post(
                "/api/studio/hypit/models/projects/project-a/requests", json=payload
            )
            self.assertEqual(first.status_code, 200, first.text)
            self.assertEqual(first.json()["status"], "queued")
            done = self.wait_for_status(client, "project-a", "same-request", "succeeded")
            repeat = client.post(
                "/api/studio/hypit/models/projects/project-a/requests", json=payload
            )
            self.assertEqual(repeat.status_code, 200, repeat.text)
            self.assertEqual(repeat.json()["task_id"], done["task_id"])
            self.assertEqual(len([call for call in self.calls if call[0] == "generate"]), 1)

            current_settings = client.get("/api/studio/hypit/models/settings").json()
            changed = client.put(
                "/api/studio/hypit/models/settings",
                json={
                    "expected_revision": current_settings["revision"],
                    "defaults": {
                        "image": {
                            "provider": "provider-a",
                            "model": "image-2",
                            "parameters": {"count": 1},
                        }
                    },
                },
            )
            self.assertEqual(changed.status_code, 200, changed.text)
            after_setting_change = client.post(
                "/api/studio/hypit/models/projects/project-a/requests", json=payload
            )
            self.assertEqual(after_setting_change.status_code, 200, after_setting_change.text)
            self.assertEqual(after_setting_change.json()["task_id"], done["task_id"])
            self.assertEqual(after_setting_change.json()["request"]["model"], "image-1")
            self.assertEqual(len([call for call in self.calls if call[0] == "generate"]), 1)

            different_input = {
                **payload,
                "constraints": {**payload["constraints"], "prompt": "a blue fox"},
            }
            conflict = client.post(
                "/api/studio/hypit/models/projects/project-a/requests", json=different_input
            )
            self.assertEqual(conflict.status_code, 409, conflict.text)
            self.assertIn("不同输入", conflict.text)

            other = client.post(
                "/api/studio/hypit/models/projects/project-b/requests", json=payload
            )
            self.assertEqual(other.status_code, 200, other.text)
            self.assertEqual(other.json()["request"]["model"], "image-2")
            self.wait_for_status(client, "project-b", "same-request", "succeeded")
            self.assertEqual(len([call for call in self.calls if call[0] == "generate"]), 2)

            self.fail_generation = True
            failed_payload = {**payload, "request_id": "failed-request"}
            failed = client.post(
                "/api/studio/hypit/models/projects/project-a/requests", json=failed_payload
            )
            self.assertEqual(failed.status_code, 200, failed.text)
            failed_task = self.wait_for_status(client, "project-a", "failed-request", "failed")
            again = client.post(
                "/api/studio/hypit/models/projects/project-a/requests", json=failed_payload
            )
            self.assertEqual(again.status_code, 200, again.text)
            self.assertEqual(again.json()["task_id"], failed_task["task_id"])
            self.assertEqual(len([call for call in self.calls if call[0] == "generate"]), 3)


if __name__ == "__main__":
    unittest.main()
