# -*- coding: utf-8 -*-
"""BỘ KIỂM THỬ TOÀN DIỆN GIAI ĐOẠN 3: HOME ASSISTANT REVERSE WEBSOCKET MCP BRIDGE.

Tuân thủ nghiêm ngặt bảng tiêu chí TEST CASE 3 (Pass Gate 3):
1. KIỂM THỬ BẢO MẬT BẮT TAY (BEARER TOKEN HANDSHAKE):
   - Chặn 100% kết nối thiếu header Authorization (HTTP 401).
   - Chặn 100% kết nối truyền token qua URL query params (HTTP 401).
   - Chặn token giả / sai định dạng (HTTP 401).
   - Cho phép kết nối thành công khi truyền đúng 'Authorization: Bearer <valid_token>' (HTTP 101).
2. KIỂM THỬ ĐIỀU PHỐI ĐA NODE (REDIS PUB/SUB BRIDGE):
   - Giả lập Node B nhận lệnh điều khiển thiết bị Home Assistant của User.
   - Node B publish lệnh qua Redis -> Node A (đang giữ socket của User) đẩy xuống HA Client.
   - HA Client xử lý và phản hồi -> Node A publish về Redis cho Node B.
   - Đo độ trễ vòng lặp RTT liên node < 25ms.
3. KIỂM THỬ THU HỒI TOKEN TỨC THÌ (INSTANT REVOCATION < 500MS):
   - Kích hoạt API thu hồi quyền truy cập của User.
   - Đường hầm WebSocket lập tức bị đóng với Close Frame 1008 (WS_CLOSE_POLICY_VIOLATION) trong vòng < 500ms.
   - Bản ghi Redis session và trạng thái DB được dọn dẹp sạch sẽ.
4. KIỂM THỬ XỬ LÝ LỖI NGOẠI TUYẾN (GRACEFUL DEGRADATION):
   - Khi User offline, Forwarder ném ngoại lệ rõ ràng mà không gây treo hay nghẽn luồng.
"""

import os
import sys
import time
import json
import uuid
import asyncio
from contextlib import asynccontextmanager
import pytest
from aiohttp import web, ClientSession, WSMsgType, WSCloseCode

# Đảm bảo đường dẫn thư mục gốc xiaozhi-esp32-server luôn có trong sys.path
SERVER_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if SERVER_ROOT not in sys.path:
    sys.path.insert(0, SERVER_ROOT)

from mcp_smarthome_hub.storage.db import SmartHomeDAL
from mcp_smarthome_hub.storage.token_vault import TokenVault
from mcp_smarthome_hub.ha_bridge import (
    RedisSessionManager,
    HATunnelServer,
    JSONRPCForwarder,
    HAForwarderException,
    HAUserOfflineException,
)


@pytest.fixture
def test_dal():
    """Khởi tạo SmartHomeDAL chạy trên SQLite Memory biệt lập cho mỗi test."""
    dal = SmartHomeDAL(db_url="sqlite:///:memory:")
    dal.init_db()
    return dal


@pytest.fixture
def valid_ha_user(test_dal):
    """Tạo người dùng mẫu và cấp phát Bearer Token hợp lệ cho Home Assistant."""
    user_id = "user_ha_prosumer_001"
    raw_token = "ha_secret_bearer_token_xyz987"
    test_dal.upsert_user(user_id=user_id)
    test_dal.save_ha_credential(
        user_id=user_id,
        token=raw_token,
        endpoint_url="http://homeassistant.local:8123",
        tunnel_id="tunnel_001",
    )
    return {
        "user_id": user_id,
        "token": raw_token,
    }


@pytest.fixture
def make_ephemeral_server():
    """Tạo máy chủ aiohttp tạm thời trên cổng ngẫu nhiên độc lập 100%."""
    @asynccontextmanager
    async def _make(app):
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        # Lấy cổng thực tế do hệ điều hành cấp
        port = site._server.sockets[0].getsockname()[1]
        try:
            yield f"http://127.0.0.1:{port}"
        finally:
            await runner.cleanup()

    return _make


# =============================================================================
# BÀI TEST 1: KIỂM THỬ BẢO MẬT BẮT TAY (BEARER TOKEN HANDSHAKE SECURITY)
# =============================================================================

