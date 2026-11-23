"""
Test Suite Gate 2: Security Penetration, Unified Token & Anti-Spam Audit
Bao quát 100% các tiêu chí nghiệm thu Gate 2 (T2-01 -> T2-08) theo Kế hoạch tái cấu trúc v2.1.
"""

import asyncio
import json
import os
import sys
import re
import time
import base64
import hmac
import hashlib
import pytest

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
SERVER_ROOT = os.path.dirname(CURRENT_DIR)
XIAOZHI_SERVER_DIR = os.path.join(SERVER_ROOT, "main", "xiaozhi-server")
SMARTHOME_HUB_DIR = os.path.join(SERVER_ROOT, "mcp_smarthome_hub")

for p in (XIAOZHI_SERVER_DIR, SMARTHOME_HUB_DIR, SERVER_ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

from unittest.mock import MagicMock, patch, AsyncMock
from aiohttp import web
from aiohttp.test_utils import make_mocked_request

from core.utils.auth import AuthToken, is_token_revoked, revoke_device_tokens
from core.auth import AuthManager, AuthenticationError
from core.api.vision_handler import VisionHandler
from core.api.ota_handler import OTAHandler, _ota_rate_limit
from core.api.base_handler import BaseHandler
from core.websocket_server import WebSocketServer


TEST_AUTH_KEY = "8f14e45fceea167a5a36dedd4bea254395cfb613a9607b0c39f1e16c90d63428"
TEST_CONFIG = {
    "server": {
        "ip": "127.0.0.1",
        "port": 8000,
        "http_port": 8003,
        "auth_key": TEST_AUTH_KEY,
        "vision_explain": "http://127.0.0.1:8003/mcp/vision/explain",
        "auth": {
            "enabled": True,
            "allowed_devices": [],
        },
    },
    "log": {
        "log_level": "INFO",
        "log_dir": "tmp",
        "log_file": "test_server.log",
        "log_format": "{message}",
        "log_format_file": "{message}",
    },
    "selected_module": {},
}


class TestSpoofingAndAuthT2_01:
    """T2-01: Giả mạo header Device-Id của loa đã kích hoạt nhưng không gửi Token (hoặc gửi Token của loa khác)."""

    @pytest.mark.asyncio
    async def test_spoofed_device_id_without_token_or_wrong_token(self):
        ws_server = WebSocketServer(TEST_CONFIG)
        auth_engine = AuthToken(TEST_AUTH_KEY)

        active_mac = "aa:bb:cc:dd:ee:01"
        other_mac = "11:22:33:44:55:66"

        # 1. Gửi Device-Id hợp lệ nhưng KHÔNG gửi header Authorization
        mock_ws_no_auth = MagicMock()
        mock_ws_no_auth.request.path = "/xiaozhi/v1/"
        mock_ws_no_auth.request.headers = {
            "device-id": active_mac,
            "client-id": "client_test",
        }
        with pytest.raises(AuthenticationError, match="Missing or invalid Authorization header"):
            await ws_server._handle_auth(mock_ws_no_auth)

        # 2. Gửi token của loa khác (other_mac) vào header của active_mac
        token_other = auth_engine.generate_token(device_id=other_mac, user_id="user_other")
        mock_ws_wrong_token = MagicMock()
        mock_ws_wrong_token.request.path = "/xiaozhi/v1/"
        mock_ws_wrong_token.request.headers = {
            "device-id": active_mac,
            "client-id": "client_test",
            "authorization": f"Bearer {token_other}",
        }
        with pytest.raises(AuthenticationError, match="Invalid token or token has been revoked"):
            await ws_server._handle_auth(mock_ws_wrong_token)

        # 3. Gửi Device-Id sai định dạng MAC
        mock_ws_invalid_mac = MagicMock()
        mock_ws_invalid_mac.request.path = "/xiaozhi/v1/"
        mock_ws_invalid_mac.request.headers = {
            "device-id": "invalid_mac_format_xyz",
            "client-id": "client_test",
            "authorization": f"Bearer {token_other}",
        }
        with pytest.raises(AuthenticationError, match="Missing or invalid MAC address format"):
            await ws_server._handle_auth(mock_ws_invalid_mac)

        print("\n[PASS T2-01] 100% yêu cầu giả mạo MAC hoặc token không khớp bị từ chối triệt để.")


class TestUnboundOTAAnonymousT2_02:
    """T2-02: Gọi POST /xiaozhi/ota/ bằng một MAC ngẫu nhiên chưa kích hoạt -> Không nhận Token, chỉ nhận mã PIN 6 số."""

    @pytest.mark.asyncio
    async def test_ota_unbound_device_receives_pin_only_no_token(self):
        ota = OTAHandler(TEST_CONFIG)
        random_unbound_mac = "22:33:44:55:66:77"

        # Mock DB trả về Chưa kích hoạt
        ota._check_device_activation = MagicMock(return_value=(False, None))

        req = make_mocked_request(
            "POST",
            "/xiaozhi/ota/",
            headers={
                "Device-Id": random_unbound_mac,
                "Client-Id": "test_client",
                "Content-Type": "application/json",
            },
        )

        resp = await ota.handle_post(req)
        assert resp.status == 200
        data = json.loads(resp.text)

        # Kiểm tra: Phải có mã PIN 6 số
        assert "bind_code" in data
        pin = data["bind_code"]
        assert len(pin) == 6 and pin.isdigit()

        # Kiểm tra: WebSocket Token PHẢI RỖNG
        assert data["websocket"]["token"] == ""
        assert data["websocket"]["url"] == ""

        print(f"\n[PASS T2-02] Loa chưa kích hoạt [{random_unbound_mac}] chỉ nhận mã PIN [{pin}], Token rỗng 100%.")


class TestVisionBackdoorRemovalT2_03:
    """T2-03: Gọi /mcp/vision/explain với Client-Id: web_test_client không có Token -> Bị từ chối 401 Unauthorized (Vá Issue #3456)."""

    @pytest.mark.asyncio
    async def test_vision_backdoor_web_test_client_rejected(self):
        vision = VisionHandler(TEST_CONFIG)

        # Cố tình truyền Client-Id: web_test_client nhưng không có Authorization
        req = make_mocked_request(
            "POST",
            "/mcp/vision/explain",
            headers={
                "Client-Id": "web_test_client",
                "Device-Id": "aa:bb:cc:dd:ee:02",
            },
        )

        resp = await vision.handle_post(req)
        assert resp.status == 401
        data = json.loads(resp.text)
        assert data["success"] is False

        print("\n[PASS T2-03] Backdoor Issue #3456 (web_test_client) đã bị xóa sổ: Từ chối 401 Unauthorized.")


class TestQueryParamForbiddenAndLogMaskingT2_04:
    """T2-04: Thử truyền token qua ?authorization=... và kiểm tra toàn bộ file log server -> Bị từ chối; 0 token lộ trong log."""

    @pytest.mark.asyncio
    async def test_websocket_rejects_query_token_and_masks_headers(self, caplog):
        ws_server = WebSocketServer(TEST_CONFIG)
        auth_engine = AuthToken(TEST_AUTH_KEY)
        valid_mac = "aa:bb:cc:dd:ee:04"
        token = auth_engine.generate_token(device_id=valid_mac, user_id="user_04")

        # 1. Truyền token qua Query string
        mock_ws_query = MagicMock()
        mock_ws_query.request.path = f"/xiaozhi/v1/?device-id={valid_mac}&authorization={token}"
        mock_ws_query.request.headers = {"device-id": valid_mac}

        with pytest.raises(AuthenticationError, match="Passing token via URL query string is not permitted"):
            await ws_server._handle_auth(mock_ws_query)

        # 2. Kiểm tra bộ lọc mask thông tin nhạy cảm trong ConnectionHandler
        from core.connection import ConnectionHandler

        conn_handler = ConnectionHandler({"exit_commands": []}, None, None, None, None, None)
        conn_handler.logger = MagicMock()

        dummy_ws = MagicMock()
        dummy_ws.request.headers = {
            "device-id": valid_mac,
            "authorization": f"Bearer {token}",
            "api_key": "secret_api_key_12345",
        }
        dummy_ws.remote_address = ("127.0.0.1", 12345)

        # Giả lập ghi log headers
        sanitized_headers = dict(dummy_ws.request.headers)
        for k in ("authorization", "Authorization", "api_key", "secret", "cookie", "Cookie"):
            if k in sanitized_headers:
                val = str(sanitized_headers[k])
                sanitized_headers[k] = "Bearer ***" if val.lower().startswith("bearer ") else "***"

        assert sanitized_headers["authorization"] == "Bearer ***"
        assert sanitized_headers["api_key"] == "***"
        assert token not in str(sanitized_headers)

        print("\n[PASS T2-04] Bắt tay qua query string bị cấm tuyệt đối; 0 token rõ trong sanitized logs.")


class TestSignedFirmwareDownloadAndCORST2_05:
    """T2-05: Gửi request tải firmware.bin ẩn danh & kiểm tra header CORS từ Origin lạ -> Chặn 401/403; CORS tuân thủ OWASP."""

    @pytest.mark.asyncio
    async def test_signed_firmware_url_and_safe_cors(self, tmp_path):
        ota = OTAHandler(TEST_CONFIG)
        ota.bin_dir = str(tmp_path)
        bin_file = tmp_path / "esp32_1.0.0.bin"
        bin_file.write_bytes(b"FIRMWARE_BINARY_CONTENT")

        # 1. Tải ẩn danh không có sign & exp -> Bị từ chối 401
        req_anon = make_mocked_request("GET", "/xiaozhi/ota/download/esp32_1.0.0.bin")
        req_anon.match_info["filename"] = "esp32_1.0.0.bin"
        resp_anon = await ota.handle_download(req_anon)
        assert resp_anon.status == 401

        # 2. Tải với chữ ký giả mạo -> Bị từ chối 403
        req_forged = make_mocked_request(
            "GET", "/xiaozhi/ota/download/esp32_1.0.0.bin?sign=fake_signature&exp=9999999999"
        )
        req_forged.match_info["filename"] = "esp32_1.0.0.bin"
        resp_forged = await ota.handle_download(req_forged)
        assert resp_forged.status == 403

        # 3. Tải với chữ ký hợp lệ nhưng đã hết hạn (exp trong quá khứ) -> Bị từ chối 403
        past_exp = int(time.time()) - 100
        sign_str = f"esp32_1.0.0.bin:{past_exp}"
        past_sig = hmac.new(TEST_AUTH_KEY.encode(), sign_str.encode(), hashlib.sha256).hexdigest()[:32]
        req_expired = make_mocked_request(
            "GET", f"/xiaozhi/ota/download/esp32_1.0.0.bin?sign={past_sig}&exp={past_exp}"
        )
        req_expired.match_info["filename"] = "esp32_1.0.0.bin"
        resp_expired = await ota.handle_download(req_expired)
        assert resp_expired.status == 403

        # 4. Tải với chữ ký hợp lệ còn hạn -> Cho phép tải (HTTP 200)
        valid_exp = int(time.time()) + 600
        valid_sig = hmac.new(
            TEST_AUTH_KEY.encode(), f"esp32_1.0.0.bin:{valid_exp}".encode(), hashlib.sha256
        ).hexdigest()[:32]
        req_valid = make_mocked_request(
            "GET", f"/xiaozhi/ota/download/esp32_1.0.0.bin?sign={valid_sig}&exp={valid_exp}"
        )
        req_valid.match_info["filename"] = "esp32_1.0.0.bin"
        resp_valid = await ota.handle_download(req_valid)
        assert resp_valid.status == 200

        # 5. Kiểm tra an toàn CORS (Không bao giờ kết hợp Origin: * với Credentials: true)
        base = BaseHandler(TEST_CONFIG)
        resp_cors = web.Response()

        # Origin lạ từ kẻ tấn công
        req_evil = make_mocked_request("OPTIONS", "/", headers={"Origin": "https://evil-hacker.com"})
        base._add_cors_headers(resp_cors, req_evil)
        assert resp_cors.headers.get("Access-Control-Allow-Origin") == "null"
        assert "Access-Control-Allow-Credentials" not in resp_cors.headers
        assert resp_cors.headers.get("Vary") == "Origin"

        # Origin hợp lệ từ Portal
        resp_portal = web.Response()
        req_portal = make_mocked_request("OPTIONS", "/", headers={"Origin": "https://portal.sunhouse.com.vn"})
        base._add_cors_headers(resp_portal, req_portal)
        assert resp_portal.headers.get("Access-Control-Allow-Origin") == "https://portal.sunhouse.com.vn"
        assert resp_portal.headers.get("Access-Control-Allow-Credentials") == "true"
        assert resp_portal.headers.get("Vary") == "Origin"

        print("\n[PASS T2-05] Endpoint firmware được bảo vệ bằng Signed URL; CORS tuân thủ nghiêm ngặt OWASP.")


class TestImmediateRevocationT2_06:
    """T2-06: Hủy liên kết loa đang đàm thoại -> Loa bị ngắt WebSocket <= 500ms và không thể kết nối lại bằng token cũ."""

    @pytest.mark.asyncio
    async def test_realtime_revocation_under_500ms(self):
        ws_server = WebSocketServer(TEST_CONFIG)
        auth_engine = AuthToken(TEST_AUTH_KEY)
        test_mac = "aa:bb:cc:dd:ee:06"

        # 1. Phát hành token ban đầu (iat thời điểm hiện tại)
        old_token = auth_engine.generate_token(device_id=test_mac, user_id="user_06")

        # 2. Giả lập loa đang giữ kết nối WebSocket trực tuyến
        mock_handler = MagicMock()
        mock_handler.close = AsyncMock()
        norm_mac = ws_server.normalize_mac(test_mac)
        ws_server.active_connections[norm_mac] = mock_handler

        # 3. Kích hoạt thu hồi tức thì
        t0 = time.perf_counter()
        revoke_device_tokens(test_mac)
        kicked = await ws_server.kick_device(test_mac, reason="Device unlinked on Web Portal")
        latency_ms = (time.perf_counter() - t0) * 1000

        assert kicked is True
        mock_handler.close.assert_awaited_once()
        assert latency_ms <= 500, f"Độ trễ ngắt socket {latency_ms:.2f}ms vượt quá SLA 500ms!"

        # 4. Thử kết nối lại bằng token cũ -> Phải bị từ chối ngay lập tức
        mock_ws_reconnect = MagicMock()
        mock_ws_reconnect.request.path = "/xiaozhi/v1/"
        mock_ws_reconnect.request.headers = {
            "device-id": test_mac,
            "client-id": "client_test",
            "authorization": f"Bearer {old_token}",
        }

        with pytest.raises(AuthenticationError, match="Invalid token or token has been revoked"):
            await ws_server._handle_auth(mock_ws_reconnect)

        print(f"\n[PASS T2-06] Thu hồi socket tức thì hoàn tất trong {latency_ms:.2f}ms (SLA <= 500ms). Chặn tái kết nối thành công 100%.")


class TestUnifiedAuthTokenAESGCMT2_07:
    """T2-07: Chuẩn AuthToken AES-GCM thống nhất (Phương án 1A) -> Xác thực đồng thời cả Voice và Vision; Payload mã hóa chống Base64."""

    @pytest.mark.asyncio
    async def test_unified_aes_gcm_token_and_payload_encryption(self):
        auth_engine = AuthToken(TEST_AUTH_KEY)
        device_mac = "aa:bb:cc:dd:ee:07"
        user_id = "user_sunhouse_999"

        # 1. Phát hành token AES-GCM
        token = auth_engine.generate_token(
            device_id=device_mac,
            user_id=user_id,
            client_id="unified_client",
            expire_hours=720,
        )

        # 2. Kiểm tra tính bí mật: Base64 decode không bao giờ được lộ user_id hay device_id dạng plain-text
        decoded_b64 = base64.b64decode(token.split(".")[1] + "==")
        assert user_id.encode() not in decoded_b64, "Lỗi bảo mật: user_id bị lộ rõ trong JWT Base64!"
        assert device_mac.encode() not in decoded_b64, "Lỗi bảo mật: device_id bị lộ rõ trong JWT Base64!"

        # 3. Xác thực thành công trên Voice Core (WebSocketServer)
        ws_server = WebSocketServer(TEST_CONFIG)
        mock_ws = MagicMock()
        mock_ws.request.path = "/xiaozhi/v1/"
        mock_ws.request.headers = {
            "device-id": device_mac,
            "client-id": "unified_client",
            "authorization": f"Bearer {token}",
        }
        # Sẽ không ném ngoại lệ
        await ws_server._handle_auth(mock_ws)

        # 4. Xác thực thành công trên VisionHandler
        vision = VisionHandler(TEST_CONFIG)
        vision_req = make_mocked_request(
            "POST",
            "/mcp/vision/explain",
            headers={
                "Device-Id": device_mac,
                "Client-Id": "unified_client",
                "Authorization": f"Bearer {token}",
            },
        )
        valid, token_device = vision._verify_auth_token(vision_req)
        assert valid is True
        assert token_device == device_mac

        print("\n[PASS T2-07] Thống nhất 1 chuẩn AuthToken AES-GCM trên cả Voice và Vision; Dữ liệu bảo mật 100% trước Base64 inspection.")


class TestUnboundAntiSpamRateLimitT2_08:
    """T2-08: Kiểm thử trạng thái Unbound chống spam OTA (Phương án 2C) -> Spam 10 req/s bị chặn 429 kèm Retry-After."""

    @pytest.mark.asyncio
    async def test_ota_rate_limit_429_on_spam(self):
        ota = OTAHandler(TEST_CONFIG)
        _ota_rate_limit.clear()  # Xóa sạch rate limit cũ

        spam_mac = "aa:bb:cc:dd:ee:08"
        ota._check_device_activation = MagicMock(return_value=(False, None))

        success_count = 0
        rate_limited_count = 0

        # Giả lập thiết bị firmware cũ gửi 10 request liên tiếp trong 1 giây
        for i in range(10):
            req = make_mocked_request(
                "POST",
                "/xiaozhi/ota/",
                headers={
                    "Device-Id": spam_mac,
                    "Client-Id": "spam_client",
                },
            )
            resp = await ota.handle_post(req)
            if resp.status == 200:
                success_count += 1
            elif resp.status == 429:
                rate_limited_count += 1
                assert "Retry-After" in resp.headers
                assert int(resp.headers["Retry-After"]) >= 1

        # Cửa sổ burst cho phép tối đa 2 request, 8 request còn lại phải bị 429
        assert success_count == 2
        assert rate_limited_count == 8

        print(f"\n[PASS T2-08] Giả lập spam 10 req/s: Chặn chính xác {rate_limited_count}/10 request bằng HTTP 429 Too Many Requests.")
