import json
from crap_everything.formatters import (
    format_csv,
    format_json,
    format_markdown,
    format_text,
)
from crap_everything.models import (
    AggregatedReport,
    ProjectReport,
    UnifiedCrapEntry,
)


def _sample_report() -> AggregatedReport:
    e1 = UnifiedCrapEntry("crap4py", "python", "fn_fast", "core.py", 2, 95.0, 2.1)
    e2 = UnifiedCrapEntry("crap4java", "java", "heavyMethod", "Main.java", 15, 20.0, 115.2)

    rep1 = ProjectReport("crap4py", "/path/crap4py", "python", [e1], exit_code=0)
    rep2 = ProjectReport("crap4java", "/path/crap4java", "java", [e2], exit_code=2)
    return AggregatedReport([rep1, rep2], fail_on_crap=30.0)


def test_format_text():
    rep = _sample_report()
    text = format_text(rep)
    assert "CRAP Everything - Multi-Project Summary" in text
    assert "crap4py" in text
    assert "crap4java" in text
    assert "heavyMethod" in text


def test_format_json():
    rep = _sample_report()
    json_str = format_json(rep)
    data = json.loads(json_str)
    assert data["total_projects"] == 2
    assert data["total_methods"] == 2
    assert len(data["projects"]) == 2


def test_format_markdown():
    rep = _sample_report()
    md = format_markdown(rep)
    assert "# CRAP Multi-Project Analysis Report" in md
    assert "| `crap4py` | python |" in md
    assert "| `heavyMethod` |" in md


def test_format_csv():
    rep = _sample_report()
    csv_str = format_csv(rep)
    assert "Project,Language,Symbol,Location,Complexity,Coverage,CRAP,Risk" in csv_str
    assert "crap4java,java,heavyMethod,Main.java,15,20.00,115.20,HIGH" in csv_str
