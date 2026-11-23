# -*- coding: utf-8 -*-
"""ROUTER CẦU NỐI GIAO THỨC OTA VÀ GHÉP NỐI THIẾT BỊ (OTA PAIRING PROTOCOL BRIDGE)
Cổng tiếp nhận và điều phối giao thức OTA chuẩn của XiaoZhi & Sunhouse (Cổng 8005).

Cung cấp:
1. POST /xiaozhi/ota/ & /ota/: Tiếp nhận bái danh từ ESP32, kiểm tra trạng thái kích hoạt,
   sinh mã PIN OTP 6 chữ số có thời hạn (TTL 300s) và cấp cấu hình WebSocket kết nối.
2. POST /xiaozhi/ota/activate & /ota/activate: Phục vụ chu kỳ Active Polling (mỗi 3 giây)
   từ ESP32. Trả về HTTP 202 (đang chờ) hoặc HTTP 200 (hoàn tất ghép nối).
3. GET /xiaozhi/ota/status: Endpoint giám sát trạng thái các phiên ghép nối đang hoạt động.
"""

import collections
import logging
import os
import random
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional
from aiohttp import web

from storage.db import SmartHomeDAL, default_dal
from storage.models import extract_mac_and_device_id

logger = logging.getLogger("OTAPairingRouter")


def _generate_auth_token(device_id: str, user_id: str, client_id: str = "default") -> str:
    """Sinh chuỗi AuthToken AES-GCM chuẩn thương mại phục vụ xác thực Voice Core (Phase 2 & 3)."""
    auth_key = os.getenv(
        "SERVER_AUTH_KEY", "8f14e45fceea167a5a36dedd4bea254395cfb613a9607b0c39f1e16c90d63428"
    ).strip()
    try:
        cur_dir = os.path.dirname(os.path.abspath(__file__))
        server_core_path = os.path.abspath(os.path.join(cur_dir, "..", "..", "main", "xiaozhi-server"))
        if server_core_path not in sys.path:
            sys.path.insert(0, server_core_path)
        from core.utils.auth import AuthToken

        generator = AuthToken(secret_key=auth_key)
        return generator.generate_token(
            device_id=device_id,
            user_id=user_id,
            client_id=client_id,
            expire_hours=720,  # 30 ngày (Task 2.1)
            scope="voice,vision",
        )
    except Exception as e:
        logger.error(f"❌ [OTA] Lỗi sinh AuthToken AES-GCM cho thiết bị [{device_id}]: {e}")
        return ""


