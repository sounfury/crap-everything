"""CLI acceptance for source analysis without executing the target project."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("language", ["python", "java"])
def test_source_complexity_without_running_project(tmp_path: Path, language: str):
    if language == "java" and not all(shutil.which(tool) for tool in ("java", "javac", "jar")):
        pytest.skip("Java source analysis requires a JDK")
    src = tmp_path / "src"
    src.mkdir()
    if language == "python":
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "example"\n', encoding="utf-8")
        (src / "sample.py").write_text('''
raise RuntimeError("Source analysis must never import this module")
def classify(value):
    if value > 0 and value < 10:
        return 1
    return -1
''', encoding="utf-8")
    else:
        # This intentionally has no usable Maven build or production dependencies.
        (tmp_path / "pom.xml").write_text("<project/>", encoding="utf-8")
        (src / "Example.java").write_text('''
class Example {
    MissingDependency dependency;
    int classify(int value) {
        if (value > 0 && value < 10) return 1;
        return -1;
    }
}
''', encoding="utf-8")
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2] / "src")
    result = subprocess.run(
        [sys.executable, "-m", "crap_everything", "complexity", str(tmp_path),
         "--json", "--top", "1", "--fail-on-complexity", "3"],
        capture_output=True, text=True, encoding="utf-8", env=env, timeout=60,
    )
    assert result.returncode == 2, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["mode"] == "complexity"
    assert report["total_methods"] == 1
    assert report["global_max_complexity"] == 3
    entry = report["projects"][0]["entries"][0]
    assert entry["language"] == language
    assert "classify" in entry["symbol"]
    assert "coverage" not in entry and "crap" not in entry
    assert not (tmp_path / "target").exists()
    assert not (tmp_path / ".coverage").exists()
