from crap_everything.adapters.base import AnalysisOptions, BaseAdapter
from crap_everything.adapters.java_adapter import JavaAdapter
from crap_everything.adapters.python_adapter import PythonAdapter
from crap_everything.adapters.registry import (
    AdapterRegistry,
    get_global_registry,
)

# 自动注册内置适配器
_registry = get_global_registry()
_registry.register(PythonAdapter())
_registry.register(JavaAdapter())

__all__ = [
    "AnalysisOptions",
    "BaseAdapter",
    "PythonAdapter",
    "JavaAdapter",
    "AdapterRegistry",
    "get_global_registry",
]
