# -*- coding: utf-8 -*-
"""BỘ KIỂM THỬ ĐƠN VỊ & TÍCH HỢP CHO DYNAMIC TRAITS & BỘ LỌC PHÂN HẠNG DP
(TEST SUITE FOR DP CLASSIFIER, DYNAMIC CAPABILITIES & SUB-FEATURE TARGETING)
"""

import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
HUB_DIR = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if HUB_DIR not in sys.path:
    sys.path.insert(0, HUB_DIR)

from adapters.dp_classifier import DPClassifier, is_blacklisted_dp
from adapters.normalizer import DeviceNormalizer
from dispatcher.context_injector import ContextInjector
from dispatcher.multisource_dispatcher import MultiSourceDispatcher
from storage.db import SmartHomeDAL
from storage.models import PlatformType
from tools.smarthome_tool import SmartHomeControlTool

# Schema thực tế từ Tuya Cloud OpenAPI của Quạt Trần (Category fskg)
REAL_TUYA_FAN_SCHEMA = {
    "category": "fskg",
    "functions": [
        {"code": "switch_fan", "type": "Boolean", "values": "{}"},
        {"code": "countdown_fan", "type": "Integer", "values": '{"unit":"s","min":0,"max":86400,"scale":0,"step":1}'},
        {"code": "fan_speed", "type": "Integer", "values": '{"unit":"%","min":1,"max":100,"scale":0,"step":1}'},
        {"code": "relay_status", "type": "Enum", "values": '{"range":["off","on","memory"]}'},
        {"code": "backlight_switch", "type": "Boolean", "values": "{}"},
    ],
    "status": [
        {"code": "switch_fan", "type": "Boolean", "values": "{}"},
        {"code": "countdown_fan", "type": "Integer", "values": '{"unit":"s","min":0,"max":86400,"scale":0,"step":1}'},
        {"code": "fan_speed", "type": "Integer", "values": '{"unit":"%","min":1,"max":100,"scale":0,"step":1}'},
        {"code": "relay_status", "type": "Enum", "values": '{"range":["off","on","memory"]}'},
        {"code": "backlight_switch", "type": "Boolean", "values": "{}"},
    ]
}

# Schema thực tế từ Tuya Cloud OpenAPI của Đèn thông minh (Category dj)
REAL_TUYA_BULB_SCHEMA = {
    "category": "dj",
    "functions": [
        {"code": "switch_led", "type": "Boolean", "values": "{}"},
        {"code": "work_mode", "type": "Enum", "values": '{"range":["white","colour","scene","music"]}'},
        {"code": "bright_value_v2", "type": "Integer", "values": '{"min":10,"max":1000,"scale":0,"step":1}'},
        {"code": "temp_value_v2", "type": "Integer", "values": '{"min":0,"max":1000,"scale":0,"step":1}'},
        {"code": "colour_data_v2", "type": "Json", "values": "{}"},
        {"code": "countdown_1", "type": "Integer", "values": '{"unit":"s","min":0,"max":86400,"scale":0,"step":1}'},
        {"code": "control_data", "type": "Json", "values": "{}"},
        {"code": "rhythm_mode", "type": "Raw", "values": '{"maxlen":"255"}'},
        {"code": "power_memory", "type": "Raw", "values": "{}"},
        {"code": "do_not_disturb", "type": "Boolean", "values": "{}"},
        {"code": "random_timing", "type": "Raw", "values": "{}"},
    ]
}

# Schema thực tế từ Tuya Cloud OpenAPI của Ổ cắm (Category cz)
REAL_TUYA_SOCKET_SCHEMA = {
    "category": "cz",
    "functions": [
        {"code": "switch_1", "type": "Boolean", "values": "{}"},
        {"code": "countdown_1", "type": "Integer", "values": '{"unit":"s","min":0,"max":86400,"scale":0,"step":1}'},
        {"code": "relay_status", "type": "Enum", "values": '{"range":["power_off","power_on","last"]}'},
        {"code": "overcharge_switch", "type": "Boolean", "values": "{}"},
        {"code": "random_time", "type": "String", "values": "{}"},
    ]
}


