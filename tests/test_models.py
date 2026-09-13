from crap_everything.models import (
    AggregatedReport,
    ProjectReport,
    UnifiedCrapEntry,
)


def test_unified_crap_entry_risk_levels():
    low = UnifiedCrapEntry("p1", "python", "fn1", "mod1", 2, 90.0, 3.5)
    mod = UnifiedCrapEntry("p1", "python", "fn2", "mod1", 8, 40.0, 15.2)
    high = UnifiedCrapEntry("p1", "python", "fn3", "mod1", 15, 10.0, 85.0)
    unknown = UnifiedCrapEntry("p1", "python", "fn4", "mod1", 1, None, None)

    assert low.risk_level == "LOW"
    assert mod.risk_level == "MODERATE"
    assert high.risk_level == "HIGH"
    assert unknown.risk_level == "UNKNOWN"


def test_project_report_metrics():
    e1 = UnifiedCrapEntry("p1", "python", "fn1", "mod1", 2, 100.0, 2.0)
    e2 = UnifiedCrapEntry("p1", "python", "fn2", "mod1", 10, 20.0, 42.0)
    report = ProjectReport(
        project_name="p1",
        project_path="/dummy/p1",
        language="python",
        entries=[e1, e2],
    )

    assert report.total_methods == 2
    assert report.max_crap == 42.0
    assert report.avg_crap == 22.0
    assert report.high_risk_count == 1


def test_aggregated_report_exit_codes():
    e1 = UnifiedCrapEntry("p1", "python", "fn1", "mod1", 2, 100.0, 2.0)
    e2 = UnifiedCrapEntry("p2", "java", "fn2", "mod2", 10, 20.0, 35.0)

    rep1 = ProjectReport("p1", "/dummy/p1", "python", [e1], exit_code=0)
    rep2 = ProjectReport("p2", "/dummy/p2", "java", [e2], exit_code=0)

    agg = AggregatedReport([rep1, rep2], fail_on_crap=30.0)
    # 因为 35.0 >= 30.0，判定为超标
    assert agg.determine_exit_code() == 2

    # 如果没有指定阈值，且底层均返回 0
    agg_pass = AggregatedReport([rep1, rep2], fail_on_crap=None)
    assert agg_pass.determine_exit_code() == 0

    # 如果有子项目执行错误
    rep_err = ProjectReport("p3", "/dummy/p3", "python", [], exit_code=1)
    agg_err = AggregatedReport([rep1, rep_err])
    assert agg_err.determine_exit_code() == 1
