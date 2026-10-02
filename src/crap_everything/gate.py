from __future__ import annotations

import argparse
import json
import math
import shlex
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

from crap_everything.adapters import get_global_registry
from crap_everything.adapters.base import AnalysisOptions
from crap_everything.formatters import format_complexity, format_text
from crap_everything.runner import AnalysisRunner
from crap_everything.scanner import scan_projects
from crap_everything.gate_guide import GUIDE_NAME, failure_help, install_guide, print_failure_help

CONFIG_NAME = "crap.toml"
HOOK_TEMPLATE = '''#!/bin/sh
# Managed by crap-everything: pre-commit gate v1
root=$(git rev-parse --show-toplevel) || exit 1
if ! command -v crap >/dev/null 2>&1; then
    echo "CRAP gate: crap command unavailable; install crap-everything and check PATH." >&2
    exit 1
fi
cd "$root" || exit 1
exec crap check --staged --if-changed __PROJECT__
'''


@dataclass
class GateConfig:
    language: str | None
    options: AnalysisOptions
    max_complexity: int | None
    max_crap: float | None
    min_coverage: float | None


def load_config(project: Path) -> GateConfig:
    filename = project / CONFIG_NAME
    if not filename.is_file():
        raise ValueError(f"缺少 {filename}；先运行 crap init，提交门禁还需 git add crap.toml")
    with filename.open("rb") as stream:
        data = tomllib.load(stream)
    allowed = {
        "project": {"language", "src", "exclude", "timeout"},
        "gate": {"mode", "max_complexity", "max_crap", "min_coverage"},
    }
    for section, value in data.items():
        if section not in allowed or not isinstance(value, dict):
            raise ValueError(f"{CONFIG_NAME}: 不支持的配置节 {section}")
        unknown = set(value) - allowed[section]
        if unknown:
            raise ValueError(f"{CONFIG_NAME}: 不支持的配置项 {section}.{sorted(unknown)[0]}")
    project_data, gate = data.get("project", {}), data.get("gate", {})
    language = project_data.get("language")
    if language is not None and language not in ("java", "python", "kotlin"):
        raise ValueError("project.language 必须为 java、python 或 kotlin")
    src = project_data.get("src")
    if src is not None and (not isinstance(src, str) or not src):
        raise ValueError("project.src 必须为非空字符串")
    exclude = project_data.get("exclude", [])
    if not isinstance(exclude, list) or any(not isinstance(p, str) or not p for p in exclude):
        raise ValueError("project.exclude 必须为非空路径字符串的数组")
    timeout = project_data.get("timeout", 300)
    if type(timeout) is not int or timeout <= 0:
        raise ValueError("project.timeout 必须为正整数秒数")
    mode = gate.get("mode", "complexity")
    if mode not in ("complexity", "crap"):
        raise ValueError("gate.mode 必须为 complexity 或 crap")
    for key in ("max_complexity", "max_crap", "min_coverage"):
        value = gate.get(key)
        if value is None:
            continue
        if type(value) not in (int, float) or (type(value) is float and not math.isfinite(value)):
            raise ValueError(f"gate.{key} 必须为有限数值")
        if key == "max_complexity" and (type(value) is not int or value < 1):
            raise ValueError("gate.max_complexity 必须为正整数")
        if key == "max_crap" and value < 1:
            raise ValueError("gate.max_crap 必须 >= 1")
        if key == "min_coverage" and not 0 <= value <= 100:
            raise ValueError("gate.min_coverage 必须在 0 到 100 之间")
    if not any(key in gate for key in ("max_complexity", "max_crap", "min_coverage")):
        raise ValueError("gate 至少需要一个阈值，避免提交门禁没有拦截条件")
    if mode == "complexity" and any(key in gate for key in ("max_crap", "min_coverage")):
        raise ValueError("CRAP / 覆盖率阈值需要 gate.mode = \"crap\"")
    return GateConfig(language, AnalysisOptions(
        src_dir=src, excludes=exclude, timeout=timeout, complexity_only=mode == "complexity",
    ), gate.get("max_complexity"), gate.get("max_crap"), gate.get("min_coverage"))


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                            text=True, encoding="utf-8", errors="replace", timeout=60)
    if result.returncode:
        raise ValueError(result.stderr.strip() or "Git 命令失败")
    return result.stdout.strip()


def _check(project: Path, display_project: Path, as_json: bool) -> int:
    config = load_config(project)
    targets = scan_projects([project], get_global_registry(), force_lang=config.language)
    if not targets:
        raise ValueError("配置的语言未检测到可分析项目，门禁拒绝放行")
    report = AnalysisRunner(config.options).run_all(targets)
    # 暂存区快照的临时路径不出现在用户报告里。
    for item in report.reports:
        relative = Path(item.project_path).relative_to(project)
        original = display_project / relative
        item.project_path, item.project_name = str(original), original.name
        for entry in item.entries:
            entry.project = original.name
    violations = []
    errors = [p.error_message or f"{p.project_name}: 分析失败"
              for p in report.reports if p.exit_code not in (0, 2) or p.error_message]
    if not any(p.entries for p in report.reports):
        errors.append("没有可分析的函数，门禁拒绝放行；请检查源码目录和排除配置")
    for item in report.reports:
        previous_violations, previous_errors = len(violations), len(errors)
        for entry in item.entries:
            label = f"{entry.symbol} ({entry.location})"
            if config.max_complexity is not None and entry.complexity > config.max_complexity:
                violations.append(f"{label}: CC {entry.complexity} > {config.max_complexity}")
            for field, threshold, maximum in (
                ("crap", config.max_crap, True), ("coverage", config.min_coverage, False),
            ):
                if threshold is None:
                    continue
                value = getattr(entry, field)
                if value is None:
                    errors.append(f"{label}: {field} 为 N/A，无法验证门禁阈值")
                elif (value > threshold if maximum else value < threshold):
                    violations.append(f"{label}: {field} {value:.2f} {'>' if maximum else '<'} {threshold}")
        if len(errors) > previous_errors or item.error_message:
            item.exit_code = 1
        elif len(violations) > previous_violations:
            item.exit_code = 2
    code = 1 if errors else 2 if violations else 0
    if as_json:
        data = json.loads(format_complexity(report, "json")) if config.options.complexity_only else report.to_dict()
        data["overall_exit_code"] = code
        data["gate"] = {"passed": code == 0, "violations": violations, "errors": errors}
        if code:
            data["gate"]["help"] = failure_help(display_project)
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(format_complexity(report, "text") if config.options.complexity_only else format_text(report))
        for message in errors + violations:
            print(f"门禁: {message}")
        print("门禁通过" if code == 0 else "门禁未通过，提交已拦截" if code == 2 else "门禁分析失败，拒绝放行")
        if code:
            print_failure_help(display_project)
    return code


