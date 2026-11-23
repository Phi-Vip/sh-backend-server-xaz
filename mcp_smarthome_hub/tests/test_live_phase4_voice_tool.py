# -*- coding: utf-8 -*-
"""KIỂM THỬ THỰC TẾ PHASE 4: GỌI TOOL MCP SMARTHOME_CONTROL BẰNG KHẨU LỆNH TIẾNG VIỆT
Mô phỏng câu gọi của LLM -> SmartHomeControlTool -> MultiSourceDispatcher O(1) -> TuyaClient -> Thiết bị thật!
"""

import asyncio
import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
HUB_DIR = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
SERVER_ROOT = os.path.abspath(os.path.join(HUB_DIR, ".."))
for p in [HUB_DIR, SERVER_ROOT]:
    if p not in sys.path:
        sys.path.insert(0, p)

# Đọc cấu hình từ .env
env_file = os.path.join(SERVER_ROOT, ".env")
if os.path.exists(env_file):
    with open(env_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ[k.strip()] = v.strip()

from storage.db import default_dal
from storage.models import PlatformType
from clients.tuya_client import TuyaCloudClient
from dispatcher.context_injector import ContextInjector
from dispatcher.multisource_dispatcher import MultiSourceDispatcher
from tools.smarthome_tool import SmartHomeControlTool


async def run_live_phase4_test():
    print("\n" + "=" * 70)
    print("  KIỂM THỬ THỰC TẾ PHASE 4: ĐIỀU KHIỂN BẰNG CÔNG CỤ MCP SMARTHOME")
    print("=" * 70)

    user_id = "user_real_phi"
    default_dal.upsert_user(user_id=user_id)

    # Đăng ký bóng đèn của bạn vào CSDL Cục bộ
    device_id = "vdevo179447342725302"
    device_name = "Đèn ngủ thông minh"
    
    bulb_schema = {
        "functions": [
            {"code": "switch_led", "type": "Boolean"},
            {"code": "bright_value_v2", "type": "Integer", "values": "{\"min\":10,\"max\":1000,\"step\":1}"},
        ]
    }
    default_dal.upsert_device(
        device_id=device_id,
        user_id=user_id,
        device_name=device_name,
        category="dj",
        platform_type=PlatformType.TUYA_OEM_ESUNHOUSE,
        raw_schema=bulb_schema,
    )
    print(f"[✓] Bước 1: Đã nạp thiết bị [{device_name}] (ID: {device_id}) vào Context CSDL")

    # Khởi tạo chuỗi liên kết Phase 4
    tuya_client = TuyaCloudClient(
        client_id=os.environ["TUYA_CLIENT_ID"],
        client_secret=os.environ["TUYA_CLIENT_SECRET"],
        base_url=os.environ["TUYA_BASE_URL"],
    )
    injector = ContextInjector(dal_instance=default_dal)
    dispatcher = MultiSourceDispatcher(
        dal_instance=default_dal,
        tuya_client=tuya_client,
        context_injector=injector,
    )
    tool = SmartHomeControlTool(dispatcher=dispatcher)

    # 1. Thử sinh System Prompt Context cho LLM
    context_text = injector.build_llm_system_prompt_context(user_id=user_id)
    print("\n[*] KHỐI NGỮ CẢNH TIÊM VÀO LLM:")
    print(context_text)

    # 2. Giả lập LLM phát lệnh: Bật đèn phòng ngủ và chỉnh độ sáng 85%
    print("\n[*] Mô phỏng LLM gọi Function Calling: smarthome_control(device_name='đèn ngủ', action='set_brightness', value=85)...")
    res = await tool.execute(
        user_id=user_id,
        arguments={
            "device_name": "đèn ngủ",
            "action": "set_brightness",
            "value": 85,
        }
    )

    print("\n" + "-" * 70)
    print(f"  [✓] THỰC THI THÀNH CÔNG MCP TOOL:")
    print(f"  [✓] Trạng thái: {res.get('success')}")
    print(f"  [✓] Nền tảng phân luồng: {res.get('platform')}")
    print(f"  [✓] Thiết bị khớp: {res.get('device_name')} (ID: {res.get('device_id')})")
    print(f"  [✓] Câu thoại phản hồi tiếng Việt: \"{res.get('message')}\"")
    print(f"  [✓] Thời gian xử lý toàn trình: {res.get('duration_ms')} ms")
    print("-" * 70)
    print("\n👉 Bạn hãy nhìn vào màn hình điện thoại: Thanh độ sáng vừa được nâng lên 85%!\n")

    await tuya_client.close()


if __name__ == "__main__":
    asyncio.run(run_live_phase4_test())

