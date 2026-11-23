"""
MCP ENDPOINT SERVER TRUNG TÂM (PORT 8004)
Kiến trúc Modular Plug-and-Play chuẩn JSON-RPC 2.0 dành cho hệ sinh thái XiaoZhi.
Hỗ trợ cả WebSocket Tunnel cho XiaoZhi Server và HTTP Health Check cho trình duyệt.
"""

import os
import sys
import json
import logging
from aiohttp import web

# Thêm thư mục hiện tại vào sys.path để import modules
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from tools import registry, discover_tools

# Cấu hình logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("MCPEndpointServer")

# Đếm số lượng kết nối robot/client hiện tại
active_connections = 0

async def health_handler(request: web.Request) -> web.Response:
    """HTTP GET /mcp_endpoint/health: Trả về trạng thái hoạt động của Server"""
    key = request.query.get("key", "default")
    tools = registry.get_tools_list()
    
    data = {
        "jsonrpc": "2.0",
        "id": None,
        "result": {
            "status": "success",
            "server": "Sunhouse-MCP-Endpoint-Server",
            "version": "1.0.0",
            "key": key,
            "tools_count": len(tools),
            "tools": [t["name"] for t in tools],
            "connections": {
                "tool_connections": len(tools),
                "robot_connections": active_connections,
                "total_connections": active_connections + len(tools)
            }
        },
        "error": None
    }
    return web.json_response(data)

async def websocket_handler(request: web.Request) -> web.WebSocketResponse:
    """WebSocket GET /mcp_endpoint/mcp/: Cổng kết nối JSON-RPC 2.0 của XiaoZhi Server"""
    global active_connections
    token = request.query.get("token", "")
    client_ip = request.remote

    ws = web.WebSocketResponse()
    await ws.prepare(request)

    active_connections += 1
    logger.info(f"==> XiaoZhi Client đã kết nối từ {client_ip} (Token: '{token}'). Tổng kết nối: {active_connections}")

    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                try:
                    payload = json.loads(msg.data)
                    logger.debug(f"Nhận bản tin: {payload}")
                except Exception as e:
                    logger.error(f"Gói tin không phải JSON hợp lệ: {msg.data} ({e})")
                    continue

                method = payload.get("method")
                msg_id = payload.get("id")

                # 1. Bắt tay khởi tạo (initialize)
                if method == "initialize":
                    client_info = payload.get("params", {}).get("clientInfo", {})
                    logger.info(f"Bắt tay MCP Initialize từ: {client_info.get('name', 'Unknown')} v{client_info.get('version', '')}")
                    
                    response = {
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "result": {
                            "protocolVersion": "2024-11-05",
                            "capabilities": {
                                "tools": {"listChanged": True}
                            },
                            "serverInfo": {
                                "name": "Sunhouse-MCP-Hub",
                                "version": "1.0.0"
                            }
                        }
                    }
                    await ws.send_str(json.dumps(response, ensure_ascii=False))

                # 2. Thông báo khởi tạo hoàn tất (notifications/initialized)
                elif method == "notifications/initialized":
                    logger.info("XiaoZhi Client đã xác nhận hoàn tất khởi tạo MCP.")

                # 3. Yêu cầu danh sách công cụ (tools/list)
                elif method == "tools/list":
                    tools = registry.get_tools_list()
                    logger.info(f"Gửi danh sách công cụ cho XiaoZhi ({len(tools)} tools: {[t['name'] for t in tools]})")
                    
                    response = {
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "result": {
                            "tools": tools
                        }
                    }
                    await ws.send_str(json.dumps(response, ensure_ascii=False))

                # 4. Yêu cầu thực thi công cụ (tools/call)
                elif method == "tools/call":
                    params = payload.get("params", {})
                    tool_name = params.get("name", "")
                    arguments = params.get("arguments", {})
                    
                    logger.info(f"==> Yêu cầu gọi Tool: '{tool_name}' | Tham số: {arguments}")
                    
                    try:
                        result_text = await registry.execute_tool(tool_name, arguments)
                        logger.info(f"<== Kết quả Tool '{tool_name}' thành công: {result_text[:120]}...")
                        response = {
                            "jsonrpc": "2.0",
                            "id": msg_id,
                            "result": {
                                "content": [
                                    {
                                        "type": "text",
                                        "text": result_text
                                    }
                                ]
                            }
                        }
                    except Exception as e:
                        logger.error(f"Lỗi khi thực thi Tool '{tool_name}': {e}")
                        response = {
                            "jsonrpc": "2.0",
                            "id": msg_id,
                            "error": {
                                "code": -32603,
                                "message": f"Internal tool execution error: {str(e)}"
                            }
                        }
                    
                    await ws.send_str(json.dumps(response, ensure_ascii=False))

                else:
                    logger.warning(f"Phương thức JSON-RPC chưa hỗ trợ: {method}")
                    if msg_id is not None:
                        err_res = {
                            "jsonrpc": "2.0",
                            "id": msg_id,
                            "error": {
                                "code": -32601,
                                "message": f"Method '{method}' not found"
                            }
                        }
                        await ws.send_str(json.dumps(err_res))

            elif msg.type == web.WSMsgType.ERROR:
                logger.error(f"Lỗi kết nối WebSocket: {ws.exception()}")

    except Exception as e:
        logger.error(f"Ngoại lệ phiên WebSocket: {e}")
    finally:
        active_connections = max(0, active_connections - 1)
        logger.info(f"<== XiaoZhi Client {client_ip} đã ngắt kết nối. Còn lại: {active_connections}")

    return ws

def create_app() -> web.Application:
    app = web.Application()
    
    # Định tuyến HTTP và WebSocket
    app.router.add_get("/", health_handler)
    app.router.add_get("/health", health_handler)
    app.router.add_get("/mcp_endpoint/health", health_handler)
    
    app.router.add_get("/mcp_endpoint/mcp", websocket_handler)
    app.router.add_get("/mcp_endpoint/mcp/", websocket_handler)
    app.router.add_get("/mcp_endpoint/call", websocket_handler)
    app.router.add_get("/mcp_endpoint/call/", websocket_handler)
    app.router.add_get("/mcp", websocket_handler)
    app.router.add_get("/mcp/", websocket_handler)
    app.router.add_get("/call", websocket_handler)
    app.router.add_get("/call/", websocket_handler)
    
    return app

def main():
    # 1. Tự động quét và nạp các plugin tool trong thư mục tools/
    logger.info("Đang quét và đăng ký công cụ trong thư mục tools/...")
    discover_tools()
    tools = registry.get_tools_list()
    logger.info(f"==> Đã nạp thành công {len(tools)} công cụ: {[t['name'] for t in tools]}")

    port = int(os.environ.get("MCP_PORT", 8004))
    host = os.environ.get("MCP_HOST", "0.0.0.0")

    app = create_app()
    
    print("\n" + "="*70)
    print("🚀  SUNHOUSE MCP ENDPOINT SERVER ĐANG CHẠY")
    print("="*70)
    print(f"👉  Địa chỉ Web Health:   http://127.0.0.1:{port}/mcp_endpoint/health?key=default")
    print(f"👉  Địa chỉ WebSocket:    ws://127.0.0.1:{port}/mcp_endpoint/mcp/?token=sunhouse_secret_token")
    print(f"👉  Công cụ đang nạp:     {[t['name'] for t in tools]}")
    print("="*70 + "\n")

    web.run_app(app, host=host, port=port, print=None)

if __name__ == "__main__":
    main()
