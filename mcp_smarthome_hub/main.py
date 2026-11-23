# -*- coding: utf-8 -*-
"""MCP ENDPOINT SERVER NHÀ THÔNG MINH & HOME ASSISTANT HUB (PORT 8005)
Kiến trúc Microservice độc lập chuẩn JSON-RPC 2.0 dành cho hệ sinh thái XiaoZhi & Sunhouse.

Cung cấp:
1. HTTP GET /health: Healthcheck và báo cáo trạng thái các module kết nối.
2. WebSocket GET /mcp_endpoint/mcp/: Cổng kết nối MCP JSON-RPC 2.0 cho XiaoZhi Voice Server.
3. WebSocket GET /xiaozhi/v1/ha/tunnel: Điểm tiếp nhận đường hầm WebSocket ngược cho Home Assistant (Phase 3).
4. HTTP POST /api/v1/ha/revoke: API thu hồi quyền truy cập tức thì (Instant Revocation < 500ms).
"""

import asyncio
import json
import logging
import os
import sys
import time
from typing import Any, Dict, List, Optional
from aiohttp import web

# Cấu hình unbuffered stream cho console Windows CMD và vô hiệu hóa QuickEdit mode
# (Tránh Windows CMD tự động Pause/Suspend toàn bộ Server khi người dùng vô tình click chuột vào cửa sổ console)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(line_buffering=True)

if sys.platform == "win32":
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        h_stdin = kernel32.GetStdHandle(-10)  # STD_INPUT_HANDLE = -10
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(h_stdin, ctypes.byref(mode)):
            # Tắt bit 0x0040 (ENABLE_QUICK_EDIT_MODE) và bật bit 0x0080 (ENABLE_EXTENDED_FLAGS)
            kernel32.SetConsoleMode(h_stdin, (mode.value & ~0x0040) | 0x0080)
    except Exception:
        pass

# Thêm thư mục hiện tại vào sys.path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

