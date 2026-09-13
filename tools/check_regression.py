"""统一回归入口：在项目盘运行 Python 测试与前端语法检查，失败返回非零值。"""
import ast
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from local_runtime import runtime_environment
from static.release_update import allowed_file


def module_boundary_errors(root, packaged_files=None):
    """检查共享内核反向依赖、缺失的本地模块和打包遗漏，不导入业务入口。"""
    root = Path(root)
    files = list(root.glob('*.py'))
    for folder in ('canvas_core', 'static'):
        files.extend((root / folder).rglob('*.py'))
    files = [path for path in files if allowed_file(path.relative_to(root).as_posix())]
    names = {path.relative_to(root).as_posix() for path in files}
    local_roots = {path.stem for path in files if path.parent == root} | {'canvas_core', 'static'}
    errors = []
    for path in files:
        relative = path.relative_to(root).as_posix()
        try:
            tree = ast.parse(path.read_text(encoding='utf-8-sig'), filename=relative)
        except (OSError, SyntaxError) as exc:
            errors.append(f'{relative}: {exc}')
            continue
        for node in ast.walk(tree):
            modules = []
            if isinstance(node, ast.Import):
                modules = [item.name for item in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    package = list(path.relative_to(root).parts[:-1])
                    base = package[:len(package) - node.level + 1]
                    modules = ['.'.join(base + ([node.module] if node.module else [item.name])) for item in node.names]
                elif node.module:
                    modules = [node.module]
            for module in modules:
                top = module.split('.')[0]
                if relative.startswith('canvas_core/') and top == 'main':
                    errors.append(f'{relative}: 共享内核不得反向依赖 main')
                if top not in local_roots:
                    continue
                stem = module.replace('.', '/')
                if stem + '.py' not in names and stem + '/__init__.py' not in names:
                    # static 是现有命名空间包；导入它本身不要求 __init__.py。
                    if not (module == 'static' and (root / 'static').is_dir()):
                        errors.append(f'{relative}: 缺少本地依赖 {module}')
            if relative.startswith('canvas_core/') and isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {'exec', 'eval'}:
                errors.append(f'{relative}: 共享内核不得通过 {node.func.id} 注入业务全局状态')
    if packaged_files is not None:
        for missing in sorted(names - set(packaged_files)):
            errors.append(f'更新包遗漏程序模块：{missing}')
        if 'canvas_agent.py' in names and 'static/agent-guide.md' not in packaged_files:
            errors.append('更新包遗漏 Agent 运行说明：static/agent-guide.md')
    return sorted(set(errors))


def main():
    errors = module_boundary_errors(ROOT)
    if errors:
        print('\n'.join(errors), flush=True)
        return 1
    env = runtime_environment(ROOT)
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    # 子进程启动前启用 UTF-8，Windows 的默认代码页不能决定源码和测试的编码。
    print(f'回归环境：{sys.platform} / Python {sys.version.split()[0]}', flush=True)
    node = shutil.which('node')
    if not node:
        print('缺少 Node.js，无法验证前端脚本；请安装 Node.js 22+。', flush=True)
        return 1
    scripts = sorted((ROOT / 'static/js').rglob('*.js'))
    for script in scripts:
        code = subprocess.call([node, '--check', str(script)], cwd=ROOT, env=env)
        if code:
            return code
    print(f'前端语法检查通过：{len(scripts)} 个脚本。开始全部固定回归案例。', flush=True)
    return subprocess.call([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests'], cwd=ROOT, env=env)


if __name__ == '__main__':
    raise SystemExit(main())
