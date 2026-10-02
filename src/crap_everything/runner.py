from __future__ import annotations

from pathlib import Path

from crap_everything.adapters.base import AnalysisOptions, BaseAdapter
from crap_everything.models import AggregatedReport, ProjectReport


class AnalysisRunner:
    def __init__(self, options: AnalysisOptions | None = None) -> None:
        self.options = options or AnalysisOptions()

    def run_all(
        self,
        targets: list[tuple[Path, BaseAdapter]],
    ) -> AggregatedReport:
        reports: list[ProjectReport] = []

        for project_path, adapter in targets:
            report = adapter.run(project_path, self.options)
            if self.options.complexity_only and report.error_message is None:
                threshold = self.options.fail_on_complexity
                if threshold is not None and any(e.complexity >= threshold for e in report.entries):
                    report.exit_code = 2
            reports.append(report)

        return AggregatedReport(
            reports=reports,
            fail_on_crap=self.options.fail_on_crap,
        )
