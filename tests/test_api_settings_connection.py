import asyncio
import base64
import json
import os
import tempfile
import threading
import unittest
from io import BytesIO
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import main
from project_storage import ProjectStorage


TEST_PNG_BASE64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Z5GkAAAAASUVORK5CYII="


class OpenAICompatibleFixtureHandler(BaseHTTPRequestHandler):
    requests = []

    def log_message(self, _format, *_args):
        return

    def _json_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8"))

    def _send_json(self, payload, status=200):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self.__class__.requests.append({"method": "GET", "path": self.path, "authorization": self.headers.get("Authorization")})
        if self.path == "/v1/models":
            self._send_json({"data": [{"id": "canvas-e2e-text"}, {"id": "canvas-e2e-image"}]})
            return
        self._send_json({"error": "not found"}, status=404)

    def do_POST(self):
        payload = self._json_body()
        self.__class__.requests.append({
            "method": "POST",
            "path": self.path,
            "authorization": self.headers.get("Authorization"),
            "payload": payload,
        })
        if self.path == "/v1/chat/completions":
            self._send_json({
                "id": "chatcmpl-canvas-e2e",
                "choices": [{"message": {"role": "assistant", "content": "画布文本链路已贯通"}}],
            })
            return
        if self.path == "/v1/images/generations":
            self._send_json({"created": 1, "data": [{"b64_json": TEST_PNG_BASE64}]})
            return
        self._send_json({"error": "not found"}, status=404)


