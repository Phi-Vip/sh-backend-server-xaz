# -*- coding: utf-8 -*-
"""PLUGIN TRÍ NHỚ PHÂN TÁN MEM_REDIS (TASK 1.2)
Dự án: Tái cấu trúc Server XiaoZhi Thương mại v2.1
Thay thế hoàn toàn mem_local_short (xóa bỏ triệt để file I/O cục bộ .memory.yaml).
- Lưu trữ trên Redis 7 phân tán (Key: xiaozhi:memory:{user_id}:{device_id}).
- Tự dọn dẹp theo TTL (mặc định 30 ngày = 2.592.000s).
- Không lock file, không gây race-condition khi 1.000 loa đàm thoại đồng thời.
- Đẩy hội thoại bất đồng bộ vào hàng đợi (async queue) để lưu trữ bền vững.
"""

import os
import time
import json
import asyncio
from typing import Optional, List, Dict, Any
from ..base import MemoryProviderBase, logger
from core.utils.util import check_model_key

TAG = "mem_redis"

# Prompt tóm tắt hồ sơ và trí nhớ người dùng chuẩn tiếng Việt
MEMORY_SUMMARY_PROMPT = """
# HỆ THỐNG TRÍ NHỚ HỒ SƠ NGƯỜI DÙNG (USER PROFILE & MEMORY)
Dựa vào lịch sử hội thoại giữa Người dùng (User) và Trợ lý AI (Assistant), hãy cập nhật hồ sơ người dùng để trợ lý phục vụ cá nhân hóa, tự nhiên và thân thiện hơn.

## NGUYÊN TẮC:
1. Chỉ trích xuất thông tin thực tế từ hội thoại, không bịa đặt.
2. Tất cả nội dung văn bản (giá trị trong JSON) BẮT BUỘC viết bằng TIẾNG VIỆT tự nhiên, súc tích.
3. Các khóa JSON (key) sử dụng tiếng Anh chuẩn (ASCII).
4. Tên gọi: Nếu người dùng xưng tên, lưu vào trường "name".
5. Sự kiện gần đây: Lưu tối đa 5 sự kiện nổi bật gần nhất, tóm tắt 1 câu ngắn gọn.

## CẤU TRÚC JSON ĐẦU RA BẮT BUỘC:
```json
{
  "user_profile": {
    "name": "Tên người dùng nếu biết",
    "traits": ["Đặc điểm nhận diện, ví dụ: Người dùng tiếng Việt, Thích ngắn gọn"]
  },
  "recent_events": [
    {
      "event": "Tóm tắt sự kiện vừa diễn ra",
      "timestamp": "YYYY-MM-DD HH:MM",
      "topic": "Chủ đề"
    }
  ],
  "preferences": {
    "favorite_topics": ["Chủ đề yêu thích"],
    "interaction_style": "Ngắn gọn, súc tích, tự nhiên, thân thiện"
  }
}
```
"""


def extract_json_data(text: str) -> str:
    """Trích xuất khối JSON từ phản hồi LLM."""
    if not text:
        return ""
    start = text.find("```json")
    if start != -1:
        end = text.find("```", start + 7)
        if end != -1:
            return text[start + 7 : end].strip()
    try:
        json.loads(text)
        return text.strip()
    except Exception:
        pass
    return text.strip()


