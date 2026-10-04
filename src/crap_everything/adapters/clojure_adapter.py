from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from crap_everything.adapters.base import AnalysisOptions, BaseAdapter
from crap_everything.clojure_complexity import SOURCE_SUFFIXES, analyze_file
from crap_everything.models import ProjectReport, UnifiedCrapEntry
from crap_everything.scanner import is_ignored_dir

_PROJECT_FILES = ("deps.edn", "project.clj", "bb.edn", "shadow-cljs.edn", "build.boot")
_REPORT_LINE = re.compile(r"^(\S+)\s+(\S+)\s+(\d+)\s+(N/A|[\d.]+%)\s+(N/A|[\d.]+)\s*$")


class ClojureAdapter(BaseAdapter):
    """Clojure / ClojureScript / Babashka 项目。

    复杂度用移植自 crap4clj 的源码计数，无需 JVM；CRAP 模式调用随附的 crap4clj，
    由它运行项目的 `clj -M:cov --lcov`（Cloverage）取得覆盖率。
    """
    language = "clojure"
    display_name = "Clojure"

    def detect(self, project_path: Path) -> bool:
        return any((project_path / name).is_file() for name in _PROJECT_FILES)

    @staticmethod
    def _crap4clj_dir() -> Path | None:
        repo = Path(__file__).resolve().parents[3] / "crap4clj"
        installed = Path(sys.prefix) / "share" / "crap-everything" / "crap4clj"
        return next((d for d in (repo, installed) if (d / "src" / "crap4clj").is_dir()), None)

    @staticmethod
    def _source_files(root: Path) -> list[Path]:
        files = []
        for directory, dirs, names in os.walk(root):
            dirs[:] = [d for d in dirs if not is_ignored_dir(d)]
            files.extend(Path(directory) / name for name in names if Path(name).suffix in SOURCE_SUFFIXES)
        return sorted(files)

    def _crap_command(self, source_dir: str) -> list[str]:
        crap4clj = self._crap4clj_dir()
        if crap4clj is None:
            raise RuntimeError("未找到随附的 crap4clj 源码，请检查安装是否完整")
        args = ["-m", "crap4clj.core", "-s", source_dir]
        # Babashka 启动快，优先使用；否则走 Clojure CLI 并把 crap4clj 作为本地依赖加入。
        if bb := shutil.which("bb"):
            return [bb, "--classpath", str(crap4clj / "src"), *args]
        if clojure := shutil.which("clojure") or shutil.which("clj"):
            deps = '{:deps {io.github.unclebob/crap4clj {:local/root "%s"}}}' % crap4clj.as_posix()
            return [clojure, "-Sdeps", deps, "-M", *args]
        raise RuntimeError("CRAP 模式需要 Babashka（bb）或 Clojure CLI；只看复杂度请用 crap complexity")

    def _coverage(self, project: Path, source_dir: str, deadline: float) -> dict[tuple[str, str], tuple[float | None, float | None]]:
        remaining = deadline - time.perf_counter()
        if remaining <= 0:
            raise subprocess.TimeoutExpired("crap4clj", 0)
        result = subprocess.run(
            self._crap_command(source_dir), cwd=project, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=remaining,
        )
        lines = result.stdout.splitlines()
        if result.returncode or "CRAP Report" not in lines:
            detail = (result.stderr.strip() + "\n" + result.stdout.strip()).strip()
            raise RuntimeError(f"crap4clj 运行失败 (exit code {result.returncode})，"
                               f"请确认项目已配置 :cov 别名（Cloverage）:\n{detail}")
        coverage = {}
        for line in lines[lines.index("CRAP Report") + 1:]:
            match = _REPORT_LINE.match(line)
            if match:
                name, namespace, _, cov, crap = match.groups()
                coverage[(namespace, name)] = (None if cov == "N/A" else float(cov.rstrip("%")),
                                               None if crap == "N/A" else float(crap))
        return coverage

    def run(self, project_path: Path, options: AnalysisOptions) -> ProjectReport:
        project = project_path.resolve()
        started = time.perf_counter()
        deadline = started + options.timeout
        report = ProjectReport(project.name, str(project), self.language)
        try:
            source_dir = options.src_dir or "src"
            root = (project / source_dir).resolve()
            if not root.is_dir() or not root.is_relative_to(project):
                raise RuntimeError(f"源码目录不存在或不在项目内: {root}")
            files = [p for p in self._source_files(root)
                     if not any(pattern in p.relative_to(project).as_posix() for pattern in options.excludes)
                     and (not options.filters or any(pattern in p.relative_to(project).as_posix() for pattern in options.filters))]
            if options.changed_only:
                from crap_everything.adapters.kotlin_adapter import KotlinAdapter
                changed = KotlinAdapter()._changed_files(project, deadline)
                files = [p for p in files if p.resolve() in changed]
            keys = []
            for path in files:
                namespace, functions = analyze_file(path)
                for function in functions:
                    keys.append((namespace, function.name))
                    report.entries.append(UnifiedCrapEntry(
                        project.name, self.language,
                        f"{namespace}/{function.name}" if namespace else function.name,
                        f"{path.relative_to(project).as_posix()}:{function.start_line}",
                        function.complexity, None, None,
                    ))
            if options.complexity_only or not report.entries:
                report.entries.sort(key=lambda e: -e.complexity)
                return report
            # crap4clj 按命名空间与函数名报告覆盖率，与本地提取的函数一一对应。
            coverage = self._coverage(project, source_dir, deadline)
            for key, entry in zip(keys, report.entries):
                entry.coverage, entry.crap = coverage.get(key, (None, None))
            report.entries.sort(key=lambda e: (e.crap is None, -(e.crap or 0)))
            if any(
                (options.fail_on_crap is not None and e.crap is not None and e.crap >= options.fail_on_crap)
                or (options.fail_on_complexity is not None and e.complexity >= options.fail_on_complexity)
                or (options.fail_on_coverage_below is not None and e.coverage is not None and e.coverage < options.fail_on_coverage_below)
                for e in report.entries
            ):
                report.exit_code = 2
        except subprocess.TimeoutExpired:
            report.exit_code = 1
            report.error_message = f"Clojure 分析超时 ({options.timeout}s)"
        except (OSError, ValueError, RuntimeError, UnicodeDecodeError) as error:
            report.exit_code = 1
            report.error_message = str(error)
        finally:
            report.elapsed_seconds = time.perf_counter() - started
        return report
