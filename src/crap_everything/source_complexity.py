from __future__ import annotations

import ast
import os
import re
import subprocess
import time
import tokenize
from pathlib import Path

from crap_everything.adapters.base import AnalysisOptions
from crap_everything.adapters.kotlin_adapter import KotlinAdapter, _IGNORED_DIRS
from crap_everything.models import ProjectReport, UnifiedCrapEntry
from crap_everything.kotlin_complexity import SourceFunction


def _decisions(node: ast.AST) -> int:
    count = 0
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if isinstance(child, (ast.If, ast.IfExp, ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler)):
            count += 1
        elif isinstance(child, ast.BoolOp):
            count += len(child.values) - 1
        elif isinstance(child, ast.comprehension):
            count += len(child.ifs)
        elif isinstance(child, ast.match_case):
            count += 1
        count += _decisions(child)
    return count


def _python_entries(project: Path, files: list[Path]) -> list[UnifiedCrapEntry]:
    entries = []
    for path in files:
        with tokenize.open(path) as stream:
            tree = ast.parse(stream.read(), filename=str(path))
        functions = []
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append((node.name, node))
            elif isinstance(node, ast.ClassDef):
                functions.extend((f"{node.name}.{item.name}", item) for item in node.body
                                 if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)))
        for name, function in functions:
            entries.append(UnifiedCrapEntry(
                project.name, "python", name,
                f"{path.relative_to(project).as_posix()}:{function.lineno}",
                1 + _decisions(function), None, None,
            ))
    return entries


def java_source_functions(project: Path, files: list[Path], deadline: float) -> list[SourceFunction]:
    """复用 Java AST 解析器，返回源码方法和起止行，不运行目标项目构建。"""
    if not files:
        return []
    from crap_everything.adapters.java_adapter import JavaAdapter
    import tempfile
    repo = Path(__file__).resolve().parents[2]
    jar = JavaAdapter()._locate_or_build_jar(repo)
    if jar is None:
        raise RuntimeError("未找到或无法构建 crap4java.jar，请检查 JDK")
    with tempfile.TemporaryDirectory(prefix="crap-java-complexity-") as temp:
        file_list = Path(temp) / "sources.txt"
        file_list.write_text('\n'.join(str(p) for p in sorted(files)), encoding="utf-8")
        result = KotlinAdapter._invoke([
            "java", "-cp", str(jar), "crap4java.ComplexityMain", str(file_list),
        ], project, deadline)
    functions = []
    for line in result.stdout.splitlines():
        cc, start_line, end_line, symbol, filename = line.split('\t', 4)
        source = Path(filename)
        package = re.search(r"^\s*package\s+([\w.]+)\s*;", source.read_text(encoding="utf-8-sig"), re.MULTILINE)
        functions.append(SourceFunction(
            source, package.group(1) if package else "", symbol,
            int(start_line), int(start_line), int(end_line), int(cc),
        ))
    return functions


def analyze_source_complexity(project_path: Path, options: AnalysisOptions, language: str) -> ProjectReport:
    project = project_path.resolve()
    start = time.perf_counter()
    report = ProjectReport(project.name, str(project), language)
    try:
        if language == "python":
            from crap_everything.adapters.python_adapter import PythonAdapter
            source_dir = PythonAdapter()._resolve_src_dir(project, options)
        else:
            source_dir = options.src_dir or "src"
        root = (project / source_dir).resolve()
        if not root.is_dir() or not root.is_relative_to(project):
            raise RuntimeError(f"源码目录不存在或不在项目内: {root}")
        suffix = ".py" if language == "python" else ".java"
        files = []
        for directory, dirs, names in os.walk(root):
            dirs[:] = [d for d in dirs if d not in _IGNORED_DIRS and not d.startswith('.')]
            for name in names:
                path = Path(directory) / name
                relative = path.relative_to(project).as_posix()
                if path.suffix == suffix and not any(p in relative for p in options.excludes):
                    if not options.filters or any(p in relative for p in options.filters):
                        files.append(path)
        deadline = start + options.timeout
        if options.changed_only:
            changed = KotlinAdapter()._changed_files(project, deadline)
            files = [p for p in files if p.resolve() in changed]
        if language == "python":
            report.entries = _python_entries(project, sorted(files))
        elif files:
            for function in java_source_functions(project, files, deadline):
                report.entries.append(UnifiedCrapEntry(
                    project.name, "java", function.symbol,
                    f"{function.source.relative_to(project).as_posix()}:{function.start_line}",
                    function.complexity, None, None,
                ))
        report.entries.sort(key=lambda e: -e.complexity)
    except subprocess.TimeoutExpired:
        report.exit_code = 1
        report.error_message = f"复杂度分析超时 ({options.timeout}s)"
    except (OSError, ValueError, RuntimeError, SyntaxError) as error:
        report.exit_code = 1
        report.error_message = str(error)
    finally:
        report.elapsed_seconds = time.perf_counter() - start
    return report
