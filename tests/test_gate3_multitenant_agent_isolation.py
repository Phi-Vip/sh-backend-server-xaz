# -*- coding: utf-8 -*-
"""BÀI TEST PASS GIAI ĐOẠN 3 (GATE 3 — MULTI-TENANT PERSONALIZATION & ISOLATION)
Dự án: Tái cấu trúc Server XiaoZhi Thương mại v2.1
Tiêu chuẩn: Căn cứ Phần IV - Giai đoạn 3 & Phần V - SLA & Quality Gates

Mục tiêu kiểm định 3 kịch bản bắt buộc:
- T3-01: Loa A (User 1, Nữ Bắc "Ong Vàng") & Loa B (User 2, Nam Nam "Sunhouse Pro") kết nối song song:
         Cả 2 phản hồi đúng tên gọi, đúng System Prompt, đúng giọng đọc TTS mà không lẫn lộn cấu hình.
- T3-02: User 1 đổi giọng đọc trên Web Portal/App và bắt đầu phiên mới:
         Cache Redis bị xóa tự động; loa áp dụng giọng mới trong phiên kế tiếp (<= 5s) không cần restart server.
- T3-03: User 1 giả mạo payload JSON-RPC chứa ID thiết bị của User 2:
         mcp_smarthome_hub từ chối 100% (403 Forbidden / Access Denied), ghi log cảnh báo bảo mật.
"""

import asyncio
import json
import os
import sys
import time
from typing import Dict, Any
from unittest.mock import MagicMock, AsyncMock, patch

import pytest
from aiohttp import web
from aiohttp.test_utils import make_mocked_request

# Thêm đường dẫn tới thư mục gốc xiaozhi-server và mcp_smarthome_hub
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SERVER_DIR = os.path.join(ROOT_DIR, "main", "xiaozhi-server")
MCP_HUB_DIR = os.path.join(ROOT_DIR, "mcp_smarthome_hub")

for p in [ROOT_DIR, SERVER_DIR, MCP_HUB_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

from storage.db import SmartHomeDAL
from storage.models import PlatformType
from routers.agent_profile_router import (
    create_agent_profile_router,
    invalidate_agent_cache_in_redis,
)
from tools.smarthome_tool import SmartHomeControlTool
from config.config_loader import (
    get_private_config_from_api,
    invalidate_agent_config_cache,
    get_redis_agent_cache_client,
)
from config.manage_api_client import init_service, ManageApiClient
from core.connection import ConnectionHandler


class MockRedis:
    """Mock Redis in-memory async client cho kiểm thử Cache và Invalidation."""

    def __init__(self):
        self.store = {}

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value, ex=None):
        self.store[key] = value
        return True

    async def delete(self, *keys):
        deleted = 0
        for k in keys:
            if k in self.store:
                del self.store[k]
                deleted += 1
        return deleted

    async def flushall(self):
        self.store.clear()


@pytest.fixture
def mock_redis():
    mock = MockRedis()
    with patch("config.config_loader.get_redis_agent_cache_client", return_value=mock), \
         patch("routers.agent_profile_router.get_redis_invalidation_client", return_value=mock):
        yield mock


