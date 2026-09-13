#!/usr/bin/env python3
"""跨平台画布 CLI，仅依赖 Python 标准库。"""
import argparse
import json
import sys
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def request(base, path, data=None):
    body = json.dumps(data, ensure_ascii=False).encode('utf-8') if data is not None else None
    req = Request(base.rstrip('/') + path, data=body, headers={'Content-Type':'application/json'})
    try:
        with urlopen(req, timeout=30) as response:
            raw = response.read().decode('utf-8')
            return json.loads(raw) if 'json' in response.headers.get('Content-Type','') else raw
    except HTTPError as exc:
        raise RuntimeError(f'HTTP {exc.code}: {exc.read().decode("utf-8", errors="replace")}') from exc


def main():
    parser = argparse.ArgumentParser(description='用结构化命令操作老胡无限画布；需保持画布页面打开。')
    parser.add_argument('--base-url', default='http://127.0.0.1:3000')
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ['capabilities','guide','canvases','models']:
        commands.add_parser(name)
    defaults = commands.add_parser('defaults', help='读取当前画布的 Agent 默认模型与参数')
    defaults.add_argument('canvas_id')
    get = commands.add_parser('get', help='读取指定画布')
    get.add_argument('canvas_id')
    status = commands.add_parser('status', help='查询原命令；不重复执行')
    status.add_argument('canvas_id'); status.add_argument('command_id', nargs='?')
    send = commands.add_parser('send', help='从 UTF-8 JSON 文件提交命令')
    send.add_argument('canvas_id'); send.add_argument('file', type=Path)
    send.add_argument('--request-id', help='幂等编号；优先使用文件内 request_id')
    send.add_argument('--wait', type=float, default=0, help='等待完成的最大秒数；超时不会重发')
    args = parser.parse_args()
    if args.command in ['capabilities','guide','canvases','models']:
        path = {'capabilities':'/api/agent/capabilities','guide':'/api/agent/guide','canvases':'/api/canvases','models':'/api/model-capabilities'}[args.command]
        result = request(args.base_url, path)
    elif args.command == 'defaults':
        result = request(args.base_url, f'/api/agent/canvases/{args.canvas_id}/defaults')
    elif args.command == 'get':
        result = request(args.base_url, '/api/canvases/' + args.canvas_id)
    elif args.command == 'status':
        result = request(args.base_url, f'/api/agent/canvases/{args.canvas_id}/commands' + ('/' + args.command_id if args.command_id else ''))
    else:
        payload = json.loads(args.file.read_text(encoding='utf-8-sig'))
        payload['request_id'] = payload.get('request_id') or args.request_id or str(uuid.uuid4())
        # 先输出编号，即使提交响应丢失，调用方也能在命令列表中找回。
        print('request_id=' + payload['request_id'], file=sys.stderr)
        path = f'/api/agent/canvases/{args.canvas_id}/commands'
        result = request(args.base_url, path, payload)
        deadline = time.monotonic() + max(0, args.wait)
        while result['status'] in {'queued','running'} and time.monotonic() < deadline:
            time.sleep(min(1, max(0, deadline - time.monotonic())))
            result = request(args.base_url, path + '/' + result['id'])
    print(result if isinstance(result,str) else json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if isinstance(result,dict) and result.get('status') == 'failed' else 0

if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
