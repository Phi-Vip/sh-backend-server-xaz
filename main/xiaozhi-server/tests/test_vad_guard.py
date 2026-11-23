"""
Unit test kiểm tra cơ chế lọc chống kích hoạt ảo giác VAD và bảo vệ ASR
- Bảo đảm loại bỏ các xung kích / dội loa ngắn (< 4 frames ~ 128ms)
- Bảo toàn 100% các câu nói thật dù ngắn ("OK", "Đúng") (>= 4 frames)
"""

import unittest
from unittest.mock import MagicMock, AsyncMock
from collections import deque
import asyncio
import time
import os
import sys

server_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path = [server_root] + [p for p in sys.path if os.path.abspath(p) != os.path.abspath(os.path.dirname(__file__))]

from core.connection import ConnectionHandler
from core.providers.asr.base import ASRProviderBase
from core.providers.vad.silero import VADProvider


class DummyVAD:
    silence_threshold_ms = 800


class DummyASR(ASRProviderBase):
    def __init__(self):
        super().__init__()
        self.interface_type = MagicMock()
        self.interface_type.STREAM = "stream"
        self.interface_type != "stream"
        self.handle_voice_stop = AsyncMock()

    async def speech_to_text(self, opus_data, session_id):
        return "dummy_text"


class TestVADGuard(unittest.TestCase):
    def setUp(self):
        self.conn = MagicMock()
        self.conn.client_listen_mode = "auto"
        self.conn.asr = DummyASR()
        self.conn.vad = DummyVAD()
        self.conn.asr_audio = []
        self.conn.client_voice_stop = True
        self.conn.listen_start_time = time.monotonic()
        self.conn.speech_frames_count = 0
        self.conn.reset_audio_states = MagicMock()

    def test_short_burst_under_8_frames_dropped(self):
        """Tiếng tặc lưỡi, chép miệng hoặc xung cơ học chỉ có 5 frames (< 8 frames) phải bị loại bỏ"""
        self.conn.speech_frames_count = 5
        self.conn.client_have_voice = True
        # Giả lập buffer 1.0s (32000 bytes) gồm 200ms tặc lưỡi + 800ms im lặng (thực tế 0.20s < 0.25s)
        self.conn.asr_audio = [b"\x00" * 3200 for _ in range(10)]
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(
                self.conn.asr.receive_audio(self.conn, b"\x00" * 3200, False)
            )
        finally:
            loop.close()

        # Phải gọi reset_audio_states và KHÔNG gọi handle_voice_stop
        self.conn.reset_audio_states.assert_called_once()
        self.conn.asr.handle_voice_stop.assert_not_called()

    def test_legitimate_speech_over_8_frames_accepted(self):
        """Câu nói thật như 'OK', 'Đúng', 'Có' có >= 8 frames (vd: 12 frames ~ 384ms) phải được gửi tới ASR"""
        self.conn.speech_frames_count = 12
        self.conn.client_have_voice = True
        # Giả lập buffer 1.3s (41600 bytes) gồm 500ms nói thật + 800ms im lặng (thực tế 0.50s >= 0.25s)
        self.conn.asr_audio = [b"\x00" * 3200 for _ in range(13)]
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(
                self.conn.asr.receive_audio(self.conn, b"\x00" * 3200, False)
            )
        finally:
            loop.close()

        # Phải gọi handle_voice_stop để gửi lên STT
        self.conn.asr.handle_voice_stop.assert_called_once()

    def test_silero_vad_stops_or_ignores_properly(self):
        """Silero VAD phải kích hoạt VAD IGNORE khi speech_frames < 8 và VAD STOP khi speech_frames >= 8"""
        vad = VADProvider({
            "model_dir": os.path.join(server_root, "models", "snakers4_silero-vad"),
            "threshold": "0.5",
            "threshold_low": "0.2",
            "min_silence_duration_ms": "800",
        })

        class SileroTestConn:
            def __init__(self):
                self.client_listen_mode = "auto"
                self.client_audio_buffer = bytearray()
                self.client_voice_window = deque(maxlen=5)
                self.last_is_voice = False
                self.client_have_voice = True
                self.client_voice_stop = False
                self.speech_frames_count = 5  # 5 frames tiếng nói (< 8 frames)
                self.vad_last_voice_time = (time.time() - 1.0) * 1000  # Đã im lặng 1000ms > 800ms
                self.reset_called = False

            def reset_audio_states(self):
                self.reset_called = True
                self.client_have_voice = False
                self.client_voice_stop = False

        conn = SileroTestConn()

        # Gửi 1 frame im lặng (zero bytes)
        silence_frame = b"\x00" * 1024
        vad.is_vad(conn, silence_frame)

        # Vì speech_frames_count = 5 < 8, conn.reset_audio_states phải được gọi, client_voice_stop = False
        self.assertTrue(conn.reset_called)
        self.assertFalse(conn.client_voice_stop)


if __name__ == "__main__":
    unittest.main()
