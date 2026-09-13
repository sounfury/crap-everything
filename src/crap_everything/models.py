from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class UnifiedCrapEntry:
    # 所属项目标识
    project: str
    # 编程语言（如 python, java）
    language: str
    # 方法或函数名
    symbol: str
    # 所在类、模块或文件路径
    location: str
    # 圈复杂度 CC
    complexity: int
    # 覆盖率百分比 (0.0 ~ 100.0)，若无数据则为 None
    coverage: float | None
    # CRAP 分数，若无数据则为 None
    crap: float | None

    @property
    def risk_level(self) -> str:
        # 计算风险等级：<=5 较低，5~30 中等，>30 高风险
        if self.crap is None:
            return "UNKNOWN"
        if self.crap <= 5.0:
            return "LOW"
        if self.crap <= 30.0:
            return "MODERATE"
        return "HIGH"

    def to_dict(self) -> dict[str, Any]:
        return {
            "project": self.project,
            "language": self.language,
            "symbol": self.symbol,
            "location": self.location,
            "complexity": self.complexity,
            "coverage": round(self.coverage, 2) if self.coverage is not None else None,
            "crap": round(self.crap, 2) if self.crap is not None else None,
            "risk_level": self.risk_level,
        }


@dataclass
class ProjectReport:
    # 项目名称
    project_name: str
    # 项目根目录绝对或相对路径
    project_path: str
    # 识别的编程语言
    language: str
    # 解析出的方法度量列表
    entries: list[UnifiedCrapEntry] = field(default_factory=list)
    # 底层执行返回码
    exit_code: int = 0
    # 错误或异常信息
    error_message: str | None = None
    # 执行耗时（秒）
    elapsed_seconds: float = 0.0

    @property
    def total_methods(self) -> int:
        return len(self.entries)

    @property
    def max_crap(self) -> float | None:
        valid_scores = [e.crap for e in self.entries if e.crap is not None]
        return max(valid_scores) if valid_scores else None

    @property
    def avg_crap(self) -> float | None:
        valid_scores = [e.crap for e in self.entries if e.crap is not None]
        return (sum(valid_scores) / len(valid_scores)) if valid_scores else None

    @property
    def high_risk_count(self) -> int:
        return sum(1 for e in self.entries if e.crap is not None and e.crap > 30.0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_name": self.project_name,
            "project_path": self.project_path,
            "language": self.language,
            "total_methods": self.total_methods,
            "max_crap": round(self.max_crap, 2) if self.max_crap is not None else None,
            "avg_crap": round(self.avg_crap, 2) if self.avg_crap is not None else None,
            "high_risk_count": self.high_risk_count,
            "exit_code": self.exit_code,
            "error_message": self.error_message,
            "elapsed_seconds": round(self.elapsed_seconds, 3),
            "entries": [e.to_dict() for e in self.entries],
        }


@dataclass
class AggregatedReport:
    # 各子项目的报告集合
    reports: list[ProjectReport] = field(default_factory=list)
    # 用户指定的 CRAP 失败阈值
    fail_on_crap: float | None = None

    @property
    def total_projects(self) -> int:
        return len(self.reports)

    @property
    def total_methods(self) -> int:
        return sum(r.total_methods for r in self.reports)

    @property
    def global_max_crap(self) -> float | None:
        max_scores = [r.max_crap for r in self.reports if r.max_crap is not None]
        return max(max_scores) if max_scores else None

    @property
    def global_high_risk_count(self) -> int:
        return sum(r.high_risk_count for r in self.reports)

    def all_sorted_entries(self) -> list[UnifiedCrapEntry]:
        # 汇总所有函数并按 CRAP 降序排列，N/A 沉底
        all_entries: list[UnifiedCrapEntry] = []
        for report in self.reports:
            all_entries.extend(report.entries)
        return sorted(
            all_entries,
            key=lambda e: (e.crap is None, -(e.crap if e.crap is not None else 0.0)),
        )

    def top_entries(self, n: int | None = None) -> list[UnifiedCrapEntry]:
        sorted_list = self.all_sorted_entries()
        if n is not None and n > 0:
            return sorted_list[:n]
        return sorted_list

    def determine_exit_code(self) -> int:
        # 1. 优先检查是否超过指定的 fail_on_crap 阈值
        if self.fail_on_crap is not None:
            for entry in self.all_sorted_entries():
                if entry.crap is not None and entry.crap >= self.fail_on_crap:
                    return 2

        # 2. 检查是否有底层工具直接报告阈值超标 (crap4java exit_code == 2)
        if any(r.exit_code == 2 for r in self.reports):
            return 2

        # 3. 检查是否有执行错误（比如无有效 entries 且 exit_code != 0，或有明显 error_message）
        for r in self.reports:
            if r.exit_code != 0 and (not r.entries or r.error_message):
                return 1

        return 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_projects": self.total_projects,
            "total_methods": self.total_methods,
            "global_max_crap": round(self.global_max_crap, 2) if self.global_max_crap is not None else None,
            "global_high_risk_count": self.global_high_risk_count,
            "fail_on_crap_threshold": self.fail_on_crap,
            "overall_exit_code": self.determine_exit_code(),
            "projects": [r.to_dict() for r in self.reports],
        }
