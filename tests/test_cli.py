import pytest
from unittest.mock import MagicMock, patch

from crap_everything.cli import build_parser, main
from crap_everything.models import AggregatedReport, ProjectReport


def test_cli_parser_defaults():
    parser = build_parser()
    args = parser.parse_args([])
    assert args.paths == ["."]
    assert args.output == "text"
    assert args.fail_on_crap is None
    assert args.top == 20


def test_cli_parser_custom_flags():
    parser = build_parser()
    args = parser.parse_args([
        "p1", "p2",
        "--json",
        "--fail-on-crap", "25",
        "--top", "10",
        "--lang", "python",
    ])
    assert args.paths == ["p1", "p2"]
    assert args.json is True
    assert args.fail_on_crap == 25.0
    assert args.top == 10
    assert args.lang == "python"


@patch("crap_everything.cli.scan_projects")
@patch("crap_everything.cli.AnalysisRunner")
def test_cli_main_exit_codes(mock_runner_cls, mock_scan):
    mock_scan.return_value = [("dummy", MagicMock())]

    mock_runner_instance = MagicMock()
    mock_runner_cls.return_value = mock_runner_instance

    # 构造真实的 AggregatedReport，设置超出阈值
    e = MagicMock(crap=50.0, coverage=20.0, complexity=10, symbol="risky_fn", project="p", risk_level="HIGH", location="loc")
    rep = ProjectReport("dummy_proj", "/path", "python", [e], exit_code=0)
    mock_report = AggregatedReport([rep], fail_on_crap=10.0)

    mock_runner_instance.run_all.return_value = mock_report

    with pytest.raises(SystemExit) as exc:
        main(["dummy", "--fail-on-crap", "10"])

    assert exc.value.code == 2


def _python_project(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'demo'\n", encoding="utf-8")
    source = tmp_path / "src" / "demo"
    source.mkdir(parents=True)
    (source / "core.py").write_text("def pick(x):\n    if x:\n        return 1\n    return 0\n", encoding="utf-8")
    return tmp_path


def test_complexity_json_exposes_file_and_line(tmp_path, capsys):
    import json
    project = _python_project(tmp_path)
    with pytest.raises(SystemExit) as exit_info:
        main(["complexity", str(project), "--json"])
    assert exit_info.value.code == 0
    entry = json.loads(capsys.readouterr().out)["projects"][0]["entries"][0]
    assert (entry["file"], entry["line"], entry["complexity"]) == ("src/demo/core.py", 1, 2)
    assert list(project.rglob("*.json")) == []


def test_report_is_written_only_when_requested(tmp_path, capsys):
    import json
    project = _python_project(tmp_path / "project")
    report = tmp_path / "out" / "report.json"
    with pytest.raises(SystemExit):
        main(["complexity", str(project), "--report", str(report)])
    assert "Complexity Report" in capsys.readouterr().out
    assert json.loads(report.read_text(encoding="utf-8"))["mode"] == "complexity"


def test_output_switches_to_utf8_for_local_code_pages(monkeypatch):
    import io
    import sys
    from crap_everything.cli import _use_utf8_output
    stdout = io.TextIOWrapper(io.BytesIO(), encoding="gbk")
    monkeypatch.setattr(sys, "stdout", stdout)
    _use_utf8_output()
    print("门禁通过")
    stdout.flush()
    assert stdout.buffer.getvalue().decode("utf-8").strip() == "门禁通过"
