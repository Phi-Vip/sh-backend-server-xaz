# -*- coding: utf-8 -*-
"""KIỂM THỬ GIAI ĐOẠN 5: TÍCH HỢP ĐỒNG BỘ ESUNHOUSE, OAUTH2 / QR TICKET & NGHIỆM THU THƯƠNG MẠI.

Mục tiêu kiểm thử:
1. Cụm API Ghép nối Loa thông minh (PIN Pairing): generate-pin, claim-pin, kiểm tra hết hạn/trùng lặp.
2. Cụm API Đồng bộ thiết bị Tuya OEM từ Backend eSunhouse (PlatformType = 2).
3. Cụm API Tuya OAuth2 Authorize URL, QR Ticket & OAuth Callback lưu trữ an toàn.
4. Đánh giá Năng lực Phục vụ Bất đồng bộ (Async Micro-Benchmark 30 luồng đồng thời < 200ms).
"""

import os
import sys
import json
import time
import asyncio
from contextlib import asynccontextmanager
import pytest
from unittest.mock import AsyncMock, MagicMock
from aiohttp import web, ClientSession

# Thêm đường dẫn thư mục gốc vào sys.path
SERVER_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HUB_ROOT = os.path.join(SERVER_ROOT, "mcp_smarthome_hub")
if SERVER_ROOT not in sys.path:
    sys.path.insert(0, SERVER_ROOT)
if HUB_ROOT not in sys.path:
    sys.path.insert(0, HUB_ROOT)

from storage.db import SmartHomeDAL
from storage.models import PlatformType
from routers.pairing_router import create_pairing_router
from routers.esunhouse_router import create_esunhouse_router
from routers.tuya_auth_router import create_tuya_auth_router


@pytest.fixture
def test_dal():
    """Tạo một phiên bản SmartHomeDAL in-memory độc lập cho kiểm thử."""
    dal = SmartHomeDAL("sqlite:///:memory:")
    return dal


@pytest.fixture
def mock_tuya_client():
    """Tạo mock TuyaCloudClient hỗ trợ OAuth2 và QR Code."""
    client = MagicMock()
    client.client_id = "test_tuya_client_id_123"
    client.get_token = AsyncMock(
        return_value={
            "access_token": "mock_tuya_user_access_token_abc",
            "refresh_token": "mock_tuya_user_refresh_token_xyz",
            "expire_time": 7200,
            "uid": "bay179456789user",
        }
    )
    client.request = AsyncMock(
        return_value={
            "success": True,
            "result": {"qrcode": "tuya://smartlife/qrcode_mock_val"},
        }
    )
    return client


@pytest.fixture
def make_ephemeral_server():
    """Tạo máy chủ aiohttp tạm thời trên cổng ngẫu nhiên độc lập 100%."""
    @asynccontextmanager
    async def _make(app):
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        try:
            yield f"http://127.0.0.1:{port}"
        finally:
            await runner.cleanup()

    return _make


def build_phase5_app(dal, mock_tuya):
    """Khởi tạo aiohttp Application với đầy đủ các Router của Phase 5."""
    app = web.Application()

    # 1. Pairing Router
    pairing_router = create_pairing_router(dal=dal)
    app.router.add_post("/api/v1/pairing/generate-pin", pairing_router["generate_pin"])
    app.router.add_post("/api/v1/pairing/claim-pin", pairing_router["claim_pin"])
    app.router.add_post("/api/v1/pairing/bind-user", pairing_router["bind_user"])
    app.router.add_post("/api/v1/pairing/delete-speaker", pairing_router["delete_speaker"])
    app.router.add_delete("/api/v1/pairing/speakers/{speaker_id}", pairing_router["delete_speaker"])

    # 2. eSunhouse Router
    esunhouse_router = create_esunhouse_router(dal=dal)
    app.router.add_post(
        "/api/v1/auth/esunhouse/sync-oem-devices",
        esunhouse_router["sync_oem_devices"],
    )

    # 3. Tuya Auth Router
    tuya_auth_router = create_tuya_auth_router(dal=dal, tuya_client=mock_tuya)
    app.router.add_get(
        "/api/v1/auth/tuya/authorize-url",
        tuya_auth_router["get_authorize_url"],
    )
    app.router.add_post(
        "/api/v1/auth/tuya/qr-ticket",
        tuya_auth_router["create_qr_ticket"],
    )
    app.router.add_post(
        "/api/v1/auth/tuya/oauth-callback",
        tuya_auth_router["oauth_callback"],
    )
    app.router.add_get(
        "/api/v1/auth/tuya/callback",
        tuya_auth_router["oauth_callback"],
    )

    # Health route
    async def health_handler(request):
        return web.json_response({"status": "healthy", "time": time.time()})

    app.router.add_get("/health", health_handler)

    return app