def create_ota_pairing_router(dal: SmartHomeDAL = default_dal, ws_url: Optional[str] = None):
    """Khởi tạo cụm router điều phối giao thức OTA XiaoZhi."""

    # Bộ theo dõi tần suất gọi API (Rate limiting & Anti-Brute Force per IP)
    # Lưu danh sách timestamp của các request trong 60 giây gần nhất
    _rate_tracker: Dict[str, collections.deque] = collections.defaultdict(
        lambda: collections.deque(maxlen=100)
    )

    def _check_rate_limit(remote_ip: str, max_requests: int = 60, window_secs: int = 60) -> bool:
        """Kiểm tra giới hạn tần suất yêu cầu chống tấn công vét cạn / từ chối dịch vụ."""
        now = time.time()
        q = _rate_tracker[remote_ip]
        while q and q[0] <= now - window_secs:
            q.popleft()
        if len(q) >= max_requests:
            return False
        q.append(now)
        return True

    def _resolve_websocket_url(request: web.Request) -> str:
        """Xác định URL WebSocket cho Voice Core Server (mặc định cổng 8000)."""
        if ws_url:
            return ws_url

        env_ws = os.getenv("XIAOZHI_WEBSOCKET_URL")
        if env_ws:
            return env_ws

        # Tự động nhận diện IP máy chủ từ Host Header của request
        host_header = request.headers.get("Host", "127.0.0.1:8005")
        host_ip = host_header.split(":")[0]
        # Nếu host_ip là localhost/127.0.0.1 nhưng có LOCAL_SERVER_IP trong env thì ưu tiên dùng
        if host_ip in ["127.0.0.1", "localhost", "0.0.0.0"]:
            local_ip = os.getenv("LOCAL_SERVER_IP")
            if local_ip:
                host_ip = local_ip

        return f"ws://{host_ip}:8000/xiaozhi/v1/"

    def _resolve_portal_url(request: web.Request) -> str:
        """Xác định URL Web Portal hiển thị trên màn hình Loa OLED."""
        host_header = request.headers.get("Host", "127.0.0.1:8005")
        parts = host_header.split(":")
        host_ip = parts[0]
        port = parts[1] if len(parts) > 1 else "8005"

        if host_ip in ["127.0.0.1", "localhost", "0.0.0.0"]:
            local_ip = os.getenv("LOCAL_SERVER_IP")
            if local_ip:
                host_ip = local_ip

        return f"http://{host_ip}:{port}/portal"

    async def check_version_handler(request: web.Request) -> web.Response:
        """Xử lý yêu cầu kiểm tra phiên bản & kích hoạt từ Loa ESP32-S3 (POST /xiaozhi/ota/).

        Headers:
            Device-Id (str): Địa chỉ MAC của chip ESP32 (vd: 84:fc:e6:01:02:03).
            Client-Id (str, optional): UUID định danh phiên client.
        Payload JSON (optional):
            application: { version: "1.0.0" }
            board: { type: "esp32-s3-box" }
        """
        remote_ip = request.remote or "unknown"
        if not _check_rate_limit(remote_ip, max_requests=60, window_secs=60):
            logger.warning(f"⚠️ [OTA RATE LIMIT] IP [{remote_ip}] bị từ chối do gửi quá 60 req/phút.")
            return web.json_response(
                {"error": "Too Many Requests", "message": "Vui lòng thử lại sau."},
                status=429,
            )

        # 1. Trích xuất MAC / Device ID từ Headers hoặc Body
        raw_id = (
            request.headers.get("Device-Id")
            or request.headers.get("device-id")
            or request.headers.get("Device_Id")
            or request.query.get("device_id")
            or request.query.get("mac")
        )

        body_data: Dict[str, Any] = {}
        if request.can_read_body:
            try:
                body_data = await request.json()
            except Exception:
                pass

        if not raw_id:
            raw_id = (
                body_data.get("device_id")
                or body_data.get("mac")
                or (body_data.get("board", {}).get("mac") if isinstance(body_data.get("board"), dict) else None)
            )

        if not raw_id:
            logger.warning("❌ [OTA] Yêu cầu check version thiếu header 'Device-Id' hoặc MAC address.")
            return web.json_response(
                {"error": "Missing Device-Id", "message": "Header Device-Id (MAC) là bắt buộc."},
                status=400,
            )

        mac, device_id = extract_mac_and_device_id(raw_id)
        resolved_ws_url = _resolve_websocket_url(request)
        portal_url = _resolve_portal_url(request)
        server_now_ms = int(time.time() * 1000)

        # 2. Tra cứu trạng thái Loa trong CSDL
        speaker = dal.get_speaker(mac) or dal.get_speaker(device_id)

        # TRƯỜNG HỢP A: Loa ĐÃ ĐƯỢC GHÉP NỐI (Đã gán User ID)
        if speaker and speaker.user_id:
            logger.info(
                f"✅ [OTA CHECK] Loa MAC [{mac}] ĐÃ KÍCH HOẠT (Chủ sở hữu: '{speaker.user_id}', "
                f"Tên: '{speaker.device_name}'). Trả về WebSocket URL sẵn sàng đàm thoại."
            )
            client_id = (
                request.headers.get("Client-Id")
                or request.headers.get("client-id")
                or "default"
            )
            ws_token = _generate_auth_token(
                device_id=mac,
                user_id=speaker.user_id,
                client_id=client_id,
            )
            response_payload = {
                "server_time": {
                    "timestamp": server_now_ms,
                    "timezone_offset": 420,  # GMT+7 (Việt Nam)
                },
                "firmware": {
                    "version": "1.0.0",
                    "url": "",
                },
                "websocket": {
                    "url": resolved_ws_url,
                    "token": ws_token,
                },
                "activation": None,
            }
            return web.json_response(response_payload, status=200)

        # TRƯỜNG HỢP B: Loa CHƯA ĐƯỢC GHÉP NỐI -> Sinh mã PIN OTP 6 chữ số
        # Tự động dọn sạch các session cũ đã quá hạn
        dal.clean_expired_pairing_sessions()

        # Kiểm tra xem Loa có phiên ghép nối nào đang chờ (pending) và còn hạn không
        active_session = dal.get_active_pairing_session(mac)
        if active_session:
            pin_code = active_session.pairing_code
            remaining_sec = max(10, int((active_session.expire_at - datetime.utcnow()).total_seconds()))
            logger.info(
                f"🔄 [OTA CHECK] Tái sử dụng mã PIN [{pin_code}] còn hiệu lực ({remaining_sec}s) cho Loa MAC [{mac}]."
            )
        else:
            # Sinh mã ngẫu nhiên 6 chữ số
            pin_code = str(random.randint(100000, 999999))
            remaining_sec = 300
            dal.create_pairing_session(
                pairing_code=pin_code,
                speaker_mac=mac,
                expire_seconds=remaining_sec,
            )
            logger.info(
                f"🔑 [OTA CHECK] Đã sinh mã PIN OTP [{pin_code}] cho Loa MAC [{mac}] (Thời hạn: {remaining_sec}s)."
            )

        # Tạo thông điệp hiển thị trên OLED: Dòng 1 là URL portal, Dòng 2 là Mã PIN
        oled_message = f"{portal_url}\n{pin_code}"

        response_payload = {
            "server_time": {
                "timestamp": server_now_ms,
                "timezone_offset": 420,  # GMT+7
            },
            "firmware": {
                "version": "1.0.0",
                "url": "",
            },
            "websocket": {
                "url": resolved_ws_url,
                "token": "",
            },
            "activation": {
                "code": pin_code,
                "message": oled_message,
                "challenge": mac,
                "timeout_ms": remaining_sec * 1000,
            },
        }

        return web.json_response(response_payload, status=200)

    async def activate_status_handler(request: web.Request) -> web.Response:
        """Xử lý Active Polling từ Firmware ESP32 (POST /xiaozhi/ota/activate).

        Quy ước giao thức Firmware (ota.cc):
            - Nếu HTTP 202: Firmware nhận diện là ESP_ERR_TIMEOUT, tiếp tục chờ 3 giây và lặp lại.
            - Nếu HTTP 200: Firmware nhận diện là ESP_OK, bắn sự kiện MAIN_EVENT_DONE,
              tắt màn hình hiển thị mã PIN và chuyển sang trạng thái Standby Idle.
        """
        raw_id = (
            request.headers.get("Device-Id")
            or request.headers.get("device-id")
            or request.headers.get("Device_Id")
            or request.query.get("device_id")
            or request.query.get("mac")
        )

        if not raw_id and request.can_read_body:
            try:
                body_data = await request.json()
                raw_id = body_data.get("device_id") or body_data.get("mac")
            except Exception:
                pass

        if not raw_id:
            return web.json_response(
                {"error": "Missing Device-Id", "message": "Header Device-Id (MAC) là bắt buộc."},
                status=400,
            )

        mac, device_id = extract_mac_and_device_id(raw_id)
        speaker = dal.get_speaker(mac) or dal.get_speaker(device_id)

        # 1. ĐÃ KÍCH HOẠT THÀNH CÔNG (Người dùng đã nhập mã PIN trên Web Portal)
        if speaker and speaker.user_id:
            logger.info(
                f"🎉 [OTA ACTIVATE SUCCESS] Loa MAC [{mac}] ĐÃ ĐƯỢC KÍCH HOẠT THÀNH CÔNG "
                f"(Gán cho User: '{speaker.user_id}')! Phản hồi HTTP 200 OK."
            )
            client_id = (
                request.headers.get("Client-Id")
                or request.headers.get("client-id")
                or "default"
            )
            resolved_ws_url = _resolve_websocket_url(request)
            ws_token = _generate_auth_token(
                device_id=mac,
                user_id=speaker.user_id,
                client_id=client_id,
            )
            return web.json_response(
                {
                    "code": 0,
                    "status": "success",
                    "message": "Thiết bị đã được kích hoạt thành công.",
                    "device_id": speaker.device_id or mac,
                    "speaker_mac": mac,
                    "user_id": speaker.user_id,
                    "websocket": {
                        "url": resolved_ws_url,
                        "token": ws_token,
                    },
                },
                status=200,
            )

        # 2. VẪN ĐANG CHỜ NGƯỜI DÙNG NHẬP MÃ (Pending)
        # Trả về HTTP 202 Accepted để Firmware ESP32 tiếp tục vòng lặp polling
        return web.json_response(
            {
                "code": 202,
                "status": "pending",
                "message": "Đang chờ người dùng nhập mã PIN xác thực trên Web Console.",
                "speaker_mac": mac,
            },
            status=202,
        )

    async def ota_status_handler(request: web.Request) -> web.Response:
        """API giám sát trạng thái chẩn đoán hệ thống OTA (GET /xiaozhi/ota/status)."""
        dal.clean_expired_pairing_sessions()
        all_speakers = []
        with dal.get_session() as session:
            from sqlalchemy import select
            from storage.models import Speaker, PairingSession
            spk_rows = session.execute(select(Speaker)).scalars().all()
            for s in spk_rows:
                all_speakers.append({
                    "mac": s.speaker_mac,
                    "device_id": s.device_id,
                    "user_id": s.user_id,
                    "device_name": s.device_name,
                    "is_active": s.is_active,
                })

            now = datetime.utcnow()
            active_sessions = []
            sess_rows = session.execute(
                select(PairingSession).where(
                    PairingSession.status == "pending",
                    PairingSession.expire_at > now,
                )
            ).scalars().all()
            for ps in sess_rows:
                active_sessions.append({
                    "pairing_code": ps.pairing_code,
                    "speaker_mac": ps.speaker_mac,
                    "expires_in_seconds": int((ps.expire_at - now).total_seconds()),
                })

        return web.json_response({
            "status": "healthy",
            "server_time_utc": datetime.utcnow().isoformat(),
            "active_pairing_sessions": active_sessions,
            "registered_speakers_count": len(all_speakers),
            "registered_speakers": all_speakers,
        })

    return {
        "check_version": check_version_handler,
        "activate_status": activate_status_handler,
        "ota_status": ota_status_handler,
    }
