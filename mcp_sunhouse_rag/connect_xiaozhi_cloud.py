"""
CẦU NỐI MCP CLIENT KẾT NỐI TRỰC TIẾP LÊN CLOUD XIAOZHI TRUNG QUỐC (XIAOZHI.ME)
--------------------------------------------------------------------------------
Script này đóng vai trò MCP Client/Worker, chủ động kết nối đường hầm WebSocket bảo mật
đến XiaoZhi Cloud (wss://api.xiaozhi.me/mcp/?token=...).

TÍNH NĂNG:
1. Đăng ký toàn bộ công cụ Tri thức Sunhouse (tra_cuu_ma_loi, tra_cuu_thong_tin, tim_kiem_truc_tuyen)
   lên Cloud XiaoZhi mà KHÔNG CẦN sửa bất kỳ dòng code nào trên phần cứng ESP32.
2. Tự động duy trì kết nối (Heartbeat / Auto-reconnect) nếu rớt mạng.
3. Nhận lệnh `tools/call` từ AI Cloud và trả về câu trả lời chính xác từ Database Sunhouse.
"""

import os
import sys
import json
import asyncio
import logging
import argparse
import websockets

# Thêm thư mục mcp_server vào sys.path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from tools import registry, discover_tools

# Cấu hình logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("XiaoZhiCloudMCP")

# Endpoint mặc định (người dùng có thể dán URL có token vào đây hoặc truyền tham số)
DEFAULT_ENDPOINT = os.environ.get("XIAOZHI_MCP_ENDPOINT", "")

async def handle_message(ws, raw_msg):
    try:
        payload = json.loads(raw_msg)
    except Exception as e:
        logger.error(f"Gói tin nhận được không phải JSON hợp lệ: {raw_msg} ({e})")
        return

    method = payload.get("method")
    msg_id = payload.get("id")

    # 1. Bắt tay khởi tạo (initialize)
    if method == "initialize":
        client_info = payload.get("params", {}).get("clientInfo", {})
        logger.info(f"🤝 Nhận yêu cầu Initialize từ Cloud XiaoZhi: {client_info.get('name', 'Cloud')} v{client_info.get('version', '')}")
        response = {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {"listChanged": True}
                },
                "serverInfo": {
                    "name": "Sunhouse-Knowledge-MCP-Hub",
                    "version": "2.0.0"
                }
            }
        }
        await ws.send(json.dumps(response, ensure_ascii=False))
        logger.info("✅ Đã phản hồi Initialize cho Cloud thành công.")

    # 2. Xác nhận khởi tạo
    elif method == "notifications/initialized":
        logger.info("🎉 Cloud XiaoZhi đã xác nhận phiên MCP kết nối hoàn tất!")

    # 3. Cloud yêu cầu danh sách Tool (tools/list)
    elif method == "tools/list":
        tools = registry.get_tools_list()
        logger.info(f"📋 Gửi danh sách {len(tools)} công cụ Sunhouse lên Cloud:")
        for t in tools:
            logger.info(f"   🔹 Tool: {t['name']}")
        response = {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "tools": tools
            }
        }
        await ws.send(json.dumps(response, ensure_ascii=False))

    # 4. AI trên Cloud gọi thực thi Tool (tools/call)
    elif method == "tools/call":
        params = payload.get("params", {})
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})
        logger.info(f"⚡ [AI GỌI TOOL] '{tool_name}' | Tham số: {arguments}")

        try:
            result_text = await registry.execute_tool(tool_name, arguments)
            preview = (result_text[:120] + "...") if len(result_text) > 120 else result_text
            logger.info(f"✅ [TRẢ VỀ KẾT QUẢ] Tool '{tool_name}': {preview}")
            response = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": result_text
                        }
                    ],
                    "isError": False
                }
            }
        except Exception as e:
            logger.error(f"❌ Lỗi khi thực thi Tool '{tool_name}': {e}")
            response = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {
                    "code": -32603,
                    "message": f"Tool execution failed: {str(e)}"
                }
            }
        await ws.send(json.dumps(response, ensure_ascii=False))

    # 5. Ping / Pong hoặc các method khác
    elif method == "ping":
        await ws.send(json.dumps({"jsonrpc": "2.0", "id": msg_id, "result": "pong"}))
    else:
        logger.warning(f"Phương thức chưa hỗ trợ từ Cloud: {method}")
        if msg_id is not None:
            err_res = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {
                    "code": -32601,
                    "message": f"Method '{method}' not implemented"
                }
            }
            await ws.send(json.dumps(err_res))

