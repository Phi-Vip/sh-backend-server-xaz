"""
core/utils/dialogue_recorder.py
Module ghi âm hội thoại phục vụ debug giữa ESP32 và Server (Dialogue Audio Sniffer).
Thiết kế theo nguyên tắc: Module hóa độc lập, Chạy nền không chặn Event Loop, Đơn giản thực dụng.
"""

import os
import time
import json
import wave
import math
import struct
from typing import List, Dict, Any, Optional
import opuslib_next
from config.logger import setup_logging

TAG = __name__
logger = setup_logging()


class DialogueAudioRecorder:
    """
    Audio Sniffer ghi lại 100% âm thanh hội thoại từ ESP32 khi cờ enabled=1.
    Chạy giải mã và lưu file hoàn toàn trong Worker Thread nền.
    """

    def __init__(self, config: Dict[str, Any]):
        recorder_cfg = config.get("dialogue_recorder", {})
        enabled_val = recorder_cfg.get("enabled", 0)
        # Hỗ trợ cấu hình 1/0, True/False, hoặc string "1"/"true"
        self.enabled = (enabled_val == 1 or enabled_val is True or str(enabled_val).lower() in ("true", "1"))
        self.output_dir = recorder_cfg.get("output_dir", "data/dataset/dialogue_audio")
        self.sample_rate = 16000
        self.samples_per_frame = 960  # 60ms @ 16kHz

    def is_enabled(self) -> bool:
        """Kiểm tra cờ bật/tắt (siêu nhanh < 10 nano-giây)"""
        return self.enabled

    def analyze_pcm(self, pcm_bytes: bytes) -> Dict[str, Any]:
        """
        Đo đạc nhanh các chỉ số vật lý của âm thanh PCM 16-bit Mono:
        - RMS: Độ lớn âm thanh trung bình
        - Peak: Biên độ đỉnh lớn nhất (thang đo 0 đến 32767)
        - Clipping: Số lượng mẫu chạm kịch trần (>= 30000)
        """
        if not pcm_bytes or len(pcm_bytes) < 2:
            return {
                "rms": 0.0,
                "peak": 0,
                "clipping_count": 0,
                "clipping_ratio": 0.0,
                "duration_sec": 0.0,
                "total_samples": 0,
            }

        num_samples = len(pcm_bytes) // 2
        try:
            samples = struct.unpack(f"<{num_samples}h", pcm_bytes[: num_samples * 2])
        except Exception:
            return {
                "rms": 0.0,
                "peak": 0,
                "clipping_count": 0,
                "clipping_ratio": 0.0,
                "duration_sec": 0.0,
                "total_samples": 0,
            }

        sum_squares = 0.0
        peak = 0
        clipping_count = 0

        for s in samples:
            abs_val = abs(s)
            if abs_val > peak:
                peak = abs_val
            if abs_val >= 30000:
                clipping_count += 1
            sum_squares += float(s) * float(s)

        rms = math.sqrt(sum_squares / num_samples) if num_samples > 0 else 0.0
        clipping_ratio = (clipping_count / num_samples) * 100.0 if num_samples > 0 else 0.0
        duration_sec = num_samples / float(self.sample_rate)

        return {
            "rms": round(rms, 2),
            "peak": int(peak),
            "clipping_count": clipping_count,
            "clipping_ratio": round(clipping_ratio, 2),
            "duration_sec": round(duration_sec, 2),
            "total_samples": num_samples,
        }

    def record_session(
        self,
        opus_packets: List[bytes],
        device_id: str,
        session_id: str,
        asr_text: str = "",
        tag: str = "SESSION",
    ) -> None:
        """
        Giải mã danh sách các gói Opus và lưu thành file WAV + JSON.
        Hàm này chạy đồng bộ bên trong Worker Thread nền, KHÔNG chặn async loop chính.
        Toàn bộ bọc trong try...except bảo đảm cách ly ngoại lệ tuyệt đối cho hệ thống.
        """
        if not self.enabled or not opus_packets:
            return

        try:
            # 1. Giải mã Opus -> PCM 16kHz Mono
            decoder = opuslib_next.Decoder(self.sample_rate, 1)
            pcm_chunks: List[bytes] = []

            for packet in opus_packets:
                try:
                    pcm_chunk = decoder.decode(packet, self.samples_per_frame)
                    if pcm_chunk:
                        pcm_chunks.append(pcm_chunk)
                except Exception:
                    pass

            if not pcm_chunks:
                logger.bind(tag=TAG).warning("Dialogue Sniffer: Không giải mã được PCM từ các gói Opus")
                return

            full_pcm = b"".join(pcm_chunks)
            metrics = self.analyze_pcm(full_pcm)

            # Đánh giá cảnh báo
            warning_note = "NORMAL"
            if metrics["clipping_ratio"] >= 3.0 or metrics["peak"] >= 32000:
                warning_note = "WARNING_AUDIO_CLIPPED_LOUD (Mic bị vỡ tiếng do nói quá to/sát mic)"
            elif metrics["rms"] < 300.0:
                warning_note = "WARNING_AUDIO_TOO_QUIET (Âm thanh quá nhỏ hoặc im lặng)"

            # 2. Tạo thư mục theo ngày: data/dataset/dialogue_audio/YYYY-MM-DD/
            date_str = time.strftime("%Y-%m-%d")
            target_dir = os.path.join(self.output_dir, date_str)
            os.makedirs(target_dir, exist_ok=True)

            # 3. Đặt tên file chuẩn
            timestamp_str = time.strftime("%Y%m%d_%H%M%S")
            clean_device = "".join(c for c in (device_id or "device") if c.isalnum() or c in ("-", "_"))

            # Gắn kèm đoạn đầu câu nói nếu có nhận dạng được
            clean_text = "".join(c for c in asr_text[:20] if c.isalnum() or c in ("_", "-"))
            suffix = f"_{clean_text}" if clean_text else f"_{tag}"

            base_name = f"{clean_device}_{timestamp_str}{suffix}"
            wav_path = os.path.join(target_dir, f"{base_name}.wav")
            json_path = os.path.join(target_dir, f"{base_name}_meta.json")

            # 4. Ghi file WAV 16kHz mono 16-bit
            with wave.open(wav_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(self.sample_rate)
                wf.writeframes(full_pcm)

            # 5. Ghi file JSON Metadata
            meta_payload = {
                "session_id": session_id,
                "device_id": device_id,
                "datetime": time.strftime("%Y-%m-%d %H:%M:%S"),
                "asr_text": asr_text,
                "note": warning_note,
                "audio_metrics": metrics,
                "packet_count": len(opus_packets),
                "wav_file": f"{base_name}.wav",
            }

            with open(json_path, "w", encoding="utf-8") as jf:
                json.dump(meta_payload, jf, ensure_ascii=False, indent=2)

            logger.bind(tag=TAG).info(
                f"🎙️ [DEBUG AUDIO SAVED] -> WAV: {base_name}.wav "
                f"({metrics['duration_sec']}s, {len(opus_packets)} pkts, RMS={metrics['rms']}, Peak={metrics['peak']}) | {warning_note}"
            )

        except Exception as e:
            logger.bind(tag=TAG).error(f"Dialogue Sniffer: Lỗi khi lưu file: {e}")


# Singleton Instance
_recorder_instance: Optional[DialogueAudioRecorder] = None


def get_dialogue_recorder(config: Dict[str, Any]) -> DialogueAudioRecorder:
    global _recorder_instance
    if _recorder_instance is None:
        _recorder_instance = DialogueAudioRecorder(config)
    return _recorder_instance
