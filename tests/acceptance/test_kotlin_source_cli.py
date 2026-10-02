"""源码复杂度的 CLI 验收：不构建项目，且不计内联、字符串或生成方法。"""

import json
import os
import subprocess
import sys
from pathlib import Path


def _run(project: Path, *args: str):
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2] / "src")
    result = subprocess.run(
        [sys.executable, "-m", "crap_everything", "complexity", str(project), "--json", *args],
        capture_output=True, text=True, encoding="utf-8", env=env, timeout=30,
    )
    return result, json.loads(result.stdout)


def test_kotlin_source_without_build_or_dependencies(tmp_path: Path):
    (tmp_path / "build.gradle.kts").write_text('error("Build must never run")\n', encoding="utf-8")
    src = tmp_path / "src/main/kotlin/Example.kt"
    src.parent.mkdir(parents=True)
    src.write_text('''package example
// if while catch && || ?: do not count in comments or strings
fun classify(chain: List<MissingType>): Int {
    val ignored = "if while catch && || ?:"
    val status = chain.firstNotNullOfOrNull { (it as? ServiceError)?.code }
    return when {
        status != null -> 1
        chain.any { it is Timeout || it is Cancelled } -> 2
        chain.any { it is Network || it is Broken } -> 3
        else -> 4
    }
}
data class Payload(val name: String)
class Compact { fun value() = 1 }
class Box {
    val size: Int get() = if (true) 1 else 0
    init { if (false) error("bad") }
    companion object { fun empty() = 1 }
}
fun outer(): Int {
    fun inner() = if (true) 1 else 0
    return 42
}
fun defaultArgument(value: Int = if (true) 1 else 2) = value
fun overloaded(value: Int) = value
fun overloaded(value: String) = value
fun elvis(value: String?) = value ?: "if || else"
fun aliases(value: Int) = when (value) {
    1, 2 -> 1
    else -> 0
}
fun lambda(values: List<Int>) = values.any { if (it > 0) true else false }
fun loops(value: String?): Int {
    for (i in 1..3) { println(i) }
    while (false) { println(value) }
    do { println(value) } while (false)
    try { println(value) } catch (error: Exception) { println(error) }
    return if (value != null && value.isNotEmpty()) 1 else 0
}
''', encoding="utf-8")
    broken = tmp_path / "src/test/kotlin/Broken.kt"
    broken.parent.mkdir(parents=True)
    broken.write_text("THIS TEST MUST NOT BE PARSED OR COMPILED !!!\n", encoding="utf-8")
    result, report = _run(tmp_path, "--fail-on-complexity", "6")
    assert result.returncode == 2, result.stdout + result.stderr
    assert report["global_max_complexity"] == 7
    entries = report["projects"][0]["entries"]

    def score(fragment):
        return next(e["complexity"] for e in entries if fragment in e["symbol"])

    assert score(".classify(") == 6
    assert score("Compact.value(") == 1
    assert score("Box.size.getter(") == 2
    assert score("Box.init@") == 2
    assert score("Box.Companion.empty(") == 1
    assert next(e["complexity"] for e in entries if e["symbol"] == "example.outer()") == 1
    assert score(".inner(") == 2
    assert score(".defaultArgument(") == 1
    assert score(".elvis(") == 2
    assert score(".aliases(") == 2
    assert score(".lambda(") == 2
    overloads = [e["symbol"] for e in entries if ".overloaded(" in e["symbol"]]
    assert len(set(overloads)) == 2
    assert not any("Payload" in e["symbol"] for e in entries)
    assert not (tmp_path / "build").exists()
    assert not (tmp_path / ".gradle").exists()


def test_kotlin_syntax_error_is_reported(tmp_path: Path):
    src = tmp_path / "src/main/kotlin/Broken.kt"
    src.parent.mkdir(parents=True)
    src.write_text("fun broken( {\n", encoding="utf-8")
    result, report = _run(tmp_path)
    assert result.returncode == 1
    assert "Broken.kt:" in report["projects"][0]["error_message"]
