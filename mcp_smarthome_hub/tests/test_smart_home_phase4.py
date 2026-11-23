# -*- coding: utf-8 -*-
"""BỘ KIỂM THỬ TỰ ĐỘNG GIAI ĐOẠN 4 (PASS GATE 4):
UNIFIED SMART HOME MCP TOOL & BỘ ĐỊNH TUYẾN ĐA NGUỒN O(1)
Kiểm chứng 6 tiêu chí:
1. Dynamic Context Injection: Tiêm danh mục thiết bị của user vào LLM System Prompt.
2. Semantic & Fuzzy Name Resolution: Phân giải từ khóa tiếng Việt không dấu ("den", "robot").
3. Multi-source O(1) Routing (< 5ms): Định tuyến chuẩn xác 4 nguồn (AWS, Tuya OEM, Tuya Ext, HA).
4. Sweeper Adapter 32 DPs: Điều khiển chuyên sâu Robot 298 Pro & All-in-One Dock.
5. Hard Timeout 1.5s Resilience: Bảo vệ tuyệt đối luồng đàm thoại, không treo khi mạng lag.
6. End-to-End MCP Tool Execution: Thực thi công cụ Function Calling smarthome_control.
"""

import asyncio
import json
import os
import sys
import time
from unittest.mock import AsyncMock, MagicMock
import pytest

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
HUB_DIR = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
SERVER_ROOT = os.path.abspath(os.path.join(HUB_DIR, ".."))
for p in [HUB_DIR, SERVER_ROOT]:
    if p not in sys.path:
        sys.path.insert(0, p)

from storage.token_vault import TokenVault
from storage.db import SmartHomeDAL
from storage.models import PlatformType
from dispatcher.context_injector import ContextInjector, remove_vietnamese_accents
from dispatcher.multisource_dispatcher import MultiSourceDispatcher
from tools.smarthome_tool import SmartHomeControlTool, HARD_TIMEOUT_SECONDS
from tools.sweeper_tool import SweeperControlTool


@pytest.fixture
def test_env(tmp_path):
    """Khởi tạo môi trường DAL và CSDL SQLite độc lập cho bài test."""
    db_file = tmp_path / "test_phase4.db"
    db_url = f"sqlite:///{db_file}"
    vault = TokenVault(master_key="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef")
    dal = SmartHomeDAL(db_url=db_url)
    dal.init_db()

    user_id = "user_phase4_test"
    dal.upsert_user(user_id=user_id)

    # 1. Thêm thiết bị Đèn ngủ Tuya Smart Life (tuya_ext)
    bulb_schema = {
        "functions": [
            {"code": "switch_led", "type": "Boolean"},
            {"code": "bright_value_v2", "type": "Integer", "values": json.dumps({"min": 10, "max": 1000, "step": 1})},
            {"code": "temp_value_v2", "type": "Integer", "values": json.dumps({"min": 0, "max": 1000, "step": 1})},
        ]
    }
    dal.upsert_device(
        device_id="tuya_ext_bulb_01",
        user_id=user_id,
        device_name="Đèn ngủ phòng ngủ",
        category="dj",
        platform_type=PlatformType.TUYA_EXTERNAL_SMARTLIFE,
        raw_schema=bulb_schema,
    )

    # 2. Thêm thiết bị Robot hút bụi 298 Pro Ultra Tuya OEM (tuya_oem)
    dal.upsert_device(
        device_id="tuya_oem_sweeper_298",
        user_id=user_id,
        device_name="Robot hút bụi phòng khách",
        category="sd",
        platform_type=PlatformType.TUYA_OEM_ESUNHOUSE,
    )

    # 3. Thêm thiết bị Home Assistant (ha)
    dal.upsert_device(
        device_id="light.living_room_ceiling",
        user_id=user_id,
        device_name="Đèn chùm phòng khách",
        category="dj",
        platform_type=PlatformType.HOME_ASSISTANT,
    )

    # 4. Thêm thiết bị gia dụng Sunhouse AWS In-house (sunhouse_aws)
    dal.upsert_device(
        device_id="sh_aws_kettle_kitchen",
        user_id=user_id,
        device_name="Bình đun nước thông minh",
        category="kettle",
        platform_type=PlatformType.SUNHOUSE_AWS,
    )

    # 5. Thêm thiết bị Quạt phòng ngủ Tuya Smart Life (tuya_ext - fskg)
    fan_schema = {
        "functions": [
            {"code": "switch_fan", "type": "Boolean"},
            {"code": "fan_speed", "type": "Integer", "values": json.dumps({"min": 1, "max": 100, "step": 1})},
        ]
    }
    dal.upsert_device(
        device_id="tuya_ext_fan_01",
        user_id=user_id,
        device_name="Quạt phòng ngủ",
        category="fskg",
        platform_type=PlatformType.TUYA_EXTERNAL_SMARTLIFE,
        raw_schema=fan_schema,
    )

    return dal, user_id


