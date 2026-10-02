from __future__ import annotations

import csv
import io
import json
from typing import Any

from crap_everything.models import AggregatedReport, UnifiedCrapEntry


def format_text(report: AggregatedReport, top_n: int | None = 20) -> str:
    lines: list[str] = []

    # 1. 项目摘要表格
    lines.append("CRAP Everything - Multi-Project Summary")
    lines.append("=" * 88)
    header = f"{'Project':<20} {'Language':<10} {'Methods':>8} {'Max CRAP':>10} {'Avg CRAP':>10} {'High Risk(>30)':>15} {'Status':>8}"
    lines.append(header)
    lines.append("-" * 88)

    for p in report.reports:
        max_c = f"{p.max_crap:.1f}" if p.max_crap is not None else "N/A"
        avg_c = f"{p.avg_crap:.1f}" if p.avg_crap is not None else "N/A"
        
        # 判定项目状态
        if p.error_message or (p.exit_code != 0 and not p.entries):
            status = "FAILED"
        elif report.fail_on_crap is not None and p.max_crap is not None and p.max_crap >= report.fail_on_crap:
            status = "VIOLATION"
        elif p.exit_code == 2:
            status = "VIOLATION"
        else:
            status = "PASSED"

        lines.append(
            f"{p.project_name:<20} {p.language:<10} {p.total_methods:>8} {max_c:>10} {avg_c:>10} {p.high_risk_count:>15} {status:>8}"
        )
        if p.error_message:
            lines.append(f"  [Error] {p.error_message}")

    lines.append("=" * 88)
    lines.append("")

    # 2. 跨项目高危函数 Top 清单
    entries = report.top_entries(top_n)
    if entries:
        title_suffix = f" (Top {len(entries)})" if top_n else ""
        lines.append(f"Worst Risk Functions / Methods{title_suffix}")
        lines.append("=" * 105)
        detail_header = f"{'Symbol':<28} {'Project':<16} {'CC':>4} {'Cov%':>8} {'CRAP':>8} {'Risk':>9} {'Location'}"
        lines.append(detail_header)
        lines.append("-" * 105)

        for e in entries:
            cov_str = f"{e.coverage:.1f}%" if e.coverage is not None else "N/A"
            crap_str = f"{e.crap:.1f}" if e.crap is not None else "N/A"
            lines.append(
                f"{e.symbol:<28} {e.project:<16} {e.complexity:>4} {cov_str:>8} {crap_str:>8} {e.risk_level:>9} {e.location}"
            )
        lines.append("-" * 105)
    else:
        lines.append("No analyzed methods found.")

    lines.append("")
    # 3. 总体统计
    global_max = f"{report.global_max_crap:.1f}" if report.global_max_crap is not None else "N/A"
    overall_status = "PASSED" if report.determine_exit_code() == 0 else "FAILED"
    lines.append(
        f"Summary: {report.total_projects} projects, {report.total_methods} methods | "
        f"Global Max CRAP: {global_max} | High Risk: {report.global_high_risk_count} | Result: {overall_status}"
    )

    return "\n".join(lines)


def format_json(report: AggregatedReport) -> str:
    return json.dumps(report.to_dict(), indent=2, ensure_ascii=False)


def format_markdown(report: AggregatedReport, top_n: int | None = 20) -> str:
    lines: list[str] = []
    lines.append("# CRAP Multi-Project Analysis Report\n")

    # 概览表
    lines.append("## Project Summary\n")
    lines.append("| Project | Language | Total Methods | Max CRAP | Avg CRAP | High Risk (>30) | Status |")
    lines.append("|---|---|---:|---:|---:|---:|---|")

    for p in report.reports:
        max_c = f"{p.max_crap:.1f}" if p.max_crap is not None else "N/A"
        avg_c = f"{p.avg_crap:.1f}" if p.avg_crap is not None else "N/A"

        if p.error_message or (p.exit_code != 0 and not p.entries):
            status = "**FAILED**"
        elif report.fail_on_crap is not None and p.max_crap is not None and p.max_crap >= report.fail_on_crap:
            status = "**VIOLATION**"
        elif p.exit_code == 2:
            status = "**VIOLATION**"
        else:
            status = "**PASSED**"

        lines.append(
            f"| `{p.project_name}` | {p.language} | {p.total_methods} | {max_c} | {avg_c} | {p.high_risk_count} | {status} |"
        )
    lines.append("")

    # 详细清单
    entries = report.top_entries(top_n)
    if entries:
        lines.append(f"## High Risk Functions & Methods (Top {len(entries)})\n")
        lines.append("| Symbol | Project | Language | Location | CC | Cov% | CRAP | Risk |")
        lines.append("|---|---|---|---|---:|---:|---:|---|")
        for e in entries:
            cov_str = f"{e.coverage:.1f}%" if e.coverage is not None else "N/A"
            crap_str = f"{e.crap:.1f}" if e.crap is not None else "N/A"
            lines.append(
                f"| `{e.symbol}` | {e.project} | {e.language} | `{e.location}` | {e.complexity} | {cov_str} | {crap_str} | {e.risk_level} |"
            )
        lines.append("")

    global_max = f"{report.global_max_crap:.1f}" if report.global_max_crap is not None else "N/A"
    overall_status = "PASSED" if report.determine_exit_code() == 0 else "FAILED"
    lines.append(
        f"> **Overall Summary**: {report.total_projects} projects analyzed, "
        f"{report.total_methods} total methods, Global Max CRAP: **{global_max}**, "
        f"High Risk Count: **{report.global_high_risk_count}**. Result: **{overall_status}**\n"
    )

    return "\n".join(lines)


