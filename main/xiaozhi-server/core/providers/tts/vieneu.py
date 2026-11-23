import os
import io
import time
import wave
import uuid
import struct
import asyncio
import threading
from datetime import datetime
from typing import Optional, Dict, Any, Callable
import warnings

# Ẩn cảnh báo không quan trọng của HuggingFace Hub khi tải model công khai
warnings.filterwarnings("ignore", message=".*unauthenticated requests to the HF Hub.*")

import requests
import numpy as np
from config.logger import setup_logging
from core.providers.tts.base import TTSProviderBase
from core.providers.tts.dto.dto import SentenceType
from core.utils.tts import MarkdownCleaner
from core.utils.textUtils import repair_vietnamese_spacing, check_emoji
from core.utils.util import (
    numpy_audio_to_pcm_stream_fast,
    numpy_audio_to_pcm_bytes_fast,
    numpy_chunk_to_opus_stream,
)

TAG = __name__
logger = setup_logging()

# Singleton cache dự phòng cho chế độ standalone_direct (nếu chạy không qua Microservice)
_VIENEU_ENGINE: Optional[Any] = None
_CACHE_LOCK = threading.Lock()
_STREAM_SEMAPHORE = threading.BoundedSemaphore(value=2)


def get_vieneu_engine(precision: str = "int8", mode: str = "v3turbo") -> Any:
    """Khởi tạo engine cục bộ nếu chạy ở chế độ standalone_direct=True"""
    global _VIENEU_ENGINE
    with _CACHE_LOCK:
        if _VIENEU_ENGINE is None:
            import vieneu

            logger.bind(tag=TAG).info(
                f"Đang nạp mô hình VieNeu-TTS vào RAM (mode={mode}, precision={precision})..."
            )
            t0 = time.time()
            try:
                _VIENEU_ENGINE = vieneu.Vieneu(mode=mode, precision=precision, backend="onnx")
            except Exception as e:
                logger.bind(tag=TAG).warning(
                    f"Không thể khởi tạo VieNeu với precision={precision} ({e}), thử mặc định..."
                )
                _VIENEU_ENGINE = vieneu.Vieneu(mode=mode, backend="onnx")

            load_time = time.time() - t0
            sample_rate = getattr(_VIENEU_ENGINE, "sample_rate", 48000)
            logger.bind(tag=TAG).info(
                f"Đã nạp thành công VieNeu-TTS vào RAM trong {load_time:.2f}s! Sample rate: {sample_rate}Hz"
            )
        return _VIENEU_ENGINE


