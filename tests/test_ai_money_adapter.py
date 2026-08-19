import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main


class AiMoneyAdapterTests(unittest.IsolatedAsyncioTestCase):
    def test_image_request_body_merges_capability_parameter_mapping(self):
        body = main.ai_money_image_request_body(
            "画一只猫",
            "qwen-image-3.0-t2i",
            capability_parameters={
                "n": 3,
                "negative_prompt": "模糊",
                "metadata": {"resolution": "2k", "prompt_extend_mode": "agent"},
            },
        )

        self.assertEqual(body["n"], 3)
        self.assertEqual(body["negative_prompt"], "模糊")
        self.assertEqual(body["metadata"]["resolution"], "2k")
        self.assertEqual(body["metadata"]["prompt_extend_mode"], "agent")

    def test_image_request_body_uses_capability_mapping_instead_of_legacy_ratio(self):
        body = main.ai_money_image_request_body(
            "横版海报",
            "laohuaimoney-image-g-v2-lowprice",
            aspect_ratio="9:16",
            resolution="4k",
            capability_parameters={"size": "16:9", "metadata": {"resolution": "1k"}},
        )

        self.assertEqual(body["size"], "16:9")
        self.assertEqual(body["metadata"], {"resolution": "1k"})

    def test_canvas_image_size_prefers_capability_ratio_over_stale_payload_size(self):
        self.assertEqual(
            main.canvas_image_request_size(
                "2160x3840",
                {"aspect_ratio": "16:9", "resolution": "1k"},
            ),
            "1280x720",
        )

    def test_video_request_body_merges_capability_parameter_mapping(self):
        body = main.ai_money_video_request_body(
            "seedance-2.5-standard-t2v",
            "海边日出",
            5,
            capability_parameters={
                "seconds": "12",
                "metadata": {"resolution": "1080p", "generate_audio": True},
            },
        )

        self.assertEqual(body["seconds"], "12")
        self.assertEqual(body["metadata"]["resolution"], "1080p")
        self.assertTrue(body["metadata"]["generate_audio"])

    def test_video_request_body_uses_capability_mapping_instead_of_legacy_ratio(self):
        body = main.ai_money_video_request_body(
            "seedance-2.5-standard-t2v",
            "横版镜头",
            15,
            aspect_ratio="9:16",
            resolution="480p",
            capability_parameters={
                "seconds": 6,
                "metadata": {"ratio": "16:9", "resolution": "1080p"},
            },
        )

        self.assertEqual(body["seconds"], 6)
        self.assertEqual(body["metadata"], {"ratio": "16:9", "resolution": "1080p"})

    def test_fashvsr_request_body_uses_uploaded_video_metadata_field(self):
        body = main.ai_money_fashvsr_request_body(
            "FashVSR_video_upscale",
            "https://cdn.example.com/input.mp4",
        )

        self.assertEqual(body, {
            "model": "FashVSR_video_upscale",
            "metadata": {"video_url": "https://cdn.example.com/input.mp4"},
        })

    def test_minimax_h3_audio_drive_request_keeps_image_and_audio_in_documented_fields(self):
        body = main.ai_money_video_request_body(
            "minimax-h3-ow-fl2va-audio-drive-fast",
            "让人物随音频说话",
            5,
            image_urls=["https://cdn.example.com/frame.png"],
            audio_urls=["https://cdn.example.com/voice.mp3"],
            capability_parameters={
                "seconds": 5,
                "metadata": {"resolution": "720p", "ratio": "16:9"},
            },
        )

        self.assertEqual(body["images"], ["https://cdn.example.com/frame.png"])
        self.assertEqual(body["metadata"]["audio_urls"], ["https://cdn.example.com/voice.mp3"])
        self.assertEqual(body["seconds"], 5)

    def test_ai_money_video_task_polling_uses_specialist_endpoint(self):
        urls = main.video_task_url_candidates(
            {"id": "ai-money", "base_url": "https://api.laohuaimoney.com"},
            "https://api.laohuaimoney.com",
            "task-1",
            "https://api.laohuaimoney.com/v1/video/generations",
        )

        self.assertEqual(urls, ["https://api.laohuaimoney.com/v1/video/generations/task-1"])

    def test_audio_request_body_supports_mureka_capability_parameters(self):
        body = main.ai_money_audio_request_body(
            "mureka-v9-bgm",
            "轻柔钢琴背景音乐",
            capability_parameters={"n": 3},
        )

        self.assertEqual(body, {
            "model": "mureka-v9-bgm",
            "prompt": "轻柔钢琴背景音乐",
            "metadata": {"n": 3},
        })

    def test_audio_request_body_maps_mureka_song_lyrics_and_parameters(self):
        body = main.ai_money_audio_request_body(
            "mureka-o2-song",
            "[主歌] 这是一次不会发送的 dry-run 歌词",
            capability_parameters={"metadata": {"n": 2, "reference_id": "ref_1"}},
        )

        self.assertEqual(body, {
            "model": "mureka-o2-song",
            "metadata": {
                "lyrics": "[主歌] 这是一次不会发送的 dry-run 歌词",
                "n": 2,
                "reference_id": "ref_1",
            },
        })

    def test_audio_request_body_rejects_empty_mureka_song_lyrics(self):
        with self.assertRaises(HTTPException):
            main.ai_money_audio_request_body("mureka-v9-song", "")

    def test_canvas_standard_parameters_map_to_mureka_song_body_without_network(self):
        provider = next(item for item in main.load_api_providers() if item.get("id") == "ai-money")
        profile = main.MODEL_CAPABILITY_REGISTRY.find_model(
            [provider], "ai-money", "mureka-o2-song", "music_generation"
        )
        platform_parameters = main.MODEL_CAPABILITY_REGISTRY.platform_parameters(
            profile, {"count": 3, "reference_id": "reference-dry-run"}
        )
        body = main.ai_money_audio_request_body(
            "mureka-o2-song",
            "[副歌] 这段歌词只用于构建请求，不会发送",
            capability_parameters=platform_parameters,
        )

        self.assertFalse(body.get("prompt"))
        self.assertEqual(body["metadata"], {
            "lyrics": "[副歌] 这段歌词只用于构建请求，不会发送",
            "n": 3,
            "reference_id": "reference-dry-run",
        })

    def test_audio_request_body_supports_reference_qwen_and_minimax_contracts(self):
        qwen = main.ai_money_audio_request_body(
            "qwen3-tts-instruct-flash",
            "欢迎使用音频节点。",
            capability_parameters={"metadata": {
                "voice": "Cherry", "language_type": "Chinese",
                "instructions": "温柔、自然", "optimize_instructions": True,
            }},
        )
        music = main.ai_money_audio_request_body(
            "minimax-music-2.6",
            "温暖电影感的器乐配乐",
            capability_parameters={"metadata": {
                "is_instrumental": True, "lyrics_optimizer": False,
                "format": "mp3", "sample_rate": "44100", "bitrate": "256000",
            }},
        )
        speech = main.ai_money_audio_request_body(
            "minimax-speech-2.8-hd",
            "这是一段清晰自然的语音。",
            capability_parameters={"metadata": {
                "voice_id": "Wise_Woman", "speed": 1.1, "vol": 1.2, "pitch": 1,
                "language_boost": "Chinese", "format": "wav", "sample_rate": "32000",
                "bitrate": "128000", "channel": 2,
            }},
        )
        clone = main.ai_money_audio_request_body(
            "minimax-voice-clone",
            "创建可复用音色",
            reference_audio_url="https://cdn.example.com/reference.mp3",
            capability_parameters={"metadata": {
                "custom_voice_id": "CanvasVoice01", "model": "minimax-speech-2.8-hd",
                "need_noise_reduction": True, "need_volume_normalization": True,
            }},
        )

        self.assertEqual(qwen["metadata"]["voice"], "Cherry")
        self.assertTrue(qwen["metadata"]["optimize_instructions"])
        self.assertEqual(music["metadata"]["bitrate"], "256000")
        self.assertEqual(speech["metadata"]["voice_id"], "Wise_Woman")
        self.assertEqual(speech["metadata"]["channel"], 2)
        self.assertEqual(clone["metadata"]["audio_url"], "https://cdn.example.com/reference.mp3")
        self.assertEqual(clone["metadata"]["custom_voice_id"], "CanvasVoice01")

    def test_ai_money_special_task_roots_use_provider_base_url(self):
        provider = {"id": "ai-money", "base_url": "https://api.laohuaimoney.com", "protocol": "openai"}

        self.assertEqual(
            main.midjourney_api_url(provider, "/v1/midjourney/generations/upscale"),
            "https://api.laohuaimoney.com/v1/midjourney/generations/upscale",
        )
        self.assertEqual(
            main.ai_money_music_api_url(provider, "extend"),
            "https://api.laohuaimoney.com/v1/music/generations/extend",
        )

    async def test_canvas_midjourney_image_uses_dedicated_task_adapter(self):
        provider = {
            "id": "ai-money",
            "name": "AI MONEY",
            "base_url": "https://api.laohuaimoney.com",
            "protocol": "openai",
            "enabled": True,
            "image_models": ["midjourney-imagine"],
            "chat_models": [],
            "video_models": [],
            "audio_models": [],
        }
        payload = main.OnlineImageRequest(
            provider_id="ai-money",
            model="midjourney-imagine",
            family_id="ai-money-midjourney",
            prompt="一座漂浮在云海上的城市",
            aspect_ratio="16:9",
            parameters={"speed": "fast", "version": "6.1", "aspect_ratio": "16:9"},
        )
        dedicated = AsyncMock(return_value=({"type": "url", "value": "https://cdn.example.com/mj.png"}, {"task_id": "mj_task_1"}))
        generic = AsyncMock(side_effect=AssertionError("Midjourney 不得进入通用图片接口"))

        with patch.object(main, "load_api_providers", return_value=[provider]), \
             patch.object(main, "get_api_provider", return_value=provider), \
             patch.object(main, "generate_ai_money_midjourney_image", dedicated, create=True), \
             patch.object(main, "generate_ai_image", generic), \
             patch.object(main, "save_ai_image_to_output", new=AsyncMock(return_value="/api/results/mj-result")), \
             patch.object(main, "save_to_history"):
            result = await main.build_online_image_result(payload)

        dedicated.assert_awaited_once()
        generic.assert_not_awaited()
        self.assertEqual(result["images"], ["/api/results/mj-result"])
        self.assertEqual(result["task_id"], "mj_task_1")

    async def test_midjourney_imagine_submits_and_polls_dedicated_endpoints(self):
        provider = {"id": "ai-money", "base_url": "https://api.laohuaimoney.com", "protocol": "openai"}
        submitted = {"data": {"task_id": "mj_task_2", "status": "queued"}}
        completed = {
            "status": "succeeded",
            "task_id": "mj_task_2",
            "images": ["/api/results/mj-final"],
            "raw": {"data": {"status": "SUCCESS"}},
        }

        with patch.object(main, "midjourney_reference_urls", new=AsyncMock(return_value=[])), \
             patch.object(main, "apimart_midjourney_request", new=AsyncMock(return_value=(submitted, "mj_task_2"))) as submit, \
             patch.object(main, "midjourney_result", new=AsyncMock(return_value=completed)) as poll:
            image, raw = await main.generate_ai_money_midjourney_image(
                "云海城市",
                "1920x1080",
                "midjourney-imagine",
                [],
                provider,
                {"speed": "fast", "size": "16:9", "version": "6.1"},
                "midjourney_imagine",
            )

        submit.assert_awaited_once_with(provider, "/v1/midjourney/generations", {
            "speed": "fast",
            "metadata": {"source": "infinite-canvas"},
            "prompt": "云海城市",
            "size": "16:9",
            "version": "6.1",
        })
        poll.assert_awaited_once_with(provider, "mj_task_2")
        self.assertEqual(image, {"type": "url", "value": "/api/results/mj-final"})
        self.assertEqual(raw["task_id"], "mj_task_2")

    async def test_midjourney_pan_uses_task_id_and_direction(self):
        provider = {"id": "ai-money", "base_url": "https://api.laohuaimoney.com", "protocol": "openai"}
        completed = {"status": "succeeded", "task_id": "mj_task_3", "images": ["/api/results/mj-pan"], "raw": {}}

        with patch.object(main, "midjourney_reference_urls", new=AsyncMock(return_value=[])), \
             patch.object(main, "apimart_midjourney_request", new=AsyncMock(return_value=({}, "mj_task_3"))) as submit, \
             patch.object(main, "midjourney_result", new=AsyncMock(return_value=completed)):
            await main.generate_ai_money_midjourney_image(
                "",
                "1024x1024",
                "midjourney-pan",
                [],
                provider,
                {"upstream_task_id": "mj_source", "direction": "left", "speed": "relax"},
                "midjourney_pan",
            )

        submit.assert_awaited_once_with(provider, "/v1/midjourney/generations/pan", {
            "speed": "relax",
            "metadata": {"source": "infinite-canvas"},
            "task_id": "mj_source",
            "direction": "left",
        })

    def test_suno_request_body_uses_public_task_identity(self):
        body = main.ai_money_suno_request_body(
            "suno-extend",
            "继续保持钢琴主题",
            {"task_id": "task_source", "audio_index": 2, "continue_at": 30, "version": "v5"},
        )

        self.assertEqual(body["model"], "suno")
        self.assertEqual(body["task_id"], "task_source")
        self.assertEqual(body["audio_index"], 2)
        self.assertEqual(body["continue_at"], 30)

    def test_ai_money_text_specialists_choose_dedicated_endpoints(self):
        provider = {"id": "ai-money", "base_url": "https://api.laohuaimoney.com", "protocol": "openai"}

        self.assertEqual(
            main.ai_money_text_specialist_url(provider, "transcription"),
            "https://api.laohuaimoney.com/v1/audio/transcriptions",
        )
        self.assertEqual(
            main.ai_money_text_specialist_url(provider, "prompt_enhancement"),
            "https://api.laohuaimoney.com/v1/video/generations",
        )
        self.assertEqual(
            main.ai_money_text_specialist_url(provider, "image_description"),
            "https://api.laohuaimoney.com/v1/midjourney/generations/describe",
        )

    def test_default_providers_include_ai_money_without_preselecting_models(self):
        provider = next(item for item in main.default_api_providers() if item["id"] == "ai-money")

        self.assertEqual(provider["name"], "AI MONEY")
        self.assertEqual(provider["base_url"], "https://api.laohuaimoney.com")
        self.assertEqual(provider["protocol"], "openai")
        self.assertEqual(provider["image_models"], [])
        self.assertEqual(provider["chat_models"], [])
        self.assertEqual(provider["video_models"], [])
        self.assertEqual(provider["audio_models"], [])

    def test_existing_provider_config_is_migrated_with_ai_money(self):
        merged = main.merge_default_api_providers([
            {
                "id": "custom",
                "name": "Custom",
                "base_url": "https://example.com",
                "protocol": "openai",
            }
        ], inject_missing=False)

        self.assertTrue(any(item.get("id") == "ai-money" for item in merged))

    def test_ai_money_provider_is_detected_by_id_or_host(self):
        self.assertTrue(main.is_ai_money_provider({"id": "ai-money", "base_url": ""}))
        self.assertTrue(main.is_ai_money_provider({"id": "custom", "base_url": "https://api.laohuaimoney.com/"}))
        self.assertFalse(main.is_ai_money_provider({"id": "custom", "base_url": "https://example.com"}))

    def test_ai_money_catalog_classifies_models_by_canvas_output(self):
        grouped, _ = main.parse_upstream_models({"data": [
            {"id": "laohuaimoney-upscaler", "owned_by": "doubaovideo"},
            {"id": "minmax-h3-context-ir-image", "owned_by": "doubaovideo"},
            {"id": "whisper-1", "owned_by": "openai"},
            {"id": "midjourney-describe", "owned_by": "apimart-midjourney"},
            {"id": "midjourney-video", "owned_by": "apimart-midjourney"},
            {"id": "suno-generation", "owned_by": "apimart music"},
        ]})

        self.assertIn("laohuaimoney-upscaler", grouped["video"])
        self.assertIn("minmax-h3-context-ir-image", grouped["chat"])
        self.assertIn("whisper-1", grouped["chat"])
        self.assertIn("midjourney-describe", grouped["chat"])
        self.assertIn("midjourney-video", grouped["video"])
        self.assertIn("suno-generation", grouped["audio"])

    def test_builds_ai_money_image_body_for_image_to_image(self):
        body = main.ai_money_image_request_body(
            prompt="一张山间湖泊的电影感照片",
            model="seedream-v5-pro-i2i",
            reference_urls=["https://cdn.example.com/reference.png"],
            aspect_ratio="16:9",
            resolution="2k",
        )

        self.assertEqual(body, {
            "model": "seedream-v5-pro-i2i",
            "prompt": "一张山间湖泊的电影感照片",
            "images": ["https://cdn.example.com/reference.png"],
            "metadata": {"ratio": "16:9", "resolution": "2k"},
        })

    def test_ai_money_image_task_url_uses_image_generations_route(self):
        provider = {"id": "ai-money", "base_url": "https://api.laohuaimoney.com"}

        self.assertEqual(
            main.ai_money_image_task_url(provider, "task_123"),
            "https://api.laohuaimoney.com/v1/image/generations/task_123",
        )

    def test_ai_money_accepts_signed_image_result_without_file_extension(self):
        image = main.ai_money_extract_image({
            "data": {"result_url": "https://cdn.example.com/generated?id=123&signature=abc"}
        })

        self.assertEqual(image, {
            "type": "url",
            "value": "https://cdn.example.com/generated?id=123&signature=abc",
        })

    def test_builds_ai_money_multimodal_video_body(self):
        body = main.ai_money_video_request_body(
            model="seedance-2.0-fast-multi",
            prompt="把视频中的人物替换成参考图人物",
            seconds=8,
            aspect_ratio="9:16",
            resolution="1080p",
            image_urls=["https://cdn.example.com/person.png"],
            video_urls=["https://cdn.example.com/source.mp4"],
            audio_urls=["https://cdn.example.com/voice.mp3"],
            generate_audio=True,
        )

        self.assertEqual(body["model"], "seedance-2.0-fast-multi")
        self.assertEqual(body["seconds"], "8")
        self.assertEqual(body["metadata"]["ratio"], "9:16")
        self.assertEqual(body["metadata"]["resolution"], "1080p")
        self.assertTrue(body["metadata"]["generate_audio"])
        self.assertEqual(body["metadata"]["content"], [
            {"type": "image_url", "image_url": {"url": "https://cdn.example.com/person.png"}},
            {"type": "video_url", "video_url": {"url": "https://cdn.example.com/source.mp4"}},
            {"type": "audio_url", "audio_url": {"url": "https://cdn.example.com/voice.mp3"}},
        ])

    def test_ai_money_video_routes_follow_documented_paths(self):
        provider = {"id": "ai-money", "base_url": "https://api.laohuaimoney.com"}

        self.assertEqual(
            main.video_submit_url_candidates(provider, "https://api.laohuaimoney.com"),
            ["https://api.laohuaimoney.com/v1/videos"],
        )
        self.assertEqual(
            main.video_task_url_candidates(provider, "https://api.laohuaimoney.com", "task_123"),
            ["https://api.laohuaimoney.com/v1/videos/task_123"],
        )

    def test_ai_money_video_result_reads_metadata_url(self):
        self.assertEqual(
            main.video_output_urls({
                "data": {
                    "status": "completed",
                    "metadata": {"url": "https://cdn.example.com/video?id=123"},
                }
            }),
            ["https://cdn.example.com/video?id=123"],
        )

    def test_ai_money_rejects_image_to_video_without_an_image(self):
        with self.assertRaises(HTTPException):
            main.ai_money_video_request_body(
                model="seedance-2.0-fast-i2v",
                prompt="生成视频",
                seconds=5,
                aspect_ratio="16:9",
                resolution="720p",
                image_urls=[],
                video_urls=[],
                audio_urls=[],
            )

    def test_builds_seed_audio_body_with_documented_metadata(self):
        body = main.ai_money_audio_request_body(
            model="doubao-seed-audio-1.0",
            prompt="温柔、清晰的中文旁白",
            reference_audio_url="https://cdn.example.com/reference.wav",
            speaker="",
            audio_format="mp3",
            sample_rate=24000,
            speech_rate=12,
            loudness_rate=-5,
            pitch_rate=2,
        )

        self.assertEqual(body, {
            "model": "doubao-seed-audio-1.0",
            "prompt": "温柔、清晰的中文旁白",
            "metadata": {
                "audio_url": "https://cdn.example.com/reference.wav",
                "format": "mp3",
                "sample_rate": "24000",
                "speech_rate": 12,
                "loudness_rate": -5,
                "pitch_rate": 2,
            },
        })

    def test_seed_audio_body_rejects_speaker_and_reference_audio_together(self):
        with self.assertRaises(HTTPException) as context:
            main.ai_money_audio_request_body(
                model="doubao-seed-audio-1.0",
                prompt="测试",
                reference_audio_url="https://cdn.example.com/reference.wav",
                speaker="speaker-id",
            )

        self.assertIn("互斥", str(context.exception.detail))

    def test_ai_money_audio_result_reads_all_documented_shapes(self):
        self.assertEqual(
            main.ai_money_audio_output_urls({"data": {"result_url": "https://cdn.example.com/a.mp3"}}),
            ["https://cdn.example.com/a.mp3"],
        )
        self.assertEqual(
            main.ai_money_audio_output_urls({"data": {"data": {"content": {"audio_url": "https://cdn.example.com/b.wav"}}}}),
            ["https://cdn.example.com/b.wav"],
        )
        self.assertEqual(
            main.ai_money_audio_output_urls({"data": {"content": {"audio_urls": ["https://cdn.example.com/c.ogg"]}}}),
            ["https://cdn.example.com/c.ogg"],
        )

    def test_ai_money_voice_clone_result_reads_text_output(self):
        self.assertEqual(
            main.ai_money_audio_result_text({"data": {"voice_id": "CanvasVoice01"}}),
            "CanvasVoice01",
        )
        self.assertEqual(
            main.ai_money_audio_result_text({"result": {"result_text": "CanvasVoice02"}}),
            "CanvasVoice02",
        )

    def test_normalized_provider_preserves_audio_models(self):
        provider = main.normalize_provider({
            "id": "ai-money",
            "name": "AI MONEY",
            "base_url": "https://api.laohuaimoney.com",
            "protocol": "openai",
            "audio_models": ["doubao-seed-audio-1.0"],
        })

        self.assertEqual(provider["audio_models"], ["doubao-seed-audio-1.0"])

    async def test_generate_seed_audio_downloads_and_returns_local_result(self):
        provider = {
            "id": "ai-money",
            "name": "AI MONEY",
            "base_url": "https://api.laohuaimoney.com",
            "protocol": "openai",
            "audio_models": ["doubao-seed-audio-1.0"],
        }
        completed = {"data": {"status": "SUCCESS", "result_url": "https://cdn.example.com/audio?id=123"}}

        with patch.object(main, "provider_env_key_value", return_value="test-key"), \
             patch.object(main, "wait_for_ai_money_audio_task", new=AsyncMock(return_value=completed)), \
             patch.object(main, "save_remote_audio_to_output", new=AsyncMock(return_value="/api/results/res_audio")), \
             patch("main.httpx.AsyncClient") as client_class:
            client = client_class.return_value.__aenter__.return_value
            submit_response = AsyncMock()
            submit_response.raise_for_status = lambda: None
            submit_response.json = lambda: {"task_id": "task_audio_1", "status": "queued"}
            client.post = AsyncMock(return_value=submit_response)

            result = await main.generate_ai_money_audio(
                provider=provider,
                model="doubao-seed-audio-1.0",
                prompt="测试音频",
                reference_audio_url="",
                speaker="speaker-id",
                audio_format="mp3",
                sample_rate=24000,
                speech_rate=0,
                loudness_rate=0,
                pitch_rate=0,
            )

        self.assertEqual(result["audios"], ["/api/results/res_audio"])
        self.assertEqual(result["task_id"], "task_audio_1")
        client.post.assert_awaited_once()

    async def test_generate_voice_clone_returns_text_material(self):
        provider = {
            "id": "ai-money",
            "name": "AI MONEY",
            "base_url": "https://api.laohuaimoney.com",
            "protocol": "openai",
            "audio_models": ["minimax-voice-clone"],
        }
        completed = {"data": {"status": "SUCCESS", "voice_id": "CanvasVoice01"}}

        with patch.object(main, "provider_env_key_value", return_value="test-key"), \
             patch.object(main, "ai_money_upload_reference", new=AsyncMock(return_value="https://cdn.example.com/reference.mp3")), \
             patch.object(main, "wait_for_ai_money_audio_task", new=AsyncMock(return_value=completed)), \
             patch.object(main, "save_remote_audio_to_output", new=AsyncMock(side_effect=AssertionError("音色 ID 不得按音频下载"))), \
             patch("main.httpx.AsyncClient") as client_class:
            client = client_class.return_value.__aenter__.return_value
            submit_response = AsyncMock()
            submit_response.raise_for_status = lambda: None
            submit_response.json = lambda: {"task_id": "task_voice_1", "status": "queued"}
            client.post = AsyncMock(return_value=submit_response)

            result = await main.generate_ai_money_audio(
                provider=provider,
                model="minimax-voice-clone",
                prompt="创建可复用音色",
                reference_audio_url="/api/results/reference",
                capability_parameters={"metadata": {"custom_voice_id": "CanvasVoice01"}},
            )

        self.assertEqual(result["texts"], [{"url": "CanvasVoice01", "kind": "text", "name": "CanvasVoice01"}])
        self.assertEqual(result["task_id"], "task_voice_1")


if __name__ == "__main__":
    unittest.main()
