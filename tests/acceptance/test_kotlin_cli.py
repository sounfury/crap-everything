"""Opt-in acceptance against a real Kotlin JVM project and its build tools."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


def test_real_kotlin_project_cli(tmp_path: Path):
    project_dir = os.environ.get("CRAP_KOTLIN_ACCEPTANCE_PROJECT")
    if not project_dir:
        pytest.skip("Set CRAP_KOTLIN_ACCEPTANCE_PROJECT to run the real JVM build")

    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    source_dir = Path(__file__).resolve().parents[2] / "src"
    env["PYTHONPATH"] = os.pathsep.join([str(source_dir), env.get("PYTHONPATH", "")])
    result = subprocess.run(
        [sys.executable, "-m", "crap_everything", project_dir,
         "--json", "--fail-on-crap", "1", "--timeout", "300"],
        capture_output=True, text=True, encoding="utf-8", env=env, timeout=330,
    )
    (tmp_path / "kotlin-report.json").write_text(result.stdout, encoding="utf-8")
    assert result.returncode == 2, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["overall_exit_code"] == 2
    assert report["total_methods"] > 0
    entries = []
    for project in report["projects"]:
        assert project["language"] == "kotlin"
        assert project["error_message"] is None
        entries.extend(project["entries"])
    assert any(entry["language"] == "kotlin" for entry in entries)
    assert len({(e["project"], e["symbol"], e["location"]) for e in entries}) == len(entries)
    for entry in entries:
        assert entry["complexity"] >= 1
        assert 0 <= entry["coverage"] <= 100
        expected = entry["complexity"] ** 2 * (1 - entry["coverage"] / 100) ** 3 + entry["complexity"]
        assert abs(entry["crap"] - expected) <= 0.1
        source, _, line = entry["location"].rpartition(":")
        assert line.isdigit()
        assert (Path(project_dir) / source).is_file()


def test_complexity_does_not_run_gradle_tests(tmp_path: Path):
    project_dir = os.environ.get("CRAP_KOTLIN_ACCEPTANCE_PROJECT")
    if not project_dir:
        pytest.skip("Set CRAP_KOTLIN_ACCEPTANCE_PROJECT to a project with a Gradle Wrapper")
    original = Path(project_dir)
    wrapper = original / ("gradlew.bat" if os.name == "nt" else "gradlew")
    if not wrapper.is_file():
        pytest.skip("This acceptance scenario requires a Gradle Wrapper")
    shutil.copy2(wrapper, tmp_path / wrapper.name)
    shutil.copytree(original / "gradle" / "wrapper", tmp_path / "gradle" / "wrapper")
    (tmp_path / "settings.gradle.kts").write_text('rootProject.name = "complexity-acceptance"\n', encoding="utf-8")
    (tmp_path / "build.gradle.kts").write_text('''
plugins { kotlin("jvm") version "2.4.20" }
repositories { mavenCentral() }
kotlin { jvmToolchain(21) }
tasks.test {
    doFirst {
        file("test-was-run").writeText("unexpected")
        throw GradleException("Complexity analysis must not execute tests")
    }
}
plugins.withId("jacoco") {
    tasks.named("jacocoTestReport") { dependsOn(tasks.test) }
}
''', encoding="utf-8")
    source = tmp_path / "src/main/kotlin/Example.kt"
    source.parent.mkdir(parents=True)
    source.write_text("fun classify(value: Int): Int = if (value > 0) 1 else -1\n", encoding="utf-8")
    test_source = tmp_path / "src/test/kotlin/Broken.kt"
    test_source.parent.mkdir(parents=True)
    test_source.write_text("THIS TEST SOURCE MUST NEVER BE COMPILED !!!\n", encoding="utf-8")
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2] / "src")
    result = subprocess.run(
        [sys.executable, "-m", "crap_everything", "complexity", str(tmp_path),
         "--json", "--fail-on-complexity", "2"],
        capture_output=True, text=True, encoding="utf-8", env=env, timeout=330,
    )
    assert result.returncode == 2, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["mode"] == "complexity"
    assert report["global_max_complexity"] == 2
    entry = next(e for p in report["projects"] for e in p["entries"] if e["symbol"] == "classify(Int)")
    assert entry["complexity"] == 2
    assert "coverage" not in entry and "crap" not in entry
    assert not (tmp_path / "test-was-run").exists()
    assert not (tmp_path / "build/classes/kotlin/test").exists()
    assert not (tmp_path / "build").exists()
    assert not (tmp_path / ".gradle").exists()


def test_crap_uses_source_complexity_with_real_coverage(tmp_path: Path):
    project_dir = os.environ.get("CRAP_KOTLIN_ACCEPTANCE_PROJECT")
    if not project_dir:
        pytest.skip("Set CRAP_KOTLIN_ACCEPTANCE_PROJECT to a project with a Gradle Wrapper")
    original = Path(project_dir)
    wrapper = original / ("gradlew.bat" if os.name == "nt" else "gradlew")
    if not wrapper.is_file():
        pytest.skip("This acceptance scenario requires a Gradle Wrapper")
    shutil.copy2(wrapper, tmp_path / wrapper.name)
    shutil.copytree(original / "gradle" / "wrapper", tmp_path / "gradle" / "wrapper")
    (tmp_path / "settings.gradle.kts").write_text('rootProject.name = "coverage-acceptance"\n', encoding="utf-8")
    (tmp_path / "build.gradle.kts").write_text('''
plugins { kotlin("jvm") version "2.4.20" }
repositories { mavenCentral() }
kotlin { jvmToolchain(21) }
dependencies { testImplementation("junit:junit:4.13.2") }
''', encoding="utf-8")
    src = tmp_path / "src/main/kotlin/Decision.kt"
    src.parent.mkdir(parents=True)
    src.write_text('''package demo
fun classify(value: Int): Int = if (value > 0) 1 else -1
fun uncovered(value: Int): Int = if (value > 0) 1 else -1
''', encoding="utf-8")
    test_src = tmp_path / "src/test/java/demo/DecisionTest.java"
    test_src.parent.mkdir(parents=True)
    test_src.write_text('''package demo;
import org.junit.Test;
import static org.junit.Assert.assertEquals;
public class DecisionTest {
    @Test public void coversBothBranches() {
        assertEquals(1, DecisionKt.classify(1));
        assertEquals(-1, DecisionKt.classify(-1));
    }
}
''', encoding="utf-8")
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2] / "src")
    outputs = []
    for args in (["complexity"], []):
        result = subprocess.run(
            [sys.executable, "-m", "crap_everything", *args, str(tmp_path), "--json"],
            capture_output=True, text=True, encoding="utf-8", env=env, timeout=330,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        outputs.append(json.loads(result.stdout)["projects"][0]["entries"])
    assert {e["symbol"]: e["complexity"] for e in outputs[0]} == {e["symbol"]: e["complexity"] for e in outputs[1]}
    covered = next(e for e in outputs[1] if ".classify(" in e["symbol"])
    uncovered = next(e for e in outputs[1] if ".uncovered(" in e["symbol"])
    assert covered["complexity"] == 2 and covered["coverage"] == 100 and covered["crap"] == 2
    assert uncovered["complexity"] == 2 and uncovered["coverage"] == 0 and uncovered["crap"] == 6
    # 项目门禁采用“最高允许”语义；浮点 CRAP 上限也严格检查。
    config = tmp_path / "crap.toml"
    for maximum, expected_code in ((6, 0), (5.9, 2)):
        config.write_text(f'''[project]
language = "kotlin"
[gate]
mode = "crap"
max_complexity = 2
max_crap = {maximum}
min_coverage = 0
''', encoding="utf-8")
        result = subprocess.run(
            [sys.executable, "-m", "crap_everything", "check", str(tmp_path), "--json"],
            capture_output=True, text=True, encoding="utf-8", env=env, timeout=330,
        )
        assert result.returncode == expected_code, result.stdout + result.stderr
        assert json.loads(result.stdout)["gate"]["passed"] == (expected_code == 0)
