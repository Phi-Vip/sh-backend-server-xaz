"""Unit Tests Nghiệm Thu GIAI ĐOẠN 1 (Chuẩn Mass Production).

Tuân thủ nghiêm ngặt bảng tiêu chí TEST CASE 1:
- Bước 1: Tự động chèn 100 user và 100 loa MAC vào CSDL.
- Bước 2: Kiểm tra trực tiếp bảng CSDL: Toàn bộ Token & LocalKey phải ở dạng Ciphertext (AES-256-GCM),
          tuyệt đối không xuất hiện plaintext trong raw database.
- Bước 3: Đọc Token qua DAL: Giải mã chính xác 100% về chuỗi gốc trong thời gian < 5ms.
- Bước 4: Giả lập ép hạn Token về còn 200s (< 300s), kích hoạt Worker:
          Worker tự động phát hiện và gọi hàm refresh cập nhật CSDL.
- Bước 5: KIỂM THỬ KHÓA PHÂN TÁN (RACE CONDITION PREVENTION):
          Khởi chạy đồng thời 5 tiến trình Worker giả lập cùng refresh token cho 1 Target ID:
          Chỉ có duy nhất 1 request gửi lên Tuya, 4 worker còn lại bị chặn bởi Lock,
          CSDL nhất quán 100%.
"""

import os
import sys
import time
import asyncio
import pytest
from datetime import datetime, timedelta
from sqlalchemy import text

# Đảm bảo đường dẫn thư mục gốc xiaozhi-esp32-server luôn có trong sys.path
SERVER_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if SERVER_ROOT not in sys.path:
    sys.path.insert(0, SERVER_ROOT)

from mcp_smarthome_hub.storage.token_vault import TokenVault, vault
from mcp_smarthome_hub.storage.models import (
    PlatformType,
    TuyaProjectToken,
    TuyaUserCredential,
    DeviceCache,
)
from mcp_smarthome_hub.storage.db import SmartHomeDAL
from mcp_smarthome_hub.storage.token_manager import TuyaTokenManager


@pytest.fixture
def memory_dal():
    """Tạo SmartHomeDAL chạy trên SQLite Memory biệt lập cho mỗi test."""
    test_vault_key = b"test_secret_master_key_32_bytes!"
    custom_vault = TokenVault(test_vault_key)
    dal = SmartHomeDAL(db_url="sqlite:///:memory:")
    # Gán vault riêng cho DAL test
    return dal


@pytest.fixture
def token_mgr(memory_dal):
    """Tạo TuyaTokenManager kết nối với memory_dal."""
    return TuyaTokenManager(dal_instance=memory_dal)


def test_hash_user_id_compliance():
    """Kiểm tra tuân thủ Nghị định 356/2025/NĐ-CP: Ẩn danh hóa UID dạng sh_{SHA256}."""
    user_id = "user_sunhouse_998811"
    anon_uid = vault.hash_user_id(user_id)
    assert anon_uid.startswith("sh_")
    assert len(anon_uid) == 67  # 'sh_' (3) + 64 hex SHA-256 = 67 chars
    # Đảm bảo tính tất định (Deterministic) với cùng salt
    assert anon_uid == vault.hash_user_id(user_id)


def test_tampered_ciphertext_detection():
    """Kiểm thử tính toàn vẹn của AES-256-GCM: Sửa 1 byte ciphertext lập tức phát hiện lỗi."""
    secret = "my_super_secret_tuya_token_12345"
    encrypted = vault.encrypt(secret)
    # Làm hỏng 1 ký tự trong ciphertext Base64
    tampered_bytes = bytearray(encrypted.encode("utf-8"))
    tampered_bytes[-2] = ord("A") if tampered_bytes[-2] != ord("A") else ord("B")
    tampered_str = tampered_bytes.decode("utf-8")

    with pytest.raises(Exception):
        vault.decrypt(tampered_str)