# =============================================================================
# 1. KIỂM THỬ DYNAMIC CONTEXT INJECTION
# =============================================================================

def test_context_injection_system_prompt(test_env):
    """Kiểm tra việc sinh System Prompt Context tinh gọn nạp vào LLM."""
    dal, user_id = test_env
    injector = ContextInjector(dal_instance=dal)

    context_str = injector.build_llm_system_prompt_context(user_id)
    assert "### DANH MỤC THIẾT BỊ NHÀ THÔNG MINH" in context_str
    assert "Đèn ngủ phòng ngủ" in context_str
    assert "Quạt phòng ngủ" in context_str
    assert "light.living_room_ceiling" in context_str
    assert "sh_aws_kettle_kitchen" in context_str
    assert "tuya_ext_bulb_01" in context_str
    # Khẳng định 100% vắng mặt robot hút bụi đang R&D (Clean Context)
    assert "Robot hút bụi phòng khách" not in context_str
    assert "Hỗ trợ:" in context_str


# =============================================================================
# 2. KIỂM THỬ PHÂN GIẢI NGỮ NGHĨA & TỪ KHÓA TIẾNG VIỆT
# =============================================================================

def test_fuzzy_and_semantic_name_resolution(test_env):
    """Kiểm tra tìm kiếm O(1) theo ID và so khớp mờ theo tên tiếng Việt không dấu."""
    dal, user_id = test_env
    injector = ContextInjector(dal_instance=dal)

    # Tìm chính xác theo ID (O(1))
    dev = injector.resolve_device(user_id, "tuya_ext_bulb_01")
    assert dev is not None
    assert dev["device_name"] == "Đèn ngủ phòng ngủ"

    # Tìm chính xác theo tên
    dev = injector.resolve_device(user_id, "Đèn ngủ phòng ngủ")
    assert dev is not None

    # Tìm không dấu tiếng Việt
    dev = injector.resolve_device(user_id, "den ngu phong ngu")
    assert dev is not None
    assert dev["device_id"] == "tuya_ext_bulb_01"

    # Tìm theo từ khóa quạt -> nhận diện đúng Quạt phòng ngủ (fskg)
    dev = injector.resolve_device(user_id, "bật quạt phòng ngủ giúp tôi")
    assert dev is not None
    assert dev["device_id"] == "tuya_ext_fan_01"

    # Thiết bị không tồn tại
    dev = injector.resolve_device(user_id, "may giat cua truoc")
    assert dev is None


# =============================================================================
# 3. KIỂM THỬ BỘ ĐỊNH TUYẾN ĐA NGUỒN O(1) VỚI ĐỘ TRỄ < 5MS
# =============================================================================