def test_dp_classifier_logic():
    """Kiểm tra thuật toán phân loại DP và lọc sạch Blacklist trên 3 schema thực tế."""
    # 1. Kiểm tra Quạt trần (fskg)
    fan_res = DPClassifier.classify_functions(REAL_TUYA_FAN_SCHEMA["functions"], category="fskg")
    primary_codes = [f["code"] for f in fan_res["primary"]]
    sub_codes = [f["code"] for f in fan_res["sub_features"]]
    blacklist_codes = [f["code"] for f in fan_res["blacklist"]]

    assert "switch_fan" in primary_codes
    assert "fan_speed" in primary_codes
    assert "backlight_switch" in sub_codes
    assert "countdown_fan" in sub_codes
    assert "relay_status" in blacklist_codes
    assert "relay_status" not in primary_codes
    assert "relay_status" not in sub_codes

    # 2. Kiểm tra Đèn (dj)
    bulb_res = DPClassifier.classify_functions(REAL_TUYA_BULB_SCHEMA["functions"], category="dj")
    b_primary = [f["code"] for f in bulb_res["primary"]]
    b_sub = [f["code"] for f in bulb_res["sub_features"]]
    b_black = [f["code"] for f in bulb_res["blacklist"]]

    assert "switch_led" in b_primary
    assert "bright_value_v2" in b_primary
    assert "temp_value_v2" in b_primary
    assert "work_mode" in b_sub
    assert "countdown_1" in b_sub
    assert "control_data" in b_black
    assert "rhythm_mode" in b_black
    assert "power_memory" in b_black
    assert "do_not_disturb" in b_black
    assert "random_timing" in b_black

    # 3. Kiểm tra Ổ cắm (cz)
    sock_res = DPClassifier.classify_functions(REAL_TUYA_SOCKET_SCHEMA["functions"], category="cz")
    s_primary = [f["code"] for f in sock_res["primary"]]
    s_sub = [f["code"] for f in sock_res["sub_features"]]
    s_black = [f["code"] for f in sock_res["blacklist"]]

    assert "switch_1" in s_primary
    assert "countdown_1" in s_sub
    assert "relay_status" in s_black
    assert "random_time" in s_black


def test_synthesize_device_capabilities():
    """Kiểm tra chuỗi năng lực tiếng Việt tự động sinh ra từ Schema thực tế."""
    # 1. Quạt trần: Phải có cánh quạt, tốc độ, đèn quạt (backlight) và hẹn giờ
    fan_cap = DPClassifier.synthesize_capabilities(REAL_TUYA_FAN_SCHEMA, category="fskg")
    assert "Bật/tắt cánh quạt" in fan_cap
    assert "tốc độ gió" in fan_cap
    assert "đèn quạt" in fan_cap
    assert "hẹn giờ tắt" in fan_cap
    # Tuyệt đối không có DP blacklist trong mô tả
    assert "relay_status" not in fan_cap

    # 2. Đèn: Phải có bật/tắt, độ sáng, nhiệt độ màu, chế độ
    bulb_cap = DPClassifier.synthesize_capabilities(REAL_TUYA_BULB_SCHEMA, category="dj")
    assert "Bật/tắt đèn" in bulb_cap
    assert "độ sáng" in bulb_cap
    assert "nhiệt độ màu" in bulb_cap
    assert "chế độ" in bulb_cap
    assert "control_data" not in bulb_cap

    # 3. Ổ cắm: Phải có bật/tắt điện, hẹn giờ tắt
    sock_cap = DPClassifier.synthesize_capabilities(REAL_TUYA_SOCKET_SCHEMA, category="cz")
    assert "Bật/tắt điện" in sock_cap
    assert "hẹn giờ tắt" in sock_cap


def test_feature_targeted_command_generation():
    """Kiểm tra DeviceNormalizer sinh lệnh riêng biệt cho tính năng con (feature)."""
    # 1. Bật đèn của quạt trần (feature='đèn') -> Gửi backlight_switch = True
    cmd_light_on = DeviceNormalizer.build_command(
        raw_schema=REAL_TUYA_FAN_SCHEMA,
        action="turn_on",
        feature="đèn",
    )
    assert len(cmd_light_on) == 1
    assert cmd_light_on[0]["code"] == "backlight_switch"
    assert cmd_light_on[0]["value"] is True

    # 2. Tắt đèn của quạt trần (feature='backlight') -> Gửi backlight_switch = False
    cmd_light_off = DeviceNormalizer.build_command(
        raw_schema=REAL_TUYA_FAN_SCHEMA,
        action="turn_off",
        feature="backlight",
    )
    assert len(cmd_light_off) == 1
    assert cmd_light_off[0]["code"] == "backlight_switch"
    assert cmd_light_off[0]["value"] is False

    # 3. Bật quạt thông thường (không truyền feature) -> Gửi switch_fan = True
    cmd_fan_on = DeviceNormalizer.build_command(
        raw_schema=REAL_TUYA_FAN_SCHEMA,
        action="turn_on",
        feature=None,
    )
    assert len(cmd_fan_on) == 1
    assert cmd_fan_on[0]["code"] == "switch_fan"
    assert cmd_fan_on[0]["value"] is True


