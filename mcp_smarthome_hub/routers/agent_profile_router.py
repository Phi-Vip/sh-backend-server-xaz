# -*- coding: utf-8 -*-
"""ROUTER QUẢN TRỊ CẤU HÌNH AGENT CÁ NHÂN HÓA THEO THIẾT BỊ (TASK 3.1 & 3.2 - GIAI ĐOẠN 3)
Cung cấp:
1. Endpoint nội bộ tương thích xiaozhi-server:
   - POST /config/agent-models
   - POST /config/correct-words
   - POST /config/server-base
2. API quản trị cho Web Portal / Mobile App (eSunhouse App):
   - POST /api/v1/agent/profile (Cập nhật tên, giọng đọc, prompt, tính cách và XÓA CACHE REDIS tức thì)
   - GET /api/v1/agent/profile (Tra cứu cấu hình hiện tại)
"""

import json
import logging
import os
import time
from typing import Any, Dict, Optional
from aiohttp import web

from storage.db import SmartHomeDAL, default_dal
from storage.models import extract_mac_and_device_id

logger = logging.getLogger("AgentProfileRouter")

# Client Redis dùng chung cho việc Invalidate Cache (Task 3.2)
_redis_invalidation_client = None


def get_redis_invalidation_client():
    global _redis_invalidation_client
    if _redis_invalidation_client is None:
        try:
            import redis.asyncio as aioredis
            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
            _redis_invalidation_client = aioredis.from_url(
                redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=0.2,
                socket_timeout=0.2,
            )
        except Exception as e:
            logger.warning(f"Không thể khởi tạo Redis client cho Invalidation: {e}")
            _redis_invalidation_client = None
    return _redis_invalidation_client


async def invalidate_agent_cache_in_redis(mac_or_device_id: str) -> int:
    """Xóa bỏ cache cấu hình Redis key `xiaozhi:agent_cfg:{device_id}` tức thì (Task 3.2)."""
    if not mac_or_device_id:
        return 0
    clean_mac, dev_id = extract_mac_and_device_id(mac_or_device_id)
    raw_str = mac_or_device_id.strip()
    keys_to_del = set()
    if clean_mac:
        keys_to_del.add(f"xiaozhi:agent_cfg:{clean_mac.lower()}")
    if dev_id:
        keys_to_del.add(f"xiaozhi:agent_cfg:{dev_id.lower()}")
    if raw_str:
        keys_to_del.add(f"xiaozhi:agent_cfg:{raw_str.lower()}")
        keys_to_del.add(f"xiaozhi:agent_cfg:{raw_str}")

    client = get_redis_invalidation_client()
    deleted = 0
    if client:
        try:
            deleted = await client.delete(*keys_to_del)
            logger.info(f"⚡ [CACHE INVALIDATED] Đã xóa cache Redis agent_cfg cho {mac_or_device_id} ({keys_to_del}) -> {deleted} keys")
        except Exception as e:
            logger.error(f"Lỗi khi xóa cache Redis agent_cfg: {e}")
    return deleted