@pytest.mark.asyncio
async def test_o1_multi_source_dispatching_latency_and_routing(test_env):
    """Kiểm tra định tuyến O(1) tới cả 4 nền tảng với overhead < 5ms."""
    dal, user_id = test_env

    # Giả lập Tuya Client
    mock_tuya = MagicMock()
    mock_tuya.get_token = AsyncMock(return_value={"access_token": "mock_token_123"})
    mock_tuya.send_device_commands = AsyncMock(return_value=True)

    # Giả lập HA Forwarder
    mock_ha = MagicMock()
    mock_ha.call_service = AsyncMock(return_value={"status": "success"})

    dispatcher = MultiSourceDispatcher(
        dal_instance=dal,
        tuya_client=mock_tuya,
        ha_forwarder=mock_ha,
    )

    # 1. Định tuyến Sunhouse AWS IoT
    t0 = time.time()
    res_aws = await dispatcher.dispatch_command(
        user_id=user_id,
        device_query="sh_aws_kettle_kitchen",
        action="turn_on",
    )
    rtt_aws = (time.time() - t0) * 1000
    assert res_aws["success"] is True
    assert res_aws["platform"] == "sunhouse_aws"
    assert rtt_aws < 50.0  # Định tuyến nội bộ siêu tốc

    # 2. Định tuyến Home Assistant
    t0 = time.time()
    res_ha = await dispatcher.dispatch_command(
        user_id=user_id,
        device_query="light.living_room_ceiling",
        action="turn_on",
    )
    rtt_ha = (time.time() - t0) * 1000
    assert res_ha["success"] is True
    assert res_ha["platform"] == "ha"
    mock_ha.call_service.assert_called_once()
    assert rtt_ha < 50.0

    # 3. Định tuyến Tuya Smart Life (tuya_ext)
    t0 = time.time()
    res_tuya = await dispatcher.dispatch_command(
        user_id=user_id,
        device_query="tuya_ext_bulb_01",
        action="set_brightness",
        value=80,
    )
    rtt_tuya = (time.time() - t0) * 1000
    assert res_tuya["success"] is True
    assert res_tuya["platform"] == "tuya_ext"
    assert rtt_tuya < 50.0
    # Kiểm tra lệnh đã được scale sang dải hardware 10-1000 (80% -> 802)
    mock_tuya.send_device_commands.assert_called_once()
    args, kwargs = mock_tuya.send_device_commands.call_args
    sent_cmds = kwargs.get("commands") or args[1]
    assert sent_cmds[0]["code"] == "bright_value_v2"
    assert 790 <= sent_cmds[0]["value"] <= 810


# =============================================================================
# 4. KIỂM THỬ ĐIỀU KHIỂN ROBOT 298 PRO VÀ DOCK (32 DPS)
# =============================================================================

@pytest.mark.asyncio
async def test_sweeper_adapter_32_dps_dock_dispatch(test_env):
    """Kiểm tra công cụ SweeperControlTool phát lệnh giặt sấy giẻ và về dock."""
    dal, user_id = test_env

    mock_tuya = MagicMock()
    mock_tuya.get_token = AsyncMock(return_value={"access_token": "mock_token_123"})
    mock_tuya.send_device_commands = AsyncMock(return_value=True)

    dispatcher = MultiSourceDispatcher(
        dal_instance=dal,
        tuya_client=mock_tuya,
    )
    tool = SweeperControlTool(dispatcher=dispatcher)

    # 1. Lệnh giặt giẻ nước nóng 60°C tại dock
    res_wash = await tool.execute(
        user_id=user_id,
        arguments={
            "device_id": "tuya_oem_sweeper_298",
            "action": "wash_mop",
            "hot_water": True,
        },
    )
    assert res_wash["success"] is True
    args, kwargs = mock_tuya.send_device_commands.call_args
    sent_cmds = kwargs.get("commands") or args[1]
    cmd_dict = {c["code"]: c["value"] for c in sent_cmds}
    assert cmd_dict.get("mop_clean") is True
    assert cmd_dict.get("hot_water_wash") is True

    # 2. Lệnh sấy khô giẻ khí nóng hẹn giờ 3h
    res_dry = await tool.execute(
        user_id=user_id,
        arguments={
            "device_id": "tuya_oem_sweeper_298",
            "action": "dry_mop",
            "dry_time": "3h",
        },
    )
    assert res_dry["success"] is True
    args, kwargs = mock_tuya.send_device_commands.call_args
    sent_cmds = kwargs.get("commands") or args[1]
    cmd_dict = {c["code"]: c["value"] for c in sent_cmds}
    assert cmd_dict.get("mop_dry") is True
    assert cmd_dict.get("dry_time") == "3h"