class ApiSettingsConnectionTests(unittest.IsolatedAsyncioTestCase):
    def test_canvas_creation_is_smart_only(self):
        request = main.CanvasCreateRequest()
        self.assertEqual(request.kind, "smart")
        self.assertEqual(request.icon, "sparkles")
        with self.assertRaises(main.HTTPException) as raised:
            main.new_canvas("普通画布", kind="classic")
        self.assertEqual(raised.exception.status_code, 400)

    def test_runninghub_output_media_kind_uses_explicit_type_or_real_reference(self):
        explicit = main.image_output_meta(
            "https://cdn.example.com/result-without-extension",
            {"type": "video"},
        )
        self.assertEqual(explicit["kind"], "video")

        with tempfile.NamedTemporaryFile(suffix=".mp4") as video:
            from_file = main.image_output_meta(video.name)
        self.assertEqual(from_file["kind"], "video")

        self.assertEqual(
            main.image_output_meta("https://cdn.example.com/result.mp3")["kind"],
            "audio",
        )

    def test_runninghub_output_items_keep_official_source_metadata_for_type_detection(self):
        items = main.runninghub_extract_output_items({
            "outputs": [
                {"fileUrl": "https://cdn.example.com/video", "mediaType": "video/mp4"},
                {"fileUrl": "https://cdn.example.com/image.png", "type": "image"},
            ]
        })

        self.assertEqual([item["url"] for item in items], [
            "https://cdn.example.com/video",
            "https://cdn.example.com/image.png",
        ])
        self.assertEqual(main.image_output_meta(items[0]["url"], items[0]["source"])["kind"], "video")

    def test_canvas_result_media_kind_hydration_repairs_output_and_nested_result_items(self):
        storage = MagicMock()
        storage.get_result.return_value = {"kind": "video"}
        storage.result_path.return_value = Path("/tmp/generated-result.mp4")
        canvas = {
            "nodes": [{
                "runRef": {"resultIds": ["res-video"]},
                "outputKind": "image",
                "outputs": [{"url": "/api/results/res-video", "kind": "image"}],
                "resultVersions": [{
                    "images": [{"url": "/api/results/res-video", "kind": "image"}],
                }],
            }]
        }

        with patch.object(main, "PROJECT_STORAGE", storage):
            changed = main.hydrate_canvas_result_media_kinds(canvas)

        self.assertTrue(changed)
        node = canvas["nodes"][0]
        self.assertEqual(node["outputKind"], "video")
        self.assertEqual(node["outputs"][0]["kind"], "video")
        self.assertEqual(node["resultVersions"][0]["images"][0]["kind"], "video")

    def test_comfyui_settings_uses_platform_navigation_and_preserves_local_layout(self):
        html = (ROOT / "static/api-settings.html").read_text(encoding="utf-8")
        script = (ROOT / "static/js/api-settings.js").read_text(encoding="utf-8")
        css = (ROOT / "static/css/api-settings.css").read_text(encoding="utf-8")

        self.assertIn('id="comfyuiLocalSection" class="comfyui-local-embed"', html)
        self.assertNotIn('id="comfyuiLocalSection" class="comfyui-local-embed block"', html)
        self.assertIn(".comfyui-local-embed { min-height:680px; padding:0;", css)
        self.assertNotIn('comfyui-settings-nav', html)
        self.assertIn('id="localComfyuiNav"', html)
        self.assertIn('id="runningHubComfyuiNav"', html)
        self.assertNotIn('comfyui-settings.html?embedded=1', html)
        self.assertIn("function setComfyUiSection", script)
        self.assertIn("comfyuiSettingsSection === 'runninghub'", script)
        self.assertIn(".comfyui-subnav", css)

    def test_runninghub_app_reference_accepts_id_and_supported_links(self):
        script = (ROOT / "static/js/api-settings.js").read_text(encoding="utf-8")

        self.assertIn("new URL(text)", script)
        self.assertIn("webappId", script)
        self.assertIn("/\\/(?:run\\/)?(ai-app|workflow)\\/", script)

    def test_new_runninghub_app_is_saved_into_its_selected_region_before_sync(self):
        script = (ROOT / "static/js/api-settings.js").read_text(encoding="utf-8")

        create_start = script.index("async function createRhEntryFromPaste()")
        sync_start = script.index("async function syncRhAppFromOfficial", create_start)
        create_source = script[create_start:sync_start]
        self.assertIn("persistActiveRunningHubRegion(item);", create_source)
        self.assertIn("regions[rollbackRegion].rh_apps", create_source)
        self.assertIn("const rollbackSaved = await saveProviders();", create_source)
        sync_source = script[sync_start:script.index("function updateRhEntry", sync_start)]
        self.assertIn("服务器未返回已保存的 AI 应用 ID", sync_source)
        self.assertNotIn("renderRunningHubCards();\n    const saved = await saveProviders();", sync_source)

    def test_runninghub_app_addition_uses_a_non_persistent_progress_card(self):
        script = (ROOT / "static/js/api-settings.js").read_text(encoding="utf-8")
        css = (ROOT / "static/css/api-settings.css").read_text(encoding="utf-8")

        self.assertIn("let rhAppSyncState = null", script)
        self.assertIn("function renderRhSyncCard(state)", script)
        self.assertIn('data-rh-sync-card', script)
        self.assertIn('aria-busy="true"', script)
        self.assertIn("api.rhAppPhaseRead", script)
        self.assertIn("api.rhAppPhaseSave", script)
        self.assertIn("setRhAppSyncState(null)", script)
        self.assertIn("api.rhAppSyncBusy", script)
        self.assertIn(".rh-sync-spinner", css)
        self.assertIn(".rh-paste-row .action-btn:disabled", css)

        i18n = (ROOT / "static/js/i18n/api-settings.js").read_text(encoding="utf-8")
        self.assertIn('"api.rhAppSyncDescription"', i18n)
        self.assertIn('en: "Reading the title, cover, and parameters', i18n)

    def test_runninghub_app_ui_shows_plain_id_and_id_only_placeholder(self):
        html = (ROOT / "static/api-settings.html").read_text(encoding="utf-8")
        script = (ROOT / "static/js/api-settings.js").read_text(encoding="utf-8")

        self.assertIn('placeholder="AI 应用 ID"', html)
        self.assertIn("<span>${escapeHtml(entry.id)}</span>", script)
        self.assertNotIn("/run/ai-app/${entry.id}", script)
        self.assertIn("输入 AI 应用 ID 后点击添加并同步", script)

    def test_runninghub_unsynced_placeholder_is_removed_but_valid_entries_remain(self):
        entries = main.normalize_runninghub_entries([
            {
                "id": "2089305540787126273",
                "title": "AI 应用 126273",
                "note": "",
                "thumbnail": "",
            },
            {
                "id": "valid-legacy",
                "title": "旧版静态应用",
                "note": "",
                "thumbnail": "",
            },
            {
                "id": "synced-empty",
                "title": "AI 应用 -empty",
                "schemaSyncedAt": 123,
            },
        ], "app")

        self.assertEqual([entry["id"] for entry in entries], ["valid-legacy", "synced-empty"])
        self.assertEqual(entries[1]["schemaSyncedAt"], 123)

    async def test_runninghub_app_info_retries_wallet_key_and_returns_schema(self):
        first = MagicMock(status_code=200)
        first.json.return_value = {"code": 332, "msg": "USER_DOES_NOT_EXIST"}
        second = MagicMock(status_code=200)
        second.json.return_value = {
            "code": 0,
            "data": {
                "webappId": "2064269998658510850",
                "webappName": "官方应用",
                "nodeInfoList": [{"nodeId": "1", "fieldName": "text", "fieldType": "STRING", "fieldData": "[]"}],
            },
        }
        client = MagicMock()
        client.get = AsyncMock(side_effect=[first, second])
        client_context = MagicMock()
        client_context.__aenter__ = AsyncMock(return_value=client)
        client_context.__aexit__ = AsyncMock(return_value=False)

        with patch.object(main, "runninghub_provider", return_value={"id": "runninghub", "base_url": "https://www.runninghub.ai"}), \
             patch.object(main, "runninghub_app_info_key_candidates", return_value=["rh-coin-key", "wallet-key"]), \
             patch.object(main, "runninghub_app_headers", return_value={"Host": "www.runninghub.ai"}), \
             patch.object(main.httpx, "AsyncClient", return_value=client_context):
            result = await main.runninghub_app_info("2064269998658510850", "global")

        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["webappName"], "官方应用")
        self.assertEqual(client.get.await_count, 2)
        self.assertEqual(client.get.await_args_list[0].kwargs["params"]["webappId"], "2064269998658510850")
        self.assertNotEqual(client.get.await_args_list[0].kwargs["params"]["apiKey"], client.get.await_args_list[1].kwargs["params"]["apiKey"])

    async def test_runninghub_app_info_rejects_incomplete_schema(self):
        response = MagicMock(status_code=200)
        response.json.return_value = {"code": 0, "data": {"webappId": "bad-app"}}
        client = MagicMock()
        client.get = AsyncMock(return_value=response)
        client_context = MagicMock()
        client_context.__aenter__ = AsyncMock(return_value=client)
        client_context.__aexit__ = AsyncMock(return_value=False)

        with patch.object(main, "runninghub_provider", return_value={"id": "runninghub", "base_url": "https://www.runninghub.ai"}), \
             patch.object(main, "runninghub_app_info_key_candidates", return_value=["global-key"]), \
             patch.object(main, "runninghub_app_headers", return_value={"Host": "www.runninghub.ai"}), \
             patch.object(main.httpx, "AsyncClient", return_value=client_context):
            with self.assertRaises(main.HTTPException) as raised:
                await main.runninghub_app_info("bad-app", "global")

        self.assertEqual(raised.exception.status_code, 502)
        self.assertIn("资料不完整", raised.exception.detail)

    def test_jimeng_login_details_parse_complete_device_flow_output(self):
        verification_url = (
            "https://jimeng.jianying.com/ai-tool/cli-auth?"
            "verification_uri=https%3A%2F%2Fjimeng.jianying.com%2Fpassport%2Fopen%2Fscan_user_code%2F"
            "%3Fuser_code%3D79a7a9cb606e0be0906a0bff81e7941c"
        )
        details = main.jimeng_login_details_from_text(
            "请使用浏览器完成 OAuth Device Flow 登录。\n"
            f"verification_uri: {verification_url}\n"
            "user_code: 79a7a9cb606e0be0906a0bff81e7941c\n"
            "device_code: c7dfda3ffe155f688167ea6fe6d1266a\n"
            "poll_interval: 1s\n"
            "expires_at: 2026-08-13T10:50:54+08:00\n"
        )

        self.assertEqual(details["verification_url"], verification_url)
        self.assertEqual(details["qr_data"], verification_url)
        self.assertEqual(details["user_code"], "79a7a9cb606e0be0906a0bff81e7941c")
        self.assertEqual(details["device_code"], "c7dfda3ffe155f688167ea6fe6d1266a")
        self.assertEqual(details["expires_at"], "2026-08-13T10:50:54+08:00")

    def test_jimeng_login_check_args_use_device_code_and_wait_for_authorization(self):
        args = main.jimeng_login_check_args(
            "verification_uri: https://jimeng.jianying.com/ai-tool/cli-auth\n"
            "device_code: c7dfda3ffe155f688167ea6fe6d1266a\n"
        )

        self.assertEqual(args, [
            "login",
            "checklogin",
            "--device_code=c7dfda3ffe155f688167ea6fe6d1266a",
            "--poll=600",
        ])

    def test_jimeng_login_payload_reports_expired_authorization(self):
        previous = dict(main.JIMENG_LOGIN_SESSION)
        main.JIMENG_LOGIN_SESSION.update({
            "stdout": "verification_uri: https://jimeng.jianying.com/ai-tool/cli-auth\n",
            "stderr": "登录已过期，请重新执行 dreamina login --headless\n",
        })
        try:
            payload = main.jimeng_login_payload(running=False, logged_in=False, returncode=1)
        finally:
            main.JIMENG_LOGIN_SESSION.clear()
            main.JIMENG_LOGIN_SESSION.update(previous)

        self.assertEqual(payload["state"], "expired")
        self.assertIn("重新", payload["message"])

    def test_jimeng_verification_url_only_allows_official_https_host(self):
        self.assertTrue(main.jimeng_verification_url_is_allowed("https://jimeng.jianying.com/ai-tool/cli-auth?code=1"))
        self.assertFalse(main.jimeng_verification_url_is_allowed("http://jimeng.jianying.com/ai-tool/cli-auth?code=1"))
        self.assertFalse(main.jimeng_verification_url_is_allowed("https://jimeng.jianying.com.evil.example/steal"))
        self.assertFalse(main.jimeng_verification_url_is_allowed("file:///tmp/secret"))

    def test_jimeng_qr_png_is_a_real_local_image(self):
        data = main.jimeng_qr_png("https://jimeng.jianying.com/ai-tool/cli-auth?code=local-only")

        self.assertTrue(data.startswith(b"\x89PNG\r\n\x1a\n"))
        image = main.Image.open(BytesIO(data))
        self.assertEqual(image.format, "PNG")
        self.assertGreaterEqual(image.width, 180)
        self.assertEqual(image.width, image.height)

    def test_jimeng_browser_command_is_cross_platform(self):
        url = "https://jimeng.jianying.com/ai-tool/cli-auth?code=1"

        self.assertEqual(main.jimeng_browser_command(url, os_name="nt", sys_platform="win32"), ["rundll32.exe", "url.dll,FileProtocolHandler", url])
        self.assertEqual(main.jimeng_browser_command(url, os_name="posix", sys_platform="darwin"), ["open", url])
        self.assertEqual(main.jimeng_browser_command(url, os_name="posix", sys_platform="linux"), ["xdg-open", url])

    async def test_jimeng_open_verification_uses_current_login_session_only(self):
        verification_url = "https://jimeng.jianying.com/ai-tool/cli-auth?code=current-session"
        previous = dict(main.JIMENG_LOGIN_SESSION)
        main.JIMENG_LOGIN_SESSION.update({"stdout": f"verification_uri: {verification_url}\n", "stderr": ""})
        try:
            with patch.object(main, "open_jimeng_verification_url") as opener:
                response = await main.jimeng_login_open_verification()
        finally:
            main.JIMENG_LOGIN_SESSION.clear()
            main.JIMENG_LOGIN_SESSION.update(previous)

        self.assertTrue(response["success"])
        opener.assert_called_once_with(verification_url)

    async def test_jimeng_login_status_becomes_authenticated_after_checklogin_finishes(self):
        class FinishedProcess:
            returncode = 0

        previous = dict(main.JIMENG_LOGIN_SESSION)
        main.JIMENG_LOGIN_SESSION.update({
            "proc": FinishedProcess(),
            "stdout": "登录成功\n",
            "stderr": "",
        })
        try:
            with patch.object(main, "run_jimeng_cli", return_value={"credit": 100}):
                response = await main.jimeng_login_status()
        finally:
            main.JIMENG_LOGIN_SESSION.clear()
            main.JIMENG_LOGIN_SESSION.update(previous)

        self.assertTrue(response["logged_in"])
        self.assertEqual(response["state"], "authenticated")
        self.assertEqual(response["raw"], {"credit": 100})

    def test_jimeng_login_frontend_uses_local_qr_endpoint(self):
        script = (ROOT / "static/js/api-settings.js").read_text(encoding="utf-8")
        stylesheet = (ROOT / "static/css/api-settings.css").read_text(encoding="utf-8")

        self.assertIn("/api/jimeng/login/qr", script)
        self.assertIn("openJimengVerification", script)
        self.assertIn("data?.state === 'expired'", script)
        self.assertIn("clearInterval(jimengLoginTimer)", script)
        self.assertNotIn('src="${escapeHtml(qrUrl)}"', script)
        self.assertIn("@media (max-width:720px)", stylesheet)
        self.assertIn(".jimeng-output { grid-template-columns:1fr; justify-items:center; }", stylesheet)

    def test_api_settings_keeps_platform_editor_visible_and_fetch_can_cancel(self):
        script = (ROOT / "static/js/api-settings.js").read_text(encoding="utf-8")
        stylesheet = (ROOT / "static/css/api-settings.css").read_text(encoding="utf-8")

        self.assertIn("let fetchModelsController = null;", script)
        self.assertIn("fetchModelsController.abort();", script)
        self.assertIn("signal:fetchModelsController.signal", script)
        self.assertIn("closeRecommendApi();\n        setStatus('');", script)
        self.assertIn("if(event.key !== 'Escape') return;", script)
        self.assertIn("if(event.target !== overlay) return;", script)
        self.assertIn(".action-btn.primary-btn.is-cancel", stylesheet)
        self.assertIn("#modelPickerOverlay {", stylesheet)
        self.assertIn("align-items:flex-start", stylesheet)
        self.assertIn("#modelPickerOverlay .picker-body", stylesheet)

    def test_runninghub_app_snapshot_keeps_official_schema_without_credentials(self):
        snapshot = main.sanitize_runninghub_app_snapshot({
            "webappName": "官方应用",
            "webappNameZh": "中文应用",
            "webappNameEn": "English App",
            "titles": {"zh": "中文应用", "en": "English App"},
            "covers": [{"thumbnailUri": "https://example.com/cover.jpg", "ignored": "x"}],
            "tags": [{"name": "视频", "ignored": "x"}],
            "nodeInfoList": [{"nodeId": "1", "fieldName": "image", "fieldType": "IMAGE", "fieldData": "[]"}],
            "curl": "--data apiKey=secret",
            "apiKey": "secret",
        })

        self.assertEqual(snapshot["webappName"], "官方应用")
        self.assertEqual(snapshot["webappNameZh"], "中文应用")
        self.assertEqual(snapshot["webappNameEn"], "English App")
        self.assertEqual(snapshot["titles"], {"zh": "中文应用", "en": "English App"})
        self.assertEqual(snapshot["covers"][0]["thumbnailUri"], "https://example.com/cover.jpg")
        self.assertEqual(snapshot["nodeInfoList"][0]["fieldType"], "IMAGE")
        self.assertNotIn("curl", snapshot)
        self.assertNotIn("apiKey", snapshot)

    def test_runninghub_preflight_rejects_text_in_official_float_field(self):
        provider = {
            "rh_apps": [{
                "id": "2089305540787126273",
                "title": "老胡音乐数字人V3",
                "fields": [
                    {"nodeId": "360", "fieldName": "text", "fieldType": "STRING", "label": "提示词文本"},
                    {"nodeId": "105", "fieldName": "megapixels", "fieldType": "FLOAT", "label": "一采参数 分辨率"},
                ],
            }],
        }

        with self.assertRaises(main.HTTPException) as caught:
            main.runninghub_preflight_app(provider, "2089305540787126273", {
                "360::text": "这个女人在录音棚里面唱歌",
                "105::megapixels": "这个女人在录音棚里面唱歌",
            })

        self.assertEqual(caught.exception.status_code, 400)
        self.assertIn("105::megapixels", str(caught.exception.detail))
        self.assertIn("要求数字", str(caught.exception.detail))

    def test_runninghub_role_does_not_use_field_name_or_label(self):
        self.assertEqual(main.rh_field_role({
            "fieldName": "prompt",
            "label": "提示词文本",
            "fieldType": "STRING",
        }), "text")
        self.assertEqual(main.rh_field_role({
            "fieldName": "text",
            "label": "普通文本",
            "fieldType": "STRING",
            "inputRole": "prompt",
        }), "prompt")

    def test_normalized_runninghub_app_removes_credentials_from_legacy_raw_snapshot(self):
        entry = main.normalize_runninghub_entry({
            "id": "2064269998658510850",
            "title": "老胡音乐数字人V2",
            "raw": {
                "webappId": "2064269998658510850",
                "webappName": "老胡音乐数字人V2",
                "nodeInfoList": [{
                    "nodeId": "720",
                    "fieldName": "select",
                    "fieldType": "SWITCH",
                    "description": "是否高清视频？",
                    "fieldData": '[{"name":"input2","index":2.0,"description":"否"},{"name":"input1","index":1.0,"description":"是"}]',
                }],
                "curl": "curl --data apiKey=secret",
                "apiKey": "secret",
            },
            "fields": [{
                "id": "720::select",
                "nodeId": "720",
                "fieldName": "select",
                "fieldType": "SWITCH",
                "label": "是否高清视频？",
                "options": [],
            }],
        }, "app")

        self.assertEqual(entry["raw"]["webappName"], "老胡音乐数字人V2")
        self.assertNotIn("curl", entry["raw"])
        self.assertNotIn("apiKey", entry["raw"])
        self.assertEqual(entry["fields"][0]["options"], ["2", "1"])
        self.assertEqual(entry["fields"][0]["optionLabels"], {"2": "否", "1": "是"})

    def test_upstream_model_classification_preserves_audio_models(self):
        grouped, model_ids = main.parse_upstream_models({
            "data": [
                {"id": "gpt-5.5"},
                {"id": "gpt-image-2"},
                {"id": "seedance-2.0"},
                {"id": "doubao-seed-audio-1.0"},
            ]
        })

        self.assertEqual(grouped["chat"], ["gpt-5.5"])
        self.assertEqual(grouped["image"], ["gpt-image-2"])
        self.assertEqual(grouped["video"], ["seedance-2.0"])
        self.assertEqual(grouped["audio"], ["doubao-seed-audio-1.0"])
        self.assertEqual(len(model_ids), 4)

    def test_runninghub_registry_payload_preserves_audio_output_type(self):
        payload = main.runninghub_registry_payload([
            {"id": "rh-image", "output_type": "image"},
            {"id": "rh-video", "output_type": "video"},
            {"id": "rh-audio", "output_type": "audio"},
        ])

        self.assertIn("rh-audio", payload["audio_models"])
        self.assertIn("rh-audio", payload["all"])

    def test_api_settings_new_provider_contract_includes_audio_models(self):
        script = (ROOT / "static/js/api-settings.js").read_text(encoding="utf-8")

        self.assertIn("image_models:[], chat_models:[], video_models:[], audio_models:[]", script)

    def test_recommended_provider_contract_preserves_audio_models(self):
        script = (ROOT / "static/js/api-settings.js").read_text(encoding="utf-8")

        self.assertIn("if(Array.isArray(api.audio_models)) item.audio_models = [...api.audio_models];", script)
        self.assertIn("item.audio_models = [];", script)
        self.assertIn("audio_models:api.empty_models_on_save ? []", script)

    def test_api_settings_script_cache_version_is_current(self):
        html = (ROOT / "static/api-settings.html").read_text(encoding="utf-8")
        app_version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        asset_version = f"{app_version}.{int(os.path.getmtime(ROOT / 'static/js/api-settings.js'))}"

        self.assertIn(f'/static/js/api-settings.js?v={asset_version}', html)

    def test_legacy_volcengine_migration_preserves_audio_models(self):
        providers = main.merge_default_api_providers([
            {
                "id": "legacy-volcengine",
                "name": "旧火山引擎",
                "base_url": main.VOLCENGINE_DEFAULT_BASE_URL,
                "protocol": "volcengine",
                "audio_models": ["doubao-seed-audio-1.0"],
            }
        ])

        provider = next(item for item in providers if item["id"] == "volcengine")
        self.assertEqual(provider["audio_models"], ["doubao-seed-audio-1.0"])

    async def test_public_model_catalog_aggregates_enabled_provider_audio_models(self):
        providers = [
            {
                "id": "audio-provider",
                "enabled": True,
                "chat_models": ["chat-model"],
                "image_models": ["image-model"],
                "video_models": ["video-model"],
                "audio_models": ["audio-model"],
            },
            {
                "id": "disabled-provider",
                "enabled": False,
                "audio_models": ["hidden-audio-model"],
            },
        ]

        with patch.object(main, "public_api_providers", return_value=providers):
            payload = await main.ai_models()

        self.assertIn("audio-model", payload["audio_models"])
        self.assertNotIn("hidden-audio-model", payload["audio_models"])

    def test_codex_cli_exposes_text_only(self):
        self.assertEqual(main.CODEX_DEFAULT_IMAGE_MODELS, [])
        self.assertEqual(main.codex_models_payload()["image_models"], [])
        self.assertEqual(main.codex_models_payload()["video_models"], [])
        self.assertEqual(main.codex_models_payload()["chat_models"], main.CODEX_DEFAULT_CHAT_MODELS)

    async def test_codex_image_generation_is_rejected(self):
        with self.assertRaises(main.HTTPException) as context:
            await main.generate_codex_provider_image("测试", "1024x1024", "gpt-image-2")

        self.assertEqual(context.exception.status_code, 400)
        self.assertIn("不支持图片生成", str(context.exception.detail))

    async def test_image_dispatch_rejects_legacy_codex_provider(self):
        legacy_provider = {
            "id": "codex",
            "name": "GPT CLI",
            "protocol": "codex",
            "image_models": ["gpt-image-2"],
        }

        with patch.object(main, "get_api_provider", return_value=legacy_provider):
            with self.assertRaises(main.HTTPException) as context:
                await main.generate_ai_image("测试", "1024x1024", "high", "gpt-image-2", provider_id="codex")

        self.assertEqual(context.exception.status_code, 400)
        self.assertIn("不支持图片生成", str(context.exception.detail))

    async def test_video_dispatch_rejects_legacy_codex_provider(self):
        legacy_provider = {
            "id": "codex",
            "name": "GPT CLI",
            "protocol": "codex",
            "video_models": ["sora-2"],
        }
        payload = main.CanvasVideoRequest(prompt="测试", provider_id="codex", model="sora-2")

        with patch.object(main, "get_api_provider", return_value=legacy_provider):
            with self.assertRaises(main.HTTPException) as context:
                await main.canvas_video(payload)

        self.assertEqual(context.exception.status_code, 400)
        self.assertIn("不支持视频生成", str(context.exception.detail))

    async def test_codex_status_does_not_expose_image_helper(self):
        with patch.object(main, "codex_cli_executable", return_value=""):
            status = await main.codex_status()

        self.assertNotIn("image2_helper_installed", status)
        self.assertNotIn("生图", status["message"])

    def test_codex_cli_candidates_include_chatgpt_bundle_on_macos(self):
        with patch.object(main.sys, "platform", "darwin"), patch.object(main, "codex_env_value", return_value=""), patch.object(main.os.path, "expanduser", return_value="/Users/test"):
            candidates = main.codex_cli_candidates()

        self.assertIn("/Applications/ChatGPT.app/Contents/Resources/codex", candidates)
        self.assertIn("/Users/test/Applications/ChatGPT.app/Contents/Resources/codex", candidates)

    async def test_codex_status_reports_login_state(self):
        version_proc = MagicMock()
        version_proc.communicate = AsyncMock(return_value=(b"codex-cli 1.0\n", b""))
        version_proc.returncode = 0
        login_proc = MagicMock()
        login_proc.communicate = AsyncMock(return_value=(b"Logged in using an API key - sk-***\n", b""))
        login_proc.returncode = 0

        with patch.object(main, "codex_cli_executable", return_value="/tmp/codex"), patch.object(main.asyncio, "create_subprocess_exec", new=AsyncMock(side_effect=[version_proc, login_proc])):
            status = await main.codex_status()

        self.assertTrue(status["installed"])
        self.assertTrue(status["logged_in"])
        self.assertEqual(status["state"], "ready")
        self.assertNotIn("sk-***", status["message"])

    def test_api_settings_does_not_register_codex_image_models(self):
        script = (ROOT / "static/js/api-settings.js").read_text(encoding="utf-8")

        self.assertIn("const CODEX_DEFAULT_IMAGE_MODELS = [];", script)
        self.assertIn("item.image_models = [];", script)
        self.assertIn("只支持文本生成", script)
        self.assertNotIn("OpenAI CLI”聊天或生成图片", script)

    def test_codex_installers_do_not_install_image_helpers(self):
        installer_paths = [
            ROOT / "CLI/macos/openai/install_openai_codex_cli.command",
            ROOT / "CLI/linux/openai/install_openai_codex_cli.sh",
            ROOT / "CLI/windows/openai/install_openai_codex_cli.ps1",
        ]

        for path in installer_paths:
            script = path.read_text(encoding="utf-8")
            self.assertNotIn("gpt-image-2-skill", script, path.as_posix())
            self.assertIn("仅接入 OpenAI Codex CLI 的文本能力", script, path.as_posix())

    def test_codex_missing_cli_message_is_cross_platform(self):
        source = (ROOT / "main.py").read_text(encoding="utf-8")

        self.assertIn("请先在 API 设置的 GPT CLI 卡片中安装或更新", source)
        self.assertNotIn("请先运行 CLI/windows/openai/install_openai_codex_cli.bat", source)

    def test_codex_provider_normalization_removes_legacy_media_models(self):
        provider = main.normalize_provider({
            "id": "codex",
            "name": "GPT CLI",
            "protocol": "codex",
            "image_models": ["gpt-image-2"],
            "video_models": ["sora-2"],
            "chat_models": ["gpt-5.5"],
        })

        self.assertEqual(provider["image_models"], [])
        self.assertEqual(provider["video_models"], [])

    def test_existing_cli_provider_model_selection_is_not_reseeded(self):
        providers = main.merge_default_api_providers([{
            "id": "jimeng",
            "name": "即梦 CLI",
            "protocol": "jimeng",
            "image_models": ["5.0Pro"],
            "chat_models": [],
            "video_models": [],
            "audio_models": [],
        }, {
            "id": "codex",
            "name": "GPT CLI",
            "protocol": "codex",
            "image_models": [],
            "chat_models": [],
            "video_models": [],
            "audio_models": [],
        }], inject_missing=False)

        jimeng = next(item for item in providers if item["id"] == "jimeng")
        codex = next(item for item in providers if item["id"] == "codex")
        self.assertEqual(jimeng["image_models"], ["5.0Pro"])
        self.assertEqual(jimeng["video_models"], [])
        self.assertEqual(codex["chat_models"], [])

    def test_api_settings_only_seeds_cli_models_on_explicit_setup(self):
        script = (ROOT / "static/js/api-settings.js").read_text(encoding="utf-8")

        self.assertIn("function applyCliProtocolDefaults(item, protocol, seedModels=false)", script)
        self.assertIn("applyCliProtocolDefaults(item, item.protocol, protocolChanged)", script)
        self.assertIn("applyCliProtocolDefaults(item, preset.protocol, created)", script)
        self.assertNotIn("if(isCliProtocol) applyCliProtocolDefaults(item, item.protocol);", script)

    def test_runninghub_supports_both_regions(self):
        self.assertEqual(
            main.upstream_models_url("https://www.runninghub.cn", "runninghub"),
            "https://www.runninghub.cn/openapi/v2/models",
        )
        self.assertEqual(
            main.upstream_models_url("https://www.runninghub.ai", "runninghub"),
            "https://www.runninghub.ai/openapi/v2/models",
        )

    def test_runninghub_payload_can_read_saved_wallet_key(self):
        payload = main.TestConnectionPayload(
            provider_id="runninghub",
            protocol="runninghub",
            base_url="https://www.runninghub.cn",
        )
        with patch.object(main, "runninghub_wallet_key_value", return_value="test-wallet-key"):
            self.assertEqual(main.api_key_from_payload(payload, "runninghub"), "test-wallet-key")

    def test_runninghub_regions_migrate_legacy_fields_without_cross_contamination(self):
        provider = main.normalize_provider({
            "id": "runninghub",
            "base_url": "https://www.runninghub.cn",
            "image_models": ["cn-image"],
            "model_names": {"cn-image": "国内图片"},
            "rh_apps": [{"id": "cn-app", "title": "国内应用"}],
        })

        self.assertEqual(provider["rh_region"], "cn")
        self.assertEqual(provider["rh_regions"]["cn"]["image_models"], ["cn-image"])
        self.assertEqual(provider["rh_regions"]["cn"]["rh_apps"][0]["id"], "cn-app")
        self.assertEqual(provider["rh_regions"]["global"]["image_models"], [])
        self.assertEqual(provider["rh_regions"]["global"]["rh_apps"], [])

    def test_runninghub_region_provider_switches_base_url_and_catalog(self):
        provider = main.normalize_provider({
            "id": "runninghub",
            "rh_region": "cn",
            "rh_regions": {
                "cn": {"base_url": "https://www.runninghub.cn", "image_models": ["cn-model"], "rh_apps": [{"id": "cn-app"}]},
                "global": {"base_url": "https://www.runninghub.ai", "image_models": ["global-model"], "rh_apps": [{"id": "global-app"}]},
            },
        })

        global_provider = main.runninghub_provider_for_region(provider, "global")
        self.assertEqual(global_provider["base_url"], "https://www.runninghub.ai")
        self.assertEqual(global_provider["image_models"], ["global-model"])
        self.assertEqual(global_provider["rh_apps"][0]["id"], "global-app")
        self.assertEqual(main.runninghub_provider_for_region(provider, "cn")["rh_apps"][0]["id"], "cn-app")

    def test_canvas_exposes_only_selected_runninghub_region(self):
        provider = main.normalize_provider({
            "id": "runninghub",
            "rh_region": "cn",
            "rh_regions": {
                "cn": {"base_url": "https://www.runninghub.cn", "image_models": ["cn-model"], "rh_apps": [{"id": "cn-app"}]},
                "global": {"base_url": "https://www.runninghub.ai", "image_models": ["global-model"], "rh_apps": [{"id": "global-app"}]},
            },
        })

        with patch.object(main, "load_api_providers", return_value=[provider]):
            canvas_provider = main.canvas_api_providers()[0]

        self.assertEqual(canvas_provider["rh_region"], "cn")
        self.assertEqual(canvas_provider["image_models"], ["cn-model"])
        self.assertEqual(canvas_provider["rh_apps"][0]["id"], "cn-app")
        self.assertNotIn("rh_regions", canvas_provider)
        self.assertNotIn("global-model", canvas_provider["image_models"])

    def test_runninghub_region_key_environment_names_are_independent(self):
        self.assertEqual(main.runninghub_api_key_env("cn"), "RUNNINGHUB_CN_API_KEY")
        self.assertEqual(main.runninghub_wallet_key_env("cn"), "RUNNINGHUB_CN_WALLET_API_KEY")
        self.assertEqual(main.runninghub_api_key_env("global"), "RUNNINGHUB_GLOBAL_API_KEY")
        self.assertEqual(main.runninghub_wallet_key_env("global"), "RUNNINGHUB_GLOBAL_WALLET_API_KEY")

    def test_api_settings_uses_safe_response_reader_for_connection_requests(self):
        script = (ROOT / "static/js/api-settings.js").read_text(encoding="utf-8")

        self.assertIn("async function readApiResponse(response", script)
        self.assertIn("return readApiResponse(r, 'RunningHub 验证失败');", script)
        self.assertIn("return readApiResponse(r, tr('api.urlInvalid') || '验证失败');", script)
        self.assertNotIn("if(!r.ok) throw new Error((await r.json()).detail", script)

    def test_runninghub_onboarding_exposes_cn_and_global_links(self):
        script = (ROOT / "static/js/api-settings.js").read_text(encoding="utf-8")
        html = (ROOT / "static/api-settings.html").read_text(encoding="utf-8")

        for host in ("www.runninghub.cn", "www.runninghub.ai"):
            self.assertIn(host, script)
            self.assertIn(host, html)
        self.assertIn('id="rhRegionInput"', html)
        self.assertIn("api.rhRegionLabel", html)

    def test_runninghub_onboarding_requires_region_before_key_links(self):
        script = (ROOT / "static/js/api-settings.js").read_text(encoding="utf-8")

        self.assertIn("let onboardingRunningHubRegion = '';", script)
        self.assertIn("onchange=\"changeOnboardingRunningHubRegion(this.value)\"", script)
        self.assertIn("function changeOnboardingRunningHubRegion(region)", script)
        self.assertIn("if(!onboardingRunningHubRegion)", script)
        self.assertIn("tr('api.rhChooseRegionAlert')", script)
        self.assertIn("RUNNINGHUB_REGIONS[onboardingRunningHubRegion]", script)

    def test_volcengine_settings_link_to_official_key_consoles(self):
        html = (ROOT / "static/api-settings.html").read_text(encoding="utf-8")

        self.assertIn("https://console.volcengine.com/ark/region:ark+cn-beijing/apiKey", html)
        self.assertIn("https://console.volcengine.com/iam/keymanage/", html)
        self.assertIn("api.volcengineGetArkKey", html)
        self.assertIn("api.volcengineGetAkSk", html)
        self.assertIn("https://ark.cn-beijing.volces.com/api/v3/models", html)

    def test_agnes_is_added_from_recommended_apis_before_configuration(self):
        script = (ROOT / "static/js/api-settings.js").read_text(encoding="utf-8")

        self.assertIn("id:'agnes'", script)
        self.assertIn("add_without_key:true", script)
        self.assertIn("async function addRecommendedApi(index)", script)
        self.assertIn("onclick=\"addRecommendedApi(${index})\"", script)
        self.assertIn("enabled:api.add_without_key ? false : true", script)
        self.assertIn("item.enabled = api.add_without_key ? Boolean(item.has_key) : true;", script)
        self.assertNotIn("|| id === 'agnes';", script)
        self.assertNotIn("refreshIcons();\n    return;\n    const recommendProtocolBadge", script)
        self.assertIn("'modelscope', 'runninghub', 'volcengine', 'ai-money', 'agnes'", script)
        self.assertIn("if(item.id === 'agnes') item.enabled = true;", script)
        self.assertIn("if(item.id === 'agnes') item.enabled = false;", script)
        self.assertIn("https://platform.agnes-ai.com/settings/apiKeys", script)
        self.assertIn("agnes-2.0-flash", script)

    def test_custom_provider_guide_exposes_local_contract_and_bilingual_safe_prompt(self):
        html = (ROOT / "static/api-settings.html").read_text(encoding="utf-8")
        script = (ROOT / "static/js/api-settings.js").read_text(encoding="utf-8")

        self.assertIn('href="/api/provider-integration-guide"', html)
        self.assertIn('href="/api/provider-manifest-schema"', html)
        self.assertIn("copyProviderAgentPrompt()", html)
        self.assertIn("window.StudioI18n?.lang?.() === 'en'", script)
        self.assertIn("Run only Manifest validation, dry-run, fixtures, mocks, and local contract tests.", script)
        self.assertIn("禁止读取、输出、复制或保存 API Key", script)
        self.assertIn("network_requested=false", script)


class ApiSettingsCanvasEndToEndTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.storage = ProjectStorage(self.root)
        self.storage.ensure_layout()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), OpenAICompatibleFixtureHandler)
        OpenAICompatibleFixtureHandler.requests = []
        self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"
        self.api_env_file = self.root / "API" / ".env"
        self.api_env_file.parent.mkdir(parents=True, exist_ok=True)
        self.api_env_file.write_text("", encoding="utf-8")
        self.providers_file = self.root / "data" / "api_providers.json"
        self.history_file = self.root / "data" / "history.json"
        self.patches = [
            patch.object(main, "PROJECT_STORAGE", self.storage),
            patch.object(main, "ASSETS_DIR", str(self.storage.assets_dir)),
            patch.object(main, "OUTPUT_OUTPUT_DIR", str(self.storage.results_dir)),
            patch.object(main, "RESULTS_DIR", str(self.storage.results_dir)),
            patch.object(main, "API_PROVIDERS_FILE", str(self.providers_file)),
            patch.object(main, "API_ENV_FILE", str(self.api_env_file)),
            patch.object(main, "HISTORY_FILE", str(self.history_file)),
            patch.object(main, "GLOBAL_LOOP", None),
        ]
        for active_patch in self.patches:
            active_patch.start()
        with main.CANVAS_TASK_LOCK:
            main.CANVAS_TASKS.clear()

    async def asyncTearDown(self):
        with main.CANVAS_TASK_LOCK:
            main.CANVAS_TASKS.clear()
        for active_patch in reversed(self.patches):
            active_patch.stop()
        key = main.provider_key_env("canvas-e2e")
        os.environ.pop(key, None)
        self.server.shutdown()
        self.server.server_close()
        self.server_thread.join(timeout=2)
        self.temp.cleanup()

    async def test_runninghub_app_is_kept_in_top_level_and_selected_region(self):
        app_id = "2089305540787126273"
        entry = {
            "id": app_id,
            "appId": app_id,
            "title": "Laohu Music Digital Human V3",
            "note": "",
            "thumbnail": "https://example.com/cover.png",
            "fields": [],
            "raw": {
                "webappName": "Laohu Music Digital Human V3",
                "nodeInfoList": [{"nodeId": "1", "fieldName": "text", "fieldType": "STRING"}],
            },
            "schemaSyncedAt": 123,
            "enabled": True,
        }
        provider = main.ApiProviderPayload(
            id="runninghub",
            name="RunningHub",
            base_url="https://www.runninghub.ai",
            protocol="runninghub",
            rh_region="global",
            rh_apps=[entry],
            rh_regions={
                "cn": {"base_url": "https://www.runninghub.cn", "rh_apps": []},
                "global": {"base_url": "https://www.runninghub.ai", "rh_apps": [entry]},
            },
        )

        saved = await main.save_providers([provider])
        saved_provider = saved["providers"][0]
        self.assertIn(app_id, [item["id"] for item in saved_provider["rh_apps"]])
        self.assertIn(app_id, [item["id"] for item in saved_provider["rh_regions"]["global"]["rh_apps"]])

        stored = json.loads(self.providers_file.read_text(encoding="utf-8"))
        stored_provider = next(item for item in stored if item["id"] == "runninghub")
        self.assertIn(app_id, [item["id"] for item in stored_provider["rh_apps"]])
        self.assertIn(app_id, [item["id"] for item in stored_provider["rh_regions"]["global"]["rh_apps"]])

    async def test_saved_openai_provider_requires_profiles_before_canvas_generation(self):
        provider = main.ApiProviderPayload(
            id="canvas-e2e",
            name="Canvas E2E",
            base_url=self.base_url,
            protocol="openai",
            enabled=True,
            chat_models=["canvas-e2e-text"],
            image_models=["canvas-e2e-image"],
            video_models=["canvas-e2e-video"],
            audio_models=["canvas-e2e-audio"],
            api_key="canvas-e2e-secret",
        )

        saved = await main.save_providers([provider])
        saved_provider = saved["providers"][0]
        self.assertEqual(saved_provider["id"], "canvas-e2e")
        self.assertTrue(saved_provider["has_key"])
        self.assertNotIn("canvas-e2e-secret", json.dumps(saved, ensure_ascii=False))

        capability_response = await main.model_capabilities()
        capabilities = json.loads(capability_response.body) if hasattr(capability_response, "body") else capability_response
        capability_provider = next(item for item in capabilities["providers"] if item["id"] == "canvas-e2e")
        self.assertEqual(
            {(item["model_id"], item["node_type"]) for item in capability_provider["models"]},
            {
                ("canvas-e2e-text", "text_generation"),
                ("canvas-e2e-image", "image_generation"),
                ("canvas-e2e-video", "video_generation"),
                ("canvas-e2e-audio", "audio_generation"),
            },
        )
        self.assertTrue(all(item["validation_mode"] == "blocked" for item in capability_provider["models"]))
        self.assertTrue(all(item["readiness"] == "needs_profile" for item in capability_provider["models"]))
        self.assertTrue(all(item["runnable"] is False for item in capability_provider["models"]))

        with self.assertRaises(main.HTTPException) as text_context:
            await main.canvas_llm(main.CanvasLLMRequest(
                message="请返回画布文本链路结果",
                model="canvas-e2e-text",
                provider="canvas-e2e",
            ))
        self.assertEqual(text_context.exception.status_code, 400)
        self.assertIn("缺少经过核实的能力档案", str(text_context.exception.detail))

        image_task = await main.create_canvas_image_task(main.OnlineImageRequest(
            prompt="一张用于验证智能画布的极简测试图片",
            provider_id="canvas-e2e",
            model="canvas-e2e-image",
            size="1024x1024",
            n=1,
        ))
        task_id = image_task["task_id"]
        completed = None
        for _ in range(100):
            completed = await main.get_canvas_image_task(task_id)
            if completed["status"] in {"succeeded", "failed"}:
                break
            await asyncio.sleep(0.01)
        self.assertEqual(completed["status"], "failed")
        self.assertIn("缺少经过核实的能力档案", completed.get("error", ""))
        self.assertFalse(any(item["method"] == "POST" for item in OpenAICompatibleFixtureHandler.requests))


if __name__ == "__main__":
    unittest.main()