def format_csv(report: AggregatedReport) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Project", "Language", "Symbol", "Location", "Complexity", "Coverage", "CRAP", "Risk"])

    for e in report.all_sorted_entries():
        writer.writerow([
            e.project,
            e.language,
            e.symbol,
            e.location,
            e.complexity,
            f"{e.coverage:.2f}" if e.coverage is not None else "",
            f"{e.crap:.2f}" if e.crap is not None else "",
            e.risk_level,
        ])

    return output.getvalue()


def format_complexity(report: AggregatedReport, output_format: str = "text", top_n: int | None = 20) -> str:
    entries = sorted((e for p in report.reports for e in p.entries), key=lambda e: -e.complexity)
    shown = entries[:top_n] if top_n else entries

    def status(project):
        if project.error_message or project.exit_code == 1:
            return "FAILED"
        return "VIOLATION" if project.exit_code == 2 else "PASSED"

    def entry_dict(entry):
        return {key: getattr(entry, key) for key in ("project", "language", "symbol", "location", "complexity")}

    def project_dict(project):
        complexities = [e.complexity for e in project.entries]
        return {
            "project_name": project.project_name, "project_path": project.project_path,
            "language": project.language, "total_methods": project.total_methods,
            "max_complexity": max(complexities, default=None),
            "avg_complexity": round(sum(complexities) / len(complexities), 2) if complexities else None,
            "exit_code": project.exit_code, "error_message": project.error_message,
            "elapsed_seconds": round(project.elapsed_seconds, 3),
            "entries": [entry_dict(e) for e in sorted(project.entries, key=lambda e: -e.complexity)],
        }

    if output_format == "json":
        return json.dumps({
            "mode": "complexity", "total_projects": report.total_projects,
            "total_methods": report.total_methods,
            "global_max_complexity": max((e.complexity for e in entries), default=None),
            "overall_exit_code": report.determine_exit_code(),
            "projects": [project_dict(p) for p in report.reports],
        }, indent=2, ensure_ascii=False)
    if output_format == "csv":
        stream = io.StringIO()
        writer = csv.writer(stream)
        writer.writerow(["Project", "Language", "Symbol", "Location", "Complexity"])
        for entry in entries:
            writer.writerow(entry_dict(entry).values())
        return stream.getvalue()
    if output_format == "markdown":
        lines = ["# Complexity Report", "", "| Project | Language | Methods | Max CC | Avg CC | Status |",
                 "|---|---|---:|---:|---:|---|"]
        for project in report.reports:
            data = project_dict(project)
            lines.append(f"| {project.project_name} | {project.language} | {project.total_methods} | "
                         f"{data['max_complexity']} | {data['avg_complexity']} | {status(project)} |")
            if project.error_message:
                lines.extend(["", f"Error: {project.error_message}", ""])
        lines.extend(["", "| Symbol | Project | CC | Location |", "|---|---|---:|---|"])
        for entry in shown:
            symbol = entry.symbol.replace('|', '\\|')
            location = entry.location.replace('|', '\\|')
            lines.append(f"| `{symbol}` | {entry.project} | {entry.complexity} | `{location}` |")
        return '\n'.join(lines)
    lines = ["Complexity Report", "=" * 80,
             f"{'Project':<24} {'Language':<10} {'Methods':>8} {'Max CC':>8} {'Avg CC':>8} {'Status':>10}"]
    for project in report.reports:
        data = project_dict(project)
        avg = f"{data['avg_complexity']:.2f}" if data['avg_complexity'] is not None else "N/A"
        maximum = str(data['max_complexity']) if data['max_complexity'] is not None else "N/A"
        lines.append(f"{project.project_name:<24} {project.language:<10} {project.total_methods:>8} "
                     f"{maximum:>8} {avg:>8} {status(project):>10}")
        if project.error_message:
            lines.append(f"  [Error] {project.error_message}")
    lines.extend(["", f"Most Complex Functions / Methods (Top {len(shown)})", "-" * 80])
    for entry in shown:
        lines.append(f"CC {entry.complexity:>3}  {entry.symbol.split('(', 1)[0]}  [{entry.project}]  {entry.location}")
    if not entries:
        lines.append("No analyzed methods found.")
    return '\n'.join(lines)