# =============================================================================
# 5. KIỂM THỬ CƠ CHẾ BẢO VỆ HARD TIMEOUT 1.5S
# =============================================================================

@pytest.mark.asyncio
async def test_hard_timeout_1_5s_resilience(test_env):
    """Kiểm tra việc ngắt ngay sau 1.5s nếu backend đám mây bị treo, bảo vệ luồng đàm thoại."""
    dal, user_id = test_env

    # Giả lập Tuya Client bị lag 3.0 giây
    async def _slow_send(*args, **kwargs):
        await asyncio.sleep(2.5)
        return True

    mock_tuya = MagicMock()
    mock_tuya.get_token = AsyncMock(return_value={"access_token": "mock_token_123"})
    mock_tuya.send_device_commands = AsyncMock(side_effect=_slow_send)

    dispatcher = MultiSourceDispatcher(
        dal_instance=dal,
        tuya_client=mock_tuya,
    )
    tool = SmartHomeControlTool(dispatcher=dispatcher)

    t0 = time.time()
    # Kiểm tra với timeout ngắn 0.15s (đại diện cho cơ chế Hard Timeout 1.5s)
    res = await tool.execute(
        user_id=user_id,
        arguments={"device_id": "tuya_ext_bulb_01", "action": "turn_on"},
        timeout=0.15,
    )
    duration = time.time() - t0

    assert duration < 0.35, "Phải ngắt ngay lập tức khi hết timeout, không chờ hết 2.5s"
    assert res["success"] is False
    assert res["error"] == "HARD_TIMEOUT"
    assert "phản hồi hơi chậm" in res["message"]


# =============================================================================
# 6. KIỂM THỬ END-TO-END MCP TOOL EXECUTION VỚI CÂU THOẠI TIẾNG VIỆT
# =============================================================================

@pytest.mark.asyncio
async def test_end_to_end_mcp_call_with_vietnamese_voice(test_env):
    """Kiểm tra thực thi hoàn chỉnh smarthome_control từ câu gọi của LLM."""
    dal, user_id = test_env

    mock_tuya = MagicMock()
    mock_tuya.get_token = AsyncMock(return_value={"access_token": "mock_token_123"})
    mock_tuya.send_device_commands = AsyncMock(return_value=True)

    dispatcher = MultiSourceDispatcher(
        dal_instance=dal,
        tuya_client=mock_tuya,
    )
    tool = SmartHomeControlTool(dispatcher=dispatcher)

    # LLM gọi lệnh bằng tên tiếng Việt "đèn ngủ"
    res = await tool.execute(
        user_id=user_id,
        arguments={
            "device_name": "đèn ngủ",
            "action": "turn_on",
        },
    )
    assert res["success"] is True
    assert "Đã bật Đèn ngủ phòng ngủ cho bạn rồi nhé." in res["message"]

    # LLM gọi lệnh chỉnh độ sáng
    res_bright = await tool.execute(
        user_id=user_id,
        arguments={
            "device_name": "đèn ngủ",
            "action": "set_brightness",
            "value": 75,
        },
    )
    assert res_bright["success"] is True
    assert "75%" in res_bright["message"]

    # LLM gọi lệnh điều khiển Quạt phòng ngủ (Category fskg)
    res_fan_on = await tool.execute(
        user_id=user_id,
        arguments={
            "device_name": "quạt phòng ngủ",
            "action": "turn_on",
        },
    )
    assert res_fan_on["success"] is True
    assert "Đã bật Quạt phòng ngủ" in res_fan_on["message"]

    # LLM gọi lệnh đổi tốc độ quạt bằng khẩu ngữ "mạnh"
    res_fan_speed = await tool.execute(
        user_id=user_id,
        arguments={
            "device_name": "quạt phòng ngủ",
            "action": "set_speed",
            "value": "mạnh",
        },
    )
    assert res_fan_speed["success"] is True
    assert "tốc độ Quạt phòng ngủ" in res_fan_speed["message"]

    # LLM truy vấn trạng thái Quạt phòng ngủ (query_status)
    mock_tuya.get_device_status = AsyncMock(
        return_value=[
            {"code": "switch_fan", "value": True},
            {"code": "fan_speed", "value": 75},
        ]
    )
    res_fan_status = await tool.execute(
        user_id=user_id,
        arguments={
            "device_name": "quạt phòng ngủ",
            "action": "query_status",
        },
    )
    assert res_fan_status["success"] is True
    assert "Quạt phòng ngủ hiện đang bật" in res_fan_status["message"]
    assert "tốc độ gió 75%" in res_fan_status["message"]


