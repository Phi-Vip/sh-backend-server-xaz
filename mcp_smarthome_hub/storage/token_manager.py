"""Quản Lý Vòng Đời Token Tuya & Khóa Phân Tán (Distributed Lock) Chuẩn Thương Mại.

Đặc tả kỹ thuật:
1. TTL Token Tuya Cloud chuẩn là 7.200 giây (2 giờ).
2. Ngưỡng làm mới an toàn (Refresh Threshold): expire_at - now < 300 giây (5 phút).
3. Project-level Token (grant_type=1): Dùng chung toàn bộ thiết bị OEM Sunhouse.
   Lưu Redis RedLock tránh xung đột giữa Backend C# (eSunhouse) và Python (XiaoZhi).
4. User-level OAuth Token (grant_type=2): Dùng cơ chế Lazy On-Demand Refresh
   (chỉ làm mới khi người dùng phát lệnh thoại mà token sắp hết hạn < 300s).
5. Khóa phân tán Redis (SET NX EX) kèm Lua script giải phóng nguyên tử;
   hỗ trợ Fallback In-Memory Lock mô phỏng hoàn hảo khi chưa có cụm Redis vật lý.
"""

import os
import time
import uuid
import random
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Callable, Awaitable

import logging

try:
    from config.logger import setup_logging
    logger = setup_logging()
except ImportError:
    logger = logging.getLogger("TuyaTokenManager")
from .db import dal, SmartHomeDAL
from .models import PlatformType


class InMemoryDistributedLock:
    """Bộ mô phỏng Khóa phân tán Redis (SET NX EX) trong bộ nhớ cho Test/Dev."""

    def __init__(self):
        self._locks: Dict[str, tuple[str, float]] = {}  # key -> (owner_id, expire_epoch)
        self._lock = asyncio.Lock()

    async def acquire(self, key: str, owner_id: str, expire_seconds: int = 30) -> bool:
        async with self._lock:
            now = time.time()
            # Xóa lock đã hết hạn
            if key in self._locks:
                _, exp = self._locks[key]
                if now >= exp:
                    del self._locks[key]

            # Kiểm tra xem có lấy được lock không (NX)
            if key not in self._locks:
                self._locks[key] = (owner_id, now + expire_seconds)
                return True
            return False

    async def release(self, key: str, owner_id: str) -> bool:
        async with self._lock:
            now = time.time()
            if key in self._locks:
                curr_owner, exp = self._locks[key]
                if now < exp and curr_owner == owner_id:
                    del self._locks[key]
                    return True
                elif now >= exp:
                    del self._locks[key]
                    return False
            return False


