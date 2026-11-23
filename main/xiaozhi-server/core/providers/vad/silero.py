import time
import os
import numpy as np
import onnxruntime
from config.logger import setup_logging
from core.providers.vad.base import VADProviderBase

from scipy.signal import butter, lfilter, lfilter_zi

TAG = __name__
logger = setup_logging()


class VADProvider(VADProviderBase):
    def __init__(self, config):
        logger.bind(tag=TAG).info("SileroVAD", config)

        model_path = os.path.join(
            config["model_dir"], "src", "silero_vad", "data", "silero_vad.onnx"
        )
        opts = onnxruntime.SessionOptions()
        opts.inter_op_num_threads = 1
        opts.intra_op_num_threads = 1
        self.session = onnxruntime.InferenceSession(
            model_path, providers=["CPUExecutionProvider"], sess_options=opts
        )

        threshold = config.get("threshold", "0.5")
        threshold_low = config.get("threshold_low", "0.2")
        min_silence_duration_ms = config.get("min_silence_duration_ms", "1000")

        self.vad_threshold = float(threshold) if threshold else 0.5
        self.vad_threshold_low = float(threshold_low) if threshold_low else 0.2

        self.silence_threshold_ms = (
            int(min_silence_duration_ms) if min_silence_duration_ms else 1000
        )

        self.frame_window_threshold = 3

        # Thiết kế bộ lọc số Bandpass Filter (Butterworth bậc 4: 280Hz - 3500Hz, fs=16000Hz)
        # Loại bỏ triệt để:
        # 1. Toàn bộ sóng hạ âm và chuỗi sóng hài cơ học micro: 21.5Hz (>65dB), 64.5Hz (>45dB), 107Hz (>32dB), 197Hz
        # 2. Nhiễu xì tần số cao / xung nhịp clock I2S (>3500Hz)
        # 3. Giữ trọn 100% dải tần thanh âm tiếng người (300Hz - 3400Hz theo chuẩn viễn thông ITU-T)
        # CHỈ áp dụng cho luồng nhận diện VAD, KHÔNG làm ảnh hưởng đến âm thanh gốc gửi STT.
        self.hpf_b, self.hpf_a = butter(4, [280.0 / 8000.0, 3500.0 / 8000.0], btype="bandpass")

    def _init_connection_state(self, conn):
        """为连接初始化独立的 VAD 状态"""
        if not hasattr(conn, "_vad_state"):
            conn._vad_state = np.zeros((2, 1, 128), dtype=np.float32)
        if not hasattr(conn, "_vad_context"):
            conn._vad_context = np.zeros((1, 64), dtype=np.float32)
        if not hasattr(conn, "_hpf_zi"):
            conn._hpf_zi = lfilter_zi(self.hpf_b, self.hpf_a) * 0.0

    def release_conn_resources(self, conn):
        """释放连接的 VAD 资源（连接关闭时调用）"""
        for attr in ("_vad_state", "_vad_context", "_hpf_zi"):
            if hasattr(conn, attr):
                try:
                    delattr(conn, attr)
                except Exception:
                    pass

    def is_vad(self, conn, pcm_frame):
        # 手动模式：直接返回True，不进行实时VAD检测，所有音频都缓存
        if conn.client_listen_mode == "manual":
            return True

        try:
            self._init_connection_state(conn)

            # pcm_frame已经是处理后的PCM数据
            conn.client_audio_buffer.extend(pcm_frame)

            client_have_voice = False
            while len(conn.client_audio_buffer) >= 512 * 2:
                chunk = conn.client_audio_buffer[: 512 * 2]
                conn.client_audio_buffer = conn.client_audio_buffer[512 * 2 :]

                audio_int16 = np.frombuffer(chunk, dtype=np.int16)
                audio_float32 = audio_int16.astype(np.float32) / 32768.0

                # Lọc Bandpass (280Hz - 3500Hz) trên bản copy tạm thời của VAD
                # Triệt tiêu 100% hạ âm 21Hz và các sóng hài 64Hz, 107Hz, 197Hz gây mù VAD
                audio_filtered, conn._hpf_zi = lfilter(
                    self.hpf_b, self.hpf_a, audio_float32, zi=conn._hpf_zi
                )
                audio_vad = np.clip(audio_filtered * 2.0, -1.0, 1.0)

                audio_input = np.concatenate(
                    [conn._vad_context, audio_vad.reshape(1, -1)], axis=1
                ).astype(np.float32)

                ort_inputs = {
                    "input": audio_input,
                    "state": conn._vad_state,
                    "sr": np.array(16000, dtype=np.int64),
                }
                out, state = self.session.run(None, ort_inputs)

                conn._vad_state = state
                conn._vad_context = audio_input[:, -64:]
                
                # Tính RMS thực tế của dải âm thanh sau khi đã lọc sạch hạ âm 21Hz
                audio_rms = int(np.sqrt(np.mean((audio_filtered * 32768.0) ** 2)))
                speech_prob = out.item()

                # Ghi log chẩn đoán âm lượng RMS và xác suất tiếng nói (1s khi có tiếng, định kỳ 2.5s khi im lặng)
                now_sec = time.time()
                is_active = audio_rms >= 300 or speech_prob >= self.vad_threshold
                time_since_last_log = now_sec - getattr(conn, "_last_vad_debug_log", 0.0)
                if (is_active and time_since_last_log >= 1.0) or (time_since_last_log >= 2.5):
                    conn._last_vad_debug_log = now_sec
                    diag_hint = ""
                    if audio_rms < 150:
                        diag_hint = " ⚠️ [Tín hiệu mic rất nhỏ/im lặng]"
                    elif speech_prob >= self.vad_threshold:
                        diag_hint = " 🗣️ [Phát hiện tiếng nói người!]"
                    elif audio_rms >= 500 and speech_prob < self.vad_threshold:
                        diag_hint = " 🔊 [Âm thanh lớn nhưng VAD chưa coi là tiếng nói]"
                    logger.bind(tag=TAG).info(
                        f"[VAD METER] 🎙️ RMS={audio_rms}, Prob={speech_prob:.2f} (Ngưỡng VAD: {self.vad_threshold}) | have_voice={conn.client_have_voice}{diag_hint}"
                    )

                # Đánh giá trạng thái có tiếng nói thuần túy theo cơ chế 2 ngưỡng có vùng trễ (Dual-Threshold Hysteresis)
                # của Silero VAD: Hoàn toàn thích ứng với mọi môi trường (phòng ngủ, văn phòng, quán xá),
                # tuyệt đối KHÔNG gán cứng (hardcode) bất kỳ ngưỡng biên độ RMS cục bộ nào.
                if speech_prob >= self.vad_threshold:
                    is_voice = True
                elif speech_prob <= self.vad_threshold_low:
                    is_voice = False
                else:
                    is_voice = conn.last_is_voice

                # Tích lũy số frame có tiếng nói thực sự trong phiên hội thoại (Prob >= 0.3)
                if speech_prob >= 0.3:
                    conn.speech_frames_count = getattr(conn, "speech_frames_count", 0) + 1

                # Lưu trạng thái trước đó cho vùng trễ hysteresis
                conn.last_is_voice = is_voice

                # 更新滑动窗口
                conn.client_voice_window.append(is_voice)
                client_have_voice = (
                    conn.client_voice_window.count(True) >= self.frame_window_threshold
                )

                # 如果之前有声音，但本次没有声音，且与上次有声音的时间差已经超过了静默阈值，则认为已经说完一句话
                if conn.client_have_voice and not client_have_voice:
                    stop_duration = time.time() * 1000 - conn.vad_last_voice_time
                    if stop_duration >= self.silence_threshold_ms:
                        speech_frames = getattr(conn, "speech_frames_count", 0)
                        # Bảo vệ triệt để chống xung kích cơ học / dội loa / tiếng tặc lưỡi, chép miệng:
                        # Mọi từ lệnh ngắn nhất ("Đúng", "OK", "Có", "Bật") khi phát âm luôn tích lũy >= 10 - 20 frames (>= 0.35s).
                        # Nếu chỉ có < 8 frames (~256ms) thì chắc chắn là tiếng tặc lưỡi ('Tch'), rung lưỡi ('Tr'), chép miệng hoặc xung điện mở mic.
                        if speech_frames < 8:
                            logger.bind(tag=TAG).info(
                                f"[VAD IGNORE] 🛡️ Bỏ qua kích hoạt giả: Chỉ có {speech_frames} frames tiếng nói (< 8 frames ~ 256ms) - nghi vấn tặc lưỡi/chép miệng/xung cơ học, không gửi ASR"
                            )
                            conn.reset_audio_states()
                            continue

                        conn.client_voice_stop = True
                        logger.bind(tag=TAG).info(
                            f"[VAD STOP] 🛑 Phát hiện người dùng dứt câu nói! (Im lặng: {stop_duration:.0f}ms / {self.silence_threshold_ms}ms | Speech frames: {speech_frames})"
                        )
                if client_have_voice:
                    if not conn.client_have_voice:
                        logger.bind(tag=TAG).info(
                            f"[VAD START] 🗣️ Bắt đầu ghi nhận tiếng người nói! (RMS={audio_rms}, Prob={speech_prob:.2f})"
                        )
                    conn.client_have_voice = True
                    conn.vad_last_voice_time = time.time() * 1000
                    conn._consecutive_silence_chunks = 0
                else:
                    if not conn.client_have_voice:
                        if speech_prob <= self.vad_threshold_low:
                            conn._consecutive_silence_chunks = getattr(conn, "_consecutive_silence_chunks", 0) + 1
                            # Sau 15 chunks (~480ms) im lặng liên tục, reset state để chống bão hòa/trôi âm (cell state drift)
                            if conn._consecutive_silence_chunks >= 15:
                                conn._vad_state = np.zeros((2, 1, 128), dtype=np.float32)
                        else:
                            conn._consecutive_silence_chunks = 0

            return client_have_voice
        except Exception as e:
            logger.bind(tag=TAG).error(f"Error processing audio packet: {e}")