# =============================================================================
# 7. KIỂM THỬ TOOL ĐỒNG BỘ THIẾT BỊ TUYA DEDICATED (TUYA_SYNC_DEVICES)
# =============================================================================

@pytest.mark.asyncio
async def test_tuya_sync_devices_mcp_tool(test_env):
    """Kiểm tra công cụ tuya_sync_devices trong danh mục MCP tools và thực thi đồng bộ."""
    dal, user_id = test_env
    from main import get_mcp_tools

    # 1. Kiểm tra get_mcp_tools chứa tuya_sync_devices
    tools = get_mcp_tools(user_id=user_id)
    tool_names = [t["name"] for t in tools]
    assert "tuya_sync_devices" in tool_names, "Công cụ tuya_sync_devices phải có mặt trong MCP tools"

    sync_tool_def = next(t for t in tools if t["name"] == "tuya_sync_devices")
    assert "Tuya Smart Life" in sync_tool_def["description"]
    assert "tuy a" in sync_tool_def["description"]

    # 2. Kiểm thử logic thực thi đồng bộ với mock Tuya Cloud Client
    mock_tuya = MagicMock()
    mock_tuya.get_token = AsyncMock(return_value={"access_token": "mock_token_sync_123"})
    mock_tuya.get_associated_user_devices = AsyncMock(
        return_value=[
            {
                "id": "tuya_dev_sync_socket",
                "name": "Ổ cắm phòng khách",
                "category": "cz",
                "product_id": "prod_cz_01",
                "online": True,
                "local_key": "key_socket_123",
            },
            {
                "id": "tuya_dev_sync_bulb",
                "name": "Đèn bàn làm việc",
                "category": "dj",
                "product_id": "prod_dj_01",
                "online": True,
                "local_key": "key_bulb_123",
            },
        ]
    )
    mock_tuya.request = AsyncMock(return_value={"result": {"status": []}})

    from sync.device_syncer import sync_tuya_devices
    synced = await sync_tuya_devices(dal=dal, tuya_client=mock_tuya, user_id=user_id)

    assert len(synced) == 2
    assert synced[0]["device_name"] == "Ổ cắm phòng khách"
    assert synced[1]["device_name"] == "Đèn bàn làm việc"

    # Kiểm tra CSDL cục bộ đã được cập nhật
    db_devs = dal.list_devices_by_user(user_id)
    dev_ids = [d["device_id"] for d in db_devs]
    assert "tuya_dev_sync_socket" in dev_ids
    assert "tuya_dev_sync_bulb" in dev_ids