class TuyaTokenManager:
    """Quản lý Vòng đời Token Tuya & Điều phối Khóa phân tán."""

    TOKEN_TTL_SECONDS = 7200  # 2 giờ
    REFRESH_THRESHOLD_SECONDS = 300  # 5 phút (300 giây)
    LOCK_EXPIRE_SECONDS = 30  # Khóa tối đa 30 giây tránh deadlock

    LUA_UNLOCK_SCRIPT = """
    if redis.call('get', KEYS[1]) == ARGV[1] then
        return redis.call('del', KEYS[1])
    else
        return 0
    end
    """

    def __init__(self, dal_instance: Optional[SmartHomeDAL] = None, redis_url: Optional[str] = None):
        self.dal = dal_instance or dal
        self.redis_url = redis_url or os.getenv("REDIS_URL")
        self._redis_client = None
        self._memory_lock = InMemoryDistributedLock()
        self._init_redis()

    def _init_redis(self):
        """Khởi tạo kết nối Redis nếu có URL."""
        if self.redis_url:
            try:
                import redis.asyncio as aioredis
                self._redis_client = aioredis.from_url(
                    self.redis_url,
                    encoding="utf-8",
                    decode_responses=True,
                )
                logger.info(f"Đã kết nối Redis: {self.redis_url}")
            except Exception as e:
                logger.warning(f"Không thể kết nối Redis ({e}), chuyển sang chế độ In-Memory Lock.")
                self._redis_client = None

    # =========================================================================
    # Distributed Lock Primitives (SET NX EX)
    # =========================================================================

    async def acquire_lock(self, lock_key: str, worker_id: str, expire_seconds: int = LOCK_EXPIRE_SECONDS) -> bool:
        """Lấy khóa phân tán với điều kiện NX (Not Exists) và EX (Expire)."""
        if self._redis_client:
            try:
                # Redis command: SET key worker_id NX EX expire_seconds
                res = await self._redis_client.set(lock_key, worker_id, nx=True, ex=expire_seconds)
                return bool(res)
            except Exception as e:
                logger.error(f"Lỗi Redis acquire_lock ({e}), fallback sang memory lock.")
        return await self._memory_lock.acquire(lock_key, worker_id, expire_seconds)

    async def release_lock(self, lock_key: str, worker_id: str) -> bool:
        """Giải phóng khóa phân tán nguyên tử bằng Lua Script."""
        if self._redis_client:
            try:
                res = await self._redis_client.eval(self.LUA_UNLOCK_SCRIPT, 1, lock_key, worker_id)
                return bool(res)
            except Exception as e:
                logger.error(f"Lỗi Redis release_lock ({e}), fallback sang memory lock.")
        return await self._memory_lock.release(lock_key, worker_id)

    # =========================================================================
    # Project-level Token Governance (grant_type=1)
    # =========================================================================

    async def get_valid_project_token(
        self,
        client_id: str,
        refresh_callback: Optional[Callable[[str, str], Awaitable[Dict[str, Any]]]] = None,
    ) -> Optional[str]:
        """Lấy Project Token hợp lệ.

        Tự động kiểm tra thời hạn sống: nếu còn < 300s, chỉ cho phép duy nhất
        1 worker giành được Distributed Lock gọi API làm mới, các worker khác
        chờ hoặc đọc lại giá trị mới từ DB/Redis.
        """
        token_data = self.dal.get_project_token(client_id)
        now = datetime.utcnow()

        needs_refresh = False
        if not token_data:
            needs_refresh = True
        else:
            time_left = (token_data["expire_at"] - now).total_seconds()
            if time_left < self.REFRESH_THRESHOLD_SECONDS:
                needs_refresh = True

        if not needs_refresh:
            return token_data["access_token"]

        # Cần làm mới token ➔ Cạnh tranh Distributed Lock
        lock_key = f"lock:tuya_project_token:{client_id}"
        worker_id = str(uuid.uuid4())

        is_locked = await self.acquire_lock(lock_key, worker_id, self.LOCK_EXPIRE_SECONDS)
        if is_locked:
            try:
                # MẪU DOUBLE-CHECK DB (Phương án 3A): Đọc lại DB sau khi lấy được khóa
                token_data = self.dal.get_project_token(client_id)
                if token_data and (token_data["expire_at"] - datetime.utcnow()).total_seconds() >= self.REFRESH_THRESHOLD_SECONDS:
                    logger.info(f"[Double-Check DB] Project Token cho {client_id} đã được worker khác cập nhật mới.")
                    return token_data["access_token"]

                logger.info(f"[Worker {worker_id}] Giành được RedLock, tiến hành làm mới Project Token cho {client_id}")
                if refresh_callback:
                    # Bọc timeout an toàn 15s (nhỏ hơn TTL khóa 30s)
                    ref_token = token_data.get("refresh_token") if token_data else ""
                    new_token_info = await asyncio.wait_for(
                        refresh_callback(client_id, ref_token),
                        timeout=15.0,
                    )
                    if new_token_info and "access_token" in new_token_info:
                        new_access = new_token_info["access_token"]
                        new_refresh = new_token_info.get("refresh_token", ref_token)
                        expires_in = new_token_info.get("expire_time", self.TOKEN_TTL_SECONDS)
                        new_expire_at = datetime.utcnow() + timedelta(seconds=expires_in)

                        # Lưu DB (được DAL mã hóa AES-256-GCM)
                        self.dal.save_project_token(
                            client_id=client_id,
                            access_token=new_access,
                            refresh_token=new_refresh,
                            expire_at=new_expire_at,
                        )

                        # Lưu cache Redis nếu có
                        if self._redis_client:
                            cache_key = f"tuya:token:project:{client_id}"
                            await self._redis_client.set(cache_key, new_access, ex=expires_in - 100)

                        return new_access
            finally:
                await self.release_lock(lock_key, worker_id)
        else:
            # Worker khác đang refresh, chờ có jitter 200-500ms và đọc lại DB
            logger.info(f"Worker {worker_id} chờ Token được làm mới bởi instance khác...")
            for _ in range(5):
                jitter = random.uniform(0.2, 0.5)
                await asyncio.sleep(jitter)
                latest = self.dal.get_project_token(client_id)
                if latest and (latest["expire_at"] - datetime.utcnow()).total_seconds() >= self.REFRESH_THRESHOLD_SECONDS:
                    return latest["access_token"]

        # Nếu không có refresh_callback hoặc fallback
        latest = self.dal.get_project_token(client_id)
        return latest["access_token"] if latest else None

    # =========================================================================
    # User-level OAuth Token Governance (grant_type=2) - Lazy On-Demand Refresh
    # =========================================================================

    async def get_valid_user_token(
        self,
        user_id: str,
        refresh_callback: Optional[Callable[[str, str], Awaitable[Dict[str, Any]]]] = None,
    ) -> Optional[str]:
        """Lấy User OAuth Token theo cơ chế Lazy On-Demand Refresh.

        Chỉ gọi API làm mới khi người dùng thực sự ra lệnh giọng nói mà token
        đã hết hạn hoặc còn sống < 300 giây. Tiết kiệm >70% lượng API call thừa.
        """
        cred = self.dal.get_user_credential(user_id)
        if not cred:
            return None

        now = datetime.utcnow()
        time_left = (cred["expire_at"] - now).total_seconds()

        if time_left >= self.REFRESH_THRESHOLD_SECONDS:
            return cred["access_token"]

        # Token còn < 300s ➔ Thực hiện Lazy Refresh với Distributed Lock theo user
        lock_key = f"lock:tuya_refresh:{user_id}"
        worker_id = str(uuid.uuid4())

        is_locked = await self.acquire_lock(lock_key, worker_id, self.LOCK_EXPIRE_SECONDS)
        if is_locked:
            try:
                # MẪU DOUBLE-CHECK DB (Phương án 3A): Đọc lại DB sau khi lấy được khóa
                cred = self.dal.get_user_credential(user_id)
                if cred and (cred["expire_at"] - datetime.utcnow()).total_seconds() >= self.REFRESH_THRESHOLD_SECONDS:
                    logger.info(f"[Double-Check DB] Token cho user {user_id} đã được worker khác làm mới trước đó.")
                    return cred["access_token"]

                logger.info(f"[Lazy Refresh] Làm mới User OAuth Token cho user_id={user_id} (còn {time_left:.1f}s)")
                if refresh_callback:
                    # Bọc timeout an toàn 15s (nhỏ hơn TTL khóa 30s)
                    new_token_info = await asyncio.wait_for(
                        refresh_callback(user_id, cred["refresh_token"]),
                        timeout=15.0,
                    )
                    if new_token_info and "access_token" in new_token_info:
                        new_access = new_token_info["access_token"]
                        new_refresh = new_token_info.get("refresh_token", cred["refresh_token"])
                        expires_in = new_token_info.get("expire_time", self.TOKEN_TTL_SECONDS)
                        new_expire_at = datetime.utcnow() + timedelta(seconds=expires_in)

                        self.dal.save_user_credential(
                            user_id=user_id,
                            external_tuya_uid=cred["external_tuya_uid"],
                            access_token=new_access,
                            refresh_token=new_refresh,
                            expire_at=new_expire_at,
                            auth_source=cred.get("auth_source", "oauth2"),
                        )
                        return new_access
            finally:
                await self.release_lock(lock_key, worker_id)
        else:
            # Chờ worker khác đang refresh, ngủ ngắn có jitter 200-500ms
            for _ in range(5):
                jitter = random.uniform(0.2, 0.5)
                await asyncio.sleep(jitter)
                latest = self.dal.get_user_credential(user_id)
                if latest and (latest["expire_at"] - datetime.utcnow()).total_seconds() >= self.REFRESH_THRESHOLD_SECONDS:
                    return latest["access_token"]

        latest = self.dal.get_user_credential(user_id)
        return latest["access_token"] if latest else None

    # =========================================================================
    # Alias Helpers (Tương thích ngược & Phòng vệ đa tầng)
    # =========================================================================

    async def get_project_token(self, client_id: Optional[str] = None) -> Optional[str]:
        """Alias tương thích cho get_valid_project_token."""
        cid = client_id or os.getenv("TUYA_CLIENT_ID", "")
        return await self.get_valid_project_token(cid)

    async def get_user_token(self, user_id: str) -> Optional[str]:
        """Alias tương thích cho get_valid_user_token."""
        return await self.get_valid_user_token(user_id)


# Global instance
token_manager = TuyaTokenManager()

