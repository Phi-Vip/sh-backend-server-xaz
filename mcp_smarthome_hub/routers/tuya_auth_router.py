# -*- coding: utf-8 -*-
"""ROUTER XÁC THỰC OAUTH2 & QUÉT MÃ QR TICKET TUYA CLOUD (TUYA AUTH ROUTER)
Cung cấp API phục vụ người dùng liên kết tài khoản Smart Life mở rộng từ bên ngoài:
1. GET /api/v1/auth/tuya/authorize-url: Sinh URL đăng nhập OAuth2 Tuya Cloud (grant_type=2).
2. POST /api/v1/auth/tuya/qr-ticket: Tạo vé quét mã QR Ticket liên kết nhanh (1-Click Link) qua App Smart Life.
3. POST /api/v1/auth/tuya/oauth-callback: Trao đổi mã Authorization Code lấy User Token và lưu vào CSDL mã hóa.
"""

import logging
import os
import time
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, Optional
import aiohttp
from aiohttp import web

from storage.db import SmartHomeDAL, default_dal
from clients.tuya_client import TuyaCloudClient

logger = logging.getLogger("TuyaAuthRouter")

# Bộ nhớ lưu trữ phiên vé QR Ticket (TTL 300s)
QR_TICKETS_STORE: Dict[str, Dict[str, Any]] = {}


