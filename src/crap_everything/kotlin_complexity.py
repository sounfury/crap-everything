from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path

from tree_sitter import Language, Node, Parser
import tree_sitter_kotlin


@dataclass
class SourceFunction:
    source: Path
    package: str
    symbol: str
    start_line: int
    body_start_line: int
    end_line: int
    complexity: int


_DECLARATIONS = {
    "function_declaration", "class_declaration", "object_declaration",
    "object_literal", "companion_object", "getter", "setter", "secondary_constructor", "anonymous_initializer",
}
_DECISIONS = {"if_expression", "for_statement", "while_statement", "do_while_statement", "catch_block"}


def _complexity(body: Node) -> int:
    """统计源码决策点；嵌套声明单独分析，lambda 内显式分支归属外层函数。"""
    decisions = 0
    stack = [body]
    while stack:
        node = stack.pop()
        if node != body and node.type in _DECLARATIONS:
            continue
        if node.type in _DECISIONS:
            decisions += 1
        elif node.type == "when_entry" and node.child_by_field_name("condition") is not None:
            decisions += 1
        elif node.type == "binary_expression":
            decisions += sum(child.type in ("&&", "||", "?:") for child in node.children)
        stack.extend(node.named_children)
    return decisions + 1


def _parameters(node: Node) -> str:
    """返回源码参数类型签名，用于区分重载，不统计参数默认值中的分支。"""
    params = next((child for child in node.named_children if child.type == "function_value_parameters"), None)
    if params is None:
        return "()"
    types = []
    for parameter in params.named_children:
        if parameter.type == "parameter":
            type_nodes = [child for child in parameter.named_children if child.type not in ("identifier", "modifiers")]
            if type_nodes:
                types.append(re.sub(r"\s+", " ", type_nodes[-1].text.decode("utf-8")))
    return f"({', '.join(types)})"


def extract_kotlin_functions(sources: list[Path], deadline: float) -> list[SourceFunction]:
    """解析 Kotlin 文件，返回有源码函数体的声明及其复杂度；语法错误直接报错。"""
    parser = Parser(Language(tree_sitter_kotlin.language()))
    functions = []
    for source in sources:
        if time.perf_counter() >= deadline:
            raise TimeoutError("Kotlin 源码分析超时")
        data = source.read_bytes()
        # UTF-8 BOM 不属于 Kotlin 源码 token，去掉后行号保持不变。
        if data.startswith(b"\xef\xbb\xbf"):
            data = data[3:]
        tree = parser.parse(data)
        if tree.root_node.has_error:
            # 语法库在同一行结束的类成员后要求可选分号；补分号重解析。
            # 只补类体/错误恢复中的右花括号，绝不修改字符串，也不改变行号。
            closing = []
            stack = [tree.root_node]
            while stack:
                node = stack.pop()
                if node.type == "}" and node.parent.type in ("class_body", "enum_class_body", "ERROR"):
                    closing.append(node.start_byte)
                stack.extend(node.children)
            for offset in sorted(set(closing), reverse=True):
                data = data[:offset] + b";" + data[offset:]
            if closing:
                tree = parser.parse(data)
        if tree.root_node.has_error:
            stack = [tree.root_node]
            while stack:
                node = stack.pop()
                if node.is_error or node.is_missing:
                    raise ValueError(f"Kotlin 源码语法解析失败: {source}:{node.start_point.row + 1}")
                stack.extend(reversed(node.children))
        package_node = next((n for n in tree.root_node.named_children if n.type == "package_header"), None)
        package = ""
        if package_node:
            qualified = next(n for n in package_node.named_children if n.type == "qualified_identifier")
            package = '.'.join(n.text.decode("utf-8").strip('`') for n in qualified.named_children)

        def visit(node: Node, owners: tuple[str, ...] = ()) -> None:
            owner = owners
            if node.type in ("class_declaration", "object_declaration", "companion_object"):
                name = node.child_by_field_name("name")
                if name is None:
                    name = next((n for n in node.named_children if n.type == "identifier"), None)
                if name is not None:
                    owner = (*owners, name.text.decode("utf-8").strip('`'))
                elif node.type == "companion_object":
                    owner = (*owners, "Companion")
            body = None
            name = None
            if node.type == "function_declaration":
                name_node = node.child_by_field_name("name")
                if name_node is not None:
                    name = name_node.text.decode("utf-8").strip('`')
                    # 源码扩展函数保留接收者，避免同名不同接收者混淆。
                    receiver = next((n for n in node.named_children if n.end_byte < name_node.start_byte
                                     and n.type in ("user_type", "nullable_type", "function_type")), None)
                    if receiver:
                        name = f"{receiver.text.decode('utf-8')}.{name}"
                    name += _parameters(node)
                body = next((n for n in node.named_children if n.type == "function_body"), None)
            elif node.type in ("getter", "setter"):
                prop = node.parent
                variable = next((n for n in prop.named_children if n.type == "variable_declaration"), None)
                if variable:
                    identifier = next((n for n in variable.named_children if n.type == "identifier"), None)
                    if identifier:
                        name = f"{identifier.text.decode('utf-8').strip('`')}.{node.type}()"
                body = next((n for n in node.named_children if n.type == "function_body"), None)
            elif node.type in ("anonymous_initializer", "secondary_constructor"):
                name = (f"init@{node.start_point.row + 1}" if node.type == "anonymous_initializer"
                        else f"constructor{_parameters(node)}")
                body = next((n for n in node.named_children if n.type == "block"), None)
            if name and body is not None:
                symbol = '.'.join(filter(None, (package, *owner, name)))
                functions.append(SourceFunction(
                    source, package, symbol, node.start_point.row + 1,
                    body.start_point.row + 1, body.end_point.row + 1, _complexity(body),
                ))
                # 局部函数有独立名字和分数，不重复计入外层复杂度。
                owner = (*owner, name)
            for child in node.named_children:
                visit(child, owner)

        visit(tree.root_node)
    return functions
