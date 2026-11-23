# -*- coding: utf-8 -*-
"""BỘ KIỂM THỬ TÍCH HỢP TOÀN DIỆN CHO TUYA SHARING GATEWAY:
Áp dụng 100% các cơ chế tối ưu DP từ Mode Dev (Mục 4.1.4) vào Mode Hiện Tại (Tuya Sharing Mode).

Bao gồm các bài test pass cho từng hạng mục:
- Hạng mục 4.1.4.1: Bộ lọc phân hạng DPClassifier & In Log cây (Tree Logging) trong Tuya Sharing Sync.
- Hạng mục 4.1.4.2: Tích hợp năng lực động vào Context Injector LLM Prompt (không hallucinate công tắc ảo).
- Hạng mục 4.1.4.3: Mở rộng Schema công cụ MCP `smarthome_control` & mô tả chi tiết năng lực thiết bị.
- Hạng mục 4.1.4.4: Bộ phân giải lệnh đa năng (Feature mapping, Xử lý duyên dáng Graceful Degradation khi thiếu công tắc nguồn, Hẹn giờ set_timer).
"""

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
HUB_DIR = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if HUB_DIR not in sys.path:
    sys.path.insert(0, HUB_DIR)

from adapters.dp_classifier import DPClassifier
from adapters.normalizer import DeviceNormalizer
from clients.tuya_sharing_manager import TuyaSharingManager
from dispatcher.context_injector import ContextInjector
from dispatcher.multisource_dispatcher import MultiSourceDispatcher
from storage.db import SmartHomeDAL
from storage.models import PlatformType


# ---------------------------------------------------------------------------
# FIXTURE MẪU DỮ LIỆU THỰC TẾ TỪ TUYA SHARING GATEWAY
# ---------------------------------------------------------------------------

class FakeDeviceFunction:
    def __init__(self, code, type_="Boolean", values="{}"):
        self.code = code
        self.type = type_
        self.name = code
        self.values = values


class FakeCustomerDevice:
    def __init__(self, id_, name, category, functions, status):
        self.id = id_
        self.name = name
        self.category = category
        self.function = {f.code: f for f in functions}
        self.status = status
        self.online = True
        self.local_key = "test_key_123456"


@pytest.fixture
def test_dal():
    """Khởi tạo SQLite DAL trong bộ nhớ in-memory."""
    return SmartHomeDAL("sqlite:///:memory:")


# ===========================================================================
# 1. TEST HẠNG MỤC 4.1.4.1: BỘ LỌC PHÂN HẠNG DP & IN LOG CÂY MINH BẠCH
# ===========================================================================

def test_tuya_sharing_sync_applies_dp_classifier_and_tree_logging(test_dal, caplog):
    """4.1.4.1: Kiểm tra Tuya Sharing sync áp dụng DPClassifier lọc rác và in log cây DPs."""
    manager = TuyaSharingManager()
    user_id = "user_test_phi"

    # Giả lập 2 thiết bị thực tế:
    # 1. Đèn phòng ngủ (16 DPs gồm cả blacklist DPs: power_memory, do_not_disturb, music_data, random_timing)
    light_fns = [
        FakeDeviceFunction("switch_led", "Boolean"),
        FakeDeviceFunction("bright_value_v2", "Integer", '{"min":10,"max":1000}'),
        FakeDeviceFunction("temp_value_v2", "Integer", '{"min":0,"max":1000}'),
        FakeDeviceFunction("work_mode", "Enum", '{"range":["white","colour","scene","music"]}'),
        FakeDeviceFunction("countdown_1", "Integer", '{"min":0,"max":86400}'),
        FakeDeviceFunction("power_memory", "Enum", '{"range":["off","on","memory"]}'),  # Blacklist
        FakeDeviceFunction("do_not_disturb", "Boolean"),  # Blacklist
        FakeDeviceFunction("random_timing", "Raw"),  # Blacklist
    ]
    light_status = {
        "switch_led": True,
        "bright_value_v2": 800,
        "temp_value_v2": 500,
        "work_mode": "white",
        "countdown_1": 0,
        "power_memory": "off",
        "do_not_disturb": False,
    }
    fake_light = FakeCustomerDevice("dev_light_01", "Đèn Phòng Ngủ", "dj", light_fns, light_status)

    # 2. Máy lọc không khí (Chỉ có 2 DPs do OEM chưa map chuẩn)
    air_fns = [
        FakeDeviceFunction("uv", "Boolean"),
        FakeDeviceFunction("filter_reset", "Boolean"),
    ]
    air_status = {"uv": True, "filter_reset": False}
    fake_air = FakeCustomerDevice("dev_air_01", "Máy Lọc Không Khí", "kj", air_fns, air_status)

    mock_mgr = MagicMock()
    mock_mgr.device_map = {
        "dev_light_01": fake_light,
        "dev_air_01": fake_air,
    }

    with patch.object(manager, "get_manager", return_value=mock_mgr):
        import logging
        with caplog.at_level(logging.INFO):
            synced = manager.sync_devices(user_id=user_id, dal=test_dal)

        assert len(synced) == 2

        # Kiểm tra Đèn phòng ngủ trong CSDL
        db_light = test_dal.get_device("dev_light_01")
        assert db_light is not None
        schema_light = db_light["raw_schema"]
        classified = schema_light.get("classified_dps", {})

        # Blacklist DPs đã được lọc thành công
        assert "power_memory" in classified["blacklist"]
        assert "do_not_disturb" in classified["blacklist"]
        assert "random_timing" in classified["blacklist"]

        # Primary & Sub-features được gom nhóm đúng
        assert "switch_led" in classified["primary"]
        assert "bright_value_v2" in classified["primary"]
        assert "work_mode" in classified["sub_features"]
        assert "countdown_1" in classified["sub_features"]

        # Năng lực tổng hợp tự nhiên tiếng Việt
        assert "Bật/tắt đèn" in schema_light["synthesized_capabilities"]
        assert "chỉnh độ sáng" in schema_light["synthesized_capabilities"]

        # Kiểm tra Máy lọc không khí
        db_air = test_dal.get_device("dev_air_01")
        schema_air = db_air["raw_schema"]
        assert "khử khuẩn uv" in schema_air["synthesized_capabilities"].lower()
        assert "reset màng lọc" in schema_air["synthesized_capabilities"].lower()
        # KHÔNG được bịa công tắc Bật/tắt nguồn khi Cloud không cấp phép
        assert "bật/tắt máy lọc không khí" not in schema_air["synthesized_capabilities"].lower()

        # Kiểm tra Tree Logging xuất hiện trong log
        log_text = caplog.text
        assert "📦 [TUYA SCHEMA] Đã nhận đặc tả DP chuẩn của [Đèn Phòng Ngủ]" in log_text
        assert "├── 📋 Danh sách Lệnh điều khiển" in log_text
        assert "└── 📊 Danh sách Trạng thái" in log_text
        assert "KHÔNG CÓ DP công tắc nguồn (Power Switch) từ Tuya Cloud" in log_text