@pytest.mark.asyncio
async def test_pairing_flow_generate_and_claim_pin(make_ephemeral_server, test_dal, mock_tuya_client):
    """Test 1: Kiểm thử toàn trình quy trình Ghép nối Loa ESP32 (PIN Generation & Claim)."""
    app = build_phase5_app(test_dal, mock_tuya_client)

    async with make_ephemeral_server(app) as base_url:
        async with ClientSession() as client:
            speaker_mac = "aa:bb:cc:dd:ee:ff"
            user_id = "user_real_phi"

            # 1. Loa ESP32 yêu cầu sinh mã PIN
            async with client.post(
                f"{base_url}/api/v1/pairing/generate-pin",
                json={"speaker_mac": speaker_mac, "expire_seconds": 300},
            ) as resp:
                assert resp.status == 200
                data = await resp.json()
                assert data["status"] == "success"
                assert "pairing_code" in data
                pin = data["pairing_code"]
                assert len(pin) == 6
                assert pin.isdigit()

            # 2. Ứng dụng di động xác nhận ghép nối với mã PIN hợp lệ
            async with client.post(
                f"{base_url}/api/v1/pairing/claim-pin",
                json={"pairing_code": pin, "user_id": user_id},
            ) as claim_resp:
                assert claim_resp.status == 200
                claim_data = await claim_resp.json()
                assert claim_data["status"] == "success"
                assert claim_data["speaker_mac"] == speaker_mac
                assert claim_data["user_id"] == user_id

            # 3. Kiểm tra trong CSDL: Bảng speakers phải có bản ghi liên kết Loa - User
            speaker_record = test_dal.get_speaker(speaker_mac)
            assert speaker_record is not None
            assert speaker_record.user_id == user_id

            # 4. Thử claim lại mã PIN đã sử dụng -> Phải bị từ chối (400)
            async with client.post(
                f"{base_url}/api/v1/pairing/claim-pin",
                json={"pairing_code": pin, "user_id": "another_user"},
            ) as reclaim_resp:
                assert reclaim_resp.status == 400

            # 5. Thử claim mã PIN không tồn tại -> Phải bị từ chối (400)
            async with client.post(
                f"{base_url}/api/v1/pairing/claim-pin",
                json={"pairing_code": "000000", "user_id": user_id},
            ) as invalid_resp:
                assert invalid_resp.status == 400


@pytest.mark.asyncio
async def test_esunhouse_sync_oem_devices(make_ephemeral_server, test_dal, mock_tuya_client):
    """Test 2: Kiểm thử đồng bộ thiết bị OEM từ eSunhouse Backend (PlatformType = 2)."""
    app = build_phase5_app(test_dal, mock_tuya_client)

    async with make_ephemeral_server(app) as base_url:
        async with ClientSession() as client:
            user_id = "user_esunhouse_tester"
            oem_devices = [
                {
                    "device_id": "sh_robot_298pro_alpha",
                    "device_name": "Robot hút bụi 298 Pro Ultra",
                    "category": "sd",
                    "product_id": "pid_298pro_ultra",
                    "is_online": True,
                    "local_key": "localkey_robot16",
                    "local_ip": "192.168.1.188",
                    "raw_schema": {
                        "functions": [
                            {"code": "power", "type": "Boolean", "values": "{}"},
                            {
                                "code": "mode",
                                "type": "Enum",
                                "values": json.dumps({"range": ["smart", "wall_follow", "spiral"]}),
                            },
                        ]
                    },
                },
                {
                    "device_id": "sh_kettle_smart_02",
                    "device_name": "Bình đun nước thông minh Sunhouse",
                    "category": "cs",
                    "product_id": "pid_kettle_smart",
                    "is_online": True,
                    "raw_schema": {
                        "functions": [
                            {"code": "switch", "type": "Boolean", "values": "{}"},
                            {"code": "temp_set", "type": "Integer", "values": json.dumps({"min": 40, "max": 100})},
                        ]
                    },
                },
            ]

            # Gửi Webhook đồng bộ
            async with client.post(
                f"{base_url}/api/v1/auth/esunhouse/sync-oem-devices",
                json={"user_id": user_id, "devices": oem_devices},
            ) as resp:
                assert resp.status == 200
                data = await resp.json()
                assert data["status"] == "success"
                assert data["synced_count"] == 2

            # Kiểm tra trong CSDL cục bộ qua DAL
            dev1 = test_dal.get_device("sh_robot_298pro_alpha")
            assert dev1 is not None
            assert dev1["device_name"] == "Robot hút bụi 298 Pro Ultra"
            assert dev1["platform_type"] == PlatformType.TUYA_OEM_ESUNHOUSE
            assert dev1["local_key"] == "localkey_robot16"

            dev2 = test_dal.get_device("sh_kettle_smart_02")
            assert dev2 is not None
            assert dev2["category"] == "cs"
            assert dev2["platform_type"] == PlatformType.TUYA_OEM_ESUNHOUSE

            # Kiểm tra lấy toàn bộ thiết bị của user
            user_devs = test_dal.list_devices_by_user(user_id)
            assert len(user_devs) == 2


