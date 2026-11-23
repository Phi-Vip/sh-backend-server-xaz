import os
import io
import wave
import uuid
import asyncio
import threading
from datetime import datetime
from typing import Optional, Dict, Any

from config.logger import setup_logging
from core.providers.tts.base import TTSProviderBase

TAG = __name__
logger = setup_logging()

# Singleton cache lưu trữ mô hình Piper TTS trong RAM, tránh nạp lại nhiều lần khi có nhiều client
_MODEL_CACHE: Dict[str, Any] = {}
_CACHE_LOCK = threading.Lock()
_INFERENCE_LOCK = threading.Lock()


def get_piper_voice(model_path: str, config_path: Optional[str] = None):
    abs_model = os.path.abspath(model_path)
    abs_config = os.path.abspath(config_path) if config_path else None

    with _CACHE_LOCK:
        if abs_model not in _MODEL_CACHE:
            from piper import PiperVoice
            if not os.path.exists(abs_model):
                raise FileNotFoundError(f"Không tìm thấy file mô hình Piper TTS tại: {abs_model}")
            
            logger.bind(tag=TAG).info(f"Đang tải mô hình Piper TTS vào bộ nhớ: {abs_model}...")
            voice = PiperVoice.load(abs_model, config_path=abs_config)
            _MODEL_CACHE[abs_model] = voice
            logger.bind(tag=TAG).info(
                f"Đã tải thành công Piper TTS! Tần số mẫu: {voice.config.sample_rate}Hz"
            )
        return _MODEL_CACHE[abs_model]


class TTSProvider(TTSProviderBase):
    TTS_PARAM_CONFIG = [
        ("ttsVolume", "volume", 0, 100, 50, int),
        ("ttsRate", "speech_rate", -100, 100, 0, int),
    ]

    def __init__(self, config, delete_audio_file):
        super().__init__(config, delete_audio_file)
        self.audio_file_type = "wav"
        self.output_file = config.get("output_dir", "tmp/")

        self.model_path = config.get("model_path", "models/piper/vi_VN-vais1000-medium.onnx")
        self.config_path = config.get("config_path", "models/piper/vi_VN-vais1000-medium.onnx.json")

        # Tốc độ đọc (speed: 1.0 là bình thường, >1 nhanh hơn, <1 chậm hơn)
        speed = config.get("speed", 1.0)
        self.speed = float(speed) if speed else 1.0

        # Âm lượng
        volume = config.get("volume", 50)
        self.volume = int(volume) if volume else 50

        speech_rate = config.get("rate", 0)
        self.speech_rate = int(speech_rate) if speech_rate else 0

        # Áp dụng phần trăm điều chỉnh nếu có từ cấu hình XiaoZhi
        self._apply_percentage_params(config)

        # Nếu có speech_rate %, cập nhật speed
        if self.speech_rate != 0:
            self.speed = max(0.5, min(2.5, 1.0 + (self.speech_rate / 100.0)))

        # length_scale trong Piper: tỉ lệ nghịch với tốc độ đọc
        # length_scale < 1.0: nói nhanh hơn; length_scale > 1.0: nói chậm hơn
        self.length_scale = round(1.0 / max(0.3, min(3.0, self.speed)), 3)

        # Speaker ID cho mô hình đa giọng (Multi-speaker, 0-4)
        speaker_id = config.get("speaker_id", None)
        self.speaker_id = int(speaker_id) if speaker_id is not None else None

        # Lấy mô hình từ cache
        self.voice = get_piper_voice(self.model_path, self.config_path)

        from piper.config import SynthesisConfig
        self.syn_config = SynthesisConfig(
            speaker_id=self.speaker_id,
            length_scale=self.length_scale,
            volume=float(self.volume) / 50.0 if self.volume else 1.0,
        )

    def generate_filename(self, extension=".wav"):
        return os.path.join(
            self.output_file,
            f"tts-{datetime.now().date()}@{uuid.uuid4().hex}{extension}",
        )

    def _clean_text(self, text: str) -> str:
        # Lọc bỏ ký tự CJK (chữ Hán) mà mô hình Piper tiếng Việt không phân giải được
        import re
        from core.utils.textUtils import repair_vietnamese_spacing
        text = repair_vietnamese_spacing((text or "").strip())
        if re.search(r'[\u4e00-\u9fff]', text):
            logger.bind(tag=TAG).warning(f"Piper TTS tiếng Việt phát hiện ký tự CJK ngoài phạm vi: {text}")
            cleaned = re.sub(r'[\u4e00-\u9fff]+', ' ', text).strip()
            # Nếu câu toàn bộ là chữ Hán bị lọc sạch, fallback sang câu tiếng Việt lịch sự
            if not cleaned:
                return "Dạ câu vừa rồi mình chưa nghe rõ, bạn nói lại giúp mình nhé!"
            return re.sub(r'\s+', ' ', cleaned).strip()
        return text

    def _sync_synthesize(self, text: str) -> bytes:
        wav_io = io.BytesIO()
        with _INFERENCE_LOCK:
            with wave.open(wav_io, "wb") as wav_file:
                self.voice.synthesize_wav(text, wav_file, syn_config=self.syn_config)
        return wav_io.getvalue()

    async def text_to_speak(self, text, output_file):
        text = self._clean_text(text or "")
        if not text:
            if output_file:
                os.makedirs(os.path.dirname(output_file), exist_ok=True)
                with wave.open(output_file, "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(getattr(self.voice.config, "sample_rate", 22050))
                    wf.writeframes(b"")
                return None
            return b""

        loop = asyncio.get_running_loop()
        wav_bytes = await loop.run_in_executor(None, self._sync_synthesize, text)

        if output_file:
            os.makedirs(os.path.dirname(output_file), exist_ok=True)
            with open(output_file, "wb") as f:
                f.write(wav_bytes)
            return None
        else:
            return wav_bytes