# ===========================================================================
# 2. TEST HẠNG MỤC 4.1.4.2: TÍCH HỢP NĂNG LỰC ĐỘNG VÀO LLM SYSTEM PROMPT
# ===========================================================================

def test_context_injector_injects_truthful_capabilities_for_tuya_sharing(test_dal):
    """4.1.4.2: Kiểm tra ContextInjector nạp đúng năng lực thực tế vào LLM Prompt."""
    user_id = "user_test_phi"

    # Nạp 1 đèn và 1 máy lọc vào CSDL
    test_dal.upsert_device(
        device_id="dev_light_01",
        user_id=user_id,
        device_name="Đèn Phòng Ngủ",
        category="dj",
        platform_type=PlatformType.TUYA_EXTERNAL_SMARTLIFE,
        raw_schema={
            "category": "dj",
            "functions": [
                {"code": "switch_led", "type": "Boolean"},
                {"code": "bright_value_v2", "type": "Integer", "values": '{"min":10,"max":1000}'},
            ],
            "synthesized_capabilities": "Bật/tắt đèn, chỉnh độ sáng (1-100%)",
        },
    )
    test_dal.upsert_device(
        device_id="dev_air_01",
        user_id=user_id,
        device_name="Máy Lọc Không Khí",
        category="kj",
        platform_type=PlatformType.TUYA_EXTERNAL_SMARTLIFE,
        raw_schema={
            "category": "kj",
            "functions": [{"code": "uv", "type": "Boolean"}, {"code": "filter_reset", "type": "Boolean"}],
            "synthesized_capabilities": "khử khuẩn UV, reset màng lọc",
        },
    )

    injector = ContextInjector(dal_instance=test_dal)
    prompt_context = injector.build_llm_system_prompt_context(user_id=user_id)

    # Đèn được mô tả đủ Bật/tắt & độ sáng
    assert "Đèn Phòng Ngủ" in prompt_context
    assert "Bật/tắt đèn, chỉnh độ sáng" in prompt_context

    # Máy lọc không khí trung thực: chỉ có UV & reset màng lọc
    assert "Máy Lọc Không Khí" in prompt_context
    assert "khử khuẩn uv" in prompt_context.lower()
    assert "reset màng lọc" in prompt_context.lower()
    assert "bật/tắt máy lọc không khí" not in prompt_context.lower()


# ===========================================================================
# 3. TEST HẠNG MỤC 4.1.4.3: MỞ RỘNG SCHEMA CÔNG CỤ MCP & MÔ TẢ NĂNG LỰC
# ===========================================================================

