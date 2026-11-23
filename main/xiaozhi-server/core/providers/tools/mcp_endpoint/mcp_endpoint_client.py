"""MCP接入点客户端定义"""

import asyncio
import threading
from concurrent.futures import Future
from core.utils.util import sanitize_tool_name
from config.logger import setup_logging

TAG = __name__
logger = setup_logging()


class MCPEndpointClient:
    """MCP接入点客户端，用于管理MCP接入点状态和工具"""

    def __init__(self, conn=None):
        self.conn = conn
        self.tools = {}  # sanitized_name -> tool_data
        self.name_mapping = {}
        self.ready = False
        self.ready_event = threading.Event()
        self.call_results = {}  # To store Futures for tool call responses
        self.next_id = 1
        self.lock = asyncio.Lock()
        self._cached_available_tools = None  # Cache for get_available_tools
        self.websocket = None  # WebSocket连接
        self.endpoint_url = None
        self.parent_multi = None

    def has_tool(self, name: str) -> bool:
        return name in self.tools

    def get_available_tools(self) -> list:
        # Check if the cache is valid
        if self._cached_available_tools is not None:
            return self._cached_available_tools

        # If cache is not valid, regenerate the list
        result = []
        for tool_name, tool_data in self.tools.items():
            function_def = {
                "name": tool_name,
                "description": tool_data["description"],
                "parameters": {
                    "type": tool_data["inputSchema"].get("type", "object"),
                    "properties": tool_data["inputSchema"].get("properties", {}),
                    "required": tool_data["inputSchema"].get("required", []),
                },
            }
            result.append({"type": "function", "function": function_def})

        self._cached_available_tools = result  # Store the generated list in cache
        return result

    async def is_ready(self) -> bool:
        async with self.lock:
            return self.ready

    async def set_ready(self, status: bool):
        async with self.lock:
            self.ready = status
            if status:
                self.ready_event.set()
            else:
                self.ready_event.clear()

    async def add_tool(self, tool_data: dict):
        async with self.lock:
            sanitized_name = sanitize_tool_name(tool_data["name"])
            self.tools[sanitized_name] = tool_data
            self.name_mapping[sanitized_name] = tool_data["name"]
            self._cached_available_tools = (
                None  # Invalidate the cache when a tool is added
            )

    async def get_next_id(self) -> int:
        async with self.lock:
            current_id = self.next_id
            self.next_id += 1
            return current_id

    async def register_call_result_future(self, id: int, future: Future):
        async with self.lock:
            self.call_results[id] = future

    async def resolve_call_result(self, id: int, result: any):
        async with self.lock:
            if id in self.call_results:
                future = self.call_results.pop(id)
                if not future.done():
                    future.set_result(result)

    async def reject_call_result(self, id: int, exception: Exception):
        async with self.lock:
            if id in self.call_results:
                future = self.call_results.pop(id)
                if not future.done():
                    future.set_exception(exception)

    async def cleanup_call_result(self, id: int):
        async with self.lock:
            if id in self.call_results:
                self.call_results.pop(id)

    def set_websocket(self, websocket):
        """设置WebSocket连接"""
        self.websocket = websocket

    async def send_message(self, message: str):
        """发送消息到MCP接入点"""
        if self.websocket:
            await self.websocket.send(message)
        else:
            raise RuntimeError("WebSocket连接未建立")

    async def close(self):
        """关闭WebSocket连接"""
        if self.websocket:
            await self.websocket.close()
            self.websocket = None


class MultiMCPEndpointClient:
    """MCP接入点客户端管理器，支持同时连接多个MCP Server（Đa Endpoint MCP Hub）"""

    def __init__(self, conn=None):
        self.conn = conn
        self.clients = []  # List[MCPEndpointClient]
        self.ready_event = threading.Event()
        self.lock = asyncio.Lock()

    def add_client(self, client: MCPEndpointClient):
        """Thêm một MCP Client vào danh sách quản lý"""
        self.clients.append(client)
        if self.conn and not client.conn:
            client.conn = self.conn
        client.parent_multi = self
        if client.ready:
            self.ready_event.set()

    def has_tool(self, name: str) -> bool:
        """Kiểm tra xem bất kỳ MCP server nào có công cụ này không"""
        for client in self.clients:
            if client.has_tool(name):
                return True
        return False

    def get_client_for_tool(self, name: str):
        """Tìm MCP Client sở hữu công cụ được gọi"""
        for client in self.clients:
            if client.has_tool(name):
                return client
        return None

    def get_available_tools(self) -> list:
        """Tổng hợp danh sách công cụ từ tất cả các MCP Server đang kết nối"""
        all_tools = []
        seen_names = set()
        for client in self.clients:
            for tool in client.get_available_tools():
                func_name = tool.get("function", {}).get("name")
                if func_name and func_name not in seen_names:
                    seen_names.add(func_name)
                    all_tools.append(tool)
        return all_tools

    @property
    def ready(self) -> bool:
        if not self.clients:
            return False
        return any(c.ready for c in self.clients)

    @property
    def tools(self) -> dict:
        combined = {}
        for client in self.clients:
            combined.update(client.tools)
        return combined

    @property
    def name_mapping(self) -> dict:
        combined = {}
        for client in self.clients:
            combined.update(client.name_mapping)
        return combined

    async def is_ready(self) -> bool:
        if not self.clients:
            return False
        for client in self.clients:
            if await client.is_ready():
                return True
        return False

    async def close(self):
        """Đóng tất cả kết nối MCP WebSocket"""
        for client in self.clients:
            try:
                await client.close()
            except Exception as e:
                logger.bind(tag=TAG).error(f"Đóng kết nối MCP endpoint thất bại: {e}")