@pytest.mark.asyncio
async def test_bearer_token_handshake_security(make_ephemeral_server, test_dal, valid_ha_user):
    """Kiểm chứng 100% các tiêu chuẩn an ninh bắt tay đường hầm WebSocket."""
    session_mgr = RedisSessionManager(node_id="node_test_sec", dal_instance=test_dal)
    await session_mgr.start()
    tunnel_server = HATunnelServer(session_mgr=session_mgr, dal_instance=test_dal)

    app = web.Application()
    app.router.add_get("/xiaozhi/v1/ha/tunnel", tunnel_server.handle_tunnel_connection)

    user_id = valid_ha_user["user_id"]
    valid_token = valid_ha_user["token"]

    async with make_ephemeral_server(app) as base_url:
        ws_url = f"{base_url}/xiaozhi/v1/ha/tunnel"

        async with ClientSession() as client:
            # 1.1. Chặn request không có Header Authorization (Trả về 401)
            resp1 = await client.get(ws_url)
            assert resp1.status == 401
            text1 = await resp1.text()
            assert "Thiếu Header 'Authorization: Bearer <token>'" in text1
            print("\n✓ [PASS 1.1]: Chặn thành công kết nối thiếu Header Authorization (HTTP 401)")

            # 1.2. Chặn request truyền token qua URL Query Parameter (Trả về 401 chống rò rỉ token)
            url_with_query = f"{ws_url}?token={valid_token}"
            resp2 = await client.get(url_with_query)
            assert resp2.status == 401
            text2 = await resp2.text()
            assert "Tuyệt đối không truyền token trên URL query param" in text2
            print("✓ [PASS 1.2]: Chặn thành công kết nối truyền token trên URL query param (HTTP 401)")

            # 1.3. Chặn request truyền Header không đúng định dạng Bearer (Trả về 401)
            resp3 = await client.get(ws_url, headers={"Authorization": "Basic dXNlcjpwYXNz"})
            assert resp3.status == 401
            text3 = await resp3.text()
            assert "phải có định dạng 'Bearer <token>'" in text3
            print("✓ [PASS 1.3]: Chặn thành công kết nối sai định dạng Authorization (HTTP 401)")

            # 1.4. Chặn request truyền Bearer Token giả / không có trong CSDL (Trả về 401)
            resp4 = await client.get(ws_url, headers={"Authorization": "Bearer fake_token_123456"})
            assert resp4.status == 401
            text4 = await resp4.text()
            assert "Token không hợp lệ hoặc đã bị thu hồi" in text4
            print("✓ [PASS 1.4]: Chặn thành công kết nối dùng Bearer Token giả (HTTP 401)")

            # 1.5. Chấp nhận kết nối khi truyền đúng Header 'Authorization: Bearer <valid_token>' (HTTP 101)
            ws_conn = await client.ws_connect(
                ws_url,
                headers={"Authorization": f"Bearer {valid_token}"},
                autoping=True,
            )
            assert not ws_conn.closed
            assert tunnel_server.is_user_local(user_id)
            assert await session_mgr.is_user_online(user_id)
            print("✓ [PASS 1.5]: Bắt tay WebSocket thành công 100% với Header Authorization hợp lệ!")

            await ws_conn.close()

    await session_mgr.stop()


# =============================================================================
# BÀI TEST 2: ĐIỀU PHỐI LỆNH CỤC BỘ & ĐO RTT (< 5MS)
# =============================================================================

