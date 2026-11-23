# -*- coding: utf-8 -*-
"""KIỂM THỬ ĐỘNG CƠ FALLBACK HAI TẦNG THING MODEL (TWO-TIER HYBRID SCHEMA RESOLUTION).
(HƯỚNG XỬ LÝ CÁCH 2 - CHUẨN THƯƠNG MẠI CHO THIẾT BỊ CHƯA MAP STANDARD ADAPTATION)

Mục tiêu kiểm thử:
1. Phát hiện chính xác thiết bị thiếu Standard Specification (< 3 DPs, thiếu công tắc nguồn).
2. Tự động truy vấn Thing Model (GET /v2.0/cloud/thing/{id}/model) và chuyển đổi thành công sang functions/status.
3. Bộ phân loại DPClassifier và tổng hợp năng lực tự động cho danh mục máy lọc không khí (kj).
4. Chuẩn hóa lệnh Bật/Tắt (Switch), Tốc độ gió (Speed), Tia UV (uv) từ khẩu lệnh tự nhiên tiếng Việt.
5. Điều phối lệnh tương thích kép (Dual-Mode Dispatching): Gửi shadow issue cho thing_model, gửi commands cho standard.
6. Kiểm thử trực tiếp với máy chủ Tuya Cloud Singapore đối với thiết bị thực tế vdevo179456346855367.
"""

import os
import sys
import json
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Đảm bảo đường dẫn thư mục gốc xiaozhi-esp32-server và mcp_smarthome_hub luôn có trong sys.path
SERVER_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HUB_ROOT = os.path.join(SERVER_ROOT, "mcp_smarthome_hub")
if SERVER_ROOT not in sys.path:
    sys.path.insert(0, SERVER_ROOT)
if HUB_ROOT not in sys.path:
    sys.path.insert(0, HUB_ROOT)

from mcp_smarthome_hub.storage.db import SmartHomeDAL
from mcp_smarthome_hub.storage.models import PlatformType
from mcp_smarthome_hub.clients.tuya_client import TuyaCloudClient
from mcp_smarthome_hub.adapters.dp_classifier import DPClassifier
from mcp_smarthome_hub.adapters.normalizer import DeviceNormalizer
from mcp_smarthome_hub.dispatcher.multisource_dispatcher import MultiSourceDispatcher
from mcp_smarthome_hub.sync.device_syncer import sync_tuya_devices


