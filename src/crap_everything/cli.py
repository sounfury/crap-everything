from __future__ import annotations

import argparse
import sys
from pathlib import Path

from crap_everything.adapters import get_global_registry
from crap_everything.adapters.base import AnalysisOptions
from crap_everything.formatters import (
    format_csv,
    format_json,
    format_markdown,
    format_text,
    format_complexity,
)
from crap_everything.runner import AnalysisRunner
from crap_everything.models import AggregatedReport
from crap_everything.scanner import scan_projects

__version__ = "0.1.0"


def build_parser(complexity_only: bool = False) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="crap complexity" if complexity_only else "crap",
        description="仅分析圈复杂度，不运行测试" if complexity_only else "CRAP Everything: 跨语言、多项目 CRAP 质量度量统一门面工具",
        epilog=None if complexity_only else "仅看复杂度：crap complexity [项目路径]；项目门禁：crap init / crap check / crap hook install",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        default=["."],
        help="待分析的项目根目录或包含多个子项目的目录（默认：当前目录）",
    )
    parser.add_argument(
        "--src",
        type=str,
        default=None,
        help="指定源码目录名称（如 app, src，默认自动推断）",
    )
    parser.add_argument(
        "--output",
        "-o",
        choices=["text", "json", "markdown", "csv"],
        default="text",
        help="输出报告格式 (text, json, markdown, csv，默认: text)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="--output json 的简写",
    )
    parser.add_argument(
        "--markdown",
        action="store_true",
        help="--output markdown 的简写",
    )
    parser.set_defaults(fail_on_crap=None, fail_on_coverage_below=None)
    if not complexity_only:
        parser.add_argument(
            "--fail-on-crap", type=float, default=None,
            help="若任何函数/方法的 CRAP 分数 >= 该阈值，则退出码为 2",
        )
    parser.add_argument(
        "--fail-on-complexity",
        type=int,
        default=None,
        help="若任何函数的圈复杂度 >= 该阈值，则视为超标",
    )
    if not complexity_only:
        parser.add_argument(
            "--fail-on-coverage-below", type=float, default=None,
            help="若任何函数的覆盖率低于该百分比，则视为超标",
        )
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        metavar="FILE",
        help="同时将 JSON 报告导出到该文件；不指定时不写任何文件",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=20,
        help="展示函数列表的最大条目数 (默认: 20，0 表示全部)",
    )
    parser.add_argument(
        "--lang",
        type=str,
        default=None,
        help="强制指定语言适配器 (python, java, kotlin, clojure)",
    )
    parser.add_argument(
        "--recursive",
        "-r",
        action="store_true",
        help="递归扫描目录下的所有子项目",
    )
    parser.add_argument(
        "--changed",
        action="store_true",
        help="仅分析版本控制中变更的代码文件",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="排除包含特定模式的路径（可多次指定）",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="单个项目分析的超时时间（秒，默认: 300）",
    )
    parser.add_argument(
        "--version",
        "-v",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser


def _export_report(path: Path | None, content: str) -> None:
    # 报告只在显式指定 --report 时导出，避免在用户项目里留下文件。
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content + "\n", encoding="utf-8")


def _use_utf8_output() -> None:
    # Windows 上输出到管道（Git Bash、Git 钩子、IDE）时 Python 默认用本地编码（如 GBK），
    # 这些终端按 UTF-8 显示就会乱码；真正的控制台窗口不受影响。
    for stream in (sys.stdout, sys.stderr):
        encoding = (getattr(stream, "encoding", None) or "").lower().replace("-", "")
        if encoding != "utf8" and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def main(args: list[str] | None = None) -> None:
    _use_utf8_output()
    arguments = list(sys.argv[1:] if args is None else args)
    if arguments and arguments[0] in ("init", "check", "hook"):
        from crap_everything.gate import main as gate_main
        sys.exit(gate_main(arguments))
    complexity_only = bool(arguments and arguments[0] == "complexity")
    if complexity_only:
        arguments.pop(0)
    parser = build_parser(complexity_only)
    parsed_args = parser.parse_args(arguments)

    fmt = parsed_args.output
    if parsed_args.json:
        fmt = "json"
    elif parsed_args.markdown:
        fmt = "markdown"

    registry = get_global_registry()
    if parsed_args.lang and registry.get_by_language(parsed_args.lang) is None:
        parser.error(f"不支持的语言: {parsed_args.lang}")
    target_paths = [Path(p) for p in parsed_args.paths]

    targets = scan_projects(
        target_paths=target_paths,
        registry=registry,
        force_lang=parsed_args.lang,
        recursive=parsed_args.recursive,
    )

    if not targets:
        empty_json = (format_complexity(AggregatedReport(), "json") if complexity_only
                      else format_json(AggregatedReport()))
        _export_report(parsed_args.report, empty_json)
        if fmt == "json":
            print(empty_json)
        else:
            print("未在指定路径下检测到受支持的项目 (Java、Python、Kotlin JVM 或 Clojure)", file=sys.stderr)
        sys.exit(0)

    options = AnalysisOptions(
        complexity_only=complexity_only,
        src_dir=parsed_args.src,
        fail_on_crap=parsed_args.fail_on_crap,
        fail_on_complexity=parsed_args.fail_on_complexity,
        fail_on_coverage_below=parsed_args.fail_on_coverage_below,
        changed_only=parsed_args.changed,
        excludes=parsed_args.exclude,
        timeout=parsed_args.timeout,
    )

    runner = AnalysisRunner(options)
    report = runner.run_all(targets)

    top_n = None if parsed_args.top <= 0 else parsed_args.top
    if parsed_args.report:
        _export_report(parsed_args.report,
                       format_complexity(report, "json") if complexity_only else format_json(report))

    if complexity_only:
        print(format_complexity(report, fmt, top_n))
    elif fmt == "json":
        print(format_json(report))
    elif fmt == "markdown":
        print(format_markdown(report, top_n=top_n))
    elif fmt == "csv":
        print(format_csv(report))
    else:
        print(format_text(report, top_n=top_n))

    sys.exit(report.determine_exit_code())


if __name__ == "__main__":
    main()
