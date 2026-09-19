"""原生 Hypit 契约回归：仅显式启用，在本地假供应商完成一次生成，不调用付费 API。"""
import base64
import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from canvas_core.json_store import read_json, write_json
from hypit_runtime import HypitRuntime

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.environ.get('STUDIO_NATIVE_HYPIT_TESTS') == '1', '原生 Hypit 验收需要显式启用')
class NativeHypitContractTests(unittest.TestCase):
    def test_native_author_http_endpoint_and_media_result_contract(self):
        distribution = HypitRuntime(ROOT).distribution
        self.assertTrue((distribution / 'bin/hypit.mjs').is_file(), '先准备已审核的 Hypit 运行环境')
        cache = ROOT / 'cache/hypit-tests'
        cache.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=cache) as folder:
            root = Path(folder)
            (root / 'static').mkdir()
            for name in ('hypit-models.mjs', 'hypit-endpoint.mjs'):
                shutil.copyfile(ROOT / 'static' / name, root / 'static' / name)
            project = root / 'workflows/hypit/native-check'
            project.mkdir(parents=True)
            (project / 'main.svml').write_text('''<?svml using="@hypit/markup@1"?>
<svml><import as="studio" from="@laohu/studio-models@1"/><import as="text" from="@hypit/text@1"/>
<text:Value id="prompt">Native contract fixture</text:Value>
<studio:Image id="image" prompt={prompt}/></svml>''')
            (project / 'main.svrun').write_text('''<?svml using="@hypit/run-markup@1"?>
<svrun version="1"><author source="./main.svml"/><target output="image.image"/></svrun>''')
            class Runtime(HypitRuntime):
                @property
                def distribution(self):
                    return distribution
                def configure_profile(self, project_id):
                    path = super().configure_profile(project_id)
                    value = read_json(path)
                    value['endpoints'] = {'studio.models': value['endpoints']['studio.models']}
                    write_json(path, value)
                    return path
            calls = []
            png = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aX1cAAAAASUVORK5CYII=')
            class Handler(BaseHTTPRequestHandler):
                def log_message(self, *_):
                    pass
                def reply(self, value):
                    self.send_response(200)
                    self.send_header('content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps(value).encode())
                def do_POST(self):
                    payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                    calls.append((self.path, payload))
                    self.reply({'task_id': 'fixture', 'status': 'queued'})
                def do_GET(self):
                    if self.path == '/fixture.png':
                        self.send_response(200)
                        self.send_header('content-type', 'image/png')
                        self.end_headers()
                        self.wfile.write(png)
                    else:
                        self.reply({'task_id': 'fixture', 'status': 'succeeded', 'result': {'images': [{'url': '/fixture.png'}]}})
            server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            runtime = Runtime(root)
            runtime.base_url = f'http://127.0.0.1:{server.server_port}'
            try:
                self.assertTrue(runtime.execute('native-check', 'check', 'main.svrun')['output']['ok'])
                plan = runtime.execute('native-check', 'plan', 'main.svrun')['output']
                self.assertEqual(plan['unresolvedRequestCount'], 0)
                self.assertNotEqual(plan['providers'][0].get('pricing', {}).get('kind'), 'local')
                runtime.execute('native-check', 'runtime-up')
                build = runtime.execute('native-check', 'build', 'main.svrun')['output']['build']['id']
                deadline = time.monotonic() + 35
                while time.monotonic() < deadline:
                    status = runtime.execute('native-check', 'status', build_id=build)['output']['build']
                    if status['work']['state'] == 'done':
                        break
                    time.sleep(.25)
                self.assertEqual(status['work'].get('outcome'), 'complete', status)
                self.assertEqual(status['result']['outputCount'], 1)
                self.assertEqual(len(calls), 1)
                path, payload = calls[0]
                self.assertEqual(path, '/api/studio/hypit/models/projects/native-check/requests')
                self.assertLessEqual(len(payload['request_id']), 160)
                self.assertEqual(payload['constraints']['prompt'], 'Native contract fixture')
                self.assertTrue(list((root / 'assets/output/hypit/native-check').rglob('*.png')))
            finally:
                subprocess.run(runtime.command() + ['runtime', 'down', '--workspace', str(project), '--json'],
                               cwd=project, env=runtime.environment(), capture_output=True, timeout=30)
                runtime.close()
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)
