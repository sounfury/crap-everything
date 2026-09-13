from pathlib import Path
from unittest.mock import MagicMock, patch

from crap_everything.adapters.base import AnalysisOptions
from crap_everything.adapters.java_adapter import JavaAdapter
from crap_everything.adapters.python_adapter import PythonAdapter
from crap_everything.adapters.registry import AdapterRegistry


def test_registry_registration_and_detection(tmp_path: Path):
    registry = AdapterRegistry()
    py_adapter = PythonAdapter()
    java_adapter = JavaAdapter()

    registry.register(py_adapter)
    registry.register(java_adapter)

    assert registry.get_by_language("python") == py_adapter
    assert registry.get_by_language("java") == java_adapter
    assert registry.get_by_language("csharp") is None

    # 创建测试 Python 项目结构
    py_proj = tmp_path / "my_py"
    py_proj.mkdir()
    (py_proj / "pyproject.toml").write_text("[project]\nname='test'\n", encoding="utf-8")

    assert py_adapter.detect(py_proj) is True
    assert registry.detect(py_proj) == py_adapter

    # 创建测试 Java 项目结构
    java_proj = tmp_path / "my_java"
    java_proj.mkdir()
    (java_proj / "pom.xml").write_text("<project></project>", encoding="utf-8")

    assert java_adapter.detect(java_proj) is True
    assert registry.detect(java_proj) == java_adapter


def test_java_adapter_regex_parsing():
    sample_stdout = """CRAP Report
===========
Method                         Class                                CC    Cov%     CRAP
-----------------------------------------------------------------------------------------
calculateScore                 crap4java.CrapScore                   4   80.0%      4.1
uncoveredComplexMethod         crap4java.RiskyClass                 12    0.0%    156.0
untestedMethod                 crap4java.NoCoverage                  2     N/A      N/A
"""
    adapter = JavaAdapter()
    entries = []
    for line in sample_stdout.splitlines():
        line_str = line.strip()
        if not line_str or line_str.startswith("CRAP Report") or line_str.startswith("=") or line_str.startswith("-") or line_str.startswith("Method"):
            continue
        m = adapter._REPORT_LINE_PATTERN.match(line_str)
        if m:
            entries.append((m.group("method"), int(m.group("cc")), m.group("cov"), m.group("crap")))

    assert len(entries) == 3
    assert entries[0] == ("calculateScore", 4, "80.0%", "4.1")
    assert entries[1] == ("uncoveredComplexMethod", 12, "0.0%", "156.0")
    assert entries[2] == ("untestedMethod", 2, "N/A", "N/A")