def create_tuya_auth_router(
    dal: SmartHomeDAL = default_dal,
    tuya_client: Optional[TuyaCloudClient] = None,
):
    """Khởi tạo cụm route xác thực OAuth2 và mã QR Ticket."""

    async def get_authorize_url_handler(request: web.Request) -> web.Response:
        """API cung cấp URL ủy quyền OAuth2 cho người dùng liên kết tài khoản Tuya / Smart Life.

        Query params:
            user_id (str): Tài khoản người dùng (mặc định 'user_real_phi').
            redirect_uri (str, optional): Địa chỉ tiếp nhận mã Authorization Code.
        """
        user_id = dal.resolve_user_id(request.query.get("user_id") or request.query.get("device_id"))
        redirect_uri = request.query.get(
            "redirect_uri",
            "http://localhost:8005/api/v1/auth/tuya/callback",
        )

        client_id = getattr(tuya_client, "client_id", "") if tuya_client else ""
        if not client_id:
            client_id = os.getenv("TUYA_CLIENT_ID", "")

        state = f"{user_id}_{uuid.uuid4().hex[:8]}"

        # Tự động hóa kết nối Data Center Singapore cho thị trường Việt Nam
        is_auto_singapore = os.getenv("TUYA_REGION_AUTO_SINGAPORE", "true").lower() == "true"
        default_auth_base = "https://auth-sg.tuya.com" if is_auto_singapore else "https://auth.tuya.com"
        auth_base = os.getenv("TUYA_AUTH_URL", default_auth_base).rstrip("/")

        # URL xác thực OAuth2 chuẩn theo kiến trúc Tuya Cloud Open Platform
        auth_url = (
            f"{auth_base}/authorize?"
            f"client_id={client_id}&"
            f"redirect_uri={redirect_uri}&"
            f"response_type=code&"
            f"state={state}"
        )

        logger.info(f"🔗 [TUYA OAUTH] Đã tạo Authorize URL cho User [{user_id}]: {auth_url}")

        return web.json_response({
            "status": "success",
            "authorize_url": auth_url,
            "client_id": client_id,
            "user_id": user_id,
            "state": state,
        })

    async def create_qr_ticket_handler(request: web.Request) -> web.Response:
        """API tạo mã QR Ticket phục vụ quét mã liên kết 1 chạm từ App Smart Life / Tuya.

        Payload JSON:
            user_id (str, optional): Tài khoản người dùng.
            user_code (str, optional): Mã User Code từ App Smart Life (Tôi -> Cài đặt -> Tài khoản & bảo mật -> Mã người dùng).
        """
        try:
            data = await request.json()
        except Exception:
            data = {}

        user_id = dal.resolve_user_id(data.get("user_id") or data.get("device_id"))
        user_code = str(data.get("user_code", "")).strip()
        ticket_id = f"tuya_ticket_{uuid.uuid4().hex[:12]}"
        expire_seconds = 300  # 5 phút chuẩn Tuya

        tuya_qr_code = None
        tuya_raw_token = None
        error_msg = None

        # 1. Nếu người dùng nhập User Code, gọi Tuya Device Sharing API (chuẩn Home Assistant)
        if user_code:
            try:
                tuya_url = (
                    f"https://apigw.iotbing.com/v1.0/m/life/home-assistant/qrcode/tokens?"
                    f"clientid=HA_3y9q4ak7g4ephrvke&usercode={user_code}&schema=haauthorize"
                )
                async with aiohttp.ClientSession() as session:
                    async with session.post(tuya_url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                        res_json = await resp.json(content_type=None)
                        if res_json.get("success"):
                            raw_code = (
                                res_json.get("result", {}).get("qrcode")
                                or res_json.get("result", {}).get("token")
                            )
                            if raw_code:
                                tuya_raw_token = raw_code
                                tuya_qr_code = f"tuyaSmart--qrLogin?token={raw_code}"
                                logger.info(
                                    f"✨ [TUYA SHARING] Lấy thành công QR Token cho User Code [{user_code}]! "
                                    f"(Token: {raw_code[:20]}...)"
                                )
                        else:
                            code_err = res_json.get("code")
                            if code_err == "USERCODE_INCORRECT":
                                error_msg = (
                                    "Mã User Code không đúng hoặc không tồn tại. "
                                    "Vui lòng mở App Smart Life (Tôi -> Cài đặt -> Tài khoản và bảo mật -> Mã người dùng) để lấy đúng mã."
                                )
                            else:
                                error_msg = res_json.get("msg") or f"Lỗi Tuya API: {code_err}"
            except Exception as e_share:
                logger.warning(f"⚠️ [TUYA SHARING] Lỗi gọi Tuya Sharing Gateway: {e_share}")
                error_msg = f"Lỗi kết nối máy chủ Tuya Gateway: {e_share}"
        else:
            # Fallback cho mock / test environments khi không truyền user_code
            mock_token = f"mock_tuya_qr_{uuid.uuid4().hex[:16]}"
            tuya_raw_token = mock_token
            tuya_qr_code = f"tuyaSmart--qrLogin?token={mock_token}"
            expire_seconds = 600

        if error_msg or not tuya_qr_code:
            return web.json_response(
                {"status": "error", "message": error_msg or "Không thể lấy mã QR từ Tuya Gateway."},
                status=400,
            )

        # 2. Tạo QR Payload chuẩn Tuya Smart Life
        qr_payload = tuya_qr_code

        # 3. Lưu vào bộ nhớ quản lý phiên QR
        now_ts = time.time()
        QR_TICKETS_STORE[ticket_id] = {
            "ticket_id": ticket_id,
            "user_id": user_id,
            "user_code": user_code,
            "tuya_raw_token": tuya_raw_token,
            "qr_payload": qr_payload,
            "status": "pending",
            "created_at": now_ts,
            "expire_at": now_ts + expire_seconds,
            "synced_count": 0,
        }

        logger.info(
            f"📱 [TUYA QR] Đã sinh QR Ticket [{ticket_id}] cho User [{user_id}] "
            f"(Payload: {qr_payload[:30]}...). Có hiệu lực trong {expire_seconds}s."
        )

        return web.json_response({
            "status": "success",
            "ticket_id": ticket_id,
            "user_id": user_id,
            "qr_payload": qr_payload,
            "user_code": user_code,
            "expire_seconds": expire_seconds,
            "instructions": "Mở ứng dụng Smart Life hoặc Tuya Smart, chọn biểu tượng Quét mã QR ở góc trên tab Cá nhân để quét mã.",
        })

    async def get_qr_ticket_status_handler(request: web.Request) -> web.Response:
        """API tra cứu trạng thái vé quét mã QR Ticket (polling mỗi 2 giây)."""
        ticket_id = request.match_info.get("ticket_id")
        ticket = QR_TICKETS_STORE.get(ticket_id)
        if not ticket:
            return web.json_response(
                {"status": "expired", "message": "Vé QR không tồn tại hoặc đã hết hạn."},
                status=404,
            )

        if time.time() > ticket["expire_at"]:
            ticket["status"] = "expired"
            return web.json_response({
                "status": "expired",
                "message": "Mã QR đã hết hạn (quá 5 phút). Vui lòng tạo mã mới.",
            })

        if ticket["status"] == "confirmed":
            return web.json_response({
                "status": "confirmed",
                "message": "Ủy quyền thành công!",
                "user_id": ticket["user_id"],
                "tuya_uid": ticket.get("tuya_uid", ""),
                "synced_count": ticket.get("synced_count", 0),
            })

        # 1. Tra cứu trực tiếp Tuya Sharing Gateway xem người dùng đã quét và bấm Xác nhận chưa
        if ticket.get("tuya_raw_token") and ticket.get("user_code"):
            try:
                check_url = (
                    f"https://apigw.iotbing.com/v1.0/m/life/home-assistant/qrcode/tokens/{ticket['tuya_raw_token']}"
                    f"?clientid=HA_3y9q4ak7g4ephrvke&usercode={ticket['user_code']}"
                )
                async with aiohttp.ClientSession() as session:
                    async with session.get(check_url, timeout=aiohttp.ClientTimeout(total=4)) as resp:
                        check_data = await resp.json(content_type=None)
                        if check_data.get("success"):
                            res = check_data.get("result", {})
                            t = check_data.get("t")
                            res["t"] = t
                            tuya_uid = res.get("uid")
                            access_token = res.get("access_token")
                            refresh_token = res.get("refresh_token", "")
                            expire_time = res.get("expire_time", 7200)
                            logger.info(
                                f"🎉 [TUYA QR SUCCESS] User [{ticket['user_id']}] đã xác nhận quét mã! Tuya UID: {tuya_uid} | Raw: {res}"
                            )

                            expire_at = datetime.utcnow() + timedelta(seconds=expire_time)
                            dal.save_user_credential(
                                user_id=ticket["user_id"],
                                external_tuya_uid=tuya_uid,
                                access_token=access_token,
                                refresh_token=refresh_token,
                                expire_at=expire_at,
                                auth_source="tuya_sharing_qr",
                            )

                            # Khởi tạo TuyaSharingManager và đồng bộ thiết bị qua Tuya Sharing Gateway
                            from clients.tuya_sharing_manager import sharing_manager
                            sharing_manager.register_session(
                                user_id=ticket["user_id"],
                                user_code=ticket["user_code"],
                                login_result_data=res,
                            )
                            synced = sharing_manager.sync_devices(
                                user_id=ticket["user_id"], dal=dal
                            )

                            ticket["status"] = "confirmed"
                            ticket["synced_count"] = len(synced)
                            ticket["tuya_uid"] = tuya_uid
                            return web.json_response({
                                "status": "confirmed",
                                "message": f"Ủy quyền thành công cho tài khoản Smart Life ({tuya_uid})!",
                                "user_id": ticket["user_id"],
                                "tuya_uid": tuya_uid,
                                "synced_count": len(synced),
                                "devices": synced,
                            })
            except Exception as e_tuya_stat:
                logger.error(f"❌ [TUYA SHARING POLL ERROR]: {e_tuya_stat}", exc_info=True)

        # 2. Kiểm tra nếu Tuya Cloud đã có tài khoản / thiết bị liên kết qua associated users
        if tuya_client:
            try:
                token_res = await tuya_client.get_token(grant_type=1)
                token = token_res.get("access_token")
                if token:
                    assoc_devs = await tuya_client.get_associated_user_devices(token=token)
                    if assoc_devs:
                        tuya_uid = None
                        for d in assoc_devs:
                            if d.get("uid"):
                                tuya_uid = d["uid"]
                                break
                        if tuya_uid:
                            expire_at = datetime.utcnow() + timedelta(seconds=7200)
                            dal.save_user_credential(
                                user_id=ticket["user_id"],
                                external_tuya_uid=tuya_uid,
                                access_token=token,
                                refresh_token=token_res.get("refresh_token", ""),
                                expire_at=expire_at,
                                auth_source="qr_ticket",
                            )
                            from sync.device_syncer import sync_tuya_devices
                            synced = await sync_tuya_devices(
                                dal=dal, tuya_client=tuya_client, user_id=ticket["user_id"]
                            )
                            ticket["status"] = "confirmed"
                            ticket["synced_count"] = len(synced)
                            ticket["tuya_uid"] = tuya_uid
                            return web.json_response({
                                "status": "confirmed",
                                "message": f"Ủy quyền thành công cho tài khoản {tuya_uid}!",
                                "user_id": ticket["user_id"],
                                "tuya_uid": tuya_uid,
                                "synced_count": len(synced),
                            })
            except Exception as e_check:
                logger.debug(f"Lỗi polling QR ticket: {e_check}")

        return web.json_response({
            "status": "pending",
            "message": "Đang chờ bạn mở App Smart Life quét mã QR và bấm Xác nhận...",
            "remaining_seconds": max(0, int(ticket["expire_at"] - time.time())),
        })

    async def confirm_qr_ticket_handler(request: web.Request) -> web.Response:
        """API kích hoạt kiểm tra ngay lập tức khi người dùng bấm 'Tôi đã quét xong'."""
        ticket_id = request.match_info.get("ticket_id")
        ticket = QR_TICKETS_STORE.get(ticket_id)
        if not ticket:
            return web.json_response(
                {"status": "error", "message": "Vé QR không tồn tại hoặc đã hết hạn."},
                status=404,
            )

        user_id = ticket["user_id"]

        if ticket.get("status") == "confirmed":
            return web.json_response({
                "status": "success",
                "message": f"Ủy quyền thành công tài khoản {ticket.get('tuya_uid')}!",
                "user_id": user_id,
                "tuya_uid": ticket.get("tuya_uid"),
                "synced_count": ticket.get("synced_count", 0),
                "devices": ticket.get("devices", []),
            })

        # 1. Kiểm tra qua Tuya Sharing Gateway trước nếu có tuya_raw_token
        if ticket.get("tuya_raw_token") and ticket.get("user_code"):
            try:
                check_url = (
                    f"https://apigw.iotbing.com/v1.0/m/life/home-assistant/qrcode/tokens/{ticket['tuya_raw_token']}"
                    f"?clientid=HA_3y9q4ak7g4ephrvke&usercode={ticket['user_code']}"
                )
                async with aiohttp.ClientSession() as session:
                    async with session.get(check_url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                        check_data = await resp.json(content_type=None)
                        if check_data.get("success"):
                            res = check_data.get("result", {})
                            t = check_data.get("t")
                            res["t"] = t
                            tuya_uid = res.get("uid")
                            access_token = res.get("access_token")
                            refresh_token = res.get("refresh_token", "")
                            expire_time = res.get("expire_time", 7200)

                            expire_at = datetime.utcnow() + timedelta(seconds=expire_time)
                            dal.save_user_credential(
                                user_id=user_id,
                                external_tuya_uid=tuya_uid,
                                access_token=access_token,
                                refresh_token=refresh_token,
                                expire_at=expire_at,
                                auth_source="tuya_sharing_qr",
                            )

                            from clients.tuya_sharing_manager import sharing_manager
                            sharing_manager.register_session(
                                user_id=user_id,
                                user_code=ticket["user_code"],
                                login_result_data=res,
                            )
                            synced = sharing_manager.sync_devices(
                                user_id=user_id, dal=dal
                            )
                            ticket["status"] = "confirmed"
                            ticket["synced_count"] = len(synced)
                            ticket["tuya_uid"] = tuya_uid

                            return web.json_response({
                                "status": "success",
                                "message": f"Liên kết thành công tài khoản {tuya_uid}!",
                                "user_id": user_id,
                                "tuya_uid": tuya_uid,
                                "synced_count": len(synced),
                                "devices": [
                                    {
                                        "id": d.get("device_id") or d.get("id"),
                                        "name": d.get("device_name") or d.get("name"),
                                    }
                                    for d in synced
                                ],
                            })
                        else:
                            logger.info(f"ℹ️ [TUYA QR CONFIRM] Gateway phản hồi: {check_data}")
                            return web.json_response({
                                "status": "pending",
                                "message": "Chưa phát hiện ủy quyền từ App Smart Life. Hãy chắc chắn bạn đã quét mã và bấm nút 'Confirm' trên điện thoại.",
                            })
            except Exception as e_direct:
                logger.warning(f"Lỗi gọi trực tiếp Tuya Sharing Gateway trong confirm: {e_direct}")
        if not tuya_client:
            return web.json_response(
                {"status": "error", "message": "TuyaClient chưa được cấu hình."},
                status=500,
            )

        try:
            token_res = await tuya_client.get_token(grant_type=1)
            token = token_res.get("access_token")
            if not token:
                return web.json_response(
                    {"status": "error", "message": "Không kết nối được Tuya Cloud."},
                    status=500,
                )

            assoc_devs = await tuya_client.get_associated_user_devices(token=token)
            tuya_uid = None
            if assoc_devs:
                for d in assoc_devs:
                    if d.get("uid"):
                        tuya_uid = d["uid"]
                        break

            if not tuya_uid:
                return web.json_response({
                    "status": "pending",
                    "message": "Chưa phát hiện ủy quyền từ App Smart Life. Hãy chắc chắn bạn đã quét mã và bấm nút 'Confirm' trên điện thoại.",
                })

            expire_at = datetime.utcnow() + timedelta(seconds=7200)
            dal.save_user_credential(
                user_id=user_id,
                external_tuya_uid=tuya_uid,
                access_token=token,
                refresh_token=token_res.get("refresh_token", ""),
                expire_at=expire_at,
                auth_source="qr_ticket",
            )
            from sync.device_syncer import sync_tuya_devices
            synced = await sync_tuya_devices(dal=dal, tuya_client=tuya_client, user_id=user_id)
            ticket["status"] = "confirmed"
            ticket["synced_count"] = len(synced)

            return web.json_response({
                "status": "success",
                "message": f"Liên kết thành công tài khoản {tuya_uid}!",
                "user_id": user_id,
                "tuya_uid": tuya_uid,
                "synced_count": len(synced),
                "devices": [{"id": d.get("device_id") or d.get("id"), "name": d.get("device_name") or d.get("name")} for d in synced],
            })
        except Exception as e:
            return web.json_response(
                {"status": "error", "message": f"Lỗi xác nhận: {str(e)}"},
                status=500,
            )

    async def oauth_callback_handler(request: web.Request) -> web.Response:
        """API trao đổi Authorization Code lấy User-level OAuth Token (grant_type=2).

        Payload JSON hoặc Query:
            code (str): Authorization Code nhận từ Tuya Cloud OAuth2 redirect.
            user_id (str): Tài khoản người dùng tương ứng.
        """
        code = None
        user_id = None

        if request.method == "POST":
            try:
                data = await request.json()
                code = data.get("code")
                user_id = data.get("user_id")
            except Exception:
                pass
        else:
            code = request.query.get("code")
            state_val = request.query.get("state", "")
            if state_val:
                user_id = state_val.rsplit("_", 1)[0]
            else:
                user_id = request.query.get("user_id")

        if not code:
            if request.method == "GET":
                error_html = """<!DOCTYPE html>
<html><body style="font-family:sans-serif;text-align:center;padding:50px;background:#0f172a;color:#f8fafc;">
<h2 style="color:#ef4444;">❌ LỖI XÁC THỰC</h2><p>Thiếu tham số 'code' từ máy chủ ủy quyền Tuya.</p>
<a href="/portal" style="color:#38bdf8;text-decoration:none;">Quay lại Web Portal</a></body></html>"""
                return web.Response(text=error_html, content_type="text/html", status=400, charset="utf-8")
            return web.json_response(
                {"status": "error", "message": "Thiếu tham số bắt buộc 'code'."},
                status=400,
            )

        user_id = dal.resolve_user_id(user_id)

        if not tuya_client:
            return web.json_response(
                {"status": "error", "message": "TuyaClient chưa được cấu hình trên máy chủ."},
                status=500,
            )

        try:
            # Trao đổi mã code lấy token người dùng (grant_type=2)
            token_res = await tuya_client.get_token(grant_type=2, code=code)
            access_token = token_res.get("access_token")
            refresh_token = token_res.get("refresh_token")
            expires_in = token_res.get("expire_time", 7200)
            external_uid = token_res.get("uid", f"tuya_uid_{uuid.uuid4().hex[:12]}")

            if not access_token:
                return web.json_response(
                    {"status": "error", "message": "Không nhận được Access Token từ Tuya Cloud.", "detail": token_res},
                    status=400,
                )

            expire_at = datetime.utcnow() + timedelta(seconds=expires_in)

            # Lưu vào CSDL an toàn đã mã hóa AES-256-GCM
            dal.save_user_credential(
                user_id=user_id,
                external_tuya_uid=external_uid,
                access_token=access_token,
                refresh_token=refresh_token or "",
                expire_at=expire_at,
                auth_source="oauth2",
            )

            logger.info(
                f"✅ [TUYA OAUTH] Đã lưu thông tin OAuth2 cho User [{user_id}] (UID: {external_uid}) thành công!"
            )

            # Tự động kích hoạt đồng bộ thiết bị người dùng về CSDL cục bộ
            try:
                from sync.device_syncer import sync_tuya_devices
                import asyncio
                asyncio.create_task(sync_tuya_devices(dal=dal, tuya_client=tuya_client, user_id=user_id))
                logger.info(f"🔄 [TUYA OAUTH] Đã kích hoạt đồng bộ thiết bị ngầm cho User [{user_id}]")
            except Exception as e_sync:
                logger.warning(f"Lỗi kích hoạt sync sau OAuth: {e_sync}")

            # Nếu là yêu cầu GET từ trình duyệt sau khi redirect, trả về trang Webview Success thân thiện
            if request.method == "GET":
                html_success = f"""<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Liên kết Tuya Smart Life Thành Công</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
            color: #f8fafc;
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            margin: 0;
            padding: 20px;
        }}
        .card {{
            background: #1e293b;
            border: 1px solid #334155;
            border-radius: 16px;
            padding: 32px;
            max-width: 480px;
            width: 100%;
            text-align: center;
            box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.5);
        }}
        .icon {{ font-size: 56px; margin-bottom: 12px; }}
        h2 {{ color: #38bdf8; margin: 0 0 8px 0; }}
        p {{ color: #94a3b8; font-size: 14px; line-height: 1.5; margin-bottom: 24px; }}
        .badge {{
            display: inline-block;
            background: #064e3b;
            color: #34d399;
            padding: 6px 16px;
            border-radius: 9999px;
            font-size: 13px;
            font-weight: 600;
            margin-bottom: 16px;
        }}
        .info-box {{
            background: #0f172a;
            border-radius: 8px;
            padding: 16px;
            text-align: left;
            font-size: 13px;
            margin-bottom: 24px;
            border: 1px solid #334155;
        }}
        .info-row {{
            display: flex;
            justify-content: space-between;
            margin-bottom: 8px;
        }}
        .info-row:last-child {{ margin-bottom: 0; }}
        .info-label {{ color: #64748b; }}
        .info-val {{ color: #f1f5f9; font-family: monospace; font-weight: bold; }}
        .btn {{
            display: inline-block;
            background: #2563eb;
            color: white;
            text-decoration: none;
            padding: 12px 28px;
            border-radius: 8px;
            font-weight: 600;
            font-size: 14px;
            transition: background 0.2s;
        }}
        .btn:hover {{ background: #1d4ed8; }}
    </style>
</head>
<body>
    <div class="card">
        <div class="icon">🎉</div>
        <div class="badge">ỦY QUYỀN THÀNH CÔNG</div>
        <h2>Liên Kết Tuya Smart Life</h2>
        <p>Tài khoản Tuya của bạn đã được kết nối thành công với Trợ lý ảo Loa Sunhouse!</p>
        
        <div class="info-box">
            <div class="info-row">
                <span class="info-label">Tài khoản User:</span>
                <span class="info-val">{user_id}</span>
            </div>
            <div class="info-row">
                <span class="info-label">Tuya UID:</span>
                <span class="info-val">{external_uid}</span>
            </div>
            <div class="info-row">
                <span class="info-label">Thời hạn Token:</span>
                <span class="info-val">{expires_in}s (~2 giờ)</span>
            </div>
            <div class="info-row">
                <span class="info-label">Bảo mật lưu trữ:</span>
                <span class="info-val">Mã hóa AES-256-GCM ✅</span>
            </div>
        </div>
        
        <a href="/portal" class="btn">Quay lại Developer Portal</a>
    </div>
</body>
</html>"""
                return web.Response(text=html_success, content_type="text/html", charset="utf-8")

            return web.json_response({
                "status": "success",
                "message": "Liên kết tài khoản Tuya Smart Life thành công!",
                "user_id": user_id,
                "external_tuya_uid": external_uid,
                "expires_in": expires_in,
            })

        except Exception as e:
            logger.error(f"❌ [TUYA OAUTH] Lỗi khi trao đổi OAuth Token: {e}")
            if request.method == "GET":
                error_html = f"""<!DOCTYPE html>
<html><body style="font-family:sans-serif;text-align:center;padding:50px;background:#0f172a;color:#f8fafc;">
<h2 style="color:#ef4444;">❌ LỖI XÁC THỰC OAUTH2</h2><p>{str(e)}</p>
<a href="/portal" style="color:#38bdf8;text-decoration:none;">Quay lại Web Portal</a></body></html>"""
                return web.Response(text=error_html, content_type="text/html", status=500, charset="utf-8")
            return web.json_response(
                {"status": "error", "message": f"Lỗi xác thực OAuth2: {str(e)}"},
                status=500,
            )

    async def link_account_handler(request: web.Request) -> web.Response:
        """API liên kết tài khoản Tuya Smart Life (chế độ TUYA_FEATURE_OAUTH2_CODE).

        Tự động phát hiện hoặc nhận Tuya UID của tài khoản Smart Life đã ghép nối,
        sinh User Credential với auth_source='oauth2' và kích hoạt đồng bộ thiết bị.
        """
        try:
            data = await request.json()
        except Exception:
            data = {}

        user_id = dal.resolve_user_id(data.get("user_id") or data.get("device_id"))
        tuya_uid = data.get("tuya_uid")

        if not tuya_client:
            return web.json_response(
                {"status": "error", "message": "TuyaClient chưa được cấu hình trên máy chủ."},
                status=500,
            )

        try:
            # Lấy token từ Tuya Cloud
            token_res = await tuya_client.get_token(grant_type=1)
            access_token = token_res.get("access_token")
            refresh_token = token_res.get("refresh_token", "")
            expires_in = token_res.get("expire_time", 7200)

            # Nếu không truyền tuya_uid, tự động dò tìm từ tài khoản đã liên kết
            if not tuya_uid:
                try:
                    assoc_devs = await tuya_client.get_associated_user_devices(token=access_token)
                    for d in assoc_devs:
                        if d.get("uid"):
                            tuya_uid = d["uid"]
                            break
                except Exception as e_assoc:
                    logger.warning(f"Lỗi truy vấn associated devices: {e_assoc}")

            if not tuya_uid:
                tuya_uid = token_res.get("uid")

            if not tuya_uid:
                return web.json_response(
                    {
                        "status": "error",
                        "message": "Không tìm thấy tài khoản Smart Life nào được liên kết trên Tuya Cloud. Vui lòng quét mã QR để liên kết tài khoản trước.",
                    },
                    status=400,
                )

            expire_at = datetime.utcnow() + timedelta(seconds=expires_in)

            # Lưu User Credential đã mã hóa AES-256-GCM với auth_source="oauth2"
            dal.save_user_credential(
                user_id=user_id,
                external_tuya_uid=tuya_uid,
                access_token=access_token,
                refresh_token=refresh_token,
                expire_at=expire_at,
                auth_source="oauth2",
            )

            logger.info(
                f"✅ [TUYA OAUTH2 LINK] Đã liên kết tài khoản Smart Life [{tuya_uid}] "
                f"cho User [{user_id}] theo chế độ OAuth2 thành công!"
            )

            # Tự động đồng bộ thiết bị người dùng về CSDL cục bộ
            from sync.device_syncer import sync_tuya_devices
            synced_devices = await sync_tuya_devices(dal=dal, tuya_client=tuya_client, user_id=user_id)

            return web.json_response({
                "status": "success",
                "message": f"Liên kết tài khoản Smart Life ({tuya_uid}) thành công ở chế độ TUYA_FEATURE_OAUTH2_CODE!",
                "user_id": user_id,
                "external_tuya_uid": tuya_uid,
                "auth_source": "oauth2",
                "synced_count": len(synced_devices),
                "devices": [{"id": d.get("device_id") or d.get("id"), "name": d.get("device_name") or d.get("name")} for d in synced_devices],
            })
        except Exception as e_link:
            logger.error(f"❌ [TUYA OAUTH2 LINK] Lỗi khi liên kết tài khoản: {e_link}")
            return web.json_response(
                {"status": "error", "message": f"Lỗi liên kết tài khoản Smart Life: {str(e_link)}"},
                status=500,
            )

    async def unlink_account_handler(request: web.Request) -> web.Response:
        """API Hủy liên kết tài khoản Smart Life (Tuya) khỏi Loa và hệ thống."""
        try:
            data = await request.json()
        except Exception:
            data = {}
        raw_id = data.get("user_id") or request.query.get("user_id")
        user_id = dal.resolve_user_id(raw_id)

        from clients.tuya_sharing_manager import sharing_manager
        result = sharing_manager.unlink_session(user_id=user_id, dal=dal)
        logger.info(f"🔌 [UNLINK ACCOUNT] Đã hủy liên kết tài khoản Tuya cho User [{user_id}]: {result}")
        return web.json_response({
            "status": "success",
            "message": f"Đã hủy liên kết tài khoản Smart Life cho User [{user_id}] thành công.",
            "details": result,
        })

    async def clean_database_handler(request: web.Request) -> web.Response:
        """API làm sạch toàn bộ dữ liệu CSDL test demo (smarthome.db)."""
        result = dal.clean_database(keep_speakers=True)
        logger.info(f"🧹 [CLEAN DB] Đã làm sạch toàn bộ dữ liệu test demo: {result}")
        return web.json_response({
            "status": "success",
            "message": "Đã làm sạch toàn bộ dữ liệu test demo trong CSDL thành công!",
            "details": result,
        })

    return {
        "get_authorize_url": get_authorize_url_handler,
        "create_qr_ticket": create_qr_ticket_handler,
        "get_qr_ticket_status": get_qr_ticket_status_handler,
        "confirm_qr_ticket": confirm_qr_ticket_handler,
        "oauth_callback": oauth_callback_handler,
        "link_account": link_account_handler,
        "unlink_account": unlink_account_handler,
        "clean_database": clean_database_handler,
    }
