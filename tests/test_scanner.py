from pathlib import Path

from crap_everything.adapters.java_adapter import JavaAdapter
from crap_everything.adapters.python_adapter import PythonAdapter
from crap_everything.adapters.registry import AdapterRegistry
from crap_everything.scanner import scan_projects


def test_scan_projects_in_monorepo(tmp_path: Path):
    registry = AdapterRegistry()
    registry.register(PythonAdapter())
    registry.register(JavaAdapter())

    # 构造假的工作区结构：包含一个 python 子项目和一个 java 子项目，以及一个忽略目录 .git
    root_dir = tmp_path / "workspace"
    root_dir.mkdir()

    sub_py = root_dir / "py_proj"
    sub_py.mkdir()
    (sub_py / "pyproject.toml").write_text("", encoding="utf-8")

    sub_java = root_dir / "java_proj"
    sub_java.mkdir()
    (sub_java / "pom.xml").write_text("", encoding="utf-8")

    git_dir = root_dir / ".git"
    git_dir.mkdir()

    # 扫描根目录
    projects = scan_projects([root_dir], registry)

    assert len(projects) == 2
    proj_names = {p[0].name for p in projects}
    assert proj_names == {"py_proj", "java_proj"}
