from crap_everything.adapters.base import AnalysisOptions, BaseAdapter
from crap_everything.adapters.clojure_adapter import ClojureAdapter
from crap_everything.adapters.java_adapter import JavaAdapter
from crap_everything.adapters.kotlin_adapter import KotlinAdapter
from crap_everything.adapters.python_adapter import PythonAdapter
from crap_everything.adapters.registry import (
    AdapterRegistry,
    get_global_registry,
)

# 自动注册内置适配器
_registry = get_global_registry()
# Clojure 项目常带少量 Python 脚本，按项目文件优先识别。
_registry.register(ClojureAdapter())
_registry.register(PythonAdapter())
_registry.register(KotlinAdapter())
_registry.register(JavaAdapter())

__all__ = [
    "AnalysisOptions",
    "BaseAdapter",
    "ClojureAdapter",
    "PythonAdapter",
    "JavaAdapter",
    "KotlinAdapter",
    "AdapterRegistry",
    "get_global_registry",
]
