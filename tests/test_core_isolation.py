"""内核模块故障隔离：保持外部行为，拒绝机械拆分造成的隐性依赖。"""
import asyncio
import importlib.util
import json
import unittest


class FakeSocket:
    def __init__(self, delay=0, broken=False):
        self.delay = delay
        self.broken = broken
        self.messages = []
        self.active = 0
        self.closed = False
        self.concurrent_send = False
        self.received = asyncio.Event()
    async def accept(self):
        pass
    async def close(self, code=1000):
        self.closed = True
    async def send_text(self, value):
        self.active += 1
        self.concurrent_send |= self.active > 1
        try:
            await asyncio.sleep(self.delay)
            if self.broken:
                raise OSError('disconnected')
            self.messages.append(json.loads(value))
            self.received.set()
        finally:
            self.active -= 1


class RealtimeIsolationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('canvas_core'), '共享内核必须独立于 main 初始化')
        from canvas_core.realtime import ConnectionManager
        self.manager = ConnectionManager(send_timeout=0.05)

    async def test_slow_client_cannot_delay_healthy_client(self):
        slow, healthy = FakeSocket(), FakeSocket()
        await self.manager.connect(slow, 'slow')
        await self.manager.connect(healthy, 'healthy')
        healthy.received.clear()
        slow.delay = 10
        broadcast = asyncio.create_task(self.manager.broadcast_canvas_updated('c', 42, 3, 'author'))
        await asyncio.wait_for(healthy.received.wait(), 0.03)
        await asyncio.wait_for(broadcast, 0.2)
        self.assertEqual(healthy.messages[-1], {'type':'canvas_updated','canvas_id':'c','updated_at':42,'revision':3,'client_id':'author'})
        self.assertNotIn(slow, self.manager.active_connections)
        self.assertNotIn('slow', self.manager.user_connections)
        self.assertTrue(slow.closed)
        self.assertEqual(self.manager.online_count(), 1)

    async def test_simultaneous_notifications_are_serialized_per_connection(self):
        ws = FakeSocket(delay=0.005)
        await self.manager.connect(ws, 'client')
        await asyncio.gather(self.manager.broadcast_new_image({'id':'a'}), self.manager.broadcast_asset_library_updated(123), self.manager.send_personal_message({'type':'pong'}, 'client'))
        self.assertFalse(ws.concurrent_send)
        self.assertEqual(len(ws.messages), 4)

    async def test_late_old_connection_disconnect_preserves_reconnected_client(self):
        old, new = FakeSocket(), FakeSocket()
        await self.manager.connect(old, 'same')
        await self.manager.connect(new, 'same')
        await self.manager.disconnect(old, 'same')
        await self.manager.send_personal_message({'type':'test'}, 'same')
        self.assertEqual(new.messages[-1], {'type':'test'})
        self.assertEqual(self.manager.online_count(), 1)

    async def test_failed_socket_does_not_change_notification_for_others(self):
        bad, good = FakeSocket(), FakeSocket()
        await self.manager.connect(bad, 'broken')
        await self.manager.connect(good, 'canvas_worker')
        bad.broken = True
        await self.manager.broadcast_new_image({'url':'/api/results/r'})
        self.assertEqual(good.messages[-1]['data']['url'], '/api/results/r')
        self.assertEqual(self.manager.online_count(), 0)
        self.assertNotIn(bad, self.manager.connection_clients)


class JsonStoreIsolationTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        from pathlib import Path
        self.assertIsNotNone(importlib.util.find_spec('canvas_core.json_store'))
        from canvas_core import json_store
        self.store = json_store
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.path = self.folder / '中文 画布.json'
        self.path.write_text('{"original":true}', encoding='utf-8')

    def test_serialization_failure_preserves_original_and_removes_partial_file(self):
        with self.assertRaises((TypeError, self.store.DataFileError)):
            self.store.write_json(self.path, {'invalid': object()})
        self.assertEqual(self.store.read_json(self.path), {'original': True})
        self.assertEqual(list(self.folder.iterdir()), [self.path])

    def test_disk_replace_failure_is_local_and_clean(self):
        from unittest.mock import patch
        other = self.folder / 'other.json'
        self.store.write_json(other, {'untouched': 1})
        with patch.object(self.store.os, 'replace', side_effect=OSError('disk unavailable')):
            with self.assertRaises(self.store.DataFileError):
                self.store.write_json(self.path, {'new': 1})
        self.assertEqual(self.store.read_json(self.path), {'original': True})
        self.assertEqual(self.store.read_json(other), {'untouched': 1})
        self.assertEqual(len(list(self.folder.iterdir())), 2)

    def test_only_missing_file_can_use_default(self):
        self.assertEqual(self.store.read_json(self.folder / 'missing.json', default=[]), [])
        self.path.write_text('{broken', encoding='utf-8')
        with self.assertRaises(self.store.DataFileError):
            self.store.read_json(self.path, default=[])


class TransportIsolationTests(unittest.IsolatedAsyncioTestCase):
    async def test_cancellation_is_not_converted_to_retry_or_failure(self):
        self.assertIsNotNone(importlib.util.find_spec('canvas_core.transport'))
        from canvas_core.transport import httpx_request_with_transient_retries
        import httpx
        calls = []
        async def handler(request):
            calls.append(request)
            raise asyncio.CancelledError()
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with self.assertRaises(asyncio.CancelledError):
                await httpx_request_with_transient_retries(client, 'GET', 'https://fixture.invalid', attempts=3, retry_delay=0)
        self.assertEqual(len(calls), 1)


class RequestBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('canvas_core.request_boundary'))
        from canvas_core.request_boundary import LocalRequestBoundary
        from fastapi import FastAPI, WebSocket
        from fastapi.testclient import TestClient
        app = FastAPI()
        @app.get('/api/probe')
        def probe():
            return {'ok': True}
        @app.post('/api/probe')
        def create():
            return {'ok': True}
        @app.websocket('/ws/probe')
        async def websocket(ws: WebSocket):
            await ws.accept()
            await ws.send_json({'ok': True})
            await ws.close()
        app.add_middleware(LocalRequestBoundary)
        self.client = TestClient(app, base_url='http://127.0.0.1:3000', client=('127.0.0.1', 42000))

    def test_current_page_and_cli_remain_usable(self):
        for headers in ({}, {'Origin':'http://127.0.0.1:3000'}, {'Origin':'http://localhost:3000'}):
            self.assertEqual(self.client.post('/api/probe', headers=headers).status_code, 200)
        response = self.client.options('/api/probe', headers={'Origin':'http://localhost:3000','Access-Control-Request-Method':'POST','Access-Control-Request-Headers':'content-type'})
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.headers['access-control-allow-origin'], 'http://localhost:3000')

    def test_foreign_site_cannot_read_or_write_local_api(self):
        for origin in ('https://evil.example', 'null', 'http://127.0.0.1:9000', 'http://localhost.evil.example:3000'):
            for method in ('get','post'):
                self.assertEqual(getattr(self.client, method)('/api/probe', headers={'Origin':origin}).status_code, 403)
        self.assertEqual(self.client.get('/api/probe', headers={'Sec-Fetch-Site':'cross-site'}).status_code, 403)

    def test_lan_same_origin_is_allowed_but_rebinding_host_is_not(self):
        self.assertEqual(self.client.get('/api/probe', headers={'Host':'192.168.1.253:3000','Origin':'http://192.168.1.253:3000'}).status_code, 200)
        self.assertEqual(self.client.get('/api/probe', headers={'Host':'evil.example:3000','Origin':'http://evil.example:3000'}).status_code, 403)

    def test_websocket_uses_same_boundary(self):
        from starlette.websockets import WebSocketDisconnect
        with self.client.websocket_connect('ws://127.0.0.1:3000/ws/probe', headers={'Origin':'http://127.0.0.1:3000'}) as ws:
            self.assertEqual(ws.receive_json(), {'ok':True})
        with self.assertRaises(WebSocketDisconnect) as caught:
            with self.client.websocket_connect('ws://127.0.0.1:3000/ws/probe', headers={'Origin':'https://evil.example'}):
                pass
        self.assertEqual(caught.exception.code, 1008)


class ModuleBoundaryTests(unittest.TestCase):
    def test_core_program_files_are_publishable_but_private_files_are_not(self):
        from static.release_update import allowed_file
        self.assertTrue(allowed_file('canvas_core/realtime.py'))
        self.assertFalse(allowed_file('canvas_core/secrets.env'))
        self.assertFalse(allowed_file('canvas_core/__pycache__/realtime.pyc'))

    def test_missing_local_dependency_and_reverse_import_fail_checks(self):
        import tempfile
        from pathlib import Path
        from tools import check_regression
        self.assertTrue(hasattr(check_regression, 'module_boundary_errors'))
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'canvas_core').mkdir()
            (root / 'canvas_core/__init__.py').write_text('')
            (root / 'main.py').write_text('from canvas_core.missing import run\n')
            errors = check_regression.module_boundary_errors(root)
            self.assertTrue(any('canvas_core.missing' in message for message in errors), errors)
            (root / 'canvas_core/missing.py').write_text('import main\n')
            errors = check_regression.module_boundary_errors(root)
            self.assertTrue(any('main' in message for message in errors), errors)
            (root / 'canvas_core/missing.py').write_text('def run(): pass\n')
            self.assertEqual(check_regression.module_boundary_errors(root), [])
            errors = check_regression.module_boundary_errors(root, packaged_files={'main.py'})
            self.assertTrue(any('canvas_core/missing.py' in message for message in errors), errors)


class ApplicationIsolationTests(unittest.IsolatedAsyncioTestCase):
    async def test_canvas_listing_disk_io_does_not_block_event_loop(self):
        import time
        from unittest.mock import patch
        import main
        def slow_read():
            time.sleep(0.15)
            return [{'id':'fixture'}]
        with patch.object(main, 'list_canvases', side_effect=slow_read):
            task = asyncio.create_task(main.canvases())
            try:
                await asyncio.sleep(0.01)
                self.assertFalse(task.done(), '慢磁盘读取不能占住事件循环，拖住其他请求与心跳')
            finally:
                result = await task
        self.assertEqual(result, {'canvases':[{'id':'fixture'}]})

    async def test_corrupt_project_catalog_is_not_replaced_by_default_project(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        import main
        from canvas_core.json_store import DataFileError
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'projects.json'
            path.write_text('{broken', encoding='utf-8')
            with patch.object(main, 'PROJECTS_PATH', str(path)):
                with self.assertRaises(DataFileError):
                    main.ensure_default_project()
            self.assertEqual(path.read_text(), '{broken')