# Nạp biến môi trường từ .env nếu có
env_file = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".env"))
if os.path.exists(env_file):
    with open(env_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

# Thiết lập ghi log chuẩn tiếng Việt
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("MCPSmartHomeHub")

# Khởi tạo các module cầu nối Home Assistant Phase 3
from ha_bridge.redis_session_mgr import RedisSessionManager
from ha_bridge.ha_tunnel_server import HATunnelServer
from ha_bridge.jsonrpc_forwarder import JSONRPCForwarder
from storage.db import default_dal
from storage.models import extract_mac_and_device_id
from storage.token_manager import token_manager
from clients.tuya_client import TuyaCloudClient
from dispatcher.context_injector import ContextInjector
from dispatcher.multisource_dispatcher import MultiSourceDispatcher
from tools.smarthome_tool import SmartHomeControlTool
from tools.sweeper_tool import SweeperControlTool
from tools.tuya_sync_tool import TuyaSyncTool

session_mgr = RedisSessionManager()
tunnel_server = HATunnelServer(session_mgr=session_mgr)
forwarder = JSONRPCForwarder(tunnel_server=tunnel_server, session_mgr=session_mgr)

# Khởi tạo Tuya Client nếu có cấu hình trong môi trường
tuya_client = None
if os.getenv("TUYA_CLIENT_ID") and os.getenv("TUYA_CLIENT_SECRET"):
    tuya_client = TuyaCloudClient(
        client_id=os.environ["TUYA_CLIENT_ID"],
        client_secret=os.environ["TUYA_CLIENT_SECRET"],
        base_url=os.getenv("TUYA_BASE_URL", "https://openapi-sg.iotbing.com"),
    )

context_injector = ContextInjector(dal_instance=default_dal)
dispatcher = MultiSourceDispatcher(
    dal_instance=default_dal,
    tuya_client=tuya_client,
    token_mgr=token_manager,
    ha_forwarder=forwarder,
    context_injector=context_injector,
)
smarthome_tool = SmartHomeControlTool(dispatcher=dispatcher)
sweeper_tool = SweeperControlTool(dispatcher=dispatcher)
sync_tool = TuyaSyncTool(dal=default_dal, tuya_client=tuya_client)

# Biến đếm kết nối client hoạt động
active_voice_connections = 0

def get_mcp_tools(user_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Tạo schema công cụ MCP động theo chuẩn JSON-RPC 2.0, tự động đồng bộ thiết bị của User."""
    tools = []
    clean_user = default_dal.resolve_user_id(user_id)

    # 1. Smarthome Control Tool
    st_def = {
        "name": smarthome_tool.tool_definition["name"],
        "description": smarthome_tool.tool_definition["description"],
        "inputSchema": smarthome_tool.tool_definition["inputSchema"],
    }
    # Truy vấn danh sách thiết bị thực tế của user từ DB
    try:
        user_devices = default_dal.list_devices_by_user(clean_user)
        # Tạm thời loại bỏ thiết bị robot hút bụi (category 'sd') đang trong quá trình phát triển
        user_devices = [d for d in user_devices if d.get("category") != "sd"]
    except Exception as e:
        logger.warning(f"Lỗi khi đọc danh sách thiết bị cho user {user_id}: {e}")
        user_devices = []

    if user_devices:
        bullets = []
        for d in user_devices:
            d_name = d.get("device_name", "Thiết bị")
            d_id = d.get("device_id")
            schema = d.get("raw_schema")
            cap_desc = ""
            if isinstance(schema, dict) and schema.get("synthesized_capabilities"):
                cap_desc = f", hỗ trợ: {schema['synthesized_capabilities']}"
            bullets.append(f"'{d_name}' (id: '{d_id}'{cap_desc})")
        dev_bullets = "; ".join(bullets)
        st_def["description"] = (
            "Điều khiển bật/tắt, tăng giảm độ sáng, đổi màu, chỉnh nhiệt độ, tốc độ hoặc tra cứu trạng thái thiết bị nhà thông minh. "
            f"Các thiết bị hiện có trong nhà: {dev_bullets}."
        )

    tools.append(st_def)

    # 2. Sweeper Control Tool (TẠM ẨN: thiết bị robot hút bụi đang trong quá trình phát triển chưa hoàn thiện)
    # sw_def = {
    #     "name": sweeper_tool.tool_definition["name"],
    #     "description": sweeper_tool.tool_definition["description"],
    #     "inputSchema": sweeper_tool.tool_definition["inputSchema"],
    # }
    # tools.append(sw_def)

    # 3. Tuya & Smart Home Sync Tool (BẮT BUỘC cho đồng bộ thiết bị Tuya / Smart Life)
    tools.append(sync_tool.tool_definition)

    return tools


async def health_handler(request: web.Request) -> web.Response:
    """Endpoint kiểm tra sức khỏe hệ thống (Health Check)."""
    user_id = default_dal.resolve_user_id(request.query.get("user_id") or request.query.get("device_id"))
    tools = get_mcp_tools(user_id=user_id)
    data = {
        "status": "healthy",
        "service": "mcp_smarthome_hub",
        "node_id": session_mgr.node_id,
        "active_voice_connections": active_voice_connections,
        "active_ha_tunnels": len(tunnel_server.local_connections),
        "mcp_tools_count": len(tools),
        "tools": [t["name"] for t in tools],
        "timestamp": time.time(),
    }
    return web.json_response(data)


async def revoke_ha_handler(request: web.Request) -> web.Response:
    """API thu hồi quyền đường hầm Home Assistant tức thì (Instant Revocation < 500ms)."""
    try:
        body = await request.json()
        user_id = body.get("user_id")
        reason = body.get("reason", "Người dùng thu hồi quyền qua ứng dụng")
        if not user_id:
            return web.json_response({"error": "Thiếu tham số 'user_id'"}, status=400)

        await session_mgr.revoke_user_tunnel(user_id, reason)
        return web.json_response(
            {
                "status": "success",
                "message": f"Đã phát sóng lệnh ngắt kết nối và thu hồi quyền User [{user_id}]",
            }
        )
    except Exception as e:
        logger.error(f"Lỗi xử lý thu hồi quyền HA: {e}")
        return web.json_response({"error": str(e)}, status=500)


async def mcp_websocket_handler(request: web.Request) -> web.StreamResponse:
    """Cổng kết nối WebSocket tiếp nhận giao thức MCP JSON-RPC 2.0 từ XiaoZhi Voice Server."""
    global active_voice_connections

    token = request.query.get("token")
    expected_token = os.environ.get("SMARTHOME_MCP_TOKEN", "smarthome_secret_token")

    # Nhận diện Device ID / Speaker MAC từ header hoặc query
    raw_dev_id = request.headers.get("device-id") or request.query.get("device_id") or request.query.get("device-id")
    raw_mac = request.headers.get("mac-address") or request.query.get("mac") or request.query.get("speaker_mac")
    
    speaker = None
    if raw_dev_id or raw_mac:
        mac, device_id = extract_mac_and_device_id(raw_dev_id or raw_mac)
        speaker = default_dal.get_speaker(mac or device_id)
    else:
        speaker = default_dal.get_first_speaker()
        if speaker:
            mac, device_id = speaker.speaker_mac, speaker.device_id
        else:
            mac, device_id = "unknown", f"speaker_{uuid.uuid4().hex[:6]}"

    raw_user_id = request.query.get("user_id")
    # Phân giải User ID chuẩn qua DAL dựa trên thực thể Loa hoặc User (không hardcode)
    conn_user_id = default_dal.resolve_user_id(raw_user_id or device_id or mac)
    if not speaker and mac != "unknown":
        speaker = default_dal.get_speaker(mac)

    if token != expected_token:
        logger.warning(
            f"Từ chối kết nối WebSocket từ {request.remote}: Token MCP không hợp lệ!"
        )
        return web.Response(
            status=401,
            text="Lỗi xác thực: Token MCP không hợp lệ hoặc bị thiếu!",
            content_type="text/plain",
            charset="utf-8",
        )

    ws = web.WebSocketResponse()
    await ws.prepare(request)

    active_voice_connections += 1
    print("\n" + "="*70)
    print(f"🔗 [MCP CONNECT] Loa XiaoZhi đã kết nối WebSocket MCP thành công!")
    print(f"   🔊 Device ID : {device_id} (MAC: {mac})")
    print(f"   👤 User ID   : {conn_user_id} {'(Đã liên kết)' if (speaker and speaker.user_id) else '(Mặc định = Device ID)'}")
    print(f"   🌐 Client IP : {request.remote}")
    print("="*70 + "\n", flush=True)

    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                try:
                    payload = json.loads(msg.data)
                except Exception as e:
                    logger.error(f"Bản tin không phải JSON hợp lệ: {msg.data} ({e})")
                    continue

                method = payload.get("method")
                msg_id = payload.get("id")

                # 1. Bắt tay khởi tạo (initialize)
                if method == "initialize":
                    client_info = payload.get("params", {}).get("clientInfo", {})
                    logger.info(
                        f"🤝 Bắt tay MCP Initialize từ: {client_info.get('name', 'XiaoZhi-Server')} v{client_info.get('version', '')}"
                    )
                    response = {
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "result": {
                            "protocolVersion": "2024-11-05",
                            "capabilities": {"tools": {"listChanged": True}},
                            "serverInfo": {
                                "name": "SmartHome-IoT-MCP-Hub",
                                "version": "2.0.0",
                            },
                        },
                    }
                    await ws.send_str(json.dumps(response, ensure_ascii=False))

                # 2. Xác nhận khởi tạo hoàn tất (notifications/initialized)
                elif method == "notifications/initialized":
                    logger.info("XiaoZhi Voice Server đã xác nhận khởi tạo hoàn tất.")

                # 3. Yêu cầu danh sách công cụ (tools/list)
                elif method == "tools/list":
                    tools_to_send = get_mcp_tools(user_id=conn_user_id)
                    print("\n" + "="*70)
                    print(f"📦 [MCP SMARTHOME HUB] ĐÃ GỬI DANH SÁCH {len(tools_to_send)} CÔNG CỤ TỚI XIAOZHI VOICE CORE:")
                    for t in tools_to_send:
                        print(f"   🔹 Tool: {t['name']}")
                    print("="*70 + "\n", flush=True)

                    response = {
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "result": {"tools": tools_to_send},
                    }
                    await ws.send_str(json.dumps(response, ensure_ascii=False))

                # 4. Yêu cầu thực thi công cụ (tools/call)
                elif method == "tools/call":
                    params = payload.get("params", {})
                    tool_name = params.get("name", "")
                    arguments = params.get("arguments", {})
                    user_id = params.get("user_id") or conn_user_id

                    start_time = time.time()
                    print("\n" + "#"*70)
                    print(f"⚡ [MCP SMARTHOME HUB] NHẬN LỆNH THỰC THI TỪ XIAOZHI LLM")
                    print(f"   👤 User ID   : {user_id}")
                    print(f"   🛠️ Tool Gọi  : {tool_name}")
                    print(f"   📝 Tham số   : {json.dumps(arguments, ensure_ascii=False)}")
                    print("#"*70, flush=True)

                    exec_res = {}
                    if tool_name == "smarthome_control":
                        exec_res = await smarthome_tool.execute(user_id=user_id, arguments=arguments)
                        res_text = exec_res.get("message", "Đã thực thi lệnh.")
                    elif tool_name == "sweeper_control":
                        exec_res = await sweeper_tool.execute(user_id=user_id, arguments=arguments)
                        res_text = exec_res.get("message", "Đã thực thi lệnh robot.")
                    elif tool_name in ["tuya_sync_devices", "smarthome_sync_devices"]:
                        exec_res = await sync_tool.execute(user_id=user_id, arguments=arguments)
                        res_text = exec_res.get("message", "Đã đồng bộ thiết bị.")
                    else:
                        res_text = f"Không tìm thấy công cụ MCP '{tool_name}'."

                    duration_ms = round((time.time() - start_time) * 1000, 2)
                    print("-" * 70)
                    print(f"✅ [MCP SMARTHOME HUB] KẾT QUẢ THỰC THI (Thời gian: {duration_ms}ms):")
                    print(f"   💬 Phản hồi  : {res_text}")
                    print(f"   📊 Dữ liệu   : {json.dumps(exec_res, ensure_ascii=False)}")
                    print("#"*70 + "\n", flush=True)

                    is_forbidden = exec_res.get("code") == 403 or exec_res.get("error") == "FORBIDDEN"
                    response = {
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "result": {
                            "content": [{"type": "text", "text": res_text}],
                            "structured_data": exec_res,
                            "isError": is_forbidden,
                        },
                    }
                    if is_forbidden:
                        response["error"] = {
                            "code": 403,
                            "message": "Access Denied: You do not own this device (403 Forbidden)",
                            "data": exec_res,
                        }
                    await ws.send_str(json.dumps(response, ensure_ascii=False))

                else:
                    if msg_id is not None:
                        err_res = {
                            "jsonrpc": "2.0",
                            "id": msg_id,
                            "error": {
                                "code": -32601,
                                "message": f"Method '{method}' not found",
                            },
                        }
                        await ws.send_str(json.dumps(err_res))

            elif msg.type == web.WSMsgType.ERROR:
                logger.error(f"Lỗi kết nối WebSocket: {ws.exception()}")

    finally:
        active_voice_connections -= 1
        print(f"\n🔌 [MCP DISCONNECT] XiaoZhi Voice Server đã ngắt kết nối MCP. Còn lại: {active_voice_connections}\n", flush=True)

    return ws


async def sync_devices_handler(request: web.Request) -> web.Response:
    """API kích hoạt đồng bộ thiết bị tức thì từ Tuya Cloud về CSDL cục bộ."""
    raw_id = request.query.get("user_id") or request.query.get("device_id") or request.headers.get("device-id")
    user_id = default_dal.resolve_user_id(raw_id)

    # 1. Ưu tiên đồng bộ qua Tuya Sharing SDK (Sharing Gateway) nếu có phiên lưu trữ
    from clients.tuya_sharing_manager import sharing_manager
    sharing_mgr = sharing_manager.get_manager(user_id)
    if sharing_mgr:
        logger.info(f"🔄 [API SYNC] Đồng bộ thiết bị qua Tuya Sharing Gateway cho user [{user_id}]...")
        synced = sharing_manager.sync_devices(user_id=user_id, dal=default_dal)
        synced = [d for d in synced if d.get("category") != "sd"]
        return web.json_response({
            "status": "success",
            "synced_count": len(synced),
            "devices": synced,
        })

    # 2. Fallback sang Tuya Developer OpenAPI cũ nếu có cấu hình
    if not tuya_client:
        return web.json_response({"status": "error", "message": "TuyaClient chưa được cấu hình"}, status=400)

    from sync.device_syncer import sync_tuya_devices
    synced = await sync_tuya_devices(dal=default_dal, tuya_client=tuya_client, user_id=user_id)
    # Tạm thời loại bỏ robot hút bụi (category 'sd') đang phát triển chưa hoàn thiện
    synced = [d for d in synced if d.get("category") != "sd"]
    return web.json_response({
        "status": "success",
        "synced_count": len(synced),
        "devices": synced,
    })


def create_app() -> web.Application:
    """Tạo và cấu hình ứng dụng aiohttp web app."""
    app = web.Application()

    # Khởi tạo và dọn dẹp các dịch vụ nền
    async def on_startup(application):
        await session_mgr.start()
        # Khởi tạo lại tất cả các phiên Tuya Sharing SDK đã lưu trong CSDL
        try:
            from clients.tuya_sharing_manager import sharing_manager
            restored = sharing_manager.restore_all_sessions(dal=default_dal)
            logger.info(f"📱 [ON-STARTUP] Đã tự động khôi phục {restored} phiên Tuya Sharing SDK từ CSDL.")
        except Exception as e_restore_all:
            logger.error(f"⚠️ [ON-STARTUP] Lỗi khôi phục Tuya Sharing sessions: {e_restore_all}")

        # Đồng bộ một lần duy nhất khi khởi động server
        if tuya_client:
            from sync.device_syncer import sync_tuya_devices
            logger.info("🔄 [ON-STARTUP] Đang đồng bộ danh mục thiết bị từ Tuya Cloud khi khởi động...")
            sync_user = default_dal.resolve_user_id(None)
            asyncio.create_task(sync_tuya_devices(dal=default_dal, tuya_client=tuya_client, user_id=sync_user))

    async def on_cleanup(application):
        await session_mgr.stop()

    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)

    # Routes kiểm tra sức khỏe
    app.router.add_get("/health", health_handler)
    app.router.add_get("/mcp_endpoint/health", health_handler)

    # Route kích hoạt đồng bộ thiết bị thủ công
    app.router.add_get("/api/v1/devices/sync", sync_devices_handler)
    app.router.add_post("/api/v1/devices/sync", sync_devices_handler)

    # Routes WebSocket cho XiaoZhi Voice Core (hỗ trợ mọi đường dẫn và alias)
    app.router.add_get("/mcp_endpoint/mcp/", mcp_websocket_handler)
    app.router.add_get("/mcp_endpoint/mcp", mcp_websocket_handler)
    app.router.add_get("/mcp_endpoint/call/", mcp_websocket_handler)
    app.router.add_get("/mcp_endpoint/call", mcp_websocket_handler)
    app.router.add_get("/mcp/", mcp_websocket_handler)
    app.router.add_get("/mcp", mcp_websocket_handler)
    app.router.add_get("/call/", mcp_websocket_handler)
    app.router.add_get("/call", mcp_websocket_handler)

    # Route WebSocket Ingress cho Home Assistant Reverse Tunnel (Phase 3)
    app.router.add_get("/xiaozhi/v1/ha/tunnel", tunnel_server.handle_tunnel_connection)

    # Route REST API thu hồi quyền tức thì (Instant Revocation)
    app.router.add_post("/api/v1/ha/revoke", revoke_ha_handler)

    # Routes Giai đoạn 5 (Phase 5): Ghép nối Loa qua PIN, eSunhouse OEM Sync & Tuya OAuth2 / QR Ticket
    from routers import (
        create_pairing_router,
        create_esunhouse_router,
        create_tuya_auth_router,
        create_portal_router,
        create_ota_pairing_router,
        create_agent_profile_router,
    )

    # Cầu nối giao thức OTA XiaoZhi (Port 8005) - Giai đoạn 1
    ota_pairing_router = create_ota_pairing_router(dal=default_dal)
    app.router.add_post("/xiaozhi/ota/", ota_pairing_router["check_version"])
    app.router.add_post("/xiaozhi/ota", ota_pairing_router["check_version"])
    app.router.add_get("/xiaozhi/ota/", ota_pairing_router["check_version"])
    app.router.add_get("/xiaozhi/ota", ota_pairing_router["check_version"])
    app.router.add_post("/ota/", ota_pairing_router["check_version"])
    app.router.add_post("/ota", ota_pairing_router["check_version"])
    app.router.add_get("/ota/", ota_pairing_router["check_version"])
    app.router.add_get("/ota", ota_pairing_router["check_version"])

    app.router.add_post("/xiaozhi/ota/activate", ota_pairing_router["activate_status"])
    app.router.add_post("/ota/activate", ota_pairing_router["activate_status"])
    app.router.add_get("/xiaozhi/ota/activate", ota_pairing_router["activate_status"])
    app.router.add_get("/ota/activate", ota_pairing_router["activate_status"])

    app.router.add_get("/xiaozhi/ota/status", ota_pairing_router["ota_status"])
    app.router.add_get("/ota/status", ota_pairing_router["ota_status"])

    pairing_router = create_pairing_router(dal=default_dal)
    app.router.add_post("/api/v1/pairing/generate-pin", pairing_router["generate_pin"])
    app.router.add_post("/api/v1/pairing/claim-pin", pairing_router["claim_pin"])
    app.router.add_post("/api/v1/pairing/bind-user", pairing_router["bind_user"])
    app.router.add_post("/api/v1/pairing/delete-speaker", pairing_router["delete_speaker"])
    app.router.add_delete("/api/v1/pairing/speakers/{speaker_id}", pairing_router["delete_speaker"])

    esunhouse_router = create_esunhouse_router(dal=default_dal)
    app.router.add_post("/api/v1/auth/esunhouse/sync-oem-devices", esunhouse_router["sync_oem_devices"])

    tuya_auth_router = create_tuya_auth_router(dal=default_dal, tuya_client=tuya_client)
    app.router.add_get("/api/v1/auth/tuya/authorize-url", tuya_auth_router["get_authorize_url"])
    app.router.add_post("/api/v1/auth/tuya/qr-ticket", tuya_auth_router["create_qr_ticket"])
    app.router.add_get("/api/v1/auth/tuya/qr-ticket/{ticket_id}/status", tuya_auth_router["get_qr_ticket_status"])
    app.router.add_post("/api/v1/auth/tuya/qr-ticket/{ticket_id}/confirm", tuya_auth_router["confirm_qr_ticket"])
    app.router.add_post("/api/v1/auth/tuya/oauth-callback", tuya_auth_router["oauth_callback"])
    app.router.add_get("/api/v1/auth/tuya/callback", tuya_auth_router["oauth_callback"])
    app.router.add_post("/api/v1/auth/tuya/link-account", tuya_auth_router["link_account"])
    app.router.add_post("/api/v1/auth/tuya/unlink", tuya_auth_router["unlink_account"])
    app.router.add_get("/api/v1/auth/tuya/unlink", tuya_auth_router["unlink_account"])
    app.router.add_post("/api/v1/admin/clean-database", tuya_auth_router["clean_database"])

    portal_router = create_portal_router(dal=default_dal, tuya_client=tuya_client, token_mgr=token_manager)
    app.router.add_get("/portal", portal_router["portal_page"])
    app.router.add_get("/", portal_router["portal_page"])

    # Cụm Route Cấu hình Agent Động & Quản trị Cá nhân hóa (Task 3.1 & 3.2 - Giai đoạn 3)
    agent_profile_router = create_agent_profile_router(dal=default_dal)
    app.router.add_post("/config/agent-models", agent_profile_router["get_agent_models"])
    app.router.add_post("/api/v1/manager/config/agent-models", agent_profile_router["get_agent_models"])
    app.router.add_post("/config/correct-words", agent_profile_router["get_correct_words"])
    app.router.add_post("/api/v1/manager/config/correct-words", agent_profile_router["get_correct_words"])
    app.router.add_post("/config/server-base", agent_profile_router["get_server_base"])
    app.router.add_post("/api/v1/manager/config/server-base", agent_profile_router["get_server_base"])
    app.router.add_post("/api/v1/agent/profile", agent_profile_router["update_agent_profile"])
    app.router.add_put("/api/v1/agent/profile", agent_profile_router["update_agent_profile"])
    app.router.add_get("/api/v1/agent/profile", agent_profile_router["get_agent_profile_admin"])

    return app


if __name__ == "__main__":
    port = int(os.environ.get("SMARTHOME_MCP_PORT", 8005))
    logger.info("======================================================================")
    logger.info(f"   KHỞI ĐỘNG SMARTHOME & HOME ASSISTANT MCP HUB SERVER (CỔNG {port})")
    logger.info("======================================================================")
    logger.info(f"- Developer Web Portal  : http://127.0.0.1:{port}/portal")
    logger.info(f"- OTA Protocol Bridge   : http://127.0.0.1:{port}/xiaozhi/ota/")
    logger.info(f"- Health Check HTTP     : http://127.0.0.1:{port}/health")
    logger.info(f"- WebSocket MCP Endpoint: ws://127.0.0.1:{port}/mcp_endpoint/mcp/")
    logger.info(f"- HA Reverse Tunnel Ingr: ws://127.0.0.1:{port}/xiaozhi/v1/ha/tunnel")
    logger.info("======================================================================")

    app = create_app()
    web.run_app(app, host="0.0.0.0", port=port)