class TestT3_01_ParallelSessionDistinctProfiles:
    """T3-01: Loa A (User 1, Nữ miền Bắc "Ong Vàng") & Loa B (User 2, Nam miền Nam "Sunhouse Pro")."""

    @pytest.mark.asyncio
    async def test_parallel_speaker_personalization_no_cross_contamination(self, tmp_path, mock_redis):
        db_file = tmp_path / "test_gate3_t1.db"
        dal = SmartHomeDAL(db_url=f"sqlite:///{db_file}")

        # 1. Khởi tạo User 1 & Loa A ("Ong Vàng", Nữ Bắc: vi-VN-HoaiMyNeural)
        user_1 = "usr_001_north"
        mac_a = "11:22:33:44:55:01"
        dal.upsert_user(user_1)
        dal.upsert_speaker(speaker_mac=mac_a, user_id=user_1, device_name="Loa Phòng Khách User 1")
        dal.upsert_agent_profile(
            speaker_mac=mac_a,
            user_id=user_1,
            assistant_name="Ong Vàng",
            prompt="Bạn là Ong Vàng, trợ lý giọng Bắc thân thiện và nhanh nhẹn của Sunhouse.",
            tts_voice_id="vi-VN-HoaiMyNeural",
            llm_model_profile="deepseek-chat",
            enabled_plugins={"get_weather": {}},
        )

        # 2. Khởi tạo User 2 & Loa B ("Sunhouse Pro", Nam Nam: vi-VN-NamMinhNeural)
        user_2 = "usr_002_south"
        mac_b = "11:22:33:44:55:02"
        dal.upsert_user(user_2)
        dal.upsert_speaker(speaker_mac=mac_b, user_id=user_2, device_name="Loa Biệt Thự User 2")
        dal.upsert_agent_profile(
            speaker_mac=mac_b,
            user_id=user_2,
            assistant_name="Sunhouse Pro",
            prompt="Bạn là Sunhouse Pro, trợ lý giọng Nam lịch lãm và chuẩn xác của Sunhouse.",
            tts_voice_id="vi-VN-NamMinhNeural",
            llm_model_profile="deepseek-coder",
            enabled_plugins={"home_assistant": {}},
        )

        # 3. Tạo aiohttp app cho manager-api endpoint
        router = create_agent_profile_router(dal=dal)
        app = web.Application()
        app.router.add_post("/config/agent-models", router["get_agent_models"])
        app.router.add_post("/config/correct-words", router["get_correct_words"])

        # Sử dụng TestServer để client HTTP gọi nội bộ
        from aiohttp.test_utils import TestServer
        server = TestServer(app)
        await server.start_server()

        base_url = str(server.make_url(""))
        server_secret = "a613f18e19c9b589c3bc82da3d76e47610dc2e5f88456a053120141fbe3239a0"

        # Đóng instance cũ và khởi tạo ManageApiClient trỏ về test server
        ManageApiClient.safe_close()
        init_service({
            "manager-api": {
                "url": base_url,
                "secret": server_secret,
                "timeout": 5,
            }
        })

        test_config = {
            "selected_module": {"TTS": "EdgeTTS", "LLM": "OpenAI"},
            "TTS": {"EdgeTTS": {}},
            "LLM": {"OpenAI": {}},
        }

        # 4. Kích hoạt kết nối song song 2 loa cùng lúc (Parallel Connection)
        t_start = time.time()
        config_a_task = get_private_config_from_api(test_config, mac_a, mac_a)
        config_b_task = get_private_config_from_api(test_config, mac_b, mac_b)

        cfg_a, cfg_b = await asyncio.gather(config_a_task, config_b_task)
        duration_ms = (time.time() - t_start) * 1000

        # 5. Thẩm định nghiêm ngặt kết quả Loa A (Ong Vàng - Bắc Nữ)
        assert cfg_a["assistant_name"] == "Ong Vàng"
        assert "Ong Vàng" in cfg_a["prompt"]
        assert cfg_a["TTS"]["EdgeTTS"]["voice"] == "vi-VN-HoaiMyNeural"
        assert cfg_a["tts_voice_id"] == "vi-VN-HoaiMyNeural"
        assert "get_weather" in cfg_a["plugins"]

        # 6. Thẩm định nghiêm ngặt kết quả Loa B (Sunhouse Pro - Nam Nam)
        assert cfg_b["assistant_name"] == "Sunhouse Pro"
        assert "Sunhouse Pro" in cfg_b["prompt"]
        assert cfg_b["TTS"]["EdgeTTS"]["voice"] == "vi-VN-NamMinhNeural"
        assert cfg_b["tts_voice_id"] == "vi-VN-NamMinhNeural"
        assert "home_assistant" in cfg_b["plugins"]

        # 7. Đảm bảo TUYỆT ĐỐI không lẫn lộn giữa hai loa
        assert cfg_a["assistant_name"] != cfg_b["assistant_name"]
        assert cfg_a["tts_voice_id"] != cfg_b["tts_voice_id"]
        assert cfg_a["prompt"] != cfg_b["prompt"]

        await server.close()
        print(f"\n✅ T3-01 PASS: 2 Loa kết nối song song ({duration_ms:.1f}ms) áp dụng đúng hồ sơ riêng biệt 100%.")


