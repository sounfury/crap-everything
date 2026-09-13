from __future__ import annotations

from pathlib import Path
from typing import Type

from crap_everything.adapters.base import BaseAdapter


class AdapterRegistry:
    def __init__(self) -> None:
        self._adapters: list[BaseAdapter] = []

    def register(self, adapter: BaseAdapter) -> None:
        # 避免重复注册同名语言适配器
        self._adapters = [a for a in self._adapters if a.language != adapter.language]
        self._adapters.append(adapter)

    def get_by_language(self, language: str) -> BaseAdapter | None:
        lang_lower = language.strip().lower()
        for adapter in self._adapters:
            if adapter.language.lower() == lang_lower:
                return adapter
        return None

    def detect(self, project_path: Path) -> BaseAdapter | None:
        # 按注册顺序依次尝试探测
        for adapter in self._adapters:
            if adapter.detect(project_path):
                return adapter
        return None

    def list_adapters(self) -> list[BaseAdapter]:
        return list(self._adapters)


# 全局默认单例注册中心
_global_registry = AdapterRegistry()


def get_global_registry() -> AdapterRegistry:
    return _global_registry
