# -*- coding: utf-8 -*-
"""ROUTER GHÉP NỐI THIẾT BỊ LOA SUNHOUSE (PAIRING ROUTER)
Cung cấp API ghép nối Loa thông minh ESP32-S3 với tài khoản người dùng qua mã PIN 6 số hiển thị trên màn hình OLED.
"""

import logging
import random
from typing import Optional
from aiohttp import web

from storage.db import SmartHomeDAL, default_dal
from storage.models import extract_mac_and_device_id

logger = logging.getLogger("PairingRouter")


def create_pairing_router(dal: SmartHomeDAL = default_dal):
    """Khởi tạo cụm route quản lý phiên ghép nối Loa."""

    async def generate_pin_handler(request: web.Request) -> web.Response:
        """API tạo mã PIN ghép nối 6 chữ số ngắn hạn (hiệu lực 5 phút) cho Loa ESP32-S3.

        Payload JSON:
            speaker_mac (str, optional): Địa chỉ MAC hoặc Device ID phần cứng của Loa.
            device_id (str, optional): Device ID chuẩn (địa chỉ MAC của loa).
            expire_seconds (int, optional): Thời gian hết hạn (mặc định 300s).
        """
        try:
            data = await request.json()
        except Exception:
            data = {}

        raw_id = data.get("device_id") or data.get("speaker_mac")
        if not raw_id:
            first_spk = dal.get_first_speaker()
            raw_id = first_spk.device_id if first_spk else None
        if not raw_id:
            return web.json_response(
                {"status": "error", "message": "Vui lòng cung cấp device_id hoặc speaker_mac của loa."},
                status=400,
            )

        mac, device_id = extract_mac_and_device_id(raw_id)
        expire_seconds = int(data.get("expire_seconds", 300))

        # Sinh mã PIN 6 chữ số ngẫu nhiên (100000 - 999999)
        pairing_code = str(random.randint(100000, 999999))

        session = dal.create_pairing_session(
            pairing_code=pairing_code,
            speaker_mac=device_id,  # Lưu Device ID chuẩn
            expire_seconds=expire_seconds,
        )

        logger.info(
            f"🔑 [PAIRING] Đã sinh mã PIN [{pairing_code}] cho Loa Device ID [{device_id}] (MAC: {mac}) "
            f"(Hiệu lực: {expire_seconds}s)"
        )

        return web.json_response({
            "status": "success",
            "pairing_code": pairing_code,
            "device_id": device_id,
            "speaker_mac": mac,
            "expires_in": expire_seconds,
            "message": f"Mã PIN ghép nối [{pairing_code}] đã được tạo cho thiết bị {device_id}.",
        })

    async def claim_pin_handler(request: web.Request) -> web.Response:
        """API xác nhận mã PIN từ Ứng dụng hoặc Web Portal để liên kết Loa với User ID.

        Payload JSON:
            pairing_code (str): Mã PIN 6 chữ số hiển thị từ Loa.
            user_id (str, optional): Tài khoản người dùng (nếu để trống, default đặt trùng với Device ID).
        """
        try:
            data = await request.json()
        except Exception:
            return web.json_response(
                {"status": "error", "message": "Payload JSON không hợp lệ."},
                status=400,
            )

        pairing_code = data.get("pairing_code")
        user_id = data.get("user_id")

        if not pairing_code:
            return web.json_response(
                {"status": "error", "message": "Thiếu tham số bắt buộc 'pairing_code'."},
                status=400,
            )

        pairing_code = str(pairing_code).strip()
        user_id = str(user_id).strip() if user_id else None

        speaker = dal.claim_pairing_session(pairing_code=pairing_code, user_id=user_id)
        if not speaker:
            logger.warning(
                f"❌ [PAIRING] Xác nhận mã PIN thất bại: Mã [{pairing_code}] không hợp lệ, "
                "đã được sử dụng hoặc đã hết hạn."
            )
            return web.json_response(
                {
                    "status": "error",
                    "message": "Mã ghép nối không hợp lệ, đã được sử dụng hoặc đã quá hạn.",
                },
                status=400,
            )

        logger.info(
            f"🎉 [PAIRING SUCCESS] Ghép nối thành công Loa [{speaker.device_id or speaker.speaker_mac}] "
            f"với User ID [{speaker.user_id}]!"
        )

        return web.json_response({
            "status": "success",
            "device_id": speaker.device_id or speaker.speaker_mac,
            "speaker_mac": speaker.speaker_mac,
            "user_id": speaker.user_id,
            "message": f"Đã ghép nối Loa thành công với tài khoản [{speaker.user_id}].",
        })

    async def bind_user_handler(request: web.Request) -> web.Response:
        """API gán trực tiếp Loa vào một User ID mới (hỗ trợ đổi tên User ID linh hoạt).

        Payload JSON:
            device_id (str): Định danh phần cứng Loa (cố định, chuẩn phần cứng).
            user_id (str): Tên User ID mới cần gán (mặc định lấy device_id nếu rỗng).
        """
        try:
            data = await request.json()
        except Exception:
            data = {}

        raw_dev_id = data.get("device_id") or data.get("speaker_mac")
        if not raw_dev_id:
            first_spk = dal.get_first_speaker()
            raw_dev_id = first_spk.device_id if first_spk else None
        if not raw_dev_id:
            return web.json_response(
                {"status": "error", "message": "Vui lòng cung cấp device_id của loa."},
                status=400,
            )
        raw_user_id = data.get("user_id")
        new_device_name = (data.get("device_name") or "").strip()

        mac, device_id = extract_mac_and_device_id(raw_dev_id)
        final_user_id = (raw_user_id or "").strip() or device_id

        if not new_device_name:
            curr_spk = dal.get_speaker(mac)
            new_device_name = curr_spk.device_name if curr_spk and curr_spk.device_name else f"Loa Sunhouse ({mac[-5:] if len(mac) >= 5 else 'Agent'})"

        if "xiaozhi" in new_device_name.lower():
            new_device_name = (
                new_device_name.replace("Loa XiaoZhi", "Loa Sunhouse")
                .replace("XiaoZhi", "Sunhouse")
                .replace("xiaozhi", "Sunhouse")
            )

        speaker = dal.upsert_speaker(
            speaker_mac=mac,
            user_id=final_user_id,
            device_id=device_id,
            device_name=new_device_name,
        )

        logger.info(
            f"🔄 [PAIRING BIND] Đã cập nhật Loa [{device_id}] (MAC: {mac}) | Tên: '{new_device_name}' | User ID: [{final_user_id}]."
        )

        return web.json_response({
            "status": "success",
            "device_id": device_id,
            "speaker_mac": mac,
            "user_id": final_user_id,
            "device_name": new_device_name,
            "message": f"Đã cập nhật thông tin Loa [{new_device_name}] ({device_id}) thành công.",
        })

    async def delete_speaker_handler(request: web.Request) -> web.Response:
        """API xóa / hủy ghép nối Loa thông minh Sunhouse khỏi hệ thống."""
        try:
            data = await request.json()
        except Exception:
            data = {}

        raw_id = (
            request.match_info.get("speaker_id")
            or data.get("device_id")
            or data.get("speaker_mac")
        )
        if not raw_id:
            first_spk = dal.get_first_speaker()
            raw_id = first_spk.device_id if first_spk else None

        if not raw_id:
            return web.json_response(
                {"status": "error", "message": "Không tìm thấy thiết bị loa để xóa."},
                status=400,
            )

        ok = dal.delete_speaker(raw_id)
        if ok:
            logger.info(f"🗑️ [SPEAKER DELETED] Đã xóa thành công Loa [{raw_id}] khỏi hệ thống.")
            # Bắn tín hiệu KICK sang Voice Server (Cổng 8003) để ngắt kết nối WebSocket thời gian thực (< 0.5s)
            try:
                import aiohttp
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        "http://127.0.0.1:8003/api/device/kick",
                        json={"device_id": raw_id, "reason": "Unlinked from Web Portal"},
                        timeout=aiohttp.ClientTimeout(total=2.0)
                    ) as kick_resp:
                        if kick_resp.status == 200:
                            kick_result = await kick_resp.json()
                            logger.info(f"⚡ [REALTIME KICK] Kết quả ngắt WebSocket cho {raw_id}: {kick_result}")
            except Exception as kick_err:
                logger.warning(f"⚠️ [REALTIME KICK] Không thể gửi tín hiệu đá kết nối sang Cổng 8003: {kick_err}")

            return web.json_response({
                "status": "success",
                "message": f"Đã xóa thành công thiết bị {raw_id} khỏi hệ thống.",
            })
        else:
            return web.json_response(
                {"status": "error", "message": f"Không tìm thấy thiết bị {raw_id} trong CSDL."},
                status=404,
            )

    return {
        "generate_pin": generate_pin_handler,
        "claim_pin": claim_pin_handler,
        "bind_user": bind_user_handler,
        "delete_speaker": delete_speaker_handler,
    }
