# -*- coding: utf-8 -*-
"""SCRIPT ĐIỀU KHIỂN THỰC TẾ BÓNG ĐÈN ẢO TỪ MÁY CHỦ XIAOZHI SANG TUYA SINGAPORE
Bóng đèn: Smart Bulb-Phi-Virtual (Device ID: vdevo179447342725302)
"""

import asyncio
import os
import sys
import time

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

from mcp_smarthome_hub.clients.tuya_client import TuyaCloudClient


async def run_live_bulb_control():
    print("\n" + "=" * 70)
    print("  ĐIỀU KHIỂN BÓNG ĐÈN THỰC TẾ: SMART BULB-PHI-VIRTUAL")
    print("=" * 70)

    client = TuyaCloudClient(
        client_id=os.environ["TUYA_CLIENT_ID"],
        client_secret=os.environ["TUYA_CLIENT_SECRET"],
        base_url=os.environ["TUYA_BASE_URL"],
    )

    device_id = "vdevo179447342725302"
    token_data = await client.get_token(grant_type=1)
    token = token_data["access_token"]
    print(f"[*] Access Token Tuya: {token[:6]}... (Hợp lệ)")

    # 1. Đọc trạng thái ban đầu
    status = await client.get_device_status(device_id, token)
    status_map = {s["code"]: s["value"] for s in status}
    is_on = status_map.get("switch_led", False)
    bright = status_map.get("bright_value_v2", 0)
    print(f"\n[*] TRẠNG THÁI HIỆN TẠI TRÊN ĐIỆN THOẠI:")
    print(f"    - Công tắc (switch_led) : {'BẬT (ON)' if is_on else 'TẮT (OFF)'}")
    print(f"    - Độ sáng (bright_value): {bright // 10}% ({bright}/1000)")

    # 2. Gửi lệnh đổi trạng thái công tắc
    new_state = not is_on
    action_str = "BẬT ĐÈN" if new_state else "TẮT ĐÈN"
    print(f"\n[*] Đang gửi lệnh từ Server XiaoZhi: >> {action_str} << sang Singapore...")
    t0 = time.time()
    ok = await client.send_device_commands(
        device_id,
        [{"code": "switch_led", "value": new_state}],
        token
    )
    rtt = (time.time() - t0) * 1000
    print(f"[✓] Kết quả thực thi: Thành công={ok} (Độ trễ RTT: {rtt:.2f}ms)")

    # 3. Đọc lại để xác nhận
    await asyncio.sleep(0.5)
    new_status = await client.get_device_status(device_id, token)
    new_map = {s["code"]: s["value"] for s in new_status}
    print(f"\n[*] TRẠNG THÁI MỚI SAU KHI SERVER RA LỆNH:")
    print(f"    - Công tắc (switch_led) : {'BẬT (ON)' if new_map.get('switch_led') else 'TẮT (OFF)'}")
    print("=" * 70)
    print(f"\n👉 Bạn hãy nhìn vào màn hình điện thoại trong app Smart Life:")
    print(f"   Bóng đèn 'Smart Bulb-Phi-Virtual' đã vừa tự động chuyển sang {'BẬT (Xanh)' if new_map.get('switch_led') else 'TẮT (Xám)'}!\n")

    await client.close()


if __name__ == "__main__":
    asyncio.run(run_live_bulb_control())

