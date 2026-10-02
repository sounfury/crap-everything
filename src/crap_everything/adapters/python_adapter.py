from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from crap_everything.adapters.base import AnalysisOptions, BaseAdapter
from crap_everything.models import ProjectReport, UnifiedCrapEntry


class PythonAdapter(BaseAdapter):
    language = "python"
    display_name = "Python"

    def detect(self, project_path: Path) -> bool:
        indicators = [
            "pyproject.toml",
            "setup.py",
            "setup.cfg",
            "requirements.txt",
            "Pipfile",
            "poetry.lock",
        ]
        if any((project_path / ind).exists() for ind in indicators):
            return True

        # 如果存在 src 且包含 .py 文件
        src_dir = project_path / "src"
        if src_dir.is_dir() and any(src_dir.glob("**/*.py")):
            return True

        return False

    def _resolve_python_executable(self, project_path: Path) -> str:
        # 优先探测子项目内自带的虚拟环境
        candidates = [
            project_path / ".venv" / "Scripts" / "python.exe",
            project_path / ".venv" / "bin" / "python",
            project_path / "venv" / "Scripts" / "python.exe",
            project_path / "venv" / "bin" / "python",
        ]
        for c in candidates:
            if c.is_file():
                return str(c)
        return sys.executable

    def _resolve_src_dir(self, project_path: Path, options: AnalysisOptions) -> str:
        if options.src_dir:
            return options.src_dir
        if (project_path / "src").is_dir():
            return "src"
        if (project_path / "app").is_dir():
            return "app"

        # 扫描包含 __init__.py 的主要包目录
        ignored = {"tests", "test", ".venv", "venv", "env", "build", "dist"}
        for child in project_path.iterdir():
            if child.is_dir() and child.name not in ignored and not child.name.startswith("."):
                if (child / "__init__.py").exists():
                    return child.name

        return "src"

    def run(self, project_path: Path, options: AnalysisOptions) -> ProjectReport:
        if options.complexity_only:
            from crap_everything.source_complexity import analyze_source_complexity
            return analyze_source_complexity(project_path, options, self.language)
        start_time = time.perf_counter()
        project_name = project_path.name

        python_bin = self._resolve_python_executable(project_path)
        src_dir = self._resolve_src_dir(project_path, options)
        cmd = [python_bin, "-m", "crap4py", "--json", "--src", src_dir]

        if options.fail_on_crap is not None:
            cmd.extend(["--fail-on-crap", str(options.fail_on_crap)])
        if options.fail_on_complexity is not None:
            cmd.extend(["--fail-on-complexity", str(options.fail_on_complexity)])
        if options.fail_on_coverage_below is not None:
            cmd.extend(["--fail-on-coverage-below", str(options.fail_on_coverage_below)])
        if options.timeout:
            cmd.extend(["--timeout", str(options.timeout)])
        for exc in options.excludes:
            cmd.extend(["--exclude", exc])
        if options.filters:
            cmd.extend(options.filters)

        # 保证 crap4py 源码目录可被当前 python 解释器定位，并强制 Python 使用 UTF-8 模式
        env = dict(os.environ)
        env["PYTHONUTF8"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        repo_root = Path(__file__).resolve().parent.parent.parent.parent
        crap4py_src = repo_root / "crap4py" / "src"
        current_pythonpath = env.get("PYTHONPATH", "")
        paths = [str(crap4py_src)]
        if current_pythonpath:
            paths.append(current_pythonpath)
        env["PYTHONPATH"] = os.pathsep.join(paths)

        def _invoke(command_args: list[str]) -> tuple[int, str, str]:
            res = subprocess.run(
                command_args,
                cwd=str(project_path),
                capture_output=True,
                text=True,
                timeout=options.timeout,
                env=env,
            )
            return res.returncode, res.stdout.strip(), res.stderr.strip()

        try:
            return_code, stdout, stderr = _invoke(cmd)
            # 如果默认运行返回错误且没有包含有效 JSON，尝试使用 unittest runner 回退
            if return_code != 0 and not stdout.startswith("{"):
                fallback_cmd = list(cmd) + ["--runner", "unittest"]
                fb_code, fb_out, fb_err = _invoke(fallback_cmd)
                if fb_code == 0 or fb_out.startswith("{"):
                    return_code, stdout, stderr = fb_code, fb_out, fb_err
        except subprocess.TimeoutExpired:
            elapsed = time.perf_counter() - start_time
            return ProjectReport(
                project_name=project_name,
                project_path=str(project_path),
                language=self.language,
                exit_code=1,
                error_message=f"Python 分析超时 ({options.timeout}s)",
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
        error_msg = None

        # 尝试解析输出中的 JSON
        json_obj = None
        if stdout:
            try:
                json_obj = json.loads(stdout)
            except json.JSONDecodeError:
                # 兼容部分场景日志夹杂在 stdout 中的情况，提取首个有效 json 块
                json_start = stdout.find("{")
                json_end = stdout.rfind("}")
                if json_start != -1 and json_end != -1 and json_end > json_start:
                    try:
                        json_obj = json.loads(stdout[json_start : json_end + 1])
                    except json.JSONDecodeError:
                        pass

        if json_obj and "entries" in json_obj:
            for item in json_obj["entries"]:
                entries.append(
                    UnifiedCrapEntry(
                        project=project_name,
                        language=self.language,
                        symbol=item.get("name", "unknown"),
                        location=item.get("module", ""),
                        complexity=int(item.get("complexity", 1)),
                        coverage=float(item.get("coverage", 0.0)) if item.get("coverage") is not None else None,
                        crap=float(item.get("crap", 0.0)) if item.get("crap") is not None else None,
                    )
                )
        else:
            if return_code != 0:
                error_msg = stderr or stdout or "crap4py 执行失败"

        return ProjectReport(
            project_name=project_name,
            project_path=str(project_path),
            language=self.language,
            entries=entries,
            exit_code=return_code,
            error_message=error_msg,
            elapsed_seconds=elapsed,
        )
