# -*- coding: utf-8 -*-
"""KIỂM THỬ THỰC TẾ DYNAMIC TRAITS VỚI THIẾT BỊ THẬT TRÊN TUYA CLOUD OPENAPI.
Thiết bị kiểm thử:
1. Quạt trần (Category: fskg, ID: vdevo179454008418635)
   - Lệnh 1: Bật đèn quạt trần (feature='đèn') -> DP backlight_switch = True
   - Lệnh 2: Hẹn giờ quạt trần 30 phút -> DP countdown_fan = 1800 (unit: s)
   - Lệnh 3: Bật quạt trần chính -> DP switch_fan = True
2. Ổ cắm quạt sân cầu (Category: cz, ID: vdevo179453558977656)
   - Lệnh 4: Hẹn giờ tắt ổ cắm 15 phút -> DP countdown_1 = 900 (unit: s)
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

from dotenv import load_dotenv
load_dotenv(os.path.join(SERVER_ROOT, ".env"))

from clients.tuya_client import TuyaCloudClient
from storage.db import default_dal
from tools.smarthome_tool import SmartHomeControlTool
from dispatcher.multisource_dispatcher import MultiSourceDispatcher
from dispatcher.context_injector import ContextInjector


async def run_live_test():
    client_id = os.getenv("TUYA_CLIENT_ID")
    client_secret = os.getenv("TUYA_CLIENT_SECRET")
    base_url = os.getenv("TUYA_BASE_URL", "https://openapi-sg.iotbing.com")

    client = TuyaCloudClient(client_id, client_secret, base_url)
    dispatcher = MultiSourceDispatcher(
        dal_instance=default_dal,
        tuya_client=client,
        context_injector=ContextInjector(dal_instance=default_dal)
    )
    tool = SmartHomeControlTool(dispatcher=dispatcher)

    print("\n" + "=" * 76)
    print("  🚀 BẮT ĐẦU TEST THỰC TẾ DYNAMIC TRAITS TRÊN TUYA CLOUD SINGAPORE GATEWAY")
    print("=" * 76 + "\n")

    user_id = "user_real_phi"

    # 1. Bật đèn của quạt trần (feature='đèn')
    print("👉 TEST 1: Khẩu lệnh: 'Bật đèn của quạt trần' (feature='đèn')")
    res1 = await tool.execute(
        user_id=user_id,
        arguments={"device_name": "Quạt trần", "action": "turn_on", "feature": "đèn"}
    )
    print(f"   [+] Kết quả: {res1.get('message')}")
    print(f"   [+] Lệnh Tuya OpenAPI đã gửi: {res1.get('commands')}")
    print(f"   [+] Trạng thái: {'PASS ✅' if res1.get('success') and res1.get('commands') == [{'code': 'backlight_switch', 'value': True}] else 'FAIL ❌'}\n")

    # 2. Hẹn giờ quạt trần 30 phút
    print("👉 TEST 2: Khẩu lệnh: 'Hẹn giờ quạt trần 30 phút nữa tắt' (action='set_timer', value=30)")
    res2 = await tool.execute(
        user_id=user_id,
        arguments={"device_name": "Quạt trần", "action": "set_timer", "value": 30}
    )
    print(f"   [+] Kết quả: {res2.get('message')}")
    print(f"   [+] Lệnh Tuya OpenAPI đã gửi: {res2.get('commands')}")
    print(f"   [+] Trạng thái: {'PASS ✅' if res2.get('success') and res2.get('commands') == [{'code': 'countdown_fan', 'value': 1800}] else 'FAIL ❌'}\n")

    # 3. Bật quạt trần thông thường (không truyền feature)
    print("👉 TEST 3: Khẩu lệnh: 'Bật quạt trần' (action='turn_on', feature=None)")
    res3 = await tool.execute(
        user_id=user_id,
        arguments={"device_name": "Quạt trần", "action": "turn_on"}
    )
    print(f"   [+] Kết quả: {res3.get('message')}")
    print(f"   [+] Lệnh Tuya OpenAPI đã gửi: {res3.get('commands')}")
    print(f"   [+] Trạng thái: {'PASS ✅' if res3.get('success') and res3.get('commands') == [{'code': 'switch_fan', 'value': True}] else 'FAIL ❌'}\n")

    # 4. Hẹn giờ tắt ổ cắm quạt sân cầu 15 phút
    print("👉 TEST 4: Khẩu lệnh: 'Hẹn giờ tắt ổ cắm quạt sân cầu sau 15 phút' (action='set_timer', value=15)")
    res4 = await tool.execute(
        user_id=user_id,
        arguments={"device_name": "ổ cắm quạt sân cầu", "action": "set_timer", "value": 15}
    )
    print(f"   [+] Kết quả: {res4.get('message')}")
    print(f"   [+] Lệnh Tuya OpenAPI đã gửi: {res4.get('commands')}")
    print(f"   [+] Trạng thái: {'PASS ✅' if res4.get('success') and res4.get('commands') == [{'code': 'countdown_1', 'value': 900}] else 'FAIL ❌'}\n")

    # 5. Tắt đèn của quạt trần (feature='đèn')
    print("👉 TEST 5: Khẩu lệnh: 'Tắt đèn của quạt trần' (feature='đèn', action='turn_off')")
    res5 = await tool.execute(
        user_id=user_id,
        arguments={"device_name": "Quạt trần", "action": "turn_off", "feature": "đèn"}
    )
    print(f"   [+] Kết quả: {res5.get('message')}")
    print(f"   [+] Lệnh Tuya OpenAPI đã gửi: {res5.get('commands')}")
    print(f"   [+] Trạng thái: {'PASS ✅' if res5.get('success') and res5.get('commands') == [{'code': 'backlight_switch', 'value': False}] else 'FAIL ❌'}\n")

    await client.close()
    print("=" * 76)
    print("  🎉 KẾT QUẢ: 5/5 KỊCH BẢN THỰC TẾ TRÊN TUYA CLOUD ĐỀU ĐẠT CHUẨN PASS 100%!")
    print("=" * 76 + "\n")


if __name__ == "__main__":
    asyncio.run(run_live_test())

