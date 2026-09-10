"""R2 发布包校验。只接收程序文件，不接收用户数据。"""
import hashlib
import io
import json
from pathlib import PurePosixPath
import re
import stat
import zipfile


PUBLIC_ROOT = 'https://infinitecanvas.lao-hu.com'
LATEST_URL = PUBLIC_ROOT + '/updates/latest.json'
MAX_PACKAGE_BYTES = 100 * 1024 * 1024
MAX_EXPANDED_BYTES = 500 * 1024 * 1024


def package_url(manifest):
    version = manifest.get('version', '')
    if not isinstance(version, str) or not re.fullmatch(r'[A-Za-z0-9_-][A-Za-z0-9._-]{0,79}', version):
        raise ValueError('更新版本号无效')
    return PUBLIC_ROOT + '/canvas-releases/' + version + '/update.zip'


def allowed_file(path):
    if not isinstance(path, str) or '\\' in path or ':' in path:
        return False
    parts = path.split('/')
    if any(p in {'', '.', '..'} for p in parts):
        return False
    if any(token in path.lower() for token in ('backup', 'broken-before', 'stable-before', '__pycache__')):
        return False
    if path.startswith(('static/', 'data/model_capabilities/')):
        return True
    return len(parts) == 1 and (PurePosixPath(path).suffix in {'.py', '.sh', '.bat', '.command'} or path in {'VERSION', 'requirements.txt'}) and path != 'get-pip.py'


def validate_package(body, manifest):
    """全部校验成功才返回文件；调用方不得边解包边覆盖正在运行的程序。"""
    if manifest.get('schema_version') != 1:
        raise ValueError('不支持的更新包格式')
    version = manifest.get('version', '')
    if not isinstance(version, str) or not re.fullmatch(r'[A-Za-z0-9._-]{1,80}', version):
        raise ValueError('更新版本号无效')
    if len(body) > MAX_PACKAGE_BYTES or len(body) != manifest.get('bytes') or hashlib.sha256(body).hexdigest() != manifest.get('sha256'):
        raise ValueError('更新包大小或 SHA-256 校验失败')
    records = manifest.get('files')
    if not isinstance(records, list) or not records or len(records) > 20000:
        raise ValueError('更新文件清单无效')
    expected = {}
    folded = set()
    for record in records:
        name = record.get('path')
        if not allowed_file(name) or name.casefold() in folded:
            raise ValueError(f'不允许或重复的更新路径：{name}')
        folded.add(name.casefold())
        expected[name] = record
    required = {'VERSION', 'main.py', 'requirements.txt', 'model_capabilities.py', 'project_storage.py', 'static/release_update.py', 'static/update-notes.json'}
    if not required.issubset(expected):
        raise ValueError('更新包缺少必要程序文件')
    result = {}
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        infos = archive.infolist()
        if len(infos) != len(expected) or sum(i.file_size for i in infos) > MAX_EXPANDED_BYTES:
            raise ValueError('更新包文件数量或解压大小异常')
        for info in infos:
            name = info.filename
            if name not in expected or name in result or stat.S_ISLNK(info.external_attr >> 16):
                raise ValueError('更新包含额外文件、重复文件或符号链接')
            data = archive.read(info)
            record = expected[name]
            if len(data) != record.get('bytes') or hashlib.sha256(data).hexdigest() != record.get('sha256'):
                raise ValueError(f'文件校验失败：{name}')
            if name.endswith('.py'):
                compile(data, name, 'exec')
            result[name] = data
    if result['VERSION'].decode('utf-8').strip() != version or json.loads(result['static/update-notes.json']).get('version') != version:
        raise ValueError('更新包版本与清单不一致')
    return result
