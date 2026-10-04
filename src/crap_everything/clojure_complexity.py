"""Clojure 函数圈复杂度。

逐行移植自 unclebob/crap4clj 的 src/crap4clj/complexity.cljc（提交 e90be2e，源码见 crap4clj/ 目录），
口径与 crap4clj 完全一致：去掉字符串和注释后按源码文本计数，无需 JVM、Clojure CLI 或运行目标项目。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_DECISION_POINT = re.compile(
    r"\((if-not|if-let|if-some|when-not|when-let|when-some|when-first|if|when|and|or|loop|catch)[\s\)]")
_COND_FORM = re.compile(r"\((some->>|some->|cond->>|cond->|cond|condp|case)[\s\)]")
_DEFN = re.compile(r"\(\s*defn-?\s+([^\s\(\)\[\]\{\}\"]+)")
_NAMESPACE = (
    re.compile(r"\(\s*ns\s+([A-Za-z0-9*+!_?.\-/]+)"),
    re.compile(r"\(\s*in-ns\s+'([A-Za-z0-9*+!_?.\-/]+)\s*\)"),
    re.compile(r"\(\s*in-ns\s+\(quote\s+([A-Za-z0-9*+!_?.\-/]+)\)\s*\)"),
)
_FORM_SKIP = {"condp": 2, "case": 1, "cond->": 1, "cond->>": 1, "some->": 1, "some->>": 1}
_THREAD_FORMS = {"some->", "some->>"}
_CHAR_LITERAL_DELIMITERS = set('()[]{}";,')
SOURCE_SUFFIXES = (".clj", ".cljc", ".cljs", ".bb")


@dataclass
class ClojureFunction:
    name: str
    start_line: int
    end_line: int
    complexity: int


def _strip_strings(text: str) -> str:
    out = []
    in_string = escaped = False
    for ch in text:
        if not in_string:
            out.append(ch)
            in_string = ch == '"'
        elif escaped:
            out.append(ch if ch == "\n" else " ")
            escaped = False
        elif ch == "\\":
            out.append(" ")
            escaped = True
        elif ch == '"':
            out.append(ch)
            in_string = False
        else:
            out.append(ch if ch == "\n" else " ")
    return "".join(out)


def _split_lines(text: str) -> list[str]:
    # 与 clojure.string/split-lines 一致：按 \r?\n 拆分并去掉末尾空行。
    lines = re.split(r"\r?\n", text)
    while lines and lines[-1] == "":
        lines.pop()
    return lines


def _strip_comments(text: str) -> str:
    return "\n".join(re.sub(r";.*", "", line) for line in _split_lines(text))


def _count_top_level_forms(text: str, start: int) -> int:
    """统计从 start（已在左括号内）到匹配右括号之间的顶层形式数。"""
    depth, forms, in_form = 1, 0, False
    i = start
    while i < len(text) and depth != 0:
        ch = text[i]
        if ch in "({[":
            if depth == 1 and not in_form:
                forms += 1
            depth, in_form = depth + 1, True
        elif ch in ")}]":
            in_form = False if depth == 1 else in_form
            depth -= 1
        elif ch.isspace():
            in_form = depth != 1
        else:
            if depth == 1 and not in_form:
                forms += 1
            in_form = True
        i += 1
    return forms


def _skip_to_body(text: str, match_start: int) -> int:
    i = match_start + 1
    while i < len(text) and not text[i].isspace() and text[i] != ")":
        i += 1
    return i


def _count_clauses(text: str, form_type: str, match_start: int) -> int:
    remaining = _count_top_level_forms(text, _skip_to_body(text, match_start)) - _FORM_SKIP.get(form_type, 0)
    if form_type in _THREAD_FORMS:
        return remaining
    base = int(remaining / 2)  # Clojure quot 向零取整
    return base + 1 if form_type == "case" and remaining % 2 else base


def cyclomatic_complexity(fn_text: str) -> int:
    clean = _strip_comments(_strip_strings(fn_text))
    conds = sum(_count_clauses(clean, m.group(1), m.start()) for m in _COND_FORM.finditer(clean))
    return 1 + len(_DECISION_POINT.findall(clean)) + conds


def _char_literal_end(source: str, idx: int) -> int:
    n = len(source)
    if idx + 1 >= n:
        return n
    i = idx + 2
    while i < n and not source[i].isspace() and source[i] not in _CHAR_LITERAL_DELIMITERS:
        i += 1
    return i


def extract_functions(source: str) -> list[ClojureFunction]:
    """找出顶层 defn / defn- 形式，返回名称、起止行和复杂度。"""
    functions = []
    n, i, line, depth = len(source), 0, 1, 0
    mode, escaped = "normal", False
    start_idx = start_line = None
    while i < n:
        ch = source[i]
        newline = ch == "\n"
        if mode == "comment":
            if newline:
                line, mode = line + 1, "normal"
        elif mode == "string":
            if escaped:
                escaped, line = False, line + newline
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                mode = "normal"
            else:
                line += newline
        elif ch == ";":
            mode = "comment"
        elif ch == "\\":
            i = _char_literal_end(source, i)
            continue
        elif ch == '"':
            mode = "string"
        elif ch == "(":
            if depth == 0:
                start_idx, start_line = i, line
            depth += 1
        elif ch == ")":
            closes = depth == 1 and start_idx is not None
            depth = max(0, depth - 1)
            if closes:
                text = source[start_idx:i + 1]
                match = _DEFN.match(text)
                if match:
                    functions.append(ClojureFunction(match.group(1), start_line, line, cyclomatic_complexity(text)))
                start_idx = start_line = None
        else:
            line += newline
        i += 1
    return functions


def declared_namespace(source: str) -> str | None:
    for pattern in _NAMESPACE:
        match = pattern.search(source)
        if match:
            return match.group(1)
    return None


def analyze_file(path: Path) -> tuple[str | None, list[ClojureFunction]]:
    source = path.read_text(encoding="utf-8-sig")
    return declared_namespace(source), extract_functions(source)