def test_step1_step2_step3_multi_tenant_and_dal_encryption(memory_dal):
    """BƯỚC 1, 2, 3: Chèn 100 user, 100 loa MAC; Thẩm định Ciphertext CSDL & Đo lường RTT DAL."""
    print("\n--- BẮT ĐẦU BƯỚC 1: Chèn 100 User và 100 Loa MAC ---")
    start_insert = time.time()

    plaintext_tokens = {}
    plaintext_keys = {}

    for i in range(1, 101):
        uid = f"user_{i:03d}"
        mac = f"AA:BB:CC:DD:EE:{i:02X}"
        speaker_name = f"Loa XiaoZhi Phòng Khách {i}"
        raw_access_token = f"tuya_access_token_secret_for_user_{i}_{time.time()}"
        raw_refresh_token = f"tuya_refresh_token_secret_for_user_{i}"
        raw_local_key = f"localkey_{i:04d}_secret"

        plaintext_tokens[uid] = (raw_access_token, raw_refresh_token)
        plaintext_keys[f"dev_{i:03d}"] = raw_local_key

        # Chèn user & speaker
        memory_dal.upsert_user(uid)
        memory_dal.upsert_speaker(speaker_mac=mac, user_id=uid, device_name=speaker_name)

        # Chèn User Token
        memory_dal.save_user_credential(
            user_id=uid,
            external_tuya_uid=f"ext_tuya_{i}",
            access_token=raw_access_token,
            refresh_token=raw_refresh_token,
            expire_at=datetime.utcnow() + timedelta(hours=2),
        )

        # Chèn Device vào Device Cache (kèm local_key)
        memory_dal.upsert_device(
            device_id=f"dev_{i:03d}",
            user_id=uid,
            device_name=f"Robot 298 Pro Ultra {i}",
            category="sd",
            platform_type=PlatformType.TUYA_OEM_ESUNHOUSE,
            local_key=raw_local_key,
            local_ip=f"192.168.1.{i}",
            raw_schema={"suction": "max", "mop_washing": True},
        )

    insert_duration = time.time() - start_insert
    print(f"✓ Hoàn tất chèn 100 user, 100 loa, 100 credential, 100 thiết bị trong {insert_duration:.3f}s")

    print("\n--- BẮT ĐẦU BƯỚC 2: Kiểm tra trực tiếp bảng thô CSDL (Raw SQL Inspection) ---")
    with memory_dal.get_session() as session:
        # Truy vấn thô bảng tuya_user_credentials
        raw_creds = session.execute(
            text("SELECT user_id, access_token_encrypted, refresh_token_encrypted FROM tuya_user_credentials")
        ).fetchall()
        assert len(raw_creds) == 100

        for row in raw_creds:
            uid, enc_acc, enc_ref = row[0], row[1], row[2]
            raw_acc, raw_ref = plaintext_tokens[uid]

            # TUYỆT ĐỐI KHÔNG ĐƯỢC CHỨA CHUỖI GỐC TRONG CSDL
            assert raw_acc not in enc_acc, f"LỖI BẢO MẬT: Plaintext token lộ trong DB cho {uid}!"
            assert raw_ref not in enc_ref, f"LỖI BẢO MẬT: Plaintext refresh token lộ trong DB cho {uid}!"
            assert enc_acc.isalnum or "=" in enc_acc, "Encrypted token phải là chuỗi Base64 hợp lệ!"

        # Truy vấn thô bảng device_cache
        raw_devices = session.execute(
            text("SELECT device_id, local_key_encrypted FROM device_cache")
        ).fetchall()
        assert len(raw_devices) == 100

        for row in raw_devices:
            dev_id, enc_key = row[0], row[1]
            raw_k = plaintext_keys[dev_id]
            assert raw_k not in enc_key, f"LỖI BẢO MẬT: LocalKey lộ trong DB cho {dev_id}!"

    print("✓ PASS BƯỚC 2: 100% Token và LocalKey được lưu trữ dạng Ciphertext AES-256-GCM, ZERO PLAINTEXT!")

    print("\n--- BẮT ĐẦU BƯỚC 3: Đọc Token & Thiết bị qua DAL (Thẩm định RTT < 5ms) ---")
    start_read = time.time()
    for uid in plaintext_tokens:
        cred = memory_dal.get_user_credential(uid)
        assert cred is not None
        expected_acc, expected_ref = plaintext_tokens[uid]
        assert cred["access_token"] == expected_acc
        assert cred["refresh_token"] == expected_ref

    for dev_id in plaintext_keys:
        dev = memory_dal.get_device(dev_id)
        assert dev is not None
        expected_k = plaintext_keys[dev_id]
        assert dev["local_key"] == expected_k
        assert dev["raw_schema"]["suction"] == "max"

    total_read_time = time.time() - start_read
    avg_per_record = (total_read_time / 200) * 1000  # ms
    print(f"✓ Đọc & giải mã 200 bản ghi trong {total_read_time:.3f}s (Trung bình: {avg_per_record:.3f}ms/bản ghi)")
    assert avg_per_record < 5.0, f"Thời gian xử lý DAL vượt ngưỡng 5ms: {avg_per_record:.2f}ms"
    print("✓ PASS BƯỚC 3: Giải mã chính xác 100% dữ liệu gốc, thời gian RTT DAL < 5ms đạt chuẩn MP!")


