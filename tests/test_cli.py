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
