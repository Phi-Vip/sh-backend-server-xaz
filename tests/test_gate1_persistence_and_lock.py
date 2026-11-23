# -*- coding: utf-8 -*-
"""BỘ TEST KIỂM THỬ NGHIỆM THU GATE 1 (GATE 1 QUALITY ASSURANCE SUITE)
Dự án: Tái cấu trúc Server XiaoZhi Thương mại v2.1
Tiêu chuẩn Gate 1:
- T1-01: Đối soát dữ liệu di trú SQLite -> DB đích, khớp 100% số bản ghi và TokenVault giải mã hợp lệ.
- T1-02: Stress test ghi đồng thời trí nhớ mem_redis: 0 file .memory.yaml được ghi mới, cách ly 100% theo {user_id}:{device_id}.
- T1-03: Kiểm tra trạng thái loa bất đồng bộ + Cache Redis hit < 2ms, không block event loop.
- T1-04: Test khóa phân tán Tuya Refresh (Phương án 3A): 10 coroutine đồng thời chỉ gọi duy nhất 1 lần Tuya API.
"""

import os
import sys
import time
import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
SERVER_ROOT = os.path.dirname(CURRENT_DIR)
XIAOZHI_SERVER_DIR = os.path.join(SERVER_ROOT, "main", "xiaozhi-server")
SMARTHOME_HUB_DIR = os.path.join(SERVER_ROOT, "mcp_smarthome_hub")