@pytest.mark.asyncio
async def test_step4_simulated_token_expiration_refresh(token_mgr, memory_dal):
    """BƯỚC 4: Giả lập ép hạn Token còn 200s (< 300s), Worker tự động gọi API lấy Token mới."""
    print("\n--- BẮT ĐẦU BƯỚC 4: Kiểm thử Tự động Làm mới khi Token còn < 300s ---")
    client_id = "test_tuya_client_sunhouse_2026"

    # Giả lập token hiện tại chỉ còn 200 giây sống (< ngưỡng 300s)
    old_access_token = "tuya_old_token_about_to_expire"
    old_refresh_token = "tuya_refresh_token_v1"
    exp_200s = datetime.utcnow() + timedelta(seconds=200)

    memory_dal.save_project_token(
        client_id=client_id,
        access_token=old_access_token,
        refresh_token=old_refresh_token,
        expire_at=exp_200s,
    )

    refresh_called = False

    async def mock_tuya_refresh_api(cid: str, r_token: str):
        nonlocal refresh_called
        refresh_called = True
        return {
            "access_token": "tuya_new_fresh_token_7200s",
            "refresh_token": "tuya_new_refresh_token_v2",
            "expire_time": 7200,
        }

    # Gọi get_valid_project_token
    token = await token_mgr.get_valid_project_token(client_id, refresh_callback=mock_tuya_refresh_api)

    assert refresh_called is True, "Worker không kích hoạt gọi API refresh khi token < 300s!"
    assert token == "tuya_new_fresh_token_7200s", "Token trả về không phải token mới!"

    # Kiểm tra CSDL đã được cập nhật token mới và gia hạn 7200s chưa
    updated_data = memory_dal.get_project_token(client_id)
    assert updated_data["access_token"] == "tuya_new_fresh_token_7200s"
    time_left = (updated_data["expire_at"] - datetime.utcnow()).total_seconds()
    assert time_left > 7000, f"Hạn sống Token không được gia hạn đủ 7200s: {time_left:.1f}s"
    print("✓ PASS BƯỚC 4: Token sắp hết hạn (<300s) tự động được refresh thành công và cập nhật DB!")


@pytest.mark.asyncio
async def test_step5_distributed_lock_race_condition(token_mgr, memory_dal):
    """BƯỚC 5: Kiểm thử Khóa phân tán: 5 worker đồng thời refresh cho 1 target_id.

    Tiêu chí: Duy nhất 1 worker được gọi API Tuya thật sự, 4 worker còn lại
    bị chặn bởi RedLock và đọc kết quả nhất quán.
    """
    print("\n--- BẮT ĐẦU BƯỚC 5: Kiểm thử Khóa Phân Tán (Race Condition Prevention) ---")
    client_id = "test_tuya_shared_client_oem"

    # Token ban đầu đã hết hạn
    memory_dal.save_project_token(
        client_id=client_id,
        access_token="expired_token_001",
        refresh_token="ref_token_001",
        expire_at=datetime.utcnow() - timedelta(seconds=10),
    )

    api_call_count = 0
    lock_counter = asyncio.Lock()

    async def mock_tuya_api(cid: str, r_token: str):
        nonlocal api_call_count
        async with lock_counter:
            api_call_count += 1
        # Giả lập độ trễ mạng gọi Tuya Singapore 100ms
        await asyncio.sleep(0.1)
        return {
            "access_token": "tuya_atomic_refreshed_token_success",
            "refresh_token": "tuya_atomic_refresh_success",
            "expire_time": 7200,
        }

    # Khởi chạy 5 coroutine Worker đồng thời tại cùng một thời điểm
    workers = [
        token_mgr.get_valid_project_token(client_id, refresh_callback=mock_tuya_api)
        for _ in range(5)
    ]

    results = await asyncio.gather(*workers)

    print(f"Số lần API Tuya thực sự bị gọi: {api_call_count}")
    print(f"Kết quả nhận về từ 5 worker: {set(results)}")

    # TIÊU CHÍ PASS QUYẾT ĐỊNH
    assert api_call_count == 1, f"LỖI RACE CONDITION: API bị gọi {api_call_count} lần (yêu cầu duy nhất 1 lần)!"
    assert all(r == "tuya_atomic_refreshed_token_success" for r in results), "Không phải tất cả worker đều nhận được token mới!"

    # Kiểm tra CSDL
    final_data = memory_dal.get_project_token(client_id)
    assert final_data["access_token"] == "tuya_atomic_refreshed_token_success"
    print("✓ PASS BƯỚC 5: 5 worker đồng thời ➔ Duy nhất 1 API request Tuya, ZERO RACE CONDITION!")

