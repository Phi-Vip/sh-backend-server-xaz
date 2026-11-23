import os
import time
import json
import wave
from typing import List, Dict, Any, Optional
from config.logger import setup_logging
import opuslib_next

TAG = __name__
logger = setup_logging()

class DatasetRecorder:
    """
    Wake Word Dataset Pipeline Recorder
    Chịu trách nhiệm giải mã các gói Opus của 2 frame âm thanh kích hoạt,
    cắt chính xác thành 2 file WAV 1.0s (16,000 samples @ 16kHz mono)
    kèm theo file metadata JSON.
    Hỗ trợ toggle bật/tắt qua cấu hình (1: Bật, 0: Tắt).
    """

    def __init__(self, config: Dict[str, Any]):
        collector_cfg = config.get("dataset_collector", {})
        # Cho phép cấu hình qua số 1/0 hoặc boolean True/False
        enabled_val = collector_cfg.get("enabled", 0)
        self.enabled = (enabled_val == 1 or enabled_val is True or str(enabled_val).lower() in ("true", "1"))
        self.output_dir = collector_cfg.get("output_dir", "data/dataset/wake_word")
        self.sample_rate = 16000
        self.frame_samples = 16000  # 1.0 giây = 16,000 mẫu
        self.frame_bytes = self.frame_samples * 2  # 16-bit PCM = 2 bytes/mẫu = 32,000 bytes

    def is_enabled(self) -> bool:
        return self.enabled

    def record(
        self,
        opus_packets: List[bytes],
        meta: Optional[Dict[str, Any]] = None,
        device_id: Optional[str] = None,
    ) -> None:
        """
        Giải mã các gói Opus và lưu 2 frame kích hoạt thành file WAV.
        Hàm này chạy đồng bộ bên trong worker thread (không chặn event loop).
        """
        if not self.enabled:
            return

        if not opus_packets:
            logger.bind(tag=TAG).warning("Dataset Pipeline: Không có gói Opus nào được cung cấp để lưu trữ")
            return

        try:
            meta_dict = meta if isinstance(meta, dict) else {}
            trigger_type = meta_dict.get("trigger_type", "smoothed_detect")
            packet_count = meta_dict.get("packet_count")

            # Lấy chính xác N gói Opus mới nhất từ đuôi danh sách (loại bỏ triệt để gói đàm thoại cũ)
            if packet_count and isinstance(packet_count, int) and len(opus_packets) > packet_count:
                opus_packets = opus_packets[-packet_count:]
            elif trigger_type in ("instant_spike",) and len(opus_packets) > 17:
                opus_packets = opus_packets[-17:]
            elif trigger_type in ("smoothed_detect", "smoothed_triggers") and len(opus_packets) > 34:
                opus_packets = opus_packets[-34:]
            elif trigger_type in ("triplet_spike", "triplet_smoothed") and len(opus_packets) > 50:
                opus_packets = opus_packets[-50:]
            elif len(opus_packets) > 50:
                opus_packets = opus_packets[-50:]

            # 1. Giải mã danh sách các gói Opus sang PCM 16kHz mono
            decoder = opuslib_next.Decoder(self.sample_rate, 1)
            pcm_chunks: List[bytes] = []
            
            for packet in opus_packets:
                try:
                    # Mỗi gói Opus từ ESP32 có frame_duration 60ms = 960 mẫu ở 16kHz
                    pcm_chunk = decoder.decode(packet, 960)
                    if pcm_chunk:
                        pcm_chunks.append(pcm_chunk)
                except Exception as dec_err:
                    logger.bind(tag=TAG).debug(f"Opus decode error on packet: {dec_err}")

            if not pcm_chunks:
                logger.bind(tag=TAG).warning("Dataset Pipeline: Giải mã Opus thất bại, không có PCM audio")
                return

            full_pcm = b"".join(pcm_chunks)

            # 2. Trích xuất metadata và thông tin frame từ ESP32
            frame1_meta = meta_dict.get("frame_1", {}) if isinstance(meta_dict.get("frame_1"), dict) else {}
            frame2_meta = meta_dict.get("frame_2", {}) if isinstance(meta_dict.get("frame_2"), dict) else {}

            # 3. Phân tách thư mục lưu trữ theo lai lịch kích hoạt:
            date_str = time.strftime("%Y-%m-%d")
            sub_dir = "instant_spikes" if trigger_type in ("instant_spike", "triplet_spike") else "smoothed_triggers"
            target_dir = os.path.join(self.output_dir, date_str, sub_dir)
            os.makedirs(target_dir, exist_ok=True)

            # 4. Đặt tên file chuẩn
            time_now = time.time()
            timestamp_str = time.strftime("%Y%m%d_%H%M%S", time.localtime(time_now))
            clean_device_id = "".join(c for c in (device_id or "device") if c.isalnum() or c in ("-", "_"))
            prefix = f"{clean_device_id}_{timestamp_str}"

            # Phân loại luồng ghi:
            # 1. Triplet (3 frames liền kề: PRE -250ms, CENTER 0ms, POST +250ms)
            # 2. Two frames (Legacy)
            # 3. Single frame (1 frame 1.0s tại đỉnh điểm số)
            is_triplet = (
                meta_dict.get("total_frames") == 3
                or trigger_type in ("triplet_spike", "triplet_smoothed")
                or (packet_count == 50 and len(full_pcm) >= self.frame_bytes * 3)
            )

            is_two_frame = (
                not is_triplet
                and (
                    meta_dict.get("total_frames") == 2
                    or (frame1_meta and frame2_meta)
                    or trigger_type in ("smoothed_detect", "smoothed_triggers")
                    or packet_count == 34
                )
            )

            if is_triplet:
                # Nhánh Triplet: Lấy 3 frame 1.0s (PRE -250ms, CENTER 0ms, POST +250ms) = 3 x 32,000 bytes = 96,000 bytes
                target_bytes = self.frame_bytes * 3
                if len(full_pcm) >= target_bytes:
                    valid_pcm = full_pcm[-target_bytes :]
                else:
                    valid_pcm = full_pcm.ljust(target_bytes, b"\x00")

                pre_pcm = valid_pcm[0 : self.frame_bytes]
                center_pcm = valid_pcm[self.frame_bytes : self.frame_bytes * 2]
                post_pcm = valid_pcm[self.frame_bytes * 2 : target_bytes]

                score = meta_dict.get("score", frame1_meta.get("score", 0.0))

                pre_filename = f"{prefix}_PRE_-250MS_SCORE_{score:.2f}.wav"
                center_filename = f"{prefix}_CENTER_0MS_SCORE_{score:.2f}.wav"
                post_filename = f"{prefix}_POST_+250MS_SCORE_{score:.2f}.wav"
                meta_filename = f"{prefix}_metadata.json"

                pre_filepath = os.path.join(target_dir, pre_filename)
                center_filepath = os.path.join(target_dir, center_filename)
                post_filepath = os.path.join(target_dir, post_filename)
                meta_filepath = os.path.join(target_dir, meta_filename)

                self._write_wav(pre_filepath, pre_pcm)
                self._write_wav(center_filepath, center_pcm)
                self._write_wav(post_filepath, post_pcm)

                meta_payload = {
                    "timestamp": int(time_now),
                    "datetime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time_now)),
                    "device_id": device_id,
                    "trigger_type": trigger_type,
                    "total_pcm_samples_decoded": len(valid_pcm) // 2,
                    "score": score,
                    "triplet_frames": {
                        "pre": {
                            "filename": pre_filename,
                            "offset_ms": -250,
                            "duration_seconds": 1.0,
                            "samples": len(pre_pcm) // 2,
                            "description": "Gói âm thanh lùi 250ms trước gói chính (-250ms)",
                        },
                        "center": {
                            "filename": center_filename,
                            "offset_ms": 0,
                            "duration_seconds": 1.0,
                            "samples": len(center_pcm) // 2,
                            "description": "Gói âm thanh bắt chính hiện tại tại thời điểm kích hoạt (0ms)",
                        },
                        "post": {
                            "filename": post_filename,
                            "offset_ms": 250,
                            "duration_seconds": 1.0,
                            "samples": len(post_pcm) // 2,
                            "description": "Gói âm thanh tiến 250ms sau gói chính (+250ms)",
                        },
                    },
                    "esp32_metadata": meta_dict,
                }

                with open(meta_filepath, "w", encoding="utf-8") as jf:
                    json.dump(meta_payload, jf, ensure_ascii=False, indent=2)

                logger.bind(tag=TAG).info(
                    f"💾 Dataset Pipeline: Đã lưu trọn bộ 3 gói âm thanh liền kề (PRE, CENTER, POST) -> "
                    f"Score={score:.2f} tại {target_dir}"
                )
            elif not is_two_frame:
                # Nhánh Single Frame (1.0s = 16,000 samples = 32,000 bytes) tại đỉnh điểm số
                # Lấy đúng 32,000 bytes đầu tiên của chuỗi 17 gói Opus (loại bỏ padding 320 samples zero ở cuối)
                score = meta_dict.get("score", frame1_meta.get("score", 0.0))
                if len(full_pcm) >= self.frame_bytes:
                    valid_pcm = full_pcm[: self.frame_bytes]
                else:
                    valid_pcm = full_pcm.ljust(self.frame_bytes, b"\x00")

                if trigger_type == "instant_spike":
                    wav_filename = f"{prefix}_SPIKE_SCORE_{score:.2f}.wav"
                else:
                    wav_filename = f"{prefix}_WAKE_SCORE_{score:.2f}.wav"

                meta_filename = f"{prefix}_metadata.json"
                wav_filepath = os.path.join(target_dir, wav_filename)
                meta_filepath = os.path.join(target_dir, meta_filename)

                self._write_wav(wav_filepath, valid_pcm)

                meta_payload = {
                    "timestamp": int(time_now),
                    "datetime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time_now)),
                    "device_id": device_id,
                    "trigger_type": trigger_type,
                    "total_pcm_samples_decoded": len(valid_pcm) // 2,
                    "score": score,
                    "frame": {
                        "filename": wav_filename,
                        "score": score,
                        "label": meta_dict.get("label", frame1_meta.get("label", "Xin chào sunhouse")),
                        "duration_seconds": 1.0,
                        "samples": len(valid_pcm) // 2,
                    },
                    "esp32_metadata": meta_dict,
                }

                with open(meta_filepath, "w", encoding="utf-8") as jf:
                    json.dump(meta_payload, jf, ensure_ascii=False, indent=2)

                logger.bind(tag=TAG).info(
                    f"💾 Dataset Pipeline: Đã lưu 1.0s audio frame ({trigger_type}) -> "
                    f"Score={score:.2f} tại {target_dir}"
                )
            else:
                # Nhánh Smoothed Trigger: Lấy đúng 2 frames kích hoạt (2 x 1.0s = 32,000 samples = 64,000 bytes)
                score_1 = frame1_meta.get("score", meta_dict.get("score", 0.0))
                score_2 = frame2_meta.get("score", meta_dict.get("score", 0.0))

                target_bytes = self.frame_bytes * 2
                if len(full_pcm) >= target_bytes:
                    valid_pcm = full_pcm[: target_bytes]
                else:
                    valid_pcm = full_pcm.ljust(target_bytes, b"\x00")

                frame1_pcm = valid_pcm[: self.frame_bytes]
                frame2_pcm = valid_pcm[self.frame_bytes : target_bytes]

                frame1_filename = f"{prefix}_FRAME1_SCORE_{score_1:.2f}.wav"
                frame2_filename = f"{prefix}_FRAME2_SCORE_{score_2:.2f}.wav"
                meta_filename = f"{prefix}_metadata.json"

                frame1_filepath = os.path.join(target_dir, frame1_filename)
                frame2_filepath = os.path.join(target_dir, frame2_filename)
                meta_filepath = os.path.join(target_dir, meta_filename)

                self._write_wav(frame1_filepath, frame1_pcm)
                self._write_wav(frame2_filepath, frame2_pcm)

                meta_payload = {
                    "timestamp": int(time_now),
                    "datetime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time_now)),
                    "device_id": device_id,
                    "trigger_type": "smoothed_detect",
                    "total_pcm_samples_decoded": (len(frame1_pcm) + len(frame2_pcm)) // 2,
                    "frame_1": {
                        "filename": frame1_filename,
                        "score": score_1,
                        "label": frame1_meta.get("label", "Xin chào sunhouse"),
                        "duration_seconds": 1.0,
                        "samples": 16000,
                    },
                    "frame_2": {
                        "filename": frame2_filename,
                        "score": score_2,
                        "label": frame2_meta.get("label", "Xin chào sunhouse"),
                        "duration_seconds": 1.0,
                        "samples": 16000,
                    },
                    "esp32_metadata": meta_dict,
                }

                with open(meta_filepath, "w", encoding="utf-8") as jf:
                    json.dump(meta_payload, jf, ensure_ascii=False, indent=2)

                logger.bind(tag=TAG).info(
                    f"💾 Dataset Pipeline: Đã lưu thành công 2 frames kích hoạt -> "
                    f"Frame 1 (score={score_1:.2f}), Frame 2 (score={score_2:.2f}) tại {target_dir}"
                )

        except Exception as e:
            logger.bind(tag=TAG).error(f"Dataset Pipeline: Lỗi trong quá trình lưu dataset: {e}")

    def _write_wav(self, file_path: str, pcm_data: bytes) -> None:
        """Ghi dữ liệu PCM thô thành file WAV 16kHz mono 16-bit"""
        with wave.open(file_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-bit PCM
            wf.setframerate(self.sample_rate)
            wf.writeframes(pcm_data)

_dataset_recorder_instance: Optional[DatasetRecorder] = None

def get_dataset_recorder(config: Dict[str, Any]) -> DatasetRecorder:
    global _dataset_recorder_instance
    if _dataset_recorder_instance is None:
        _dataset_recorder_instance = DatasetRecorder(config)
    return _dataset_recorder_instance
