"""跨版本固定案例：提交去重边界、跨平台文件名和更新包运行文件。"""
import asyncio
import ast
from pathlib import Path
import unittest

import httpx
from project_storage import safe_name
from static.release_update import allowed_file


def retry_function():
    from canvas_core.transport import httpx_request_with_transient_retries
    return httpx_request_with_transient_retries


class TransportPolicyTests(unittest.IsolatedAsyncioTestCase):
    async def test_submission_gateway_error_is_not_resubmitted(self):
        calls = []
        def handler(request):
            calls.append(request)
            return httpx.Response(503)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            response = await retry_function()(client, 'POST', 'https://fixture.invalid/tasks', attempts=3, retry_delay=0)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(len(calls), 1, '无法知道上游是否已接单时，禁止重复提交付费任务')

    async def test_submission_read_timeout_is_not_resubmitted(self):
        calls = []
        def handler(request):
            calls.append(request)
            raise httpx.ReadTimeout('response lost', request=request)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with self.assertRaises(httpx.ReadTimeout):
                await retry_function()(client, 'POST', 'https://fixture.invalid/tasks', attempts=3, retry_delay=0)
        self.assertEqual(len(calls), 1)

    async def test_read_poll_can_recover_from_gateway_failure(self):
        calls = []
        def handler(request):
            calls.append(request)
            return httpx.Response(503 if len(calls) == 1 else 200, json={'status': 'succeeded'})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            response = await retry_function()(client, 'GET', 'https://fixture.invalid/tasks/1', attempts=3, retry_delay=0)
        self.assertEqual(response.json()['status'], 'succeeded')
        self.assertEqual(len(calls), 2)


class PortableFilenameTests(unittest.TestCase):
    def test_windows_devices_are_safe_even_with_extension_and_case(self):
        for name in ('CON.png', 'nul.txt', 'AUX', 'PRN.mp4', 'COM1.mp3', 'LPT9.png', 'COM¹.png'):
            with self.subTest(name=name):
                self.assertEqual(safe_name(name), '_' + name)

    def test_long_chinese_filename_fits_component_and_keeps_extension(self):
        name = safe_name('这是很长的中文素材名称' * 30 + '.png')
        self.assertLessEqual(len(name.encode('utf-8')), 180)
        self.assertTrue(name.endswith('.png'))

    def test_ordinary_names_and_non_device_prefix_are_preserved(self):
        for name in ('林澈_外套_破损.png', 'COM10.png', 'console.txt'):
            self.assertEqual(safe_name(name), name)


class AgentReleaseFilesTests(unittest.TestCase):
    def test_agent_instructions_and_cli_survive_application_update(self):
        for name in ('static/agent-guide.md', 'canvas_cli.py'):
            self.assertTrue(allowed_file(name), name)
            self.assertTrue(Path(name).is_file(), name)
        self.assertFalse(allowed_file('docs/private.md'))
        self.assertFalse(allowed_file('tools/private.py'))


class IndexRecoveryBoundaryTests(unittest.TestCase):
    def test_bad_index_never_turns_into_empty_library_and_gets_overwritten(self):
        import tempfile
        from project_storage import ProjectStorage, StorageError
        for content in ('{broken', '{"items": "not-a-list"}', '{"version": 999, "items": []}'):
            with self.subTest(content=content), tempfile.TemporaryDirectory() as folder:
                storage = ProjectStorage(folder)
                storage.ensure_layout()
                storage.run_index_path.write_text(content, encoding='utf-8')
                with self.assertRaises(StorageError):
                    storage.prepare_run('canvas', 'node', 'request', {'model': 'test'}, {'model': 'test'})
                self.assertEqual(storage.run_index_path.read_text(encoding='utf-8'), content)
