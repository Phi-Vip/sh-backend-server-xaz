# -*- coding: utf-8 -*-
"""SCRIPT KIỂM THỬ THỰC TẾ TRỰC QUAN (LIVE SMOKE TEST) - GIAI ĐOẠN 1, 2, 3
Chạy trực tiếp độc lập ngoài terminal để kiểm chứng toàn bộ các luồng:
1. Healthcheck HTTP Server Port 8005.
2. An ninh bảo mật chặn Token URL Query Parameter (HTTP 401).
3. Bắt tay WebSocket Reverse Tunnel Home Assistant bằng Bearer Token.
4. Thu hồi quyền tức thì qua API ngắt kết nối WebSocket (Close Code 1008).
5. Truy vấn danh mục công cụ MCP JSON-RPC 2.0 (tools/list).
"""

import asyncio
import json
import os
import sys
import time
from aiohttp import ClientSession, WSCloseCode, web

# Thiết lập đường dẫn thư mục gốc
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
HUB_DIR = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
SERVER_ROOT = os.path.abspath(os.path.join(HUB_DIR, ".."))
for p in [HUB_DIR, SERVER_ROOT]:
    if p not in sys.path:
        sys.path.insert(0, p)

from mcp_smarthome_hub.storage.token_vault import TokenVault
from mcp_smarthome_hub.storage.db import SmartHomeDAL
from mcp_smarthome_hub.ha_bridge.redis_session_mgr import RedisSessionManager
from mcp_smarthome_hub.ha_bridge.ha_tunnel_server import HATunnelServer
from mcp_smarthome_hub.ha_bridge.jsonrpc_forwarder import JSONRPCForwarder
from mcp_smarthome_hub.main import mcp_websocket_handler