@pytest.mark.asyncio
async def test_local_forwarding_and_rtt(make_ephemeral_server, test_dal, valid_ha_user):
    """Kiểm thử gửi lệnh xuống HA Client cùng Node và đo độ trễ RTT."""
    session_mgr = RedisSessionManager(node_id="node_local_01", dal_instance=test_dal)
    await session_mgr.start()
    tunnel_server = HATunnelServer(session_mgr=session_mgr, dal_instance=test_dal)
    forwarder = JSONRPCForwarder(tunnel_server=tunnel_server, session_mgr=session_mgr)

    app = web.Application()
    app.router.add_get("/xiaozhi/v1/ha/tunnel", tunnel_server.handle_tunnel_connection)

    user_id = valid_ha_user["user_id"]
    valid_token = valid_ha_user["token"]

    async with make_ephemeral_server(app) as base_url:
        ws_url = f"{base_url}/xiaozhi/v1/ha/tunnel"

        async with ClientSession() as client:
            ws = await client.ws_connect(
                ws_url,
                headers={"Authorization": f"Bearer {valid_token}"},
            )

            # Giả lập tiến trình HA Client phản hồi lệnh
            async def ha_client_mock():
                msg = await ws.receive()
                if msg.type == WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    req_id = data.get("id")
                    res = {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "entity_id": "light.living_room",
                            "state": "on",
                            "brightness": 255,
                        },
                    }
                    await ws.send_str(json.dumps(res))

            client_task = asyncio.create_task(ha_client_mock())

            t0 = time.perf_counter()
            result = await forwarder.call_service(
                user_id=user_id,
                domain="light",
                service="turn_on",
                target={"entity_id": "light.living_room"},
                service_data={"brightness": 255},
            )
            rtt_ms = (time.perf_counter() - t0) * 1000

            await client_task
            await ws.close()

            assert result["state"] == "on"
            assert result["brightness"] == 255
            assert rtt_ms < 20.0
            print(f"\n✓ [PASS 2]: Điều phối lệnh cục bộ thành công! RTT = {rtt_ms:.3f}ms (< 20ms)")

    await session_mgr.stop()


# =============================================================================
# BÀI TEST 3: ĐIỀU PHỐI ĐA NODE LIÊN CONTAINER QUA REDIS PUB/SUB (< 25MS)
# =============================================================================

@pytest.mark.asyncio
async def test_cross_node_redis_pubsub_bridge(make_ephemeral_server, test_dal, valid_ha_user):
    """Mô phỏng 2 Node phân tán: Node B nhận lệnh từ Voice Core -> Bridge qua Redis -> Node A gửi HA."""
    user_id = valid_ha_user["user_id"]
    valid_token = valid_ha_user["token"]

    # 1. Khởi tạo Node A (Nơi HA Client thực tế kết nối vào)
    session_mgr_a = RedisSessionManager(node_id="node_a_ingress", dal_instance=test_dal)
    await session_mgr_a.start()
    tunnel_server_a = HATunnelServer(session_mgr=session_mgr_a, dal_instance=test_dal)
    _ = JSONRPCForwarder(tunnel_server=tunnel_server_a, session_mgr=session_mgr_a)

    # 2. Khởi tạo Node B (Nơi XiaoZhi Voice Core nhận khẩu lệnh của người dùng)
    session_mgr_b = RedisSessionManager(node_id="node_b_voice_core", dal_instance=test_dal)
    await session_mgr_b.start()
    tunnel_server_b = HATunnelServer(session_mgr=session_mgr_b, dal_instance=test_dal)
    forwarder_b = JSONRPCForwarder(tunnel_server=tunnel_server_b, session_mgr=session_mgr_b)

    # Đăng ký handler lắng nghe command trên Node A
    session_mgr_a.on_command(tunnel_server_a._handle_remote_command)

    # Chạy Server trên Node A
    app_a = web.Application()
    app_a.router.add_get("/xiaozhi/v1/ha/tunnel", tunnel_server_a.handle_tunnel_connection)

    async with make_ephemeral_server(app_a) as base_url_a:
        ws_url_a = f"{base_url_a}/xiaozhi/v1/ha/tunnel"

        async with ClientSession() as client:
            ws = await client.ws_connect(
                ws_url_a,
                headers={"Authorization": f"Bearer {valid_token}"},
            )

            assert await session_mgr_b.get_session_node(user_id) == "node_a_ingress"

            async def mock_ha_worker():
                msg = await ws.receive()
                if msg.type == WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    req_id = data.get("id")
                    res = {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "domain": "climate",
                            "service": "set_temperature",
                            "target_temperature": 24.5,
                            "status": "success",
                        },
                    }
                    await ws.send_str(json.dumps(res))

            client_task = asyncio.create_task(mock_ha_worker())

            t_start = time.perf_counter()
            result_b = await forwarder_b.call_service(
                user_id=user_id,
                domain="climate",
                service="set_temperature",
                target={"entity_id": "climate.living_room"},
                service_data={"temperature": 24.5},
                timeout=2.0,
            )
            cross_rtt_ms = (time.perf_counter() - t_start) * 1000

            await client_task
            await ws.close()

            assert result_b["status"] == "success"
            assert result_b["target_temperature"] == 24.5
            assert cross_rtt_ms < 25.0  # Tiêu chuẩn Pass Gate < 25ms
            print(f"\n✓ [PASS 3]: Điều phối liên node xuyên container thành công! RTT = {cross_rtt_ms:.3f}ms (< 25ms)")

    await session_mgr_a.stop()
    await session_mgr_b.stop()


