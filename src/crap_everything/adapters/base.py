from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

from crap_everything.models import ProjectReport


@dataclass
class AnalysisOptions:
    # 源码所在子目录（例如 src, app 等），若未指定则由适配器智能推断
    src_dir: str | None = None

    # 失败门禁阈值
    fail_on_crap: float | None = None
    fail_on_complexity: int | None = None
    fail_on_coverage_below: float | None = None

    # 是否仅分析变更文件
    changed_only: bool = False

    # 包含过滤项与排除模式
    filters: list[str] = field(default_factory=list)
    excludes: list[str] = field(default_factory=list)

    # 分析超时时间（秒）
    timeout: int = 300

    # 仅度量复杂度，不运行测试。
    complexity_only: bool = False


class BaseAdapter(ABC):
    # 语言标识，如 "python", "java"
    language: str = "unknown"
    # 显示名称
    display_name: str = "Unknown Language"

    def owns_subprojects(self, project_path: Path) -> bool:
        # 构建根目录是否需要统一分析其模块，默认仍逐个发现子项目。
        return False

    @abstractmethod
    def detect(self, project_path: Path) -> bool:
        # 探测给定目录是否符合该语言的项目结构
        pass

    @abstractmethod
    def run(self, project_path: Path, options: AnalysisOptions) -> ProjectReport:
        # 执行度量分析并返回统一格式的项目报告
        pass
