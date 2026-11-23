import os
import uuid
import time
import asyncio
from datetime import datetime
from typing import Callable, Any, Optional

import secrets
import edge_tts
from edge_tts.drm import DRM
from config.logger import setup_logging
from core.providers.tts.base import TTSProviderBase
from core.providers.tts.dto.dto import SentenceType
from core.utils.tts import MarkdownCleaner
from core.utils.util import mp3_bytes_to_pcm_stream_fast

TAG = __name__
logger = setup_logging()

# Giữ MUID phiên ổn định cho Microsoft EdgeTTS nhằm định danh phiên hợp lệ
_SESSION_MUID: Optional[str] = None

# Timestamp kết thúc lần tổng hợp EdgeTTS gần nhất (dùng cho Safety Pacing Cooldown >= 0.8s)
_LAST_EDGETTS_FINISH_TIME: float = 0.0


def get_session_muid() -> str:
    global _SESSION_MUID
    if not _SESSION_MUID:
        _SESSION_MUID = secrets.token_hex(16).upper()
    return _SESSION_MUID


def refresh_session_muid() -> str:
    global _SESSION_MUID
    _SESSION_MUID = secrets.token_hex(16).upper()
    return _SESSION_MUID


# Ghi đè hàm generate_muid của thư viện edge_tts bằng MUID phiên bền vững
DRM.generate_muid = staticmethod(get_session_muid)


