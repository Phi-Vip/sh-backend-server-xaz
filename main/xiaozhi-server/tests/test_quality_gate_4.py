# -*- coding: utf-8 -*-
"""BÀI TEST QUALITY GATE 4: ĐỒNG BỘ & CHẶN LUỒNG AN NINH VOICE SERVER (SAFETY NET & REAL-TIME KICK)
Kiểm tra:
1. Tra cứu CSDL smarthome.db xác thực quyền sở hữu thiết bị khi WebSocket kết nối.
2. Kích hoạt cờ need_bind = True đối với thiết bị chưa kích hoạt hoặc đã bị xóa.
3. Cơ chế Real-time Kick: Đóng ngay WebSocket khi nhận tín hiệu từ Web Portal.
4. Thông điệp cảnh báo tiếng Việt chuẩn thương mại Sunhouse.
"""

import os
import sys
import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

# Thêm đường dẫn core vào sys.path
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from core.websocket_server import WebSocketServer
from core.http_server import SimpleHttpServer
from core.handle.receiveAudioHandle import check_bind_device


class TestQualityGate4(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.mock_config = {
            "server": {
                "ip": "127.0.0.1",
                "port": 8000,
                "http_port": 8003,
                "auth_key": "test_auth_key_12345",
                "auth": {"enabled": False},
            },
            "selected_module": {},
            "read_config_from_api": False,
            "log": {"log_level": "INFO"},
        }

    async def test_01_mac_normalization(self):
        """Kiểm tra hàm chuẩn hóa MAC address."""
        self.assertEqual(WebSocketServer.normalize_mac("68-EE-8F-4D-87-1C"), "68:ee:8f:4d:87:1c")
        self.assertEqual(WebSocketServer.normalize_mac("68:ee:8f:4d:87:1c"), "68:ee:8f:4d:87:1c")
        self.assertEqual(WebSocketServer.normalize_mac(""), "")

    async def test_02_realtime_kick_in_websocket_server(self):
        """Kiểm tra cơ chế Real-time Kick ngắt kết nối WebSocket của thiết bị đang hoạt động."""
        with patch("core.websocket_server.initialize_modules") as mock_init:
            mock_init.return_value = {}
            server = WebSocketServer(self.mock_config)

        test_mac = "68:ee:8f:4d:87:1c"
        mock_handler = MagicMock()
        mock_handler.close = AsyncMock()
        server.active_connections[test_mac] = mock_handler

        # 1. Kick thiết bị đang online
        result = await server.kick_device(test_mac, reason="Test Unlink")
        self.assertTrue(result)
        mock_handler.close.assert_awaited_once_with(code=4001, reason="Test Unlink")

        # 2. Kick thiết bị offline
        result_offline = await server.kick_device("11:22:33:44:55:66", reason="Not found")
        self.assertFalse(result_offline)

    async def test_03_http_kick_endpoint_handler(self):
        """Kiểm tra HTTP API /api/device/kick xử lý JSON và gọi sang ws_server."""
        mock_ws_server = MagicMock()
        mock_ws_server.kick_device = AsyncMock(return_value=True)

        http_server = SimpleHttpServer(self.mock_config, ws_server=mock_ws_server)

        # Giả lập request aiohttp
        mock_request = MagicMock()
        mock_request.json = AsyncMock(return_value={"device_id": "68:ee:8f:4d:87:1c", "reason": "Portal Delete"})

        response = await http_server.kick_device_handler(mock_request)
        self.assertEqual(response.status, 200)

        mock_ws_server.kick_device.assert_awaited_once_with("68:ee:8f:4d:87:1c", reason="Portal Delete")

    async def test_04_vietnamese_bind_prompt_in_receive_audio(self):
        """Kiểm tra hàm check_bind_device phát câu nhắc tiếng Việt khi Loa chưa kích hoạt."""
        mock_conn = MagicMock()
        mock_conn.bind_code = None
        mock_conn.session_id = "test_session_id"
        mock_conn.tts = MagicMock()
        mock_conn.tts.tts_audio_queue = MagicMock()

        with patch("core.handle.receiveAudioHandle.send_stt_message", new_callable=AsyncMock) as mock_stt:
            await check_bind_device(mock_conn)

            # Phải gọi send_stt_message với câu tiếng Việt
            mock_stt.assert_awaited_once()
            call_text = mock_stt.call_args[0][1]
            self.assertIn("Thiết bị chưa được kích hoạt", call_text)
            self.assertIn("bảng điều khiển", call_text)

    async def test_05_safety_net_database_check(self):
        """Kiểm tra logic _is_speaker_active_in_db phát hiện đúng Loa trong CSDL."""
        from core.connection import ConnectionHandler

        # Tạo một dummy instance để test phương thức
        dummy_conn = object.__new__(ConnectionHandler)
        dummy_conn.logger = MagicMock()

        # Kiểm tra với Loa thực tế trong smarthome.db (68:ee:8f:4d:87:1c đã được lưu từ Giai đoạn 2)
        is_active = ConnectionHandler._is_speaker_active_in_db(dummy_conn, "68:ee:8f:4d:87:1c")
        self.assertTrue(is_active, "Loa đã đăng ký phải trả về True")

        # Kiểm tra với Loa giả mạo (chưa từng đăng ký)
        is_fake_active = ConnectionHandler._is_speaker_active_in_db(dummy_conn, "ff:ff:ff:ff:ff:ff")
        self.assertFalse(is_fake_active, "Loa chưa đăng ký phải trả về False")


if __name__ == "__main__":
    unittest.main()
