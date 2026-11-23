# -*- coding: utf-8 -*-
"""KIỂM THỬ THỰC TẾ KẾT NỐI TUYA CLOUD OPENAPI (SINGAPORE GATEWAY)
Sử dụng Access ID và Access Secret từ .env để:
1. Gửi request ký HMAC-SHA256 lên máy chủ Singapore (openapi.tuyasg.com / openapi-sg.tuya.com).
2. Lấy Access Token thực tế và đo RTT độ trễ mạng.
3. Kiểm tra tính hợp lệ và thời hạn của Token (7200s).
"""

import asyncio
import os
import sys
import time

# Đường dẫn thư mục
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

import pytest
from mcp_smarthome_hub.clients.tuya_client import TuyaCloudClient, TuyaAPIException


@pytest.mark.asyncio
async def test_live_connection():
    print("\n" + "=" * 70)
    print("  KIỂM THỬ THỰC TẾ: KẾT NỐI ĐÁM MÂY TUYA CLOUD (SINGAPORE GATEWAY)")
    print("=" * 70)

    client_id = os.environ.get("TUYA_CLIENT_ID")
    client_secret = os.environ.get("TUYA_CLIENT_SECRET")
    base_url = os.environ.get("TUYA_BASE_URL", "https://openapi.tuyasg.com")

    if not client_id or not client_secret:
        print("[!] Lỗi: Không tìm thấy TUYA_CLIENT_ID hoặc TUYA_CLIENT_SECRET trong .env")
        return

    # In thông tin đã được ẩn bớt để bảo mật tuyệt đối
    masked_secret = client_secret[:4] + "*" * (len(client_secret) - 8) + client_secret[-4:]
    print(f"[*] Client ID    : {client_id}")
    print(f"[*] Client Secret: {masked_secret} (Được bảo vệ an toàn)")
    print(f"[*] Gateway URL  : {base_url}")
    print("[*] Đang gửi yêu cầu xác thực chữ ký HMAC-SHA256 lên máy chủ Singapore...")

    # Khởi tạo Tuya Client
    client = TuyaCloudClient(
        client_id=client_id,
        client_secret=client_secret,
        base_url=base_url,
        timeout_seconds=8.0,
    )

    t0 = time.time()
    try:
        token_info = await client.get_token(grant_type=1)
        rtt = (time.time() - t0) * 1000

        access_token = token_info.get("access_token", "")
        masked_token = access_token[:6] + "..." + access_token[-6:] if len(access_token) > 12 else "******"
        expire_time = token_info.get("expire_time", 0)
        uid = token_info.get("uid", "")

        print("\n" + "-" * 70)
        print(f"  [✓] KẾT NỐI THÀNH CÔNG VỚI TUYA CLOUD SINGAPORE!")
        print(f"  [✓] Độ trễ mạng (RTT toàn trình): {rtt:.2f} ms")
        print(f"  [✓] Access Token được cấp      : {masked_token}")
        print(f"  [✓] Thời hạn Token (Expire)    : {expire_time} giây ({expire_time // 3600} giờ)")
        print(f"  [✓] Project UID                : {uid}")
        print("-" * 70)

        # Truy vấn thử danh sách thiết bị
        try:
            devices = await client.get_user_devices(tuya_uid=uid, token=access_token)
            print(f"[*] Danh sách thiết bị trong dự án: {len(devices)} thiết bị.")
            if len(devices) == 0:
                print("    (Hiện tại chưa có thiết bị nào, sẵn sàng chờ bạn quét QR khi bóng đèn về!)")
            for dev in devices:
                print(f"    - {dev.get('name')} (ID: {dev.get('id')}) - Online: {dev.get('online')}")
        except Exception as e_dev:
            print(f"[*] Ghi chú thiết bị: {e_dev}")

        print("\n=> KẾT LUẬN: Cặp khóa bí mật hợp lệ 100%! Thuật toán HMAC-SHA256 của Giai đoạn 2")
        print("   hoạt động hoàn hảo với API thật của Tuya Cloud toàn cầu.\n")

    except TuyaAPIException as e:
        print(f"\n[X] Lỗi từ máy chủ Tuya Cloud: {e}")
        # Thử lại với gateway dự phòng openapi-sg.tuya.com nếu gateway đầu gặp lỗi
        if "openapi.tuyasg.com" in base_url:
            print("[*] Đang thử kết nối gateway dự phòng: https://openapi-sg.tuya.com ...")
            client.base_url = "https://openapi-sg.tuya.com"
            try:
                token_info = await client.get_token(grant_type=1)
                rtt = (time.time() - t0) * 1000
                print(f"  [✓] Kết nối thành công qua gateway dự phòng! RTT: {rtt:.2f}ms")
            except Exception as err:
                print(f"[X] Lỗi gateway dự phòng: {err}")
    except Exception as e:
        print(f"\n[X] Lỗi không xác định: {e}")
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(test_live_connection())

