#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from project_storage import ProjectStorage, StorageError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="无限画布数据管理工具")
    parser.add_argument("--root", default=str(PROJECT_ROOT), help="项目根目录，默认使用当前项目")
    subparsers = parser.add_subparsers(dest="command", required=True)

    status = subparsers.add_parser("status", help="查看目录、素材和生成结果状态")
    status.add_argument("--json", action="store_true", help="输出 JSON")

    migrate = subparsers.add_parser("migrate", help="把旧目录数据迁移到新结构")
    migrate.add_argument("--cleanup", action="store_true", help="迁移成功后清理已确认复用的旧文件")
    migrate.add_argument("--json", action="store_true", help="输出 JSON")

    backup = subparsers.add_parser("backup", help="创建项目数据备份")
    backup.add_argument("--output", help="指定备份 ZIP 路径")
    backup.add_argument("--include-secrets", action="store_true", help="把 API/.env 一并备份")
    backup.add_argument("--json", action="store_true", help="输出 JSON")

    restore = subparsers.add_parser("restore", help="从备份 ZIP 恢复项目数据")
    restore.add_argument("archive", help="备份 ZIP 路径")
    restore.add_argument("--no-safety-backup", action="store_true", help="恢复前不创建当前数据的安全备份")
    restore.add_argument("--json", action="store_true", help="输出 JSON")
    return parser


def print_result(payload: dict, as_json: bool, title: str) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False))
        return
    print(title)
    for key, value in payload.items():
        print(f"- {key}: {value}")


def run(args: argparse.Namespace) -> dict:
    storage = ProjectStorage(Path(args.root).expanduser().resolve())
    if args.command == "status":
        return storage.status()
    if args.command == "migrate":
        return storage.migrate_legacy(cleanup=args.cleanup)
    if args.command == "backup":
        archive = storage.create_backup(args.output, include_secrets=args.include_secrets)
        return {"ok": True, "path": str(archive), "include_secrets": bool(args.include_secrets)}
    if args.command == "restore":
        return storage.restore_backup(args.archive, create_safety_backup=not args.no_safety_backup)
    raise StorageError("未知命令")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = run(args)
    except (StorageError, OSError, ValueError) as exc:
        print(f"数据操作失败：{exc}", file=sys.stderr)
        return 1
    titles = {
        "status": "当前数据状态",
        "migrate": "数据迁移完成",
        "backup": "数据备份完成",
        "restore": "数据恢复完成",
    }
    print_result(result, bool(getattr(args, "json", False)), titles[args.command])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