class TTSProvider(TTSProviderBase):
    """
    VieNeu-TTS Provider chuẩn thương mại (Decoupled Compute Tier):
    - Mặc định: Hoạt động như một Microservice Client kết nối tới VieNeuTTS Server (Port 8008)
      qua giao thức HTTP Streaming Chunked. Bộ nhớ Worker chỉ tốn ~45MB RAM (không nạp weights).
    - Tự động truyền nhận luồng Opus 60ms binary frames có gắn nhãn thời gian thực.
    - Dự phòng: Hỗ trợ standalone_direct=True cho các bài unit test độc lập không có tts_server.
    """
    TTS_PARAM_CONFIG = [
        ("ttsVolume", "volume", 0, 100, 50, int),
        ("ttsRate", "speech_rate", -100, 100, 0, int),
    ]

    def __init__(self, config, delete_audio_file):
        super().__init__(config, delete_audio_file)
        self.audio_file_type = "wav"
        self.output_file = config.get("output_dir", "tmp/")

        # Cấu hình Microservice URL (Mặc định Port 8008 nội bộ)
        self.server_url = config.get("server_url", "http://127.0.0.1:8008").rstrip("/")
        self.standalone_direct = bool(config.get("standalone_direct", False))

        # Độ chính xác lượng tử hóa CPU: int8 hoặc fp32
        self.precision = config.get("precision", "int8")
        self.mode = config.get("model_mode", "v3turbo")

        # Âm lượng & Tốc độ
        volume = config.get("volume", 50)
        self.volume = int(volume) if volume is not None else 50
        speech_rate = config.get("rate", 0)
        self.speech_rate = int(speech_rate) if speech_rate is not None else 0
        self._apply_percentage_params(config)

        # Cấu hình Voice Cloning
        self.enable_voice_clone = bool(config.get("enable_voice_clone", False))
        ref_audio = config.get("ref_audio", None)
        if ref_audio:
            self.ref_audio = os.path.abspath(ref_audio) if not os.path.isabs(ref_audio) else ref_audio
        else:
            self.ref_audio = None
        self.ref_text = config.get("ref_text", None)

        # Cấu hình Giọng Preset
        preset_voice = config.get("preset_voice", config.get("voice", "default"))
        if preset_voice in ("default", "", None):
            self.preset_voice = None
        else:
            self.preset_voice = preset_voice

        # Cấu hình ngắt câu tối ưu cho VieNeu-TTS
        self.punctuations = (".", "?", "!", ";", "\n", "。", "？", "！", "；")
        self.first_sentence_punctuations = (".", "?", "!", ";", "\n", "。", "？", "！", "；")

        if self.standalone_direct:
            logger.bind(tag=TAG).info("Chế độ VieNeuTTS Standalone Direct (nạp trực tiếp mô hình vào Worker).")
            self.engine = get_vieneu_engine(precision=self.precision, mode=self.mode)
        else:
            self.engine = None
            logger.bind(tag=TAG).info(
                f"[Decoupled TTS] Worker kết nối VieNeuTTS Microservice tại {self.server_url} (RAM worker ~45MB)."
            )

    def _clean_text(self, text: str) -> str:
        """Chuẩn hóa văn bản tiếng Việt"""
        if not text:
            return ""
        text = check_emoji(text)
        text = repair_vietnamese_spacing(text)
        return text.strip()

    def _is_aborted(self) -> bool:
        """Kiểm tra cờ ngắt lời (barge-in)"""
        conn = getattr(self, "conn", None)
        if conn and hasattr(conn, "client_abort"):
            return bool(conn.client_abort)
        return False

    async def text_to_speak(self, text: str, output_file: Optional[str] = None):
        """Tổng hợp nguyên câu trả về WAV bytes (Zero Disk I/O) hoặc ghi ra file đĩa"""
        text = self._clean_text(text or "")
        sample_rate = getattr(getattr(self, "conn", None), "sample_rate", 24000)
        
        if not text:
            if output_file:
                os.makedirs(os.path.dirname(output_file), exist_ok=True)
                with wave.open(output_file, "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(sample_rate)
                    wf.writeframes(b"")
                return None
            return b""

        if self.standalone_direct and self.engine:
            # Chạy trực tiếp qua engine nội bộ
            loop = asyncio.get_running_loop()
            audio_np = await loop.run_in_executor(None, self._sync_synthesize_direct, text)
            if self._is_aborted() or audio_np is None:
                return None if output_file else b""
            raw_pcm = np.clip(audio_np * 32767.0, -32768, 32767).astype(np.int16).tobytes()
            wav_io = io.BytesIO()
            with wave.open(wav_io, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(getattr(self.engine, "sample_rate", 48000))
                wf.writeframes(raw_pcm)
            wav_bytes = wav_io.getvalue()
        else:
            # Gọi qua VieNeuTTS Microservice
            loop = asyncio.get_running_loop()
            payload = {
                "text": text,
                "voice": self.preset_voice,
                "ref_audio": self.ref_audio if (self.enable_voice_clone and self.ref_audio) else None,
                "ref_text": self.ref_text if self.enable_voice_clone else None,
                "sample_rate": sample_rate,
                "format": "pcm"
            }
            def _call_service():
                try:
                    resp = requests.post(f"{self.server_url}/tts/synthesize", json=payload, timeout=12.0)
                    if resp.status_code == 200:
                        return resp.content
                    logger.bind(tag=TAG).warning(f"TTS Server error: {resp.status_code} - {resp.text}")
                    return None
                except Exception as e:
                    logger.bind(tag=TAG).error(f"Lỗi gọi VieNeuTTS Microservice: {e}")
                    return None

            wav_bytes = await loop.run_in_executor(None, _call_service)
            if not wav_bytes:
                return None if output_file else b""

        if output_file:
            os.makedirs(os.path.dirname(output_file), exist_ok=True)
            with open(output_file, "wb") as f:
                f.write(wav_bytes)
            return None
        return wav_bytes

    def _sync_synthesize_direct(self, text: str):
        with _STREAM_SEMAPHORE:
            infer_kwargs = {}
            if self.enable_voice_clone and self.ref_audio and os.path.exists(self.ref_audio):
                infer_kwargs["ref_audio"] = self.ref_audio
            elif self.preset_voice:
                infer_kwargs["voice"] = self.preset_voice
            return self.engine.infer(text, **infer_kwargs)

    def to_tts_stream(self, text: str, opus_handler: Callable[[bytes], None] = None) -> None:
        """
        Cơ chế Rolling Streaming qua VieNeuTTS Microservice (Port 8008):
        - Nhận dòng Opus packet nhị phân 60ms từ microservice qua HTTP stream.
        - Đẩy cờ SentenceType.FIRST lập tức cho subtitle.
        - Kiểm tra ngắt lời (barge-in) trên từng packet nhị phân.
        - Đẩy liên tục SentenceType.BODY vào tts_audio_queue với độ trễ < 250ms.
        """
        if self._is_aborted():
            return None

        original_text = text
        text = MarkdownCleaner.clean_markdown(text)
        if self._correct_words_pattern:
            text = self._correct_words_pattern.sub(
                lambda m: self.correct_words[m.group(0)], text
            )

        text = self._clean_text(text)
        if not text:
            return None

        display_text = text
        sample_rate = getattr(getattr(self, "conn", None), "sample_rate", 24000)
        sentence_id = getattr(self, "current_sentence_id", None)

        # 1. Đẩy cờ SentenceType.FIRST lập tức để client hiển thị subtitle
        self.tts_audio_queue.put(
            (
                SentenceType.FIRST,
                None,
                display_text,
                sentence_id,
            )
        )

        if self._is_aborted():
            return None

        # 2. Nếu ở chế độ standalone_direct, chạy local engine
        if self.standalone_direct and self.engine:
            self._stream_direct_local(text, display_text, sample_rate, sentence_id, opus_handler)
            return

        # 3. Chế độ Microservice (Mặc định cho cụm 4 Workers):
        payload = {
            "text": text,
            "voice": self.preset_voice,
            "ref_audio": self.ref_audio if (self.enable_voice_clone and self.ref_audio) else None,
            "ref_text": self.ref_text if self.enable_voice_clone else None,
            "speed": 1.0,
            "sample_rate": sample_rate,
            "format": "opus"
        }

        try:
            t0 = time.time()
            first_packet = True
            with requests.post(
                f"{self.server_url}/tts/stream",
                json=payload,
                stream=True,
                timeout=(3.0, 15.0)
            ) as resp:
                if resp.status_code != 200:
                    logger.bind(tag=TAG).error(
                        f"VieNeuTTS Microservice ({self.server_url}) trả về lỗi HTTP {resp.status_code}"
                    )
                    return

                # Đọc luồng byte Opus 60ms: mỗi packet gồm [2 bytes độ dài uint16] + [dữ liệu opus]
                while not self._is_aborted():
                    len_bytes = resp.raw.read(2)
                    if not len_bytes or len(len_bytes) < 2:
                        break
                    
                    packet_len = struct.unpack(">H", len_bytes)[0]
                    opus_packet = resp.raw.read(packet_len)
                    if not opus_packet or self._is_aborted():
                        break

                    if first_packet:
                        logger.bind(tag=TAG).info(
                            f"[TTS Microservice Stream] Gói âm thanh đầu tiên nhận sau {time.time() - t0:.3f}s"
                        )
                        first_packet = False

                    if opus_handler:
                        opus_handler(opus_packet)
                    else:
                        self.tts_audio_queue.put(
                            (
                                SentenceType.BODY,
                                opus_packet,
                                None,
                                sentence_id,
                            )
                        )
        except Exception as e:
            logger.bind(tag=TAG).error(
                f"Lỗi kết nối VieNeuTTS Microservice tại {self.server_url}: {e}"
            )

    def _stream_direct_local(self, text, display_text, sample_rate, sentence_id, opus_handler):
        """Xử lý stream trực tiếp khi chạy standalone"""
        from core.utils import opus_encoder_utils
        opus_encoder = getattr(self, "opus_encoder", None)
        if opus_encoder is None:
            opus_encoder = opus_encoder_utils.OpusEncoderUtils(
                sample_rate=sample_rate, channels=1, frame_size_ms=60
            )
            self.opus_encoder = opus_encoder

        orig_rate = getattr(self.engine, "sample_rate", 48000)
        infer_kwargs = {}
        if self.enable_voice_clone and self.ref_audio and os.path.exists(self.ref_audio):
            infer_kwargs["ref_audio"] = self.ref_audio
        elif self.preset_voice:
            infer_kwargs["voice"] = self.preset_voice

        acquired = _STREAM_SEMAPHORE.acquire(timeout=5.0)
        if not acquired:
            logger.bind(tag=TAG).warning("VieNeu-TTS Semaphore timeout!")
            return

        try:
            for chunk_np in self.engine.infer_stream(text, **infer_kwargs):
                if self._is_aborted():
                    return
                if chunk_np is not None and len(chunk_np) > 0:
                    numpy_chunk_to_opus_stream(
                        chunk_np=chunk_np,
                        opus_encoder=opus_encoder,
                        callback=opus_handler,
                        orig_sample_rate=orig_rate,
                        target_sample_rate=sample_rate,
                        is_end=False,
                    )
            if not self._is_aborted():
                numpy_chunk_to_opus_stream(
                    chunk_np=None,
                    opus_encoder=opus_encoder,
                    callback=opus_handler,
                    orig_sample_rate=orig_rate,
                    target_sample_rate=sample_rate,
                    is_end=True,
                )
        finally:
            _STREAM_SEMAPHORE.release()