def create_agent_profile_router(dal: SmartHomeDAL = default_dal):
    """Khởi tạo cụm route cấu hình Agent động."""

    expected_secret = os.getenv("SERVER_SECRET", "a613f18e19c9b589c3bc82da3d76e47610dc2e5f88456a053120141fbe3239a0")

    def _verify_server_secret(request: web.Request) -> bool:
        """Xác thực Bearer token bí mật giữa xiaozhi-server và manager-api."""
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return False
        token = auth_header[7:].strip()
        # Chấp nhận SERVER_SECRET hoặc SMARTHOME_MCP_TOKEN
        valid_tokens = {expected_secret, os.getenv("SMARTHOME_MCP_TOKEN", "smarthome_secret_token")}
        return token in valid_tokens

    async def get_agent_models_handler(request: web.Request) -> web.Response:
        """Endpoint nội bộ chuẩn tương thích xiaozhi-server (/config/agent-models).
        
        Trả về JSON cấu hình riêng biệt theo device_id & user_id (Prompt, TTS Voice, Model...).
        """
        if not _verify_server_secret(request):
            return web.json_response({"code": 401, "msg": "Unauthorized: Invalid server secret"}, status=401)

        try:
            body = await request.json()
        except Exception:
            body = {}

        mac_address = body.get("macAddress") or body.get("mac") or request.headers.get("device-id") or ""
        clean_mac, dev_id = extract_mac_and_device_id(mac_address)
        target_mac = clean_mac or dev_id or mac_address.strip().lower()

        # Tra cứu hồ sơ cấu hình Agent trong database
        profile = dal.get_agent_profile(target_mac)
        if not profile:
            # Kiểm tra xem loa có tồn tại trong bảng speakers không
            speaker = dal.get_speaker(target_mac)
            if not speaker:
                # Chưa đăng ký / chưa kích hoạt -> trả code 10041
                return web.json_response({
                    "code": 10041,
                    "msg": f"Thiết bị '{target_mac}' chưa được kích hoạt hoặc không tồn tại trong hệ thống.",
                })
            # Tạo default profile cho Loa vừa ghép nối (kế thừa trọn vẹn AI của server)
            profile = {
                "speaker_mac": speaker.speaker_mac,
                "user_id": speaker.user_id,
                "assistant_name": "default",
                "prompt": None,  # Mặc định để None để Voice Core kế thừa trọn vẹn System Prompt gốc của máy chủ
                "tts_voice_id": "default",  # Mặc định kế thừa TTS cục bộ của server (VieNeuTTS)
                "llm_model_profile": "default",  # Mặc định kế thừa LLM của server (DeepSeekLLM)
                "enabled_plugins": {},
            }

        asst_name = profile.get("assistant_name")
        custom_prompt = profile.get("prompt")

        tts_voice = profile.get("tts_voice_id") or "default"
        llm_model = profile.get("llm_model_profile") or "default"

        agent_data = {
            "plugins": profile.get("enabled_plugins") or {},
        }
        if asst_name and asst_name not in ("default", "XiaoZhi"):
            agent_data["assistant_name"] = asst_name

        # Chỉ ghi đè Prompt khi người dùng thực sự tùy biến trên Web Portal / App.
        # Nếu để trống (custom_prompt is None), Voice Core sẽ tự động kế thừa trọn vẹn
        # System Prompt chuẩn từ data/.config.yaml & agent-base-prompt.txt!
        if custom_prompt:
            agent_data["prompt"] = custom_prompt

        # 1. Cơ chế Kế thừa Thông minh TTS:
        # Nếu là "default": KHÔNG gửi khối ghi đè TTS để Voice Core kế thừa 100% TTS từ data/.config.yaml
        # Chỉ ghi đè khi người dùng cố ý chọn giọng đọc cụ thể
        if tts_voice and tts_voice != "default":
            agent_data["tts_voice_id"] = tts_voice
            if tts_voice.startswith("vi-VN-") or tts_voice.startswith("en-US-") or tts_voice.startswith("zh-CN-"):
                agent_data.setdefault("selected_module", {})["TTS"] = "EdgeTTS"
                agent_data["TTS"] = {
                    "EdgeTTS": {
                        "type": "edge",
                        "voice": tts_voice,
                    }
                }
            elif tts_voice.lower() == "vieneu":
                # Kế thừa hoàn toàn cấu hình VieNeuTTS và preset_voice từ data/.config.yaml
                agent_data.setdefault("selected_module", {})["TTS"] = "VieNeuTTS"
            else:
                # Nếu người dùng chọn tên giọng VieNeuTTS cụ thể
                agent_data.setdefault("selected_module", {})["TTS"] = "VieNeuTTS"
                agent_data["TTS"] = {
                    "VieNeuTTS": {
                        "type": "vieneu",
                        "preset_voice": tts_voice,
                    }
                }

        # 2. Cơ chế Kế thừa Thông minh LLM:
        # Nếu là "default": KHÔNG gửi khối ghi đè LLM để Voice Core kế thừa 100% LLM từ data/.config.yaml
        if llm_model and llm_model != "default":
            agent_data.setdefault("selected_module", {})["LLM"] = "OpenAI"
            agent_data["LLM"] = {
                "OpenAI": {
                    "type": "openai",
                    "model": llm_model,
                }
            }

        return web.json_response({
            "code": 0,
            "msg": "success",
            "data": agent_data,
        })

    async def get_correct_words_handler(request: web.Request) -> web.Response:
        """Endpoint nội bộ trả về từ điển thay thế / sửa từ cho ASR/TTS (/config/correct-words)."""
        return web.json_response({
            "code": 0,
            "msg": "success",
            "data": {},
        })

    async def get_server_base_handler(request: web.Request) -> web.Response:
        """Endpoint nội bộ trả về cấu hình cơ sở máy chủ (/config/server-base)."""
        return web.json_response({
            "code": 0,
            "msg": "success",
            "data": {
                "server": {
                    "auth": {
                        "enabled": True,
                    }
                }
            },
        })

    async def update_agent_profile_handler(request: web.Request) -> web.Response:
        """API Quản trị Web Portal & App eSunhouse: Cập nhật thông số cá nhân hóa Agent.
        
        Tự động kích hoạt cơ chế Active Cache Invalidation trên Redis (Task 3.1 & 3.2).
        """
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"status": "error", "message": "Invalid JSON body"}, status=400)

        raw_mac = body.get("speaker_mac") or body.get("device_id")
        if not raw_mac:
            return web.json_response({"status": "error", "message": "Missing speaker_mac or device_id"}, status=400)

        user_id = body.get("user_id")
        assistant_name = body.get("assistant_name")
        prompt = body.get("prompt")
        tts_voice_id = body.get("tts_voice_id")
        llm_model_profile = body.get("llm_model_profile")
        enabled_plugins = body.get("enabled_plugins")

        # 1. Lưu hồ sơ vào cơ sở dữ liệu bền vững (PostgreSQL / SQLite)
        profile = dal.upsert_agent_profile(
            speaker_mac=raw_mac,
            user_id=user_id,
            assistant_name=assistant_name,
            prompt=prompt,
            tts_voice_id=tts_voice_id,
            llm_model_profile=llm_model_profile,
            enabled_plugins=enabled_plugins,
        )

        # 2. Xóa cache Redis ngay lập tức (Active Cache Invalidation)
        deleted_keys = await invalidate_agent_cache_in_redis(raw_mac)

        return web.json_response({
            "status": "success",
            "message": "Cập nhật hồ sơ Agent cá nhân hóa thành công và đã xóa cache Redis.",
            "invalidated_redis_keys": deleted_keys,
            "profile": profile,
        })

    async def get_agent_profile_admin_handler(request: web.Request) -> web.Response:
        """API Web Portal & App eSunhouse: Tra cứu hồ sơ Agent của thiết bị."""
        raw_mac = request.query.get("speaker_mac") or request.query.get("device_id")
        if not raw_mac:
            return web.json_response({"status": "error", "message": "Missing speaker_mac query parameter"}, status=400)

        profile = dal.get_agent_profile(raw_mac)
        if not profile:
            return web.json_response({"status": "not_found", "message": "Chưa có cấu hình cho thiết bị này"}, status=404)

        return web.json_response({
            "status": "success",
            "profile": profile,
        })

    return {
        "get_agent_models": get_agent_models_handler,
        "get_correct_words": get_correct_words_handler,
        "get_server_base": get_server_base_handler,
        "update_agent_profile": update_agent_profile_handler,
        "get_agent_profile_admin": get_agent_profile_admin_handler,
    }