class MemoryProvider(MemoryProviderBase):
    """Memory Provider phân tán trên Redis 7."""

    DEFAULT_TTL_SECONDS = 30 * 24 * 3600  # 30 ngày

    def __init__(self, config: Dict[str, Any], summary_memory: Optional[str] = None):
        super().__init__(config)
        self.short_memory = summary_memory or ""
        self.role_id = None
        self.user_id = None
        self.redis_key = None

        # Cấu hình Redis
        mem_cfg = config.get("Memory", {}).get("mem_redis", {})
        self.redis_url = mem_cfg.get("redis_url") or os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.ttl = int(mem_cfg.get("ttl_seconds", self.DEFAULT_TTL_SECONDS))

        self._redis_client = None
        self._fallback_memory: Dict[str, str] = {}
        self._init_redis()

    def _init_redis(self):
        """Khởi tạo kết nối bất đồng bộ tới Redis."""
        if self.redis_url:
            try:
                import redis.asyncio as aioredis
                self._redis_client = aioredis.from_url(
                    self.redis_url,
                    encoding="utf-8",
                    decode_responses=True,
                    socket_connect_timeout=0.2,
                    socket_timeout=0.2,
                )
                logger.bind(tag=TAG).info(f"mem_redis đã kết nối Redis: {self.redis_url}")
            except Exception as e:
                logger.bind(tag=TAG).warning(f"mem_redis không thể kết nối Redis ({e}), fallback in-memory.")
                self._redis_client = None

    def _build_key(self, role_id: str, user_id: Optional[str] = None) -> str:
        """Xây dựng Redis key chuẩn đa người dùng: xiaozhi:memory:{user_id}:{device_id}."""
        if user_id:
            return f"xiaozhi:memory:{user_id}:{role_id}"
        return f"xiaozhi:memory:{role_id}"

    def init_memory(
        self,
        role_id: str,
        llm: Any,
        summary_memory: Optional[str] = None,
        user_id: Optional[str] = None,
        **kwargs,
    ):
        """Khởi tạo trí nhớ cho phiên đàm thoại."""
        super().init_memory(role_id, llm, **kwargs)
        self.role_id = role_id
        self.user_id = user_id
        self.redis_key = self._build_key(role_id, user_id)

        if summary_memory:
            self.short_memory = summary_memory

    async def query_memory(self, query: str = "") -> str:
        """Truy vấn trí nhớ từ Redis."""
        if not self.redis_key:
            return self.short_memory

        if self._redis_client:
            try:
                cached = await self._redis_client.get(self.redis_key)
                if cached:
                    self.short_memory = cached
                    return cached
            except Exception as e:
                logger.bind(tag=TAG).error(f"Lỗi đọc trí nhớ từ Redis ({e}), dùng in-memory")

        return self._fallback_memory.get(self.redis_key, self.short_memory)

    async def save_memory(self, msgs: List[Any], session_id: Optional[str] = None) -> Optional[str]:
        """Tóm tắt và lưu trí nhớ vào Redis (hoàn toàn không dùng file I/O)."""
        if not self.llm:
            logger.bind(tag=TAG).error("Chưa cấu hình LLM cho mem_redis")
            return None

        if len(msgs) < 2:
            return None

        # Trích xuất hội thoại
        msg_str = ""
        for msg in msgs:
            content = getattr(msg, "content", "")
            try:
                if content and content.strip().startswith("{") and content.strip().endswith("}"):
                    data = json.loads(content)
                    content = data.get("content", content)
            except Exception:
                pass

            role = getattr(msg, "role", "")
            if role == "user":
                msg_str += f"User: {content}\n"
            elif role == "assistant":
                msg_str += f"Assistant: {content}\n"

        if self.short_memory:
            msg_str += f"\n[Trí nhớ trước đó]:\n{self.short_memory}\n"

        time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        msg_str += f"\n[Thời gian hiện tại]: {time_str}\n"

        try:
            # Gọi LLM tóm tắt trí nhớ (không stream)
            result = self.llm.response_no_stream(
                MEMORY_SUMMARY_PROMPT,
                msg_str,
                temperature=0.3,
            )

            json_text = extract_json_data(result)
            if json_text:
                self.short_memory = json_text

                # Ghi vào Redis với TTL 30 ngày (Zero-Lock Persistence)
                if self.redis_key:
                    if self._redis_client:
                        try:
                            await self._redis_client.set(self.redis_key, json_text, ex=self.ttl)
                            logger.bind(tag=TAG).debug(f"Đã lưu trí nhớ Redis: {self.redis_key} (TTL={self.ttl}s)")
                        except Exception as e:
                            logger.bind(tag=TAG).error(f"Lỗi ghi Redis ({e}), lưu fallback RAM")
                            self._fallback_memory[self.redis_key] = json_text
                    else:
                        self._fallback_memory[self.redis_key] = json_text

                    # Đẩy bất đồng bộ vào Redis queue để phục vụ lưu trữ PostgreSQL sau này
                    if self._redis_client and session_id:
                        queue_payload = json.dumps({
                            "session_id": session_id,
                            "user_id": self.user_id,
                            "device_id": self.role_id,
                            "timestamp": time_str,
                            "memory": json_text,
                        }, ensure_ascii=False)
                        try:
                            await self._redis_client.rpush("xiaozhi:dialogue:queue", queue_payload)
                        except Exception:
                            pass

                return json_text
        except Exception as e:
            logger.bind(tag=TAG).error(f"Lỗi khi tóm tắt và lưu trí nhớ: {e}")

        return None