# Mẫu dữ liệu giả lập Thing Model của Máy lọc không khí K15A (15 DPs gốc)
MOCK_AIR_PURIFIER_THING_MODEL = {
    "model": json.dumps({
        "modelId": "elktmg",
        "services": [{
            "code": "",
            "name": "默认服务",
            "properties": [
                {"abilityId": 1, "code": "Switch", "name": "开关", "typeSpec": {"type": "bool"}},
                {"abilityId": 2, "code": "PM25", "name": "PM2.5", "typeSpec": {"type": "value", "min": 0, "max": 500, "scale": 0, "step": 1, "unit": ""}},
                {"abilityId": 3, "code": "Mode", "name": "模式", "typeSpec": {"type": "enum", "range": ["0", "1", "2", "3"]}},
                {"abilityId": 4, "code": "Speed", "name": "风速", "typeSpec": {"type": "enum", "range": ["1", "2", "3"]}},
                {"abilityId": 5, "code": "Filter", "name": "滤网已使用", "typeSpec": {"type": "value", "min": 0, "max": 999999, "scale": 0, "step": 1, "unit": "小时"}},
                {"abilityId": 6, "code": "Anion", "name": "负离子", "typeSpec": {"type": "bool"}},
                {"abilityId": 7, "code": "Lock", "name": "童锁", "typeSpec": {"type": "bool"}},
                {"abilityId": 8, "code": "Light", "name": "灯光", "typeSpec": {"type": "bool"}},
                {"abilityId": 9, "code": "uv", "name": "UV杀菌", "typeSpec": {"type": "bool"}},
                {"abilityId": 11, "code": "filter_reset", "name": "滤芯复位", "typeSpec": {"type": "bool"}},
                {"abilityId": 17, "code": "TotalTime", "name": "累计运行时间", "typeSpec": {"type": "value", "min": 0, "max": 5256000, "scale": 0, "step": 60, "unit": "小时"}},
                {"abilityId": 19, "code": "Timer", "name": "倒计时", "typeSpec": {"type": "enum", "range": ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12"]}},
                {"abilityId": 20, "code": "Countdown", "name": "倒计时剩余时间", "typeSpec": {"type": "value", "min": 0, "max": 720, "scale": 0, "step": 1, "unit": "分钟"}},
                {"abilityId": 21, "code": "Fault", "name": "故障告警", "typeSpec": {"type": "bitmap", "label": ["1", "2", "3", "4", "5", "6"], "maxlen": 6}},
                {"abilityId": 101, "code": "AB", "name": "调试", "typeSpec": {"type": "string", "maxlen": 255}},
            ]
        }]
    })
}


@pytest.fixture
def memory_dal():
    """CSDL SQLite In-Memory độc lập."""
    return SmartHomeDAL(db_url="sqlite:///:memory:")


@pytest.mark.asyncio
async def test_two_tier_fallback_detection_and_sync(memory_dal):
    """Test 1: Kiểm tra cơ chế tự động kích hoạt Thing Model Fallback khi Standard Specification thiếu hụt."""
    mock_client = MagicMock()
    mock_client.get_token = AsyncMock(return_value={"access_token": "mock_token_123"})
    
    # Giả lập trả về 2 thiết bị: 1 thiết bị chuẩn (Quạt trần) và 1 thiết bị thiếu (Máy lọc không khí)
    mock_client.get_associated_user_devices = AsyncMock(return_value=[
        {
            "id": "dev_fan_001",
            "name": "Quạt trần phòng khách",
            "category": "fskg",
            "online": True,
        },
        {
            "id": "dev_purifier_002",
            "name": "Máy lọc không khí K15A",
            "category": "kj",
            "online": True,
        }
    ])

    # Thiết bị 1: Quạt trần trả về Standard Specification đầy đủ 5 DPs
    standard_fan_spec = {
        "category": "fskg",
        "functions": [
            {"code": "switch_fan", "type": "Boolean", "values": "{}"},
            {"code": "fan_speed", "type": "Integer", "values": json.dumps({"min": 1, "max": 100})},
            {"code": "backlight_switch", "type": "Boolean", "values": "{}"},
            {"code": "countdown_fan", "type": "Integer", "values": json.dumps({"min": 0, "max": 86400})},
            {"code": "relay_status", "type": "Enum", "values": json.dumps({"range": ["on", "off"]})},
        ],
        "status": []
    }

    # Thiết bị 2: Máy lọc không khí chỉ trả về 2 DPs phụ (uv, filter_reset), thiếu công tắc nguồn!
    incomplete_purifier_spec = {
        "category": "kj",
        "functions": [
            {"code": "uv", "type": "Boolean", "values": "{}"},
            {"code": "filter_reset", "type": "Boolean", "values": "{}"},
        ],
        "status": []
    }

    async def mock_get_device_spec(dev_id, token):
        if dev_id == "dev_fan_001":
            return standard_fan_spec
        return incomplete_purifier_spec

    mock_client.get_device_specification = AsyncMock(side_effect=mock_get_device_spec)
    mock_client.get_thing_model = AsyncMock(return_value=MOCK_AIR_PURIFIER_THING_MODEL)

    # Thực hiện đồng bộ thiết bị
    synced = await sync_tuya_devices(dal=memory_dal, tuya_client=mock_client, user_id="user_test_phi")
    assert len(synced) == 2

    # 1. Kiểm tra Quạt trần: Giữ nguyên chế độ standard
    fan_dev = memory_dal.get_device("dev_fan_001")
    assert fan_dev is not None
    assert fan_dev["raw_schema"].get("instruction_mode") == "standard"
    assert len(fan_dev["raw_schema"].get("functions")) == 5

    # 2. Kiểm tra Máy lọc không khí: ĐÃ TỰ ĐỘNG FALLBACK sang thing_model!
    purifier_dev = memory_dal.get_device("dev_purifier_002")
    assert purifier_dev is not None
    assert purifier_dev["raw_schema"].get("instruction_mode") == "thing_model"
    # Khôi phục đầy đủ 15 DPs gốc!
    p_functions = purifier_dev["raw_schema"].get("functions", [])
    assert len(p_functions) == 15

    p_codes = [f["code"] for f in p_functions]
    assert "Switch" in p_codes
    assert "Speed" in p_codes
    assert "Mode" in p_codes
    assert "PM25" in p_codes
    assert "Timer" in p_codes
    assert "uv" in p_codes


def test_dp_classifier_and_synthesize_for_purifier():
    """Test 2: Kiểm tra phân hạng DPClassifier và sinh chuỗi năng lực cho Máy lọc không khí."""
    # Nạp 15 functions từ Thing Model đã convert
    functions = [
        {"code": "Switch", "name": "开关", "type": "Boolean", "values": "{}"},
        {"code": "PM25", "name": "PM2.5", "type": "Integer", "values": "{}"},
        {"code": "Mode", "name": "模式", "type": "Enum", "values": json.dumps({"range": ["0", "1", "2", "3"]})},
        {"code": "Speed", "name": "风速", "type": "Enum", "values": json.dumps({"range": ["1", "2", "3"]})},
        {"code": "Anion", "name": "负离子", "type": "Boolean", "values": "{}"},
        {"code": "Lock", "name": "童锁", "type": "Boolean", "values": "{}"},
        {"code": "Light", "name": "灯光", "type": "Boolean", "values": "{}"},
        {"code": "uv", "name": "UV杀菌", "type": "Boolean", "values": "{}"},
        {"code": "filter_reset", "name": "滤芯复位", "type": "Boolean", "values": "{}"},
        {"code": "Fault", "name": "故障告警", "type": "Bitmap", "values": "{}"},
        {"code": "Timer", "name": "倒计时", "type": "Enum", "values": "{}"},
    ]

    classified = DPClassifier.classify_functions(functions, category="kj")
    primary_codes = [f["code"] for f in classified["primary"]]
    sub_codes = [f["code"] for f in classified["sub_features"]]
    blacklist_codes = [f["code"] for f in classified["blacklist"]]

    # Switch và Speed phải thuộc primary
    assert "Switch" in primary_codes
    assert "Speed" in primary_codes

    # Mode, uv, anion, filter_reset, Timer, Lock phải thuộc sub_features
    assert "Mode" in sub_codes
    assert "uv" in sub_codes
    assert "Anion" in sub_codes
    assert "filter_reset" in sub_codes
    assert "Timer" in sub_codes

    # Fault là cảnh báo lỗi phải bị lọc vào blacklist
    assert "Fault" in blacklist_codes

    # Sinh chuỗi năng lực tiếng Việt tự nhiên
    caps = DPClassifier.synthesize_capabilities({"functions": functions}, category="kj")
    assert "Bật/tắt máy lọc không khí" in caps
    assert "chỉnh cấp tốc độ gió" in caps
    assert "khử khuẩn UV" in caps
    assert "ion âm" in caps
    assert "chế độ lọc" in caps
    assert "Fault" not in caps


def test_command_generation_for_thing_model_purifier():
    """Test 3: Kiểm tra DeviceNormalizer sinh lệnh điều khiển chuẩn xác cho thiết bị Thing Model."""
    raw_schema = {
        "category": "kj",
        "instruction_mode": "thing_model",
        "functions": [
            {"code": "Switch", "name": "开关", "type": "Boolean", "values": "{}"},
            {"code": "Speed", "name": "风速", "type": "Enum", "values": json.dumps({"range": ["1", "2", "3"]})},
            {"code": "Mode", "name": "模式", "type": "Enum", "values": json.dumps({"range": ["0", "1", "2", "3"]})},
            {"code": "uv", "name": "UV杀菌", "type": "Boolean", "values": "{}"},
            {"code": "Anion", "name": "负离子", "type": "Boolean", "values": "{}"},
            {"code": "Timer", "name": "倒计时", "type": "Enum", "values": json.dumps({"range": ["0", "1", "2"]})},
        ]
    }

    # 1. Bật nguồn: Tự động nhận diện Switch
    cmd_on = DeviceNormalizer.build_command(raw_schema, action="turn_on")
    assert cmd_on == [{"code": "Switch", "value": True}]

    # 2. Tắt nguồn: Switch = False
    cmd_off = DeviceNormalizer.build_command(raw_schema, action="turn_off")
    assert cmd_off == [{"code": "Switch", "value": False}]

    # 3. Chỉnh tốc độ gió mức số 2
    cmd_speed_2 = DeviceNormalizer.build_command(raw_schema, action="set_speed", value=2)
    assert cmd_speed_2 == [{"code": "Speed", "value": "2"}]

    # 4. Chỉnh tốc độ khẩu ngữ "mạnh" -> tự động map sang cấp cao nhất '3'
    cmd_speed_strong = DeviceNormalizer.build_command(raw_schema, action="set_speed", value="mạnh")
    assert cmd_speed_strong == [{"code": "Speed", "value": "3"}]

    # 5. Điều khiển tính năng con (Sub-feature target): Bật tia UV
    cmd_uv = DeviceNormalizer.build_command(raw_schema, action="turn_on", feature="uv")
    assert cmd_uv == [{"code": "uv", "value": True}]

    # 6. Hẹn giờ theo Enum số giờ (120 phút -> '2' giờ)
    cmd_timer_120 = DeviceNormalizer.build_command(raw_schema, action="set_timer", value=120)
    assert cmd_timer_120 == [{"code": "Timer", "value": "2"}]

    # 7. Hẹn giờ khẩu ngữ tiếng Việt "1 tiếng" -> '1'
    cmd_timer_1h = DeviceNormalizer.build_command(raw_schema, action="set_timer", value="1 tiếng")
    assert cmd_timer_1h == [{"code": "Timer", "value": "1"}]

    # 8. Hủy hẹn giờ ("hủy" hoặc 0) -> '0'
    cmd_timer_cancel = DeviceNormalizer.build_command(raw_schema, action="set_timer", value="hủy")
    assert cmd_timer_cancel == [{"code": "Timer", "value": "0"}]


@pytest.mark.asyncio
async def test_multisource_dispatcher_dual_mode_routing(memory_dal):
    """Test 4: Kiểm tra MultiSourceDispatcher tự động phân luồng đúng endpoint theo instruction_mode."""
    mock_client = MagicMock()
    mock_client.send_device_commands = AsyncMock(return_value=True)
    mock_client.send_thing_shadow_properties = AsyncMock(return_value=True)

    dispatcher = MultiSourceDispatcher(dal_instance=memory_dal, tuya_client=mock_client)
    dispatcher._get_tuya_token = AsyncMock(return_value="mock_token_abc")

    # 1. Dispatcher điều khiển thiết bị Thing Model (Máy lọc không khí)
    memory_dal.upsert_device(
        device_id="dev_purifier_test",
        user_id="user_phi_01",
        device_name="máy lọc không khí",
        category="kj",
        platform_type=PlatformType.TUYA_EXTERNAL_SMARTLIFE,
        raw_schema={
            "category": "kj",
            "instruction_mode": "thing_model",
            "functions": [
                {"code": "Switch", "type": "Boolean", "values": "{}"},
                {"code": "Speed", "type": "Enum", "values": json.dumps({"range": ["1", "2", "3"]})},
                {"code": "Timer", "type": "Enum", "values": json.dumps({"range": ["0", "1", "2", "3"]})},
            ],
            "status": [
                {"code": "Switch", "type": "Boolean", "values": "{}"},
                {"code": "Speed", "type": "Enum", "values": json.dumps({"range": ["1", "2", "3"]})},
                {"code": "Timer", "type": "Enum", "values": json.dumps({"range": ["0", "1", "2", "3"]})},
                {"code": "PM25", "type": "Integer", "values": json.dumps({"min": 0, "max": 500})},
            ]
        }
    )

    res_purifier = await dispatcher.dispatch_command(
        user_id="user_phi_01",
        device_query="máy lọc không khí",
        action="turn_on",
    )
    assert res_purifier["success"] is True
    # BẮT BUỘC: Phải gọi send_thing_shadow_properties thay vì send_device_commands!
    mock_client.send_thing_shadow_properties.assert_called_once_with(
        device_id="dev_purifier_test",
        properties={"Switch": True},
        token="mock_token_abc",
    )
    mock_client.send_device_commands.assert_not_called()

    # 1b. Dispatcher truy vấn trạng thái thiết bị có hẹn giờ và PM2.5
    mock_client.get_thing_shadow_properties = AsyncMock(return_value=[
        {"code": "Switch", "value": True},
        {"code": "Speed", "value": "3"},
        {"code": "Timer", "value": "2"},
        {"code": "PM25", "value": 15},
    ])
    st_res = await dispatcher.dispatch_command(user_id="user_phi_01", device_query="máy lọc không khí", action="query_status")
    assert st_res["success"] is True
    assert "đang hẹn giờ tắt sau 2 tiếng" in st_res["message"]
    assert "chỉ số bụi mịn PM2.5 là 15" in st_res["message"]

    # 2. Dispatcher điều khiển thiết bị Standard (Ổ cắm)
    mock_client.send_thing_shadow_properties.reset_mock()
    mock_client.send_device_commands.reset_mock()

    memory_dal.upsert_device(
        device_id="dev_socket_test",
        user_id="user_phi_01",
        device_name="ổ cắm sân cầu",
        category="cz",
        platform_type=PlatformType.TUYA_EXTERNAL_SMARTLIFE,
        raw_schema={
            "category": "cz",
            "instruction_mode": "standard",
            "functions": [
                {"code": "switch_1", "type": "Boolean", "values": "{}"},
            ]
        }
    )

    res_socket = await dispatcher.dispatch_command(
        user_id="user_phi_01",
        device_query="ổ cắm sân cầu",
        action="turn_on",
    )
    assert res_socket["success"] is True
    # Thiết bị standard phải gọi send_device_commands!
    mock_client.send_device_commands.assert_called_once_with(
        device_id="dev_socket_test",
        commands=[{"code": "switch_1", "value": True}],
        token="mock_token_abc",
    )
    mock_client.send_thing_shadow_properties.assert_not_called()


@pytest.mark.asyncio
async def test_live_air_purifier_real_cloud():
    """Test 5 (Live Integration): Kiểm thử thực tế với máy lọc không khí vdevo179456346855367 trên Tuya Cloud."""
    env_file = os.path.join(SERVER_ROOT, ".env")
    if os.path.exists(env_file):
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

    client_id = os.getenv("TUYA_CLIENT_ID")
    client_secret = os.getenv("TUYA_CLIENT_SECRET")
    if not client_id or not client_secret:
        pytest.skip("Bỏ qua live test: Chưa có biến môi trường TUYA_CLIENT_ID / TUYA_CLIENT_SECRET")

    client = TuyaCloudClient(
        client_id=client_id,
        client_secret=client_secret,
        base_url=os.getenv("TUYA_BASE_URL", "https://openapi-sg.iotbing.com"),
    )
    token_info = await client.get_token(1)
    token = token_info.get("access_token")
    assert token is not None

    dev_id = "vdevo179456346855367"

    try:
        # 1. Truy vấn Thing Model thực tế
        model_res = await client.get_thing_model(dev_id, token=token)
        assert model_res is not None
        assert "model" in model_res

        # 2. Truy vấn Shadow Properties thực tế
        shadow_props = await client.get_thing_shadow_properties(dev_id, token=token)
        assert len(shadow_props) >= 10
        prop_codes = [p.get("code") for p in shadow_props]
        assert "Switch" in prop_codes
        assert "Speed" in prop_codes

        # 3. Gửi lệnh Bật nguồn qua Shadow Properties Issue
        ok = await client.send_thing_shadow_properties(dev_id, {"Switch": True}, token=token)
        assert ok is True

    finally:
        await client.close()


@pytest.mark.asyncio
async def test_delete_device_and_purge_stale_reconciliation():
    """Test 6: Kiểm thử DAL.delete_device và cơ chế tự động đối soát xóa thiết bị gỡ bỏ (Purge Stale Devices)."""
    dal = SmartHomeDAL("sqlite:///:memory:")
    user_id = "test_user_reconcile"

    # 1. Nạp ban đầu 3 thiết bị vào CSDL:
    # - dev_keep (Platform 3: Tuya SmartLife)
    # - dev_stale (Platform 3: Tuya SmartLife - đã bị gỡ trên App)
    # - dev_other_platform (Platform 2: Tuya OEM - không được phép đụng tới)
    dal.upsert_device(
        device_id="dev_keep",
        user_id=user_id,
        device_name="Đèn trần",
        category="dj",
        platform_type=PlatformType.TUYA_EXTERNAL_SMARTLIFE,
    )
    dal.upsert_device(
        device_id="dev_stale",
        user_id=user_id,
        device_name="Quạt trần cũ",
        category="fskg",
        platform_type=PlatformType.TUYA_EXTERNAL_SMARTLIFE,
    )
    dal.upsert_device(
        device_id="dev_other_platform",
        user_id=user_id,
        device_name="Robot hút bụi OEM",
        category="sd",
        platform_type=PlatformType.TUYA_OEM_ESUNHOUSE,
    )

    # Kiểm tra ban đầu có đủ 3 thiết bị
    all_devs = dal.list_devices_by_user(user_id)
    assert len(all_devs) == 3

    # Kiểm tra trực tiếp hàm delete_device
    assert dal.delete_device("non_existent_id") is False
    assert dal.delete_device("dev_stale") is True
    assert dal.get_device("dev_stale") is None

    # Khôi phục lại dev_stale để kiểm thử tự động dọn dẹp qua sync_tuya_devices
    dal.upsert_device(
        device_id="dev_stale",
        user_id=user_id,
        device_name="Quạt trần cũ",
        category="fskg",
        platform_type=PlatformType.TUYA_EXTERNAL_SMARTLIFE,
    )
    assert len(dal.list_devices_by_user(user_id)) == 3

    # Mock Tuya Cloud chỉ trả về dev_keep (người dùng đã xóa dev_stale khỏi App Smart Life)
    mock_tuya_client = MagicMock()
    mock_tuya_client.get_token = AsyncMock(return_value={"access_token": "mock_token"})
    mock_tuya_client.get_associated_user_devices = AsyncMock(
        return_value=[
            {
                "id": "dev_keep",
                "name": "Đèn trần",
                "category": "dj",
                "online": True,
            }
        ]
    )
    mock_tuya_client.request = AsyncMock(
        return_value={
            "result": {
                "functions": [{"code": "switch_led", "type": "Boolean", "values": "{}"}],
                "status": [{"code": "switch_led", "type": "Boolean", "values": "{}"}],
            }
        }
    )

    # Chạy đồng bộ từ Tuya Cloud
    synced = await sync_tuya_devices(dal=dal, tuya_client=mock_tuya_client, user_id=user_id)
    assert len(synced) == 1
    assert synced[0]["device_id"] == "dev_keep"

    # Kiểm tra đối soát sau khi sync:
    # 1. dev_keep vẫn tồn tại
    assert dal.get_device("dev_keep") is not None
    # 2. dev_stale đã bị tự động xóa sạch khỏi CSDL
    assert dal.get_device("dev_stale") is None
    # 3. dev_other_platform (thuộc platform_type khác) được bảo vệ nguyên vẹn
    assert dal.get_device("dev_other_platform") is not None
    assert dal.get_device("dev_other_platform")["device_name"] == "Robot hút bụi OEM"

    # Tổng số thiết bị trong DB của user này chỉ còn 2 (dev_keep và dev_other_platform)
    remaining_devs = dal.list_devices_by_user(user_id)
    remaining_ids = {d["device_id"] for d in remaining_devs}
    assert remaining_ids == {"dev_keep", "dev_other_platform"}

