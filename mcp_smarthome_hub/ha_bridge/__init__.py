# -*- coding: utf-8 -*-
"""Package Cầu Nối Ngược Home Assistant WebSocket & MCP Bridge (ha_bridge).

Cung cấp:
- RedisSessionManager: Quản trị phiên kết nối phân tán và thu hồi quyền tức thì qua Redis Pub/Sub.
- HATunnelServer: Điểm Ingress WebSocket wss://.../ha/tunnel bảo mật Bearer Token.
- JSONRPCForwarder: Bộ chuyển tiếp lệnh MCP JSON-RPC 2.0 nội bộ và xuyên node < 15ms.
"""

from .redis_session_mgr import RedisSessionManager
from .ha_tunnel_server import HATunnelServer
from .jsonrpc_forwarder import (
    JSONRPCForwarder,
    HAForwarderException,
    HAUserOfflineException,
)

__all__ = [
    "RedisSessionManager",
    "HATunnelServer",
    "JSONRPCForwarder",
    "HAForwarderException",
    "HAUserOfflineException",
]
