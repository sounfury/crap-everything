from __future__ import annotations

import os
from pathlib import Path

from crap_everything.adapters.base import BaseAdapter
from crap_everything.adapters.registry import AdapterRegistry

# 默认跳过的非项目或构建输出目录
DEFAULT_IGNORED_DIRS = {
    ".git",
    ".svn",
    ".hg",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "target",
    "dist",
    "build",
    "__pycache__",
    ".pytest_cache",
    ".idea",
    ".vscode",
}


def is_ignored_dir(name: str) -> bool:
    return name in DEFAULT_IGNORED_DIRS or name.startswith(".")


def scan_projects(
    target_paths: list[Path],
    registry: AdapterRegistry,
    force_lang: str | None = None,
    recursive: bool = False,
) -> list[tuple[Path, BaseAdapter]]:
    # 发现并返回 (项目路径, 对应适配器) 列表
    results: list[tuple[Path, BaseAdapter]] = []
    seen_paths: set[Path] = set()

    for raw_path in target_paths:
        path = raw_path.resolve()
        if not path.is_dir():
            continue

        # 若强制指定语言
        if force_lang:
            adapter = registry.get_by_language(force_lang)
            if adapter and adapter.detect(path):
                if path not in seen_paths:
                    seen_paths.add(path)
                    results.append((path, adapter))
                continue

        # 检查当前目录是否包含多个子项目（如 monorepo 根目录）
        sub_projects: list[tuple[Path, BaseAdapter]] = []
        try:
            for child in sorted(path.iterdir()):
                if child.is_dir() and not is_ignored_dir(child.name):
                    child_adapter = registry.detect(child)
                    if child_adapter:
                        sub_projects.append((child, child_adapter))
        except (PermissionError, OSError):
            pass

        if sub_projects:
            # 如果存在子项目，优先将子项目作为独立分析目标
            for sub_p, sub_a in sub_projects:
                if sub_p not in seen_paths:
                    seen_paths.add(sub_p)
                    results.append((sub_p, sub_a))
        else:
            # 否则尝试检测当前目录本身
            adapter = registry.detect(path)
            if adapter:
                if path not in seen_paths:
                    seen_paths.add(path)
                    results.append((path, adapter))

        # 若启用深度递归
        if recursive:
            for root, dirs, _ in os.walk(path):
                # 原地过滤忽略目录
                dirs[:] = [d for d in dirs if not is_ignored_dir(d)]
                for d in dirs:
                    curr = (Path(root) / d).resolve()
                    if curr not in seen_paths:
                        curr_adapter = registry.detect(curr)
                        if curr_adapter:
                            seen_paths.add(curr)
                            results.append((curr, curr_adapter))

    return results
