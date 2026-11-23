# -*- coding: utf-8 -*-
"""QUẢN LÝ PHIÊN PHÂN TÁN ĐA NODE & THU HỒI QUYỀN TỨC THÌ (REDIS SESSION MANAGER - PHASE 3).

Chịu trách nhiệm:
1. Đăng ký & tra cứu Node ID đang duy trì đường hầm WebSocket của từng User (HSET ha:sessions {user_id} {node_id}).
2. Điều phối thông điệp Pub/Sub liên node xuyên qua cụm Container (ha:cmd:{node_id} & ha:res:{req_id}).
3. Cơ chế thu hồi quyền tức thì (Instant Revocation < 500ms) qua kênh phát sóng 'ha:revocations'.
4. Tích hợp sẵn bộ In-Memory Pub/Sub dự phòng đảm bảo kiểm thử tự động độc lập 100% không bắt buộc Redis vật lý.
"""

import os
import sys
import time
import json
import uuid
import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional, Set

try:
    import redis.asyncio as aioredis
except ImportError:
    aioredis = None

try:
    from mcp_smarthome_hub.storage.db import SmartHomeDAL, dal as default_dal
except ImportError:
    try:
        from storage.db import SmartHomeDAL, dal as default_dal
    except ImportError:
        from ..storage.db import SmartHomeDAL, dal as default_dal

logger = logging.getLogger("HARedisSessionMgr")