@pytest.mark.asyncio
async def test_tuya_auth_endpoints(make_ephemeral_server, test_dal, mock_tuya_client):
    """Test 3: Kiểm thử Authorize URL, QR Ticket và OAuth Callback trao đổi Token."""
    app = build_phase5_app(test_dal, mock_tuya_client)

    async with make_ephemeral_server(app) as base_url:
        async with ClientSession() as client:
            user_id = "user_real_phi"

            # 1. Lấy Authorize URL
            async with client.get(
                f"{base_url}/api/v1/auth/tuya/authorize-url",
                params={"user_id": user_id},
            ) as auth_resp:
                assert auth_resp.status == 200
                auth_data = await auth_resp.json()
                assert auth_data["status"] == "success"
                assert "tuya.com/authorize?" in auth_data["authorize_url"]
                assert "auth-sg.tuya.com" in auth_data["authorize_url"] or "auth.tuya.com" in auth_data["authorize_url"]
                assert "client_id=" in auth_data["authorize_url"]
                assert "response_type=code" in auth_data["authorize_url"]

            # 2. Tạo QR Ticket
            async with client.post(
                f"{base_url}/api/v1/auth/tuya/qr-ticket",
                json={"user_id": user_id},
            ) as qr_resp:
                assert qr_resp.status == 200
                qr_data = await qr_resp.json()
                assert qr_data["status"] == "success"
                assert "ticket_id" in qr_data
                assert "qr_payload" in qr_data
                assert qr_data["expire_seconds"] == 600

            # 3. Trao đổi Authorization Code qua OAuth Callback
            async with client.post(
                f"{base_url}/api/v1/auth/tuya/oauth-callback",
                json={"code": "tuya_auth_code_123456", "user_id": user_id},
            ) as callback_resp:
                assert callback_resp.status == 200
                cb_data = await callback_resp.json()
                assert cb_data["status"] == "success"
                assert cb_data["user_id"] == user_id
                assert "external_tuya_uid" in cb_data

            # 4. Xác minh CSDL: Token người dùng đã được giải mã chính xác từ vault
            cred = test_dal.get_user_credential(user_id)
            assert cred is not None
            assert cred["access_token"] == "mock_tuya_user_access_token_abc"
            assert cred["refresh_token"] == "mock_tuya_user_refresh_token_xyz"


@pytest.mark.asyncio
async def test_async_micro_benchmark_concurrent_load(make_ephemeral_server, test_dal, mock_tuya_client):
    """Test 4 (Benchmark): Đo lường năng lực phục vụ bất đồng bộ với 30 kết nối song song (< 200ms)."""
    app = build_phase5_app(test_dal, mock_tuya_client)

    async with make_ephemeral_server(app) as base_url:
        num_requests = 30
        speaker_base_mac = "68:ee:8f:4d:87:"

        async with ClientSession() as client:
            async def single_call(i):
                mac = f"{speaker_base_mac}{i:02x}"
                t0 = time.perf_counter()
                # Gọi sinh PIN
                async with client.post(
                    f"{base_url}/api/v1/pairing/generate-pin",
                    json={"speaker_mac": mac},
                ) as resp:
                    t_gen = (time.perf_counter() - t0) * 1000
                    assert resp.status == 200
                    data = await resp.json()
                    pin = data["pairing_code"]

                # Gọi claim PIN
                t1 = time.perf_counter()
                async with client.post(
                    f"{base_url}/api/v1/pairing/claim-pin",
                    json={"pairing_code": pin, "user_id": f"benchmark_user_{i}"},
                ) as claim_resp:
                    t_claim = (time.perf_counter() - t1) * 1000
                    assert claim_resp.status == 200

                return t_gen, t_claim

            t_start = time.perf_counter()
            # Chạy 30 luồng đồng thời bằng asyncio.gather
            results = await asyncio.gather(*(single_call(i) for i in range(num_requests)))
            total_time = (time.perf_counter() - t_start) * 1000

            gen_times = [r[0] for r in results]
            claim_times = [r[1] for r in results]

            avg_gen = sum(gen_times) / len(gen_times)
            avg_claim = sum(claim_times) / len(claim_times)
            max_gen = max(gen_times)

            print(f"\n📊 [BENCHMARK RESULTS] 30 Concurrent Pairing Calls:")
            print(f"   ⏱️ Tổng thời gian: {total_time:.2f}ms cho {num_requests*2} transactions")
            print(f"   ⚡ Trung bình Generate PIN: {avg_gen:.2f}ms (Max: {max_gen:.2f}ms)")
            print(f"   ⚡ Trung bình Claim PIN   : {avg_claim:.2f}ms")

            # Tiêu chí KPI: Thời gian trung bình mỗi tác vụ REST API phải < 200ms
            assert avg_gen < 200.0
            assert avg_claim < 200.0