async def connect_loop(endpoint_url: str):
    logger.info(f"🚀 Bắt đầu kết nối tới XiaoZhi Cloud MCP Endpoint: {endpoint_url[:35]}... (đã ẩn token)")
    retry_delay = 3

    while True:
        try:
            logger.info("⏳ Đang thiết lập kết nối WebSocket tới Cloud...")
            async with websockets.connect(
                endpoint_url,
                ping_interval=20,
                ping_timeout=20,
                close_timeout=10
            ) as ws:
                logger.info("🟢 ĐÃ KẾT NỐI THÀNH CÔNG ĐẾN XIAOZHI CLOUD MCP ENDPOINT!")
                print("\n" + "="*70)
                print("🌟 TRẠNG THÁI TRÊN WEB XIAOZHI.ME BÂY GIỜ SẼ LÀ: [Connected]")
                print("👉 Bạn có thể bấm nút [Save] trên trang web xiaozhi.me để lưu cấu hình.")
                print("👉 Giờ hãy cầm loa ESP32 lên và hỏi về mã lỗi hoặc thông tin Sunhouse!")
                print("="*70 + "\n")

                retry_delay = 3  # Reset retry delay

                async for raw_msg in ws:
                    await handle_message(ws, raw_msg)

        except websockets.exceptions.ConnectionClosed as e:
            logger.warning(f"⚠️ Kết nối WebSocket bị đóng bởi Server ({e}). Thử lại sau {retry_delay}s...")
        except Exception as e:
            logger.error(f"❌ Lỗi kết nối: {e}. Thử kết nối lại sau {retry_delay}s...")

        await asyncio.sleep(retry_delay)
        retry_delay = min(retry_delay * 1.5, 30)

def main():
    parser = argparse.ArgumentParser(description="XiaoZhi Cloud MCP Bridge for Sunhouse")
    parser.add_argument("url", nargs="?", default=DEFAULT_ENDPOINT, help="Đường link wss://api.xiaozhi.me/mcp/?token=...")
    args = parser.parse_args()

    endpoint = args.url.strip().strip('"\'')
    if not endpoint:
        print("\n" + "="*70)
        print("🔗 KET NOI CONG CU TRI THUC SUNHOUSE LEN XIAOZHI CLOUD (XIAOZHI.ME)")
        print("="*70)
        print("Vui long dan dia chi 'Endpoint URL' tu giao dien web xiaozhi.me:")
        print("(Vi du: wss://api.xiaozhi.me/mcp/?token=abc123xyz...)")
        try:
            endpoint = input("\n👉 Nhap Endpoint URL: ").strip().strip('"\'')
        except (EOFError, KeyboardInterrupt):
            endpoint = ""

    if not endpoint or not endpoint.startswith("ws"):
        print("\n❌ LOI: Dia chi Endpoint URL khong hop le! Phai bat dau bang 'wss://' hoac 'ws://'.")
        sys.exit(1)

    # 1. Nạp danh sách Tool Sunhouse
    logger.info("Đang quét và đăng ký các công cụ Sunhouse...")
    discover_tools()
    tools = registry.get_tools_list()
    logger.info(f"Đã nạp sẵn sàng {len(tools)} công cụ: {[t['name'] for t in tools]}")

    # 2. Khởi chạy vòng lặp kết nối
    try:
        asyncio.run(connect_loop(endpoint))
    except KeyboardInterrupt:
        print("\nĐã ngắt kết nối theo yêu cầu người dùng.")

if __name__ == "__main__":
    main()