def check(project: Path, staged: bool, as_json: bool, if_changed: bool = False) -> int:
    project = project.resolve()
    if not staged:
        return _check(project, project, as_json)
    root = Path(_git(project, "rev-parse", "--show-toplevel")).resolve()
    relative = project.relative_to(root)
    if if_changed and not _git(root, "diff", "--cached", "--name-only", "--",
                               f":(literal){relative.as_posix()}" if relative != Path('.') else "."):
        if as_json:
            print(json.dumps({"overall_exit_code": 0, "gate": {"passed": True, "skipped": True, "violations": [], "errors": []}}))
        else:
            print(f"{project.name} 没有暂存变更，跳过提交门禁")
        return 0
    # 不 stash、不改 index/工作区；checkout-index 导出即将提交的完整内容。
    # 有冲突时 checkout-index 返回失败，门禁拒绝放行。
    with tempfile.TemporaryDirectory(prefix="crap-staged-") as directory:
        snapshot = Path(directory)
        _git(root, "checkout-index", "--all", f"--prefix={snapshot.as_posix()}/")
        return _check(snapshot / relative, project, as_json)


def install_hook(project: Path) -> Path:
    project = project.resolve()
    root = Path(_git(project, "rev-parse", "--show-toplevel")).resolve()
    load_config(project)
    content = HOOK_TEMPLATE.replace("__PROJECT__", shlex.quote(project.relative_to(root).as_posix()))
    hook = Path(_git(root, "rev-parse", "--git-path", "hooks/pre-commit"))
    if not hook.is_absolute():
        hook = root / hook
    if hook.exists() or hook.is_symlink():
        if hook.is_symlink() or hook.read_text(encoding="utf-8") != content:
            raise ValueError(f"已有 pre-commit 钩子，未覆盖：{hook}；请在现有钩子中接入 crap check --staged")
    else:
        hook.parent.mkdir(parents=True, exist_ok=True)
        with hook.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
    hook.chmod(hook.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    created = install_guide(project)
    print(f"{'已安装' if created else '已保留现有'}门禁说明：{project / GUIDE_NAME}")
    return hook


def main(arguments: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="crap", description="项目配置与 Git 提交门禁")
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="创建 crap.toml，不覆盖已有配置")
    init.add_argument("path", nargs="?", default=".")
    init.add_argument("--lang", choices=["java", "python", "kotlin"])
    init.add_argument("--max-complexity", type=int, default=12, help="最高允许复杂度（默认 12）")
    checking = commands.add_parser("check", help="按 crap.toml 执行门禁")
    checking.add_argument("path", nargs="?", default=".")
    checking.add_argument("--staged", action="store_true", help="分析暂存区的完整快照，包括配置文件")
    checking.add_argument("--if-changed", action="store_true", help="与 --staged 一起使用，项目无暂存变更时跳过")
    checking.add_argument("--json", action="store_true")
    hooks = commands.add_parser("hook", help="管理 Git 钩子")
    hooks.add_argument("action", choices=["install"])
    hooks.add_argument("path", nargs="?", default=".")
    args = parser.parse_args(arguments)
    project = Path(args.path).resolve()
    try:
        if args.command == "check":
            if args.if_changed and not args.staged:
                raise ValueError("--if-changed 必须与 --staged 一起使用")
            return check(project, args.staged, args.json, args.if_changed)
        if args.command == "hook":
            print(f"已安装提交门禁：{install_hook(project)}")
            print(f"请将 crap.toml 和 {GUIDE_NAME} 一起提交；每个克隆需单独安装钩子。")
            return 0
        if args.max_complexity < 1:
            raise ValueError("--max-complexity 必须为正整数")
        language = args.lang
        if language is None:
            adapter = get_global_registry().detect(project)
            language = adapter.language if adapter else None
        if language is None:
            raise ValueError("无法识别项目语言，请使用 --lang java/python/kotlin")
        config = project / CONFIG_NAME
        with config.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(f'''[project]
language = "{language}"
exclude = []
timeout = 300

[gate]
mode = "complexity"
max_complexity = {args.max_complexity}
''')
        print(f"已创建 {config}；复杂度 <= {args.max_complexity} 通过。")
        return 0
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        if args.command == "check" and args.json:
            print(json.dumps({"overall_exit_code": 1, "gate": {"passed": False, "violations": [], "errors": [str(error)], "help": failure_help(project)}}, ensure_ascii=False))
        else:
            print(f"门禁错误: {error}", file=sys.stderr)
            if args.command == "check":
                print_failure_help(project)
        return 1
