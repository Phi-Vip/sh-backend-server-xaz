import asyncio
import time
import unittest
from unittest.mock import MagicMock, AsyncMock

from core.handle.receiveAudioHandle import no_voice_close_connect
from core.handle.textHandler.listenMessageHandler import ListenTextMessageHandler
from core.handle.abortHandle import handleAbortMessage


class TestMusicSilenceTimeoutFreeze(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.conn = MagicMock()
        self.conn.session_id = "test-session-123"
        self.conn.client_have_voice = False
        self.conn.client_is_speaking = False
        self.conn.close_after_chat = False
        self.conn.config = {"close_connection_no_voice_time": 40}
        self.conn.logger = MagicMock()
        self.conn.logger.bind.return_value = MagicMock()
        self.conn.last_activity_time = time.time() * 1000 - 45000  # 45 seconds ago
        self.conn.is_playing_music = False
        self.conn.music_start_time = 0.0

    async def test_silence_timeout_triggers_when_not_playing_music(self):
        """Khi KHÔNG phát nhạc: Sau 45s im lặng, phải kích hoạt chào tạm biệt"""
        self.conn.is_playing_music = False
        
        # Mock startToChat
        with unittest.mock.patch("core.handle.receiveAudioHandle.startToChat", new_callable=AsyncMock) as mock_chat:
            await no_voice_close_connect(self.conn, have_voice=False)
            self.assertTrue(self.conn.close_after_chat)
            mock_chat.assert_called_once()
            print("✅ PASS: Không phát nhạc -> Timeout kích hoạt sau 45s im lặng")

    async def test_silence_timeout_frozen_when_playing_music(self):
        """Khi ĐANG phát nhạc: Sau 45s im lặng, timer PHẢI BỊ ĐÓNG BĂNG, không chào tạm biệt"""
        self.conn.is_playing_music = True
        self.conn.music_start_time = time.time()
        initial_time = self.conn.last_activity_time

        with unittest.mock.patch("core.handle.receiveAudioHandle.startToChat", new_callable=AsyncMock) as mock_chat:
            await no_voice_close_connect(self.conn, have_voice=False)
            # close_after_chat KHÔNG được bật
            self.assertFalse(self.conn.close_after_chat)
            # startToChat KHÔNG được gọi
            mock_chat.assert_not_called()
            # last_activity_time phải được làm mới
            self.assertGreater(self.conn.last_activity_time, initial_time)
            print("✅ PASS: Đang phát nhạc -> Timeout bị đóng băng hoàn toàn")

    async def test_listen_start_unfreezes_timer(self):
        """Khi người dùng bấm BOOT hoặc Wake word detected: Gửi listen start -> hủy đóng băng"""
        self.conn.is_playing_music = True
        self.conn.asr_audio_queue = MagicMock()
        self.conn.asr_audio_queue.empty.return_value = True

        handler = ListenTextMessageHandler()
        msg_json = {"type": "listen", "state": "start", "mode": "manual"}

        await handler.handle(self.conn, msg_json)

        # is_playing_music phải trở về False
        self.assertFalse(self.conn.is_playing_music)
        # client_is_listening phải là True
        self.assertTrue(self.conn.client_is_listening)
        print("✅ PASS: Listen start -> Hủy đóng băng, chuyển sang lắng nghe người dùng")

    async def test_abort_unfreezes_timer(self):
        """Khi nhận tin nhắn abort: Hủy cờ is_playing_music"""
        self.conn.is_playing_music = True
        self.conn.websocket = MagicMock()
        self.conn.websocket.send = AsyncMock()

        await handleAbortMessage(self.conn)

        self.assertFalse(self.conn.is_playing_music)
        print("✅ PASS: Abort message -> Hủy cờ is_playing_music")

    async def test_unified_tool_handler_music_flags(self):
        """Khi tool play/stop/pause/resume được gọi: Cờ is_playing_music cập nhật chính xác"""
        from core.providers.tools.unified_tool_handler import UnifiedToolHandler
        from plugins_func.register import Action, ActionResponse

        handler = UnifiedToolHandler(self.conn)
        handler.tool_manager = MagicMock()
        
        # 1. Gọi play_online_music -> is_playing_music = True
        handler.tool_manager.execute_tool = AsyncMock(return_value=ActionResponse(action=Action.RESPONSE, response="OK"))
        with unittest.mock.patch("core.providers.tools.unified_tool_handler.send_display_message", new_callable=AsyncMock):
            await handler.handle_llm_function_call(self.conn, {"name": "play_online_music", "arguments": {}})
            self.assertTrue(self.conn.is_playing_music)
            self.assertGreater(self.conn.music_start_time, 0)
            print("✅ PASS: Tool play_online_music -> is_playing_music = True")

            # 2. Gọi pause_music -> is_playing_music = False
            await handler.handle_llm_function_call(self.conn, {"name": "pause_music", "arguments": {}})
            self.assertFalse(self.conn.is_playing_music)
            print("✅ PASS: Tool pause_music -> is_playing_music = False")

            # 3. Gọi resume_music -> is_playing_music = True
            await handler.handle_llm_function_call(self.conn, {"name": "resume_music", "arguments": {}})
            self.assertTrue(self.conn.is_playing_music)
            print("✅ PASS: Tool resume_music -> is_playing_music = True")

            # 4. Gọi stop_music -> is_playing_music = False
            await handler.handle_llm_function_call(self.conn, {"name": "stop_music", "arguments": {}})
            self.assertFalse(self.conn.is_playing_music)
            print("✅ PASS: Tool stop_music -> is_playing_music = False")

            # 5. Gọi self.radio.play -> is_playing_music = True
            await handler.handle_llm_function_call(self.conn, {"name": "self.radio.play", "arguments": {}})
            self.assertTrue(self.conn.is_playing_music)
            print("✅ PASS: Tool self.radio.play -> is_playing_music = True (Radio đóng băng timeout)")

            # 6. Gọi switch_radio -> is_playing_music = True
            await handler.handle_llm_function_call(self.conn, {"name": "switch_radio", "arguments": {}})
            self.assertTrue(self.conn.is_playing_music)
            print("✅ PASS: Tool switch_radio -> is_playing_music = True")

            # 7. Gọi self.radio.stop -> is_playing_music = False
            await handler.handle_llm_function_call(self.conn, {"name": "self.radio.stop", "arguments": {}})
            self.assertFalse(self.conn.is_playing_music)
            print("✅ PASS: Tool self.radio.stop -> is_playing_music = False")

    async def test_listen_detect_unfreezes_timer(self):
        """Khi WakeNet phát hiện từ khóa (listen detect): Cờ is_playing_music phải được hủy để nghe người dùng"""
        self.conn.is_playing_music = True
        self.conn.asr_audio_queue = MagicMock()
        self.conn.asr_audio_queue.empty.return_value = True
        self.conn.websocket = MagicMock()
        self.conn.websocket.send = AsyncMock()

        handler = ListenTextMessageHandler()
        msg_json = {"type": "listen", "state": "detect", "text": "Alexa"}

        await handler.handle(self.conn, msg_json)

        # is_playing_music phải trở về False
        self.assertFalse(self.conn.is_playing_music)
        print("✅ PASS: Listen detect -> Hủy đóng băng phát nhạc/radio, sẵn sàng lắng nghe")


if __name__ == "__main__":
    unittest.main()