def test_mcp_tools_description_reflects_synthesized_capabilities(test_dal):
    """4.1.4.3: Kiểm tra Schema công cụ smarthome_control mô tả chính xác năng lực thực tế."""
    user_id = "user_test_phi"
    test_dal.upsert_device(
        device_id="dev_air_01",
        user_id=user_id,
        device_name="Máy Lọc Không Khí",
        category="kj",
        platform_type=PlatformType.TUYA_EXTERNAL_SMARTLIFE,
        raw_schema={
            "category": "kj",
            "functions": [{"code": "uv", "type": "Boolean"}],
            "synthesized_capabilities": "khử khuẩn UV, reset màng lọc",
        },
    )

    from main import get_mcp_tools
    with patch("main.default_dal", test_dal):
        tools = get_mcp_tools(user_id=user_id)
        assert len(tools) >= 1
        st_tool = next(t for t in tools if t["name"] == "smarthome_control")
        desc = st_tool["description"]
        assert "Máy Lọc Không Khí" in desc
        assert "khử khuẩn uv" in desc.lower()
        assert "reset màng lọc" in desc.lower()


# ===========================================================================
# 4. TEST HẠNG MỤC 4.1.4.4: BỘ PHÂN GIẢI LỆNH ĐA NĂNG & XỬ LÝ DUYÊN DÁNG
# ===========================================================================

@pytest.mark.asyncio
async def test_sub_feature_control_and_graceful_handling_missing_power(test_dal):
    """4.1.4.4: Kiểm thử điều khiển tính năng con UV và phản hồi duyên dáng khi thiếu công tắc nguồn."""
    user_id = "user_test_phi"

    # CSDL chứa máy lọc chỉ có DP uv
    test_dal.upsert_device(
        device_id="dev_air_01",
        user_id=user_id,
        device_name="Máy Lọc Không Khí",
        category="kj",
        platform_type=PlatformType.TUYA_EXTERNAL_SMARTLIFE,
        raw_schema={
            "category": "kj",
            "functions": [
                {"code": "uv", "type": "Boolean", "values": "{}"},
                {"code": "filter_reset", "type": "Boolean", "values": "{}"},
            ],
            "status": {"uv": False, "filter_reset": False},
        },
    )

    mock_sharing_mgr = MagicMock()
    mock_dev = MagicMock()
    mock_dev.status = {"uv": False, "filter_reset": False}
    mock_sharing_mgr.device_map = {"dev_air_01": mock_dev}

    dispatcher = MultiSourceDispatcher(dal_instance=test_dal)

    with patch("clients.tuya_sharing_manager.sharing_manager.get_manager", return_value=mock_sharing_mgr), \
         patch("clients.tuya_sharing_manager.sharing_manager.send_commands", return_value=True) as mock_send:

        # A. Người dùng yêu cầu điều khiển tính năng con: Bật đèn UV
        res_uv = await dispatcher.dispatch_command(
            user_id=user_id,
            device_query="dev_air_01",
            action="turn_on",
            extra_params={"feature": "đèn uv"},
        )
        assert res_uv["success"] is True
        assert res_uv["commands"] == [{"code": "uv", "value": True}]
        mock_send.assert_called_with(user_id, "dev_air_01", [{"code": "uv", "value": True}])

        # B. Người dùng yêu cầu Bật/Tắt nguồn chung (thiết bị không có công tắc nguồn)
        res_power = await dispatcher.dispatch_command(
            user_id=user_id,
            device_query="dev_air_01",
            action="turn_on",
        )
        # Hệ thống không crash, trả về thông báo giải thích rõ ràng và duyên dáng
        assert res_power["success"] is False
        assert "chưa được nhà sản xuất mở quyền" in res_power["message"]
        assert "khử khuẩn uv" in res_power["message"].lower()


@pytest.mark.asyncio
async def test_set_timer_control_on_tuya_sharing_device(test_dal):
    """4.1.4.4: Kiểm thử tính năng hẹn giờ set_timer cho thiết bị Tuya Sharing có DP countdown."""
    user_id = "user_test_phi"
    test_dal.upsert_device(
        device_id="dev_light_01",
        user_id=user_id,
        device_name="Đèn Phòng Ngủ",
        category="dj",
        platform_type=PlatformType.TUYA_EXTERNAL_SMARTLIFE,
        raw_schema={
            "category": "dj",
            "functions": [
                {"code": "switch_led", "type": "Boolean"},
                {"code": "countdown_1", "type": "Integer", "values": '{"unit":"s","min":0,"max":86400}'},
            ],
            "status": {"switch_led": True, "countdown_1": 0},
        },
    )

    mock_sharing_mgr = MagicMock()
    mock_dev = MagicMock()
    mock_dev.status = {"switch_led": True, "countdown_1": 0}
    mock_sharing_mgr.device_map = {"dev_light_01": mock_dev}

    dispatcher = MultiSourceDispatcher(dal_instance=test_dal)

    with patch("clients.tuya_sharing_manager.sharing_manager.get_manager", return_value=mock_sharing_mgr), \
         patch("clients.tuya_sharing_manager.sharing_manager.send_commands", return_value=True) as mock_send:

        # Hẹn giờ tắt đèn sau 10 phút (600 giây)
        res_timer = await dispatcher.dispatch_command(
            user_id=user_id,
            device_query="dev_light_01",
            action="set_timer",
            value=10,  # 10 phút
        )
        assert res_timer["success"] is True
        assert res_timer["commands"] == [{"code": "countdown_1", "value": 600}]
        mock_send.assert_called_with(user_id, "dev_light_01", [{"code": "countdown_1", "value": 600}])