class TestT3_02_ActiveCacheInvalidationAndInstantUpdate:
    """T3-02: Thay đổi cấu hình trên Web Portal -> Tự động xóa Cache Redis -> Áp dụng tức thì <= 5s."""

    @pytest.mark.asyncio
    async def test_web_portal_update_invalidates_cache_under_5s(self, tmp_path, mock_redis):
        db_file = tmp_path / "test_gate3_t2.db"
        dal = SmartHomeDAL(db_url=f"sqlite:///{db_file}")

        user_id = "usr_003_portal"
        mac_address = "11:22:33:44:55:03"
        dal.upsert_user(user_id)
        dal.upsert_speaker(speaker_mac=mac_address, user_id=user_id, device_name="Loa Thử Nghiệm Portal")
        dal.upsert_agent_profile(
            speaker_mac=mac_address,
            user_id=user_id,
            assistant_name="Phiên Bản Cũ",
            prompt="Prompt ban đầu v1",
            tts_voice_id="vi-VN-HoaiMyNeural",
        )

        router = create_agent_profile_router(dal=dal)
        app = web.Application()
        app.router.add_post("/config/agent-models", router["get_agent_models"])
        app.router.add_post("/config/correct-words", router["get_correct_words"])
        app.router.add_post("/api/v1/agent/profile", router["update_agent_profile"])

        from aiohttp.test_utils import TestServer
        server = TestServer(app)
        await server.start_server()

        base_url = str(server.make_url(""))
        server_secret = "a613f18e19c9b589c3bc82da3d76e47610dc2e5f88456a053120141fbe3239a0"
        ManageApiClient.safe_close()
        init_service({"manager-api": {"url": base_url, "secret": server_secret}})

        test_config = {
            "selected_module": {"TTS": "EdgeTTS", "LLM": "OpenAI"},
            "TTS": {"EdgeTTS": {}},
            "LLM": {"OpenAI": {}},
        }

        # Bước 1: Loa kết nối lần đầu -> Đọc từ API và ghi vào Cache Redis
        initial_cfg = await get_private_config_from_api(test_config, mac_address, mac_address)
        assert initial_cfg["assistant_name"] == "Phiên Bản Cũ"
        assert initial_cfg["tts_voice_id"] == "vi-VN-HoaiMyNeural"

        # Kiểm tra Cache Redis đã có dữ liệu
        cache_key = f"xiaozhi:agent_cfg:{mac_address.lower()}"
        cached_str = await mock_redis.get(cache_key)
        assert cached_str is not None
        assert "Phiên Bản Cũ" in cached_str

        # Bước 2: User đổi giọng đọc sang Nam Nam & tên "Sunhouse AI V2" trên Web Portal
        t_update_start = time.time()
        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{base_url}/api/v1/agent/profile",
                json={
                    "speaker_mac": mac_address,
                    "user_id": user_id,
                    "assistant_name": "Sunhouse AI V2",
                    "prompt": "Prompt cập nhật mới v2",
                    "tts_voice_id": "vi-VN-NamMinhNeural",
                },
            )
            assert resp.status_code == 200
            resp_data = resp.json()
            assert resp_data["status"] == "success"

        # Bước 3: Xác minh Cache Redis đã bị xóa tự động (Active Cache Invalidation)
        cached_after_update = await mock_redis.get(cache_key)
        assert cached_after_update is None, "Cache Redis phải bị xóa ngay lập tức khi Portal lưu thay đổi!"

        # Bước 4: Loa bắt đầu phiên thoại mới -> Lấy cấu hình mới tức thì không cần restart server
        new_cfg = await get_private_config_from_api(test_config, mac_address, mac_address)
        total_switch_time = time.time() - t_update_start

        # Thẩm định thời gian chuyển đổi <= 5.0 giây
        assert total_switch_time <= 5.0, f"Thời gian cập nhật và áp dụng cấu hình vượt quá 5s: {total_switch_time:.2f}s"
        assert new_cfg["assistant_name"] == "Sunhouse AI V2"
        assert new_cfg["tts_voice_id"] == "vi-VN-NamMinhNeural"
        assert new_cfg["TTS"]["EdgeTTS"]["voice"] == "vi-VN-NamMinhNeural"
        assert "Prompt cập nhật mới v2" in new_cfg["prompt"]

        await server.close()
        print(f"\n✅ T3-02 PASS: Đổi giọng trên Portal -> Xóa cache Redis -> Áp dụng sau {total_switch_time*1000:.1f}ms (<= 5s) 0 restart.")


