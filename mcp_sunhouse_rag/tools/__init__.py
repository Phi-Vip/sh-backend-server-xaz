"""
Bộ quản lý và đăng ký công cụ MCP (Tool Registry & Auto-Discovery)
Hỗ trợ cơ chế Plugin: Thả bất kỳ file tool .py nào vào thư mục này là hệ thống tự nhận diện.
"""

import os
import sys
import importlib
import inspect
import asyncio
from typing import Callable, Dict, Any, List

class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, Dict[str, Any]] = {}

    def register(self, name: str, description: str, parameters: Dict[str, Any] = None):
        """
        Decorator đăng ký một hàm Python thành một MCP Tool chuẩn
        """
        def decorator(func: Callable):
            schema = {
                "name": name,
                "description": description,
                "inputSchema": parameters or {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
            self._tools[name] = {
                "func": func,
                "schema": schema,
                "is_async": inspect.iscoroutinefunction(func)
            }
            return func
        return decorator

    def get_tools_list(self) -> List[Dict[str, Any]]:
        """Lấy danh sách tất cả các tool schema để trả lời lệnh tools/list"""
        return [tool["schema"] for tool in self._tools.values()]

    def has_tool(self, name: str) -> bool:
        return name in self._tools

    async def execute_tool(self, name: str, arguments: Dict[str, Any]) -> str:
        """Thực thi một tool theo tên và truyền arguments"""
        if name not in self._tools:
            raise ValueError(f"Công cụ '{name}' không tồn tại trong hệ thống MCP Server.")
        
        tool = self._tools[name]
        func = tool["func"]
        
        try:
            if tool["is_async"]:
                result = await func(**arguments)
            else:
                result = func(**arguments)
            return str(result)
        except TypeError as e:
            # Lỗi thiếu tham số hoặc sai tên tham số
            return f"Lỗi gọi công cụ '{name}': Tham số không khớp ({e})."
        except Exception as e:
            return f"Lỗi nội bộ khi thực thi công cụ '{name}': {str(e)}"

# Instance toàn cục
registry = ToolRegistry()
register_tool = registry.register

def discover_tools():
    """
    Tự động quét và nạp toàn bộ các file .py trong thư mục tools/
    """
    tools_dir = os.path.dirname(__file__)
    for filename in os.listdir(tools_dir):
        if filename.endswith(".py") and filename != "__init__.py":
            module_name = filename[:-3]
            try:
                importlib.import_module(f"tools.{module_name}")
            except Exception as e:
                print(f"[CẢNH BÁO] Không thể nạp module tool '{module_name}': {e}", file=sys.stderr)