def test_countdown_timer_command_generation():
    """Kiểm tra DeviceNormalizer sinh lệnh hẹn giờ đếm ngược (set_timer)."""
    # 1. Hẹn giờ quạt 30 phút -> unit: s -> 30 * 60 = 1800 giây
    cmd_timer = DeviceNormalizer.build_command(
        raw_schema=REAL_TUYA_FAN_SCHEMA,
        action="set_timer",
        value=30,
    )
    assert len(cmd_timer) == 1
    assert cmd_timer[0]["code"] == "countdown_fan"
    assert cmd_timer[0]["value"] == 1800

    # 2. Hẹn giờ ổ cắm 1 tiếng -> 60 * 60 = 3600 giây
    cmd_timer_sock = DeviceNormalizer.build_command(
        raw_schema=REAL_TUYA_SOCKET_SCHEMA,
        action="set_timer",
        value="1 tiếng",
    )
    assert len(cmd_timer_sock) == 1
    assert cmd_timer_sock[0]["code"] == "countdown_1"
    assert cmd_timer_sock[0]["value"] == 3600


@pytest.mark.asyncio
async def test_end_to_end_sub_feature_and_timer_dispatch(tmp_path):
    """Kiểm thử end-to-end qua SmartHomeControlTool và MultiSourceDispatcher."""
    db_file = os.path.join(tmp_path, "test_traits.db")
    dal = SmartHomeDAL(f"sqlite:///{db_file}")
    user_id = "user_test_traits"
    dal.upsert_user(user_id)

    # Đăng ký quạt trần với schema thực tế có 5 DPs
    dal.upsert_device(
        device_id="tuya_test_ceiling_fan",
        user_id=user_id,
        device_name="Quạt trần phòng khách",
        category="fskg",
        platform_type=PlatformType.TUYA_EXTERNAL_SMARTLIFE,
        raw_schema=REAL_TUYA_FAN_SCHEMA,
        is_online=True,
    )

    mock_tuya = MagicMock()
    mock_tuya.get_token = AsyncMock(return_value={"access_token": "mock_token_123"})
    mock_tuya.send_device_commands = AsyncMock(return_value=True)

    dispatcher = MultiSourceDispatcher(dal_instance=dal, tuya_client=mock_tuya)
    tool = SmartHomeControlTool(dispatcher=dispatcher)

    # 1. Lệnh 1: Bật đèn quạt trần (feature='đèn')
    res_light = await tool.execute(
        user_id=user_id,
        arguments={
            "device_name": "quạt trần phòng khách",
            "action": "turn_on",
            "feature": "đèn",
        },
    )
    assert res_light["success"] is True
    assert "Đã bật đèn của Quạt trần phòng khách" in res_light["message"]
    mock_tuya.send_device_commands.assert_called_with(
        device_id="tuya_test_ceiling_fan",
        commands=[{"code": "backlight_switch", "value": True}],
        token="mock_token_123",
    )

    # 2. Lệnh 2: Hẹn giờ tắt quạt 45 phút (action='set_timer', value=45)
    res_timer = await tool.execute(
        user_id=user_id,
        arguments={
            "device_name": "quạt trần phòng khách",
            "action": "set_timer",
            "value": 45,
        },
    )
    assert res_timer["success"] is True
    assert "Đã hẹn giờ tắt Quạt trần phòng khách sau 45 phút" in res_timer["message"]
    mock_tuya.send_device_commands.assert_called_with(
        device_id="tuya_test_ceiling_fan",
        commands=[{"code": "countdown_fan", "value": 2700}],
        token="mock_token_123",
    )

    # 3. Lệnh 3: Bật quạt cánh thông thường (không truyền feature)
    res_fan = await tool.execute(
        user_id=user_id,
        arguments={
            "device_name": "quạt trần phòng khách",
            "action": "turn_on",
        },
    )
    assert res_fan["success"] is True
    assert "Đã bật Quạt trần phòng khách cho bạn rồi nhé" in res_fan["message"]
    mock_tuya.send_device_commands.assert_called_with(
        device_id="tuya_test_ceiling_fan",
        commands=[{"code": "switch_fan", "value": True}],
        token="mock_token_123",
    )