class TTSProvider(TTSProviderBase):
    TTS_PARAM_CONFIG = [
        ("ttsVolume", "volume", 0, 100, 50, int),
        ("ttsRate", "speech_rate", -100, 100, 0, int),
        ("ttsPitch", "pitch_rate", -100, 100, 0, int),
    ]

    def __init__(self, config, delete_audio_file):
        super().__init__(config, delete_audio_file)
        if config.get("private_voice"):
            self.voice = config.get("private_voice")
        else:
            self.voice = config.get("voice", "vi-VN-HoaiMyNeural")
        if not self.voice:
            self.voice = "vi-VN-HoaiMyNeural"

        self.audio_file_type = config.get("format", "mp3")
        self.output_file = config.get("output_dir", "tmp/")

        volume = config.get("volume", 50)
        try:
            self.volume = int(volume) if volume is not None else 50
        except (ValueError, TypeError):
            self.volume = 50

        speech_rate = config.get("rate", 0)
        try:
            self.speech_rate = int(speech_rate) if speech_rate is not None else 0
        except (ValueError, TypeError):
            self.speech_rate = 0

        pitch_rate = config.get("pitch", 0)
        try:
            self.pitch_rate = int(pitch_rate) if pitch_rate is not None else 0
        except (ValueError, TypeError):
            self.pitch_rate = 0

        # Áp dụng phần trăm điều chỉnh nếu có từ cấu hình
        self._apply_percentage_params(config)
        self._update_edge_params()

        # Cấu hình ngắt câu tối ưu hóa riêng cho EdgeTTS:
        # CHỈ ngắt ở dấu kết thúc câu thực sự (chấm, hỏi, than, chấm phẩy, xuống dòng).
        # TUYỆT ĐỐI không ngắt ở dấu phẩy để tránh chia vụn câu thành nhiều kết nối dồn dập
        # gây kích hoạt Anti-Spam / Rate-Limiter (ws.close_code: 1000) của Microsoft Cloud.
        self.punctuations = (
            "。",
            ".",
            "？",
            "?",
            "！",
            "!",
            "；",
            ";",
            "\n",
        )
        self.first_sentence_punctuations = (
            "。",
            ".",
            "？",
            "?",
            "！",
            "!",
            "；",
            ";",
            "\n",
        )

    def _update_edge_params(self):
        """Chuẩn hóa tham số phát cho SSML EdgeTTS"""
        self.edge_rate = f"{self.speech_rate:+}%"
        self.edge_pitch = f"{self.pitch_rate:+}Hz"

        # Chuẩn hóa âm lượng SSML: mức mặc định 50 (hoặc 0) là "+0%"
        if self.volume in (0, 50):
            self.edge_volume = "+0%"
        elif self.volume > 50:
            self.edge_volume = f"+{self.volume - 50}%"
        else:
            self.edge_volume = f"-{50 - self.volume}%"

    def _is_aborted(self) -> bool:
        """Kiểm tra tín hiệu ngắt lời (barge-in / client_abort) từ client hoặc sự kiện dừng kết nối"""
        conn = getattr(self, "conn", None)
        if conn:
            if getattr(conn, "client_abort", False):
                return True
            stop_event = getattr(conn, "stop_event", None)
            if stop_event and stop_event.is_set():
                return True
        return False

    def generate_filename(self, extension=".mp3"):
        return os.path.join(
            self.output_file,
            f"tts-{datetime.now().date()}@{uuid.uuid4().hex}{extension}",
        )

    async def _synthesize_in_memory(self, text: str) -> bytes:
        """
        Gửi text đến Microsoft EdgeTTS Cloud và thu nhận toàn bộ bitstream MP3 vào RAM.
        Tối ưu hóa:
        - Safety Pacing Cooldown (>= 0.8s): Đảm bảo các kết nối cách nhau tối thiểu 0.8s,
          triệt tiêu hoàn toàn việc kích hoạt WAF Rate Limiting / Anti-Scraping của Microsoft.
          Vì loa ESP32 phát câu trước mất 4–8 giây, khoảng giãn 0.8s này hoàn toàn vô hình với người nghe.
        - Mỗi câu được thực hiện qua một phiên Communicate chuẩn mực, độc lập, sạch sẽ.
          Tránh việc giữ socket thây ma (zombie socket) sau khi Microsoft đã giải phóng worker (lỗi 1006).
        - Kiểm tra tín hiệu ngắt lời (client_abort / barge-in) trên từng chunk âm thanh.
        - Tự động thử lại với luân chuyển MUID và backoff tối ưu (1.0s, 2.0s).
        - Zero Disk I/O: 100% dữ liệu nằm trong RAM bytearray.
        """
        global _LAST_EDGETTS_FINISH_TIME
        if self._is_aborted() or not text:
            return b""

        # Safety Pacing Cooldown: Đảm bảo tối thiểu 0.8s giữa 2 lần mở socket tránh Anti-Spam của Microsoft
        now = time.time()
        elapsed = now - _LAST_EDGETTS_FINISH_TIME
        MIN_PACING = 0.8
        if elapsed < MIN_PACING:
            wait_time = MIN_PACING - elapsed
            await asyncio.sleep(wait_time)

        max_retries = 2

        for attempt in range(max_retries + 1):
            if self._is_aborted():
                _LAST_EDGETTS_FINISH_TIME = time.time()
                return b""

            try:
                communicate = edge_tts.Communicate(
                    text,
                    voice=self.voice,
                    rate=self.edge_rate,
                    volume=self.edge_volume,
                    pitch=self.edge_pitch,
                    connect_timeout=10,
                    receive_timeout=30,
                )
                audio_buffer = bytearray()
                async for chunk in communicate.stream():
                    if self._is_aborted():
                        logger.bind(tag=TAG).debug(
                            "EdgeTTS phát hiện client_abort trong lúc stream, dừng tải."
                        )
                        _LAST_EDGETTS_FINISH_TIME = time.time()
                        return b""
                    if chunk["type"] == "audio":
                        audio_buffer.extend(chunk["data"])

                if audio_buffer:
                    _LAST_EDGETTS_FINISH_TIME = time.time()
                    return bytes(audio_buffer)

                raise edge_tts.exceptions.NoAudioReceived("No audio received from EdgeTTS stream.")

            except Exception as e:
                if self._is_aborted():
                    _LAST_EDGETTS_FINISH_TIME = time.time()
                    return b""

                # Khi gặp sự cố socket / NoAudioReceived, làm mới MUID cho lần thử tiếp theo
                refresh_session_muid()
                if attempt < max_retries:
                    backoff = 1.0 * (attempt + 1)
                    logger.bind(tag=TAG).warning(
                        f"EdgeTTS socket gặp sự cố ({e}), tự động thử lại {attempt + 1}/{max_retries} sau {backoff:.1f}s..."
                    )
                    await asyncio.sleep(backoff)
                else:
                    logger.bind(tag=TAG).error(
                        f"EdgeTTS không nhận được audio sau {max_retries + 1} lần thử: {e}"
                    )
                    _LAST_EDGETTS_FINISH_TIME = time.time()
                    return b""

        _LAST_EDGETTS_FINISH_TIME = time.time()
        return b""

    async def text_to_speak(self, text, output_file=None):
        """
        Tổng hợp giọng nói theo giao diện chuẩn của TTSProviderBase:
        - Nếu output_file is None: Trả về MP3 bytes trong RAM (Zero Disk I/O).
        - Nếu output_file có giá trị: Ghi thẳng 1 lần ra file đĩa.
        """
        try:
            audio_bytes = await self._synthesize_in_memory(text)
            if self._is_aborted() or not audio_bytes:
                return None if output_file else b""

            if output_file:
                os.makedirs(os.path.dirname(output_file), exist_ok=True)
                with open(output_file, "wb") as f:
                    f.write(audio_bytes)
                return None
            return audio_bytes
        except Exception as e:
            error_msg = f"Edge TTS请求失败: {e}"
            raise Exception(error_msg)

    def to_tts_stream(self, text, opus_handler: Callable[[bytes], None] = None) -> None:
        """
        Cơ chế In-Memory Sentence Pipelining:
        1. Thu nhận toàn bộ chunk MP3 của câu vào RAM (< 700ms từ Microsoft).
        2. Giải mã siêu tốc bằng C miniaudio sang PCM 24000Hz Mono (< 2ms) mà không gọi ffmpeg.exe hay ghi đĩa.
        3. Đóng gói Opus 60ms (1.440 samples cho MAX98357A) và đẩy trực tiếp vào queue phát.
        """
        if self._is_aborted():
            return None

        original_text = text
        text = MarkdownCleaner.clean_markdown(text)
        if self._correct_words_pattern:
            text = self._correct_words_pattern.sub(
                lambda m: self.correct_words[m.group(0)], text
            )

        text = text.strip()
        if not text:
            return None

        sample_rate = getattr(getattr(self, "conn", None), "sample_rate", 24000)

        if self.delete_audio_file:
            # Chế độ In-Memory Stream thuần RAM
            audio_bytes = None
            try:
                audio_bytes = asyncio.run(self.text_to_speak(text, None))
            except Exception as e:
                logger.bind(tag=TAG).warning(f"EdgeTTS text_to_speak lỗi: {e}")

            if not audio_bytes or self._is_aborted():
                return None

            try:
                # Đẩy cờ SentenceType.FIRST cho câu này để client hiển thị subtitle
                self.tts_audio_queue.put(
                    (SentenceType.FIRST, None, original_text, getattr(self, "current_sentence_id", None))
                )

                opus_encoder = getattr(self, "opus_encoder", None)
                if opus_encoder is None:
                    from core.utils import opus_encoder_utils
                    opus_encoder = opus_encoder_utils.OpusEncoderUtils(
                        sample_rate=sample_rate,
                        channels=1,
                        frame_size_ms=60,
                    )
                    self.opus_encoder = opus_encoder

                # Giải mã trực tiếp MP3 sang PCM 24kHz bằng miniaudio và chuyển thành Opus stream
                mp3_bytes_to_pcm_stream_fast(
                    audio_bytes,
                    is_opus=True,
                    callback=opus_handler,
                    sample_rate=sample_rate,
                    opus_encoder=opus_encoder,
                )
            except Exception as e:
                logger.bind(tag=TAG).error(f"TTS to_tts_stream phát sinh lỗi: {e}")
        else:
            # Chế độ lưu file tạm trên đĩa (nếu delete_audio_file = False)
            tmp_file = self.generate_filename()
            try:
                asyncio.run(self.text_to_speak(text, tmp_file))
                if os.path.exists(tmp_file) and os.path.getsize(tmp_file) > 0:
                    self.tts_audio_queue.put(
                        (SentenceType.FIRST, None, original_text, getattr(self, "current_sentence_id", None))
                    )
                    self._process_audio_file_stream(tmp_file, callback=opus_handler)
            except Exception as e:
                logger.bind(tag=TAG).error(f"Failed to generate TTS file: {e}")

    def _close_fallback_loop(self):
        """Tương thích ngược cho các hook dọn dẹp hoặc test suite."""
        pass