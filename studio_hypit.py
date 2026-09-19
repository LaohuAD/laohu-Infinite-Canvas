"""Hypit 项目接入边界；模型调用由注入的工作台服务负责。"""
import asyncio
import hashlib
import json
import time
from pathlib import Path
from threading import RLock

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from canvas_agent import is_local_client
from canvas_core.json_store import read_json, write_json
from hypit_runtime import HypitRuntime


class FileWrite(BaseModel):
    path: str
    content: str = Field(max_length=2000000)
    expected_sha256: str


class HypitOperation(BaseModel):
    request_id: str = Field(min_length=1, max_length=160)
    operation: str
    source: str = ''
    build_id: str = ''


class StudioOpen(BaseModel):
    source: str = 'main.svrun'


def create_hypit_router(root, get_project, runtime=None, register_result=None):
    root = Path(root)
    runtime = runtime or HypitRuntime(root)
    lock = RLock()
    tasks = set()
    active_operations = set()
    router = APIRouter(prefix='/api/studio', tags=['Hypit'])

    async def local(request: Request):
        if not await run_in_threadpool(is_local_client, request.client.host if request.client else ''):
            raise HTTPException(403, '请在工作台服务所在电脑操作')
        if request.headers.get('origin', str(request.base_url)).rstrip('/') != str(request.base_url).rstrip('/'):
            raise HTTPException(403, '不允许跨站操作')
        from urllib.parse import urlparse
        address = urlparse(str(request.base_url))
        if address.hostname in {'127.0.0.1', 'localhost', '::1'}:
            runtime.base_url = str(request.base_url).rstrip('/')

    router.dependencies.append(Depends(local))

    def project(project_id):
        value = get_project(project_id, 'hypit')
        runtime.project(project_id)
        return value

    async def call(function, *args):
        try:
            return await run_in_threadpool(function, *args)
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(400, str(exc)) from exc

    @router.get('/hypit/runtime')
    async def status():
        return await call(runtime.status)

    @router.post('/hypit/runtime/prepare')
    async def prepare():
        return await call(runtime.install)

    @router.get('/hypit/projects/{project_id}/files')
    async def files(project_id: str, path: str = ''):
        project(project_id)
        if path:
            target = await call(runtime.source, project_id, path)
            if not target.is_file():
                raise HTTPException(404, '工程文件不存在')
            if target.stat().st_size > 2000000:
                raise HTTPException(413, '文件过大，请按原生工程工具处理')
            content = target.read_bytes()
            return {'path': path, 'content': content.decode('utf-8'), 'sha256': hashlib.sha256(content).hexdigest()}
        base = runtime.project(project_id)
        return {'files': sorted(p.relative_to(base).as_posix() for p in base.rglob('*')
                                if p.is_file() and p.suffix in {'.svml', '.svrun', '.svs', '.md', '.json'}
                                and not any(part.startswith('.') or part == 'node_modules' for part in p.relative_to(base).parts))[:2000]}

    @router.put('/hypit/projects/{project_id}/files')
    async def save_file(project_id: str, payload: FileWrite):
        project(project_id)
        target = await call(runtime.source, project_id, payload.path)
        # 结果仓库属于工作台配置；不能经一般文件写入口改到其他目录。
        if target.name in {'hypit.results.json', 'hypit.runtime.json', 'package-lock.json'}:
            raise HTTPException(400, '此文件由工作台管理')
        with lock:
            current = target.read_bytes() if target.exists() else b''
            digest = hashlib.sha256(current).hexdigest() if target.exists() else ''
            if payload.expected_sha256 != digest:
                raise HTTPException(409, {'message': '文件已更新，请重新读取并合并', 'sha256': digest,
                                          'content': current.decode('utf-8')})
            target.parent.mkdir(parents=True, exist_ok=True)
            # 与 JSON 写入一样，先落临时文件再原子替换；临时文件不离开工程盘。
            import tempfile
            with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as temp:
                temp.write(payload.content.encode('utf-8'))
                temporary = Path(temp.name)
            try:
                temporary.replace(target)
            finally:
                temporary.unlink(missing_ok=True)
        return {'path': payload.path, 'sha256': hashlib.sha256(payload.content.encode('utf-8')).hexdigest()}

    @router.post('/hypit/projects/{project_id}/studio')
    async def studio(project_id: str, payload: StudioOpen):
        project(project_id)
        return await call(runtime.studio, project_id, payload.source)

    @router.get('/hypit/projects/{project_id}/operations/{request_id}')
    async def operation_status(project_id: str, request_id: str):
        project(project_id)
        key = hashlib.sha256(request_id.encode()).hexdigest()
        target = root / 'data' / 'hypit_operations' / project_id / f'{key}.json'
        if not target.exists():
            raise HTTPException(404, '操作不存在')
        with lock:
            record = read_json(target)
            if record.get('status') == 'running' and str(target) not in active_operations:
                record.update(status='recoverable', error='服务已重启，请查询原生 Build 状态；不会自动重新提交')
                write_json(target, record)
        return record

    def collect_results(project_id):
        if register_result is None:
            return []
        base = root / 'assets' / 'output' / 'hypit' / project_id
        output = []
        seen = set()
        for manifest_path in base.glob('*/*/result.json'):
            manifest = read_json(manifest_path)
            if manifest.get('format') != 'hypit.build-result@1':
                raise ValueError('不支持的 Hypit 结果清单格式')
            def collect_ref(ref, label=''):
                if ref.get('kind') != 'build-file' or ref.get('build'):
                    return  # 其他 Build 拥有的文件在其自己的清单中登记。
                relative = ref.get('path', '')
                path = (manifest_path.parent / relative).resolve()
                if not relative or not path.is_relative_to(manifest_path.parent.resolve()):
                    raise ValueError('Hypit 结果路径超出 Build 目录')
                if path in seen or not str(ref.get('mediaType', '')).startswith(('image/', 'video/', 'audio/')):
                    return
                seen.add(path)
                name = (label + path.suffix) if label and not Path(label).suffix else label or path.name
                output.append(register_result(path, name, source_module='hypit', source_project_id=project_id,
                                              source_build_id=manifest_path.parent.name))
            for label, entry in manifest.get('outputs', {}).items():
                value = entry.get('value', {})
                if value.get('kind') == 'value':
                    document_path = (manifest_path.parent / value.get('path', '')).resolve()
                    if not document_path.is_relative_to(manifest_path.parent.resolve()):
                        raise ValueError('Hypit 复合结果路径越界')
                    document = read_json(document_path)
                    if document.get('format') != 'hypit.result-value@1':
                        raise ValueError('不支持的 Hypit 复合结果格式')
                    for binding in document.get('resources', []):
                        collect_ref(binding.get('file', {}))
                else:
                    collect_ref(value, entry.get('displayName', label))
        return output

    @router.get('/hypit/projects/{project_id}/results')
    async def results(project_id: str):
        project(project_id)
        return {'results': await run_in_threadpool(collect_results, project_id)}

    @router.post('/hypit/projects/{project_id}/operations')
    async def operate(project_id: str, payload: HypitOperation):
        project(project_id)
        key = hashlib.sha256(payload.request_id.encode()).hexdigest()
        target = root / 'data' / 'hypit_operations' / project_id / f'{key}.json'
        fingerprint = hashlib.sha256(json.dumps([payload.operation, payload.source, payload.build_id]).encode()).hexdigest()
        with lock:
            if target.exists():
                existing = read_json(target)
                if existing['fingerprint'] != fingerprint:
                    raise HTTPException(409, '相同 request_id 不能用于不同操作')
                return existing
            record = {'request_id': payload.request_id, 'fingerprint': fingerprint, 'status': 'running',
                      'created_at': time.time(), 'operation': payload.operation, 'source': payload.source, 'build_id': payload.build_id}
            write_json(target, record)
            active_operations.add(str(target))
        async def execute():
            try:
                result = await call(runtime.execute, project_id, payload.operation, payload.source, payload.build_id)
                if payload.operation in {'build', 'status', 'history', 'builds'}:
                    result['results'] = await run_in_threadpool(collect_results, project_id)
                record.update(status='succeeded', result=result)
            except Exception as exc:
                record.update(status='failed', error=str(getattr(exc, 'detail', None) or exc))
            record['completed_at'] = time.time()
            with lock:
                write_json(target, record)
                active_operations.discard(str(target))
        task = asyncio.create_task(execute())
        tasks.add(task)
        task.add_done_callback(tasks.discard)
        return record

    return router