class RedisSessionManager:
    """Bộ quản lý phiên đường hầm Home Assistant phân tán đa node qua Redis."""

    # Bảng registry đa node In-Memory dùng khi không có Redis ngoài
    _IN_MEMORY_NODES: Dict[str, "RedisSessionManager"] = {}
    _IN_MEMORY_SESSIONS: Dict[str, str] = {}  # user_id -> node_id

    def __init__(
        self,
        node_id: Optional[str] = None,
        redis_url: Optional[str] = None,
        dal_instance: Optional[SmartHomeDAL] = None,
    ):
        """Khởi tạo quản lý phiên với Node ID định danh riêng biệt."""
        self.node_id = node_id or f"node_{uuid.uuid4().hex[:8]}"
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.dal = dal_instance or default_dal

        # Client Redis bất đồng bộ
        self._redis: Optional[Any] = None
        self._pubsub: Optional[Any] = None
        self._is_connected = False
        self._running = False

        # Quản lý sự kiện In-Memory dự phòng (dùng khi không có Redis ngoài hoặc trong unit test)
        self._revocation_callbacks: List[Callable[[str, str], Any]] = []
        self._command_callbacks: List[Callable[[Dict[str, Any]], Any]] = []
        self._pending_responses: Dict[str, asyncio.Future] = {}

        # Task chạy nền lắng nghe tin nhắn Redis
        self._listener_task: Optional[asyncio.Task] = None

    async def start(self):
        """Kích hoạt kết nối Redis và bắt đầu lắng nghe các kênh thông điệp."""
        self._running = True
        RedisSessionManager._IN_MEMORY_NODES[self.node_id] = self

        # Thử kết nối tới Redis Server
        if aioredis and self.redis_url:
            try:
                self._redis = aioredis.from_url(
                    self.redis_url,
                    encoding="utf-8",
                    decode_responses=True,
                    socket_connect_timeout=1.0,
                )
                await self._redis.ping()
                self._is_connected = True
                logger.info(f"Node [{self.node_id}] kết nối thành công Redis: {self.redis_url}")

                # Khởi tạo PubSub
                self._pubsub = self._redis.pubsub()
                await self._pubsub.subscribe("ha:revocations", f"ha:cmd:{self.node_id}")
                self._listener_task = asyncio.create_task(self._redis_listen_loop())
                return
            except Exception as e:
                logger.warning(
                    f"Không thể kết nối Redis ({e}). Tự động kích hoạt In-Memory Bridge dự phòng cho Node [{self.node_id}]."
                )
                self._is_connected = False
                self._redis = None

        logger.info(f"Node [{self.node_id}] đang hoạt động ở chế độ In-Memory Pub/Sub Bridge.")

    async def stop(self):
        """Dừng bộ quản lý phiên và giải phóng các kết nối mạng."""
        self._running = False
        RedisSessionManager._IN_MEMORY_NODES.pop(self.node_id, None)

        if self._listener_task and not self._listener_task.done():
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass

        if self._pubsub:
            try:
                await self._pubsub.unsubscribe()
                await self._pubsub.close()
            except Exception:
                pass

        if self._redis:
            try:
                await self._redis.close()
            except Exception:
                pass

        self._is_connected = False
        logger.info(f"Node [{self.node_id}] đã dừng toàn bộ tiến trình lắng nghe.")

    # =========================================================================
    # Đăng Ký & Tra Cứu Phiên (Session Registry)
    # =========================================================================

    async def register_session(self, user_id: str, target_node_id: Optional[str] = None) -> bool:
        """Đăng ký Node ID đang phục vụ WebSocket tunnel của User vào Redis (HSET ha:sessions)."""
        assigned_node = target_node_id or self.node_id
        if self._is_connected and self._redis:
            try:
                await self._redis.hset("ha:sessions", user_id, assigned_node)
                await self._redis.hset("ha:sessions:heartbeat", user_id, str(time.time()))
            except Exception as e:
                logger.error(f"Lỗi ghi nhận phiên vào Redis: {e}")
                RedisSessionManager._IN_MEMORY_SESSIONS[user_id] = assigned_node
        else:
            RedisSessionManager._IN_MEMORY_SESSIONS[user_id] = assigned_node

        # Đồng bộ trạng thái trực tuyến vào CSDL
        try:
            self.dal.set_ha_online_status(user_id, True)
        except Exception as e:
            logger.warning(f"Lỗi cập nhật CSDL trạng thái online của {user_id}: {e}")

        logger.info(f"Đã đăng ký phiên: User [{user_id}] ➔ Node [{assigned_node}]")
        return True

    async def unregister_session(self, user_id: str) -> bool:
        """Hủy phiên kết nối khi WebSocket đóng (HDEL ha:sessions)."""
        if self._is_connected and self._redis:
            try:
                await self._redis.hdel("ha:sessions", user_id)
                await self._redis.hdel("ha:sessions:heartbeat", user_id)
            except Exception as e:
                logger.error(f"Lỗi xóa phiên khỏi Redis: {e}")
                RedisSessionManager._IN_MEMORY_SESSIONS.pop(user_id, None)
        else:
            RedisSessionManager._IN_MEMORY_SESSIONS.pop(user_id, None)

        try:
            self.dal.set_ha_online_status(user_id, False)
        except Exception as e:
            logger.warning(f"Lỗi cập nhật CSDL trạng thái offline của {user_id}: {e}")

        logger.info(f"Đã hủy đăng ký phiên: User [{user_id}]")
        return True

    async def get_session_node(self, user_id: str) -> Optional[str]:
        """Tra cứu Node ID đang nắm giữ socket của User (HGET ha:sessions)."""
        if self._is_connected and self._redis:
            try:
                node = await self._redis.hget("ha:sessions", user_id)
                if node:
                    return str(node)
            except Exception as e:
                logger.error(f"Lỗi tra cứu phiên từ Redis: {e}")

        return RedisSessionManager._IN_MEMORY_SESSIONS.get(user_id)

    async def is_user_online(self, user_id: str) -> bool:
        """Kiểm tra xem User hiện có đường hầm Home Assistant trực tuyến hay không."""
        node = await self.get_session_node(user_id)
        return node is not None

    # =========================================================================
    # Cơ Chế Thu Hồi Quyền Tức Thì (Instant Revocation < 500ms)
    # =========================================================================

    def on_revocation(self, callback: Callable[[str, str], Any]):
        """Đăng ký hàm xử lý khi nhận được thông điệp thu hồi quyền (user_id, reason)."""
        self._revocation_callbacks.append(callback)

    async def revoke_user_tunnel(self, user_id: str, reason: str = "Người dùng thu hồi quyền truy cập") -> bool:
        """Phát sóng lệnh thu hồi quyền lập tức xuyên cụm mạng qua Redis Pub/Sub."""
        msg = {
            "action": "revoke",
            "user_id": user_id,
            "reason": reason,
            "timestamp": time.time(),
            "source_node": self.node_id,
        }
        msg_str = json.dumps(msg, ensure_ascii=False)

        # 1. Phát sóng qua Redis hoặc đa Node In-Memory
        if self._is_connected and self._redis:
            try:
                await self._redis.publish("ha:revocations", msg_str)
            except Exception as e:
                logger.error(f"Lỗi publish lệnh thu hồi qua Redis: {e}")
                for node in list(RedisSessionManager._IN_MEMORY_NODES.values()):
                    await node._dispatch_local_revocation(user_id, reason)
        else:
            for node in list(RedisSessionManager._IN_MEMORY_NODES.values()):
                await node._dispatch_local_revocation(user_id, reason)

        # 2. Xóa phiên và thu hồi trong CSDL
        await self.unregister_session(user_id)
        try:
            self.dal.revoke_ha_credential(user_id)
        except Exception as e:
            logger.warning(f"Lỗi xóa chứng thực HA trong DB: {e}")

        logger.warning(f"⚡ [THU HỒI TỨC THÌ]: Đã phát sóng lệnh ngắt kết nối User [{user_id}] ({reason})")
        return True

    async def _dispatch_local_revocation(self, user_id: str, reason: str):
        """Thực thi ngay lập tức các callback thu hồi trên node cục bộ."""
        for cb in self._revocation_callbacks:
            try:
                res = cb(user_id, reason)
                if asyncio.iscoroutine(res):
                    await res
            except Exception as e:
                logger.error(f"Lỗi khi thực thi callback thu hồi: {e}")

    # =========================================================================
    # Chuyển Tiếp Lệnh Liên Node (Cross-Node Command Pub/Sub)
    # =========================================================================

    def on_command(self, callback: Callable[[Dict[str, Any]], Any]):
        """Đăng ký callback tiếp nhận lệnh chuyển tiếp từ các node khác gửi tới node này."""
        self._command_callbacks.append(callback)

    async def publish_command(self, target_node_id: str, cmd_payload: Dict[str, Any]) -> bool:
        """Gửi lệnh thực thi tới Node cụ thể đang giữ socket của User."""
        msg_str = json.dumps(cmd_payload, ensure_ascii=False)
        channel = f"ha:cmd:{target_node_id}"

        if self._is_connected and self._redis:
            try:
                await self._redis.publish(channel, msg_str)
                return True
            except Exception as e:
                logger.error(f"Lỗi publish command tới {channel}: {e}")
                return False
        else:
            # Chuyển tiếp tới Target Node trong registry In-Memory
            target_mgr = RedisSessionManager._IN_MEMORY_NODES.get(target_node_id)
            if target_mgr:
                for cb in list(target_mgr._command_callbacks):
                    try:
                        res = cb(cmd_payload)
                        if asyncio.iscoroutine(res):
                            asyncio.create_task(res)
                    except Exception as e:
                        logger.error(f"Lỗi dispatch in-memory command: {e}")
                return True
            logger.warning(f"Không tìm thấy Node [{target_node_id}] trong In-Memory registry!")
            return False

    async def publish_response(self, request_id: str, res_payload: Dict[str, Any]) -> bool:
        """Gửi kết quả phản hồi từ Node nhận lệnh về cho Node gọi lệnh (ha:res:{req_id})."""
        msg_str = json.dumps(res_payload, ensure_ascii=False)
        channel = f"ha:res:{request_id}"

        # 1. Đánh thức Future nếu Node gọi lệnh là chính node này
        fut = self._pending_responses.pop(request_id, None)
        if fut and not fut.done():
            fut.set_result(res_payload)
            return True

        # 2. Hoặc tìm trên tất cả các Node trong registry In-Memory
        for mgr in list(RedisSessionManager._IN_MEMORY_NODES.values()):
            f = mgr._pending_responses.pop(request_id, None)
            if f and not f.done():
                f.set_result(res_payload)
                return True

        # 3. Phát sóng qua Redis nếu có kết nối
        if self._is_connected and self._redis:
            try:
                await self._redis.publish(channel, msg_str)
                return True
            except Exception as e:
                logger.error(f"Lỗi publish response tới {channel}: {e}")
                return False

        return True

    async def wait_for_response(self, request_id: str, timeout: float = 3.0) -> Dict[str, Any]:
        """Node gọi lệnh đợi phản hồi từ Node nhận lệnh với Hard Timeout (đo RTT < 25ms)."""
        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        self._pending_responses[request_id] = fut

        channel = f"ha:res:{request_id}"
        temp_pubsub = None

        if self._is_connected and self._redis:
            try:
                temp_pubsub = self._redis.pubsub()
                await temp_pubsub.subscribe(channel)

                async def _wait_redis():
                    async for message in temp_pubsub.listen():
                        if message and message.get("type") == "message":
                            data = json.loads(message["data"])
                            if not fut.done():
                                fut.set_result(data)
                            break

                listen_task = asyncio.create_task(_wait_redis())
                try:
                    result = await asyncio.wait_for(fut, timeout=timeout)
                    return result
                finally:
                    if not listen_task.done():
                        listen_task.cancel()
                    await temp_pubsub.unsubscribe(channel)
                    await temp_pubsub.close()
                    self._pending_responses.pop(request_id, None)
            except asyncio.TimeoutError:
                self._pending_responses.pop(request_id, None)
                raise TimeoutError(f"Quá thời gian chờ phản hồi ({timeout}s) cho request [{request_id}]")
        else:
            # Cơ chế In-Memory: fut sẽ được publish_response() đánh thức trực tiếp qua _IN_MEMORY_NODES
            try:
                result = await asyncio.wait_for(fut, timeout=timeout)
                return result
            except asyncio.TimeoutError:
                raise TimeoutError(f"Quá thời gian chờ phản hồi ({timeout}s) cho request [{request_id}]")
            finally:
                self._pending_responses.pop(request_id, None)

    # =========================================================================
    # Vòng Lặp Lắng Nghe Redis Nền (Background Listener Loop)
    # =========================================================================

    async def _redis_listen_loop(self):
        """Lắng nghe các tin nhắn đến từ Redis Pub/Sub và chuyển tiếp nội bộ."""
        try:
            async for message in self._pubsub.listen():
                if not self._running:
                    break
                if not message or message.get("type") != "message":
                    continue

                channel = message.get("channel")
                raw_data = message.get("data")
                try:
                    payload = json.loads(raw_data)
                except Exception:
                    continue

                # 1. Kênh thu hồi quyền
                if channel == "ha:revocations":
                    user_id = payload.get("user_id")
                    reason = payload.get("reason", "Revoked")
                    if user_id:
                        await self._dispatch_local_revocation(user_id, reason)

                # 2. Kênh nhận lệnh gửi tới Node này
                elif channel == f"ha:cmd:{self.node_id}":
                    for cb in self._command_callbacks:
                        try:
                            res = cb(payload)
                            if asyncio.iscoroutine(res):
                                await res
                        except Exception as e:
                            logger.error(f"Lỗi thực thi command callback: {e}")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Lỗi trong vòng lặp Redis listener: {e}")
