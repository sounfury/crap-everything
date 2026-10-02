from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path

from crap_everything.adapters.base import AnalysisOptions, BaseAdapter
from crap_everything.models import ProjectReport, UnifiedCrapEntry


class JavaAdapter(BaseAdapter):
    language = "java"
    display_name = "Java"

    # 正则匹配 crap4java 报告中的数据行：Method, Class, CC, Cov%, CRAP
    _REPORT_LINE_PATTERN = re.compile(
        r"^(?P<method>[a-zA-Z0-9_$<>]+)\s+"
        r"(?P<class>[a-zA-Z0-9_$.]+)\s+"
        r"(?P<cc>\d+)\s+"
        r"(?P<cov>[\d\.]+%|N/A)\s+"
        r"(?P<crap>[\d\.]+|N/A)\s*$"
    )

    def detect(self, project_path: Path) -> bool:
        indicators = ["pom.xml", "build.gradle", "build.gradle.kts"]
        if any((project_path / ind).exists() for ind in indicators):
            return True

        src_dir = project_path / "src"
        if src_dir.is_dir() and any(src_dir.glob("**/*.java")):
            return True

        return False

    def _locate_or_build_jar(self, repo_root: Path) -> Path | None:
        crap4java_dir = repo_root / "crap4java"
        if not crap4java_dir.exists():
            crap4java_dir = Path(sys.prefix) / "share" / "crap-everything" / "crap4java"
            if not crap4java_dir.exists():
                return None

        target_dir = crap4java_dir / "target"
        jar_path = target_dir / "crap4java-0.1.0-SNAPSHOT.jar"
        java_files = list((crap4java_dir / "src" / "crap4java").glob("*.java"))
        if jar_path.exists() and all(f.stat().st_mtime_ns <= jar_path.stat().st_mtime_ns for f in java_files):
            return jar_path

        # 若 jar 不存在，利用 javac 和 jar 工具进行快速打包
        classes_dir = target_dir / "classes"
        classes_dir.mkdir(parents=True, exist_ok=True)
        java_files = list((crap4java_dir / "src" / "crap4java").glob("*.java"))
        if not java_files:
            return None

        try:
            # 编译源代码
            javac_cmd = ["javac", "-encoding", "UTF-8", "-d", str(classes_dir)] + [str(f) for f in java_files]
            res = subprocess.run(javac_cmd, capture_output=True, text=True)
            if res.returncode != 0:
                return None

            # 创建包含主类清单的可执行 jar
            manifest_file = target_dir / "MANIFEST.MF"
            manifest_file.write_text("Main-Class: crap4java.Main\n", encoding="utf-8")

            jar_cmd = [
                "jar",
                "cfm",
                str(jar_path),
                str(manifest_file),
                "-C",
                str(classes_dir),
                ".",
            ]
            res_jar = subprocess.run(jar_cmd, capture_output=True, text=True)
            if res_jar.returncode == 0 and jar_path.exists():
                return jar_path
        except Exception:
            return None

        return None

    def run(self, project_path: Path, options: AnalysisOptions) -> ProjectReport:
        if options.complexity_only:
            from crap_everything.source_complexity import analyze_source_complexity
            return analyze_source_complexity(project_path, options, self.language)
        start_time = time.perf_counter()
        project_name = project_path.name

        repo_root = Path(__file__).resolve().parent.parent.parent.parent
        jar_path = self._locate_or_build_jar(repo_root)

        if not jar_path or not jar_path.exists():
            elapsed = time.perf_counter() - start_time
            return ProjectReport(
                project_name=project_name,
                project_path=str(project_path),
                language=self.language,
                exit_code=1,
                error_message="未能构建或找到 crap4java.jar 可执行包",
                elapsed_seconds=elapsed,
            )

        cmd = ["java", "-jar", str(jar_path)]
        if options.changed_only:
            cmd.append("--changed")
        if options.filters:
            cmd.extend(options.filters)

        try:
            res = subprocess.run(
                cmd,
                cwd=str(project_path),
                capture_output=True,
                text=True,
                timeout=options.timeout,
            )
            stdout = res.stdout
            stderr = res.stderr
            return_code = res.returncode
        except subprocess.TimeoutExpired:
            elapsed = time.perf_counter() - start_time
            return ProjectReport(
                project_name=project_name,
                project_path=str(project_path),
                language=self.language,
                exit_code=1,
                error_message=f"Java 分析超时 ({options.timeout}s)",
                elapsed_seconds=elapsed,
            )
        except Exception as ex:
            elapsed = time.perf_counter() - start_time
            return ProjectReport(
                project_name=project_name,
                project_path=str(project_path),
                language=self.language,
                exit_code=1,
                error_message=f"执行异常: {ex}",
                elapsed_seconds=elapsed,
            )

        elapsed = time.perf_counter() - start_time
        entries: list[UnifiedCrapEntry] = []

        for line in stdout.splitlines():
            line_str = line.strip()
            if not line_str or line_str.startswith("CRAP Report") or line_str.startswith("=") or line_str.startswith("-") or line_str.startswith("Method"):
                continue

            match = self._REPORT_LINE_PATTERN.match(line_str)
            if match:
                method_name = match.group("method")
                class_name = match.group("class")
                complexity = int(match.group("cc"))
                cov_str = match.group("cov")
                crap_str = match.group("crap")

                coverage = None
                if cov_str != "N/A":
                    try:
                        coverage = float(cov_str.rstrip("%"))
                    except ValueError:
                        coverage = None

                crap_score = None
                if crap_str != "N/A":
                    try:
                        crap_score = float(crap_str)
                    except ValueError:
                        crap_score = None

                entries.append(
                    UnifiedCrapEntry(
                        project=project_name,
                        language=self.language,
                        symbol=method_name,
                        location=class_name,
                        complexity=complexity,
                        coverage=coverage,
                        crap=crap_score,
                    )
                )

        error_msg = None
        # 如果返回码不为 0 且不为 2 (2 为 crap4java 的阈值超标退出码)
        if return_code not in (0, 2):
            error_msg = stderr.strip() or stdout.strip() or f"crap4java 异常退出 (exit code {return_code})"

        return ProjectReport(
            project_name=project_name,
            project_path=str(project_path),
            language=self.language,
            entries=entries,
            exit_code=return_code,
            error_message=error_msg,
            elapsed_seconds=elapsed,
        )