# =============================================================================
# BÀI TEST 4: THU HỒI QUYỀN TỨC THÌ (INSTANT REVOCATION < 500MS & CODE 1008)
# =============================================================================

@pytest.mark.asyncio
async def test_instant_revocation_close_code_1008(make_ephemeral_server, test_dal, valid_ha_user):
    """Kiểm chứng tính năng thu hồi quyền tức thì ngắt kết nối WebSocket trong < 500ms với mã 1008."""
    session_mgr = RedisSessionManager(node_id="node_revoker", dal_instance=test_dal)
    await session_mgr.start()
    tunnel_server = HATunnelServer(session_mgr=session_mgr, dal_instance=test_dal)

    app = web.Application()
    app.router.add_get("/xiaozhi/v1/ha/tunnel", tunnel_server.handle_tunnel_connection)

    user_id = valid_ha_user["user_id"]
    valid_token = valid_ha_user["token"]

    async with make_ephemeral_server(app) as base_url:
        ws_url = f"{base_url}/xiaozhi/v1/ha/tunnel"

        async with ClientSession() as client:
            ws = await client.ws_connect(
                ws_url,
                headers={"Authorization": f"Bearer {valid_token}"},
            )
            assert not ws.closed
            assert tunnel_server.is_user_local(user_id)

            t0 = time.perf_counter()
            await session_mgr.revoke_user_tunnel(user_id=user_id, reason="Admin thu hồi chứng thực bảo mật")

            msg = await ws.receive()
            revocation_time_ms = (time.perf_counter() - t0) * 1000

            assert ws.closed
            assert msg.type in (WSMsgType.CLOSE, WSMsgType.CLOSED)
            # Mã đóng WSCloseCode.POLICY_VIOLATION = 1008
            assert ws.close_code == 1008
            assert revocation_time_ms < 500.0  # Tiêu chí < 500ms

            assert test_dal.get_ha_credential(user_id) is None
            assert not await session_mgr.is_user_online(user_id)

            print(
                f"\n✓ [PASS 4]: Thu hồi quyền tức thì ngắt kết nối thành công! "
                f"Close Code = {ws.close_code} (1008 Policy Violation), Thời gian: {revocation_time_ms:.2f}ms (< 500ms)"
            )

    await session_mgr.stop()


# =============================================================================
# BÀI TEST 5: XỬ LÝ LỖI KHI HA CLIENT NGOẠI TUYẾN (GRACEFUL DEGRADATION)
# =============================================================================

@pytest.mark.asyncio
async def test_offline_user_handling(test_dal):
    """Kiểm tra khi user chưa kết nối tunnel, Forwarder ném ngoại lệ rõ ràng không gây treo worker."""
    session_mgr = RedisSessionManager(node_id="node_offline_test", dal_instance=test_dal)
    await session_mgr.start()
    tunnel_server = HATunnelServer(session_mgr=session_mgr, dal_instance=test_dal)
    forwarder = JSONRPCForwarder(tunnel_server=tunnel_server, session_mgr=session_mgr)

    unconnected_user = "user_never_connected_999"

    with pytest.raises(HAUserOfflineException) as exc_info:
        await forwarder.call_service(
            user_id=unconnected_user,
            domain="switch",
            service="turn_on",
            target={"entity_id": "switch.water_heater"},
        )

    assert "ngoại tuyến hoặc chưa ghép nối" in str(exc_info.value)
    print("\n✓ [PASS 5]: Xử lý chuẩn xác khi HA client ngoại tuyến, ném HAUserOfflineException thành công!")

    await session_mgr.stop()
