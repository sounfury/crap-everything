import subprocess
from pathlib import Path

import pytest

from crap_everything.adapters import get_global_registry
from crap_everything.adapters.base import AnalysisOptions
from crap_everything.adapters.clojure_adapter import ClojureAdapter
from crap_everything.clojure_complexity import cyclomatic_complexity, declared_namespace, extract_functions


# 用例取自 crap4clj 的 spec/crap4clj/complexity_spec.clj，保证移植口径一致。
@pytest.mark.parametrize("source, expected", [
    ("(defn foo [])", 1),
    ("(defn foo [x]\n  (+ x 1))", 1),
    ("(defn foo [x]\n  (if x 1 0))", 2),
    ("(defn foo [x]\n  (if-let [y x] y 0))", 2),
    ("(defn foo [x]\n  (when-first [y x] y))", 2),
    ("(defn foo [x y]\n  (and x y))", 2),
    ("(defn foo [x]\n  (loop [i 0] (recur (inc i))))", 2),
    ("(defn foo []\n  (try (bar)\n    (catch Exception e nil)\n    (catch Error e nil)))", 3),
    ("(defn foo [x]\n  (cond\n    (= x 1) :one\n    :else :other))", 3),
    ("(defn foo [x]\n  (condp = x\n    1 :one\n    2 :two))", 3),
    ("(defn foo [x]\n  (case x\n    1 :one\n    :other))", 3),
    ("(defn foo [x]\n  (some-> x inc dec))", 3),
    ("(defn foo [x]\n  (str \"(if x y)\") ; (when z)\n  x)", 1),
    ("(defn sign [x] (cond (neg? x) -1 (pos? x) 1 :else 0))", 4),
])
def test_complexity_matches_crap4clj(source, expected):
    assert cyclomatic_complexity(source) == expected


def test_extracts_top_level_defns_with_lines_and_namespace():
    source = ("(ns demo.core)\n; (defn ignored [] 1)\n\"(defn ignored2 [] 2)\"\n"
              "(def x 1)\n(defn- alpha [a]\n  (when a\n    \\)))\n\n(defn beta [] (if 1 2 3))\n")
    functions = extract_functions(source)
    assert [(f.name, f.start_line, f.end_line, f.complexity) for f in functions] == [
        ("alpha", 5, 7, 2), ("beta", 9, 9, 2)]
    assert declared_namespace(source) == "demo.core"
    assert declared_namespace("(in-ns 'demo.other)") == "demo.other"


def _project(tmp_path: Path) -> Path:
    (tmp_path / "deps.edn").write_text("{:paths [\"src\"]}", encoding="utf-8")
    source = tmp_path / "src" / "demo"
    source.mkdir(parents=True)
    (source / "core.clj").write_text("(ns demo.core)\n(defn pick [x]\n  (if x 1 0))\n(defn plain [] 1)\n", encoding="utf-8")
    # Clojure 项目里的辅助 Python 脚本不应让项目被识别为 Python。
    (source / "helper.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    return tmp_path


def test_clojure_project_is_detected_before_python(tmp_path):
    assert get_global_registry().detect(_project(tmp_path)).language == "clojure"


def test_complexity_mode_needs_no_clojure_toolchain(tmp_path):
    report = ClojureAdapter().run(_project(tmp_path), AnalysisOptions(complexity_only=True))
    assert report.error_message is None
    assert [(e.symbol, e.location, e.complexity, e.crap) for e in report.entries] == [
        ("demo.core/pick", "src/demo/core.clj:2", 2, None), ("demo.core/plain", "src/demo/core.clj:4", 1, None)]


def test_crap_mode_reads_crap4clj_report(tmp_path, monkeypatch):
    output = ("Ran Cloverage\nCRAP Report\n===========\n"
              "Function                       Namespace                             CC    Cov%     CRAP\n"
              "-----\n"
              "pick                           demo.core                              2   50.0%      2.5\n"
              "plain                          demo.core                              1    N/A       N/A\n")
    monkeypatch.setattr(ClojureAdapter, "_crap_command", lambda self, source_dir: ["bb"])
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, output, ""))
    report = ClojureAdapter().run(_project(tmp_path), AnalysisOptions(fail_on_crap=2.0))
    pick = next(e for e in report.entries if e.symbol == "demo.core/pick")
    assert (pick.coverage, pick.crap, report.exit_code) == (50.0, 2.5, 2)


def test_crap_mode_explains_missing_toolchain(tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)
    report = ClojureAdapter().run(_project(tmp_path), AnalysisOptions())
    assert report.exit_code == 1 and "Babashka" in report.error_message