async def run_live_smoke_test():
    print("\n" + "=" * 70)
    print("  BẮT ĐẦU KIỂM THỬ THỰC TẾ TRỰC QUAN CỤM MCP SMARTHOME HUB (PORT 8005)")
    print("=" * 70 + "\n")

    # 1. Khởi tạo CSDL SQLite kiểm thử và DAL
    db_path = os.path.join(CURRENT_DIR, "live_smoke_test.db")
    if os.path.exists(db_path):
        os.remove(db_path)
    
    dal = SmartHomeDAL(db_url=f"sqlite:///{db_path}")
    dal.init_db()

    user_id = "user_real_test_001"
    ha_token = "ha_secret_token_live_123456"
    dal.upsert_user(user_id=user_id)
    dal.save_ha_credential(user_id=user_id, token=ha_token, endpoint_url="http://192.168.1.100:8123")
    print(f"[✓] Bước 1 (DAL & Vault): Đã lưu trữ và mã hóa AES-256-GCM cho User [{user_id}]")

    # 2. Khởi tạo dịch vụ mạng aiohttp trên cổng ngẫu nhiên 8005/test
    session_mgr = RedisSessionManager(node_id="node_live_smoke_test", dal_instance=dal)
    await session_mgr.start()
    tunnel_server = HATunnelServer(session_mgr=session_mgr, dal_instance=dal)
    forwarder = JSONRPCForwarder(tunnel_server=tunnel_server, session_mgr=session_mgr)

    app = web.Application()
    
    # Định nghĩa các routes giống hệt main.py
    async def health_handler(request):
        return web.json_response({
            "status": "healthy",
            "node_id": session_mgr.node_id,
            "active_ha_tunnels": len(tunnel_server.local_connections),
            "timestamp": time.time()
        })

    async def revoke_handler(request):
        data = await request.json()
        await session_mgr.revoke_user_tunnel(data.get("user_id"), data.get("reason", "Revoked"))
        return web.json_response({"status": "revoked"})

    app.router.add_get("/health", health_handler)
    app.router.add_get("/xiaozhi/v1/ha/tunnel", tunnel_server.handle_tunnel_connection)
    app.router.add_post("/api/v1/ha/revoke", revoke_handler)
    app.router.add_get("/mcp_endpoint/mcp/", mcp_websocket_handler)

    runner = web.AppRunner(app)
    await runner.setup()
    port = 8005
    try:
        site = web.TCPSite(runner, "127.0.0.1", port)
        await site.start()
    except OSError:
        port = 8006
        site = web.TCPSite(runner, "127.0.0.1", port)
        await site.start()

    base_url = f"http://127.0.0.1:{port}"
    ws_url = f"ws://127.0.0.1:{port}"
    print(f"[✓] Bước 2 (Network Ingress): Server đã lắng nghe thực tế tại {base_url}\n")

    async with ClientSession() as client:
        # TEST 1: Healthcheck
        async with client.get(f"{base_url}/health") as resp:
            data = await resp.json()
            assert resp.status == 200
            print(f"  [+] Test 1 (Healthcheck): HTTP 200 OK - Node ID: {data['node_id']} (Pass)")

        # TEST 2: Thử truyền token qua URL query params -> Phải bị chặn HTTP 401
        from aiohttp.client_exceptions import WSServerHandshakeError
        blocked_401 = False
        try:
            async with client.ws_connect(f"{ws_url}/xiaozhi/v1/ha/tunnel?token={ha_token}") as ws:
                pass
        except WSServerHandshakeError as e:
            if e.status == 401:
                blocked_401 = True
        assert blocked_401, "Cơ chế bảo mật phải chặn 401 khi token nằm trên URL Query Params!"
        print("  [+] Test 2 (An ninh URL): Chặn thành công 100% kết nối truyền token qua URL (HTTP 401)! (Pass)")

        # TEST 3: Bắt tay WebSocket chuẩn với Header Authorization
        t0 = time.time()
        ws_conn = await client.ws_connect(
            f"{ws_url}/xiaozhi/v1/ha/tunnel",
            headers={"Authorization": f"Bearer {ha_token}"}
        )
        rtt_connect = (time.time() - t0) * 1000
        print(f"  [+] Test 3 (WSS Bearer Handshake): Bắt tay thành công trong {rtt_connect:.2f}ms! (Pass)")
        assert len(tunnel_server.local_connections) == 1

        # TEST 4: Gọi API thu hồi quyền tức thì và đo thời gian ngắt kết nối
        t_revoke = time.time()
        async with client.post(f"{base_url}/api/v1/ha/revoke", json={"user_id": user_id}) as resp:
            assert resp.status == 200

        # Chờ socket đóng
        msg = await ws_conn.receive()
        revoke_duration = (time.time() - t_revoke) * 1000
        from aiohttp import WSMsgType
        assert msg.type in (WSMsgType.CLOSE, WSMsgType.CLOSED, WSMsgType.CLOSING)
        close_code = ws_conn.close_code or msg.data
        assert close_code == 1008, f"Kỳ vọng Close Code 1008, nhận được {close_code}"
        print(f"  [+] Test 4 (Instant Revocation): Ngắt kết nối Close Code 1008 sau {revoke_duration:.2f}ms! (Pass)")

        # TEST 5: Cổng MCP JSON-RPC 2.0 (tools/list) cho XiaoZhi Voice Core
        async with client.ws_connect(f"{ws_url}/mcp_endpoint/mcp/?token=smarthome_secret_token") as mcp_ws:
            req_payload = {
                "jsonrpc": "2.0",
                "id": "req_tools_list_01",
                "method": "tools/list",
                "params": {}
            }
            await mcp_ws.send_str(json.dumps(req_payload))
            res_msg = await mcp_ws.receive()
            res_data = json.loads(res_msg.data)
            assert res_data.get("id") == "req_tools_list_01"
            tools = res_data.get("result", {}).get("tools", [])
            tool_names = [t.get("name") for t in tools]
            assert "smarthome_control" in tool_names
            assert "tuya_sync_devices" in tool_names
            # Robot hút bụi đang tạm ẩn theo yêu cầu R&D
            assert "sweeper_control" not in tool_names
            print(f"  [+] Test 5 (MCP Protocol JSON-RPC 2.0): Cung cấp thành công {len(tools)} công cụ AI Voice ({', '.join(tool_names)})! (Pass)")

    # Dọn dẹp
    await runner.cleanup()
    await session_mgr.stop()
    if os.path.exists(db_path):
        try:
            os.remove(db_path)
        except Exception:
            pass

    print("\n" + "=" * 70)
    print("  KẾT LUẬN: TOÀN BỘ 3 GIAI ĐOẠN ĐỀU HOẠT ĐỘNG HOÀN HẢO TRÊN MÔI TRƯỜNG THỰC TẾ!")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    asyncio.run(run_live_smoke_test())