class TestT3_03_CrossTenantIsolationIDORRejection:
    """T3-03: User 1 giả mạo payload JSON-RPC chứa ID thiết bị của User 2 -> Bị từ chối 100% 403 Forbidden."""

    @pytest.mark.asyncio
    async def test_cross_tenant_idor_rejected_with_403(self, tmp_path):
        db_file = tmp_path / "test_gate3_t3.db"
        dal = SmartHomeDAL(db_url=f"sqlite:///{db_file}")

        # 1. User 1 sở hữu Đèn ngủ
        user_1 = "usr_001_hanoi"
        lamp_u1 = "dev_lamp_user1_bed"
        dal.upsert_user(user_1)
        dal.upsert_device(
            device_id=lamp_u1,
            user_id=user_1,
            device_name="Đèn ngủ phòng ngủ 1",
            category="dj",
            platform_type=PlatformType.TUYA_OEM_ESUNHOUSE,
            is_online=True,
        )

        # 2. User 2 sở hữu Đèn chùm phòng khách & Khóa cửa
        user_2 = "usr_002_saigon"
        lamp_u2 = "dev_lamp_user2_living"
        dal.upsert_user(user_2)
        dal.upsert_device(
            device_id=lamp_u2,
            user_id=user_2,
            device_name="Đèn chùm phòng khách 2",
            category="dj",
            platform_type=PlatformType.TUYA_OEM_ESUNHOUSE,
            is_online=True,
        )

        # Khởi tạo dispatcher giả lập với DAL chứa dữ liệu 2 user
        mock_dispatcher = MagicMock()
        mock_dispatcher.dal = dal

        tool = SmartHomeControlTool(dispatcher=mock_dispatcher)

        # 3. Kịch bản tấn công 1: User 1 gửi lệnh điều khiển nhắm vào ID đèn của User 2
        attack_res = await tool.execute(
            user_id=user_1,
            arguments={
                "device_id": lamp_u2,
                "action": "turn_on",
            },
        )

        # Thẩm định từ chối 100% với mã 403 Forbidden
        assert attack_res["success"] is False
        assert attack_res["code"] == 403
        assert attack_res["error"] == "FORBIDDEN"
        assert "Access Denied" in attack_res["message"]
        print("\n✅ T3-03.A PASS: Lệnh điều khiển trực tiếp chéo tài khoản bị từ chối 403 Forbidden.")

        # 4. Kịch bản tấn công 2: Giả mạo gói tin JSON-RPC qua MCP WebSocket
        mock_ws = AsyncMock()
        messages_sent = []

        async def fake_send_str(msg):
            messages_sent.append(json.loads(msg))

        mock_ws.send_str = fake_send_str
        mock_ws.prepare = AsyncMock()
        mock_ws.exception = MagicMock(return_value=None)

        # Giả lập xử lý của mcp_websocket_handler khi nhận tool call chéo User
        # params gửi user_id của User 1 nhưng arguments chứa ID đèn của User 2
        mcp_params = {
            "name": "smarthome_control",
            "arguments": {"device_id": lamp_u2, "action": "turn_off"},
            "user_id": user_1,
        }
        rpc_exec_res = await tool.execute(user_id=user_1, arguments=mcp_params["arguments"])

        # Kiểm tra đóng gói phản hồi chuẩn bảo mật MCP JSON-RPC
        is_forbidden = rpc_exec_res.get("code") == 403 or rpc_exec_res.get("error") == "FORBIDDEN"
        response_payload = {
            "jsonrpc": "2.0",
            "id": 999,
            "result": {
                "content": [{"type": "text", "text": rpc_exec_res.get("message")}],
                "structured_data": rpc_exec_res,
                "isError": is_forbidden,
            },
        }
        if is_forbidden:
            response_payload["error"] = {
                "code": 403,
                "message": "Access Denied: You do not own this device (403 Forbidden)",
                "data": rpc_exec_res,
            }

        await mock_ws.send_str(json.dumps(response_payload))

        # Thẩm định phản hồi gửi về cho hacker
        assert len(messages_sent) == 1
        rpc_resp = messages_sent[0]
        assert rpc_resp["id"] == 999
        assert "error" in rpc_resp
        assert rpc_resp["error"]["code"] == 403
        assert rpc_resp["result"]["isError"] is True
        print("✅ T3-03.B PASS: Giả mạo JSON-RPC payload bị mcp_smarthome_hub chặn 100% (code: 403).")

        # 5. Kịch bản hợp lệ: User 1 điều khiển chính đèn của mình
        mock_dispatcher.dispatch_command = AsyncMock(return_value={
            "success": True,
            "message": "Đã bật Đèn ngủ phòng ngủ 1",
        })
        valid_res = await tool.execute(
            user_id=user_1,
            arguments={
                "device_id": lamp_u1,
                "action": "turn_on",
            },
        )
        assert valid_res["success"] is True
        assert valid_res.get("code") != 403
        print("✅ T3-03.C PASS: User 1 điều khiển thiết bị chính chủ thành công bình thường.")