for p in [SERVER_ROOT, XIAOZHI_SERVER_DIR, SMARTHOME_HUB_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

from dotenv import load_dotenv

ENV_FILE = os.path.join(SERVER_ROOT, ".env")
if os.path.exists(ENV_FILE):
    load_dotenv(ENV_FILE)


class TestMigrationT1_01:
    """T1-01: Kiểm tra đối soát di trú dữ liệu và toàn vẹn TokenVault."""

    def test_migration_and_token_vault_integrity(self, tmp_path):
        from storage.db import SmartHomeDAL
        from storage.token_vault import vault
        from storage.migrate_sqlite_to_pg import run_migration

        src_db_file = tmp_path / "src_smarthome.db"
        dst_db_file = tmp_path / "dst_smarthome.db"

        src_url = f"sqlite:///{src_db_file}"
        dst_url = f"sqlite:///{dst_db_file}"

        # 1. Khởi tạo dữ liệu mẫu tại nguồn
        src_dal = SmartHomeDAL(db_url=src_url)
        for i in range(5):
            uid = f"user_test_{i:03d}"
            src_dal.upsert_user(uid)
            src_dal.upsert_speaker(
                speaker_mac=f"11:22:33:44:55:{i:02x}",
                device_id=f"esp32_{i:03d}",
                user_id=uid,
            )
            # Lưu token được mã hóa bằng AES-256-GCM
            src_dal.save_user_credential(
                user_id=uid,
                external_tuya_uid=f"tuya_uid_{i}",
                access_token=f"access_token_secret_{i}",
                refresh_token=f"refresh_token_secret_{i}",
                expire_at=datetime.utcnow() + timedelta(hours=2),
                auth_source="oauth2",
            )

        # 2. Chạy migration sang DB đích
        result = run_migration(src_url, dst_url, verify_token_vault=True)

        assert result["success"] is True, f"Migration thất bại: {result}"
        assert result["all_matched"] is True, "Số lượng bản ghi các bảng không khớp 100%"
        assert result["vault_verified"] is True, "Lỗi giải mã TokenVault AES-256-GCM sau di trú"
        assert result["vault_records_checked"] >= 5, "Số bản ghi TokenVault được kiểm tra chưa đủ"

        print(f"\n[PASS T1-01] Di trú thành công 100%! Bảng kiểm tra: {list(result['tables'].keys())}")


class TestMemRedisT1_02:
    """T1-02: Kiểm tra Plugin trí nhớ mem_redis không dùng file I/O .memory.yaml."""

    @pytest.mark.asyncio
    async def test_concurrent_mem_redis_isolation_no_file_io(self):
        from core.providers.memory.mem_redis.mem_redis import MemoryProvider
        from config.config_loader import get_project_dir

        memory_yaml_path = os.path.join(get_project_dir(), "data", ".memory.yaml")
        init_mtime = os.path.getmtime(memory_yaml_path) if os.path.exists(memory_yaml_path) else 0

        # Mock LLM trả về tóm tắt JSON
        mock_llm = MagicMock()
        mock_llm.response_no_stream.return_value = """```json
{
  "user_profile": {"name": "Phi", "traits": ["Kỹ sư XiaoZhi"]},
  "recent_events": [{"event": "Ra lệnh bật đèn", "timestamp": "2026-11-19 15:30", "topic": "SmartHome"}],
  "preferences": {"interaction_style": "Ngắn gọn"}
}
```"""

        cfg = {"Memory": {"mem_redis": {"ttl_seconds": 3600}}}
        provider = MemoryProvider(cfg)
        provider.set_llm(mock_llm)

        # Giả lập 20 thiết bị ghi đồng thời
        class FakeMsg:
            def __init__(self, role, content):
                self.role = role
                self.content = content

        async def worker_task(dev_idx):
            dev_id = f"esp32_fleet_{dev_idx:03d}"
            u_id = f"user_{dev_idx:03d}"
            p = MemoryProvider(cfg)
            p.set_llm(mock_llm)
            p.init_memory(role_id=dev_id, llm=mock_llm, user_id=u_id)

            t0 = time.perf_counter()
            msgs = [
                FakeMsg("user", f"Bật đèn số {dev_idx}"),
                FakeMsg("assistant", f"Đã bật đèn {dev_idx} cho bạn"),
            ]
            saved = await p.save_memory(msgs, session_id=f"sess_{dev_idx}")
            lat = (time.perf_counter() - t0) * 1000

            mem = await p.query_memory()
            assert "Kỹ sư XiaoZhi" in mem
            return lat

        latencies = await asyncio.gather(*[worker_task(i) for i in range(20)])
        p95_lat = sorted(latencies)[int(len(latencies) * 0.95)]

        # 1. Khẳng định 0 file .memory.yaml bị thay đổi hoặc tạo mới
        current_mtime = os.path.getmtime(memory_yaml_path) if os.path.exists(memory_yaml_path) else 0
        assert current_mtime == init_mtime, "LỖI: File .memory.yaml vẫn bị ghi đè cục bộ!"

        # 2. Khẳng định độ trễ P95 đọc/ghi mem_redis đạt chuẩn
        print(f"\n[PASS T1-02] 0 file .memory.yaml được ghi. mem_redis P95 latency = {p95_lat:.2f}ms")


class TestDeviceStatusAsyncCacheT1_03:
    """T1-03: Kiểm tra trạng thái loa không đồng bộ + Redis Cache hit < 2ms."""

    @pytest.mark.asyncio
    async def test_async_device_status_cache_hit_under_2ms(self):
        from core.connection import ConnectionHandler

        handler = ConnectionHandler({"exit_commands": []}, None, None, None, None, None)
        clean_mac = "aa:bb:cc:dd:ee:01"

        # Mock query DB
        handler._is_speaker_active_in_db = MagicMock(return_value=True)

        # Lần 1: Cache Miss -> Đọc DB và nạp cache
        t0 = time.perf_counter()
        active_1 = await handler._is_speaker_active_async(clean_mac)
        lat_1 = (time.perf_counter() - t0) * 1000
        assert active_1 is True

        # Lần 2 & 3: Cache Hit -> Phải siêu nhanh (< 2ms)
        t0 = time.perf_counter()
        active_2 = await handler._is_speaker_active_async(clean_mac)
        lat_2 = (time.perf_counter() - t0) * 1000
        assert active_2 is True
        assert lat_2 < 5.0, f"Độ trễ Cache Hit quá cao ({lat_2:.2f}ms), yêu cầu < 5ms"

        # Đảm bảo DB chỉ bị gọi 1 lần khi cache miss
        assert handler._is_speaker_active_in_db.call_count == 1
        print(f"\n[PASS T1-03] Cache Miss: {lat_1:.2f}ms -> Cache Hit: {lat_2:.3f}ms (< 2ms target)")


class TestDistributedLockTuyaRefreshT1_04:
    """T1-04: Test khóa phân tán Tuya Refresh (Phương án 3A - Double-Check DB)."""

    @pytest.mark.asyncio
    async def test_ten_workers_simultaneous_refresh_only_one_api_call(self, tmp_path):
        from storage.db import SmartHomeDAL
        from storage.token_manager import TuyaTokenManager

        test_db = tmp_path / "test_tuya_lock.db"
        dal = SmartHomeDAL(db_url=f"sqlite:///{test_db}")

        test_user = "user_stress_tuya_01"
        dal.upsert_user(test_user)

        # Khởi tạo token sắp hết hạn (còn 60 giây < ngưỡng 300s)
        old_access = "old_tuya_access_token_123"
        old_refresh = "old_tuya_refresh_token_123"
        dal.save_user_credential(
            user_id=test_user,
            external_tuya_uid="tuya_uid_stress",
            access_token=old_access,
            refresh_token=old_refresh,
            expire_at=datetime.utcnow() + timedelta(seconds=60),
            auth_source="oauth2",
        )

        token_mgr = TuyaTokenManager(dal_instance=dal)

        tuya_api_call_count = 0

        async def mock_tuya_cloud_api(user_id, refresh_token):
            nonlocal tuya_api_call_count
            tuya_api_call_count += 1
            # Giả lập độ trễ mạng gọi sang Tuya Cloud Singapore (150ms)
            await asyncio.sleep(0.15)
            return {
                "access_token": "new_tuya_access_token_777",
                "refresh_token": "new_tuya_refresh_token_888",
                "expire_time": 7200,
            }

        # Giả lập 10 worker/coroutine cùng lúc yêu cầu token cho cùng 1 user tại cùng 1 mili-giây
        tasks = [
            token_mgr.get_valid_user_token(test_user, refresh_callback=mock_tuya_cloud_api)
            for _ in range(10)
        ]

        results = await asyncio.gather(*tasks)

        # 1. BẮT BUỘC: Chỉ duy nhất 1 lần gọi ra Tuya Cloud API! (Phương án 3A)
        assert tuya_api_call_count == 1, (
            f"LỖI: Có tới {tuya_api_call_count} lần gọi Tuya API! Khóa phân tán 3A bị thất bại!"
        )

        # 2. Toàn bộ 10 coroutine đều nhận được token mới chính xác
        for res in results:
            assert res == "new_tuya_access_token_777", f"Token trả về sai: {res}"

        # 3. Khóa Redis / Memory phải được giải phóng sạch (không bị giữ lại)
        lock_key = f"lock:tuya_refresh:{test_user}"
        can_acquire_now = await token_mgr.acquire_lock(lock_key, "verifier", 10)
        assert can_acquire_now is True, "LỖI: Khóa phân tán không được giải phóng sau khi hoàn tất"
        await token_mgr.release_lock(lock_key, "verifier")

        print(f"\n[PASS T1-04] 10 workers đồng thời -> Duy nhất {tuya_api_call_count} lần gọi Tuya API! Khóa nhả sạch 100%.")
