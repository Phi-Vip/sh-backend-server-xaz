import os
import sys
import math
import struct
import wave
import json
import shutil
import unittest
import opuslib_next

# Thêm đường dẫn gốc server
current_dir = os.path.dirname(os.path.abspath(__file__))
server_root = os.path.dirname(current_dir)
if server_root not in sys.path:
    sys.path.insert(0, server_root)

from core.utils.dialogue_recorder import DialogueAudioRecorder, get_dialogue_recorder


class TestDialogueAudioRecorder(unittest.TestCase):
    def setUp(self):
        self.test_output_dir = os.path.join(server_root, "data", "test_dialogue_audio")
        self.config_enabled = {
            "dialogue_recorder": {
                "enabled": 1,
                "output_dir": self.test_output_dir
            }
        }
        self.config_disabled = {
            "dialogue_recorder": {
                "enabled": 0,
                "output_dir": self.test_output_dir
            }
        }

    def tearDown(self):
        if os.path.exists(self.test_output_dir):
            shutil.rmtree(self.test_output_dir, ignore_errors=True)

    def test_01_init_and_is_enabled(self):
        """Kiểm tra khởi tạo và cờ bật/tắt"""
        rec_on = DialogueAudioRecorder(self.config_enabled)
        self.assertTrue(rec_on.is_enabled())

        rec_off = DialogueAudioRecorder(self.config_disabled)
        self.assertFalse(rec_off.is_enabled())

        # Kiểm tra singleton getter
        rec_singleton = get_dialogue_recorder(self.config_enabled)
        self.assertIsNotNone(rec_singleton)

    def test_02_analyze_pcm_normal_and_clipped(self):
        """Kiểm tra tính toán âm học RMS, Peak và Clipping"""
        rec = DialogueAudioRecorder(self.config_enabled)

        # 1. Âm thanh bình thường (sóng sine biên độ 5000, 960 mẫu)
        num_samples = 960
        normal_samples = [int(5000 * math.sin(2 * math.pi * 440 * i / 16000)) for i in range(num_samples)]
        normal_pcm = struct.pack(f"<{num_samples}h", *normal_samples)

        metrics_normal = rec.analyze_pcm(normal_pcm)
        self.assertGreater(metrics_normal["rms"], 3000)
        self.assertLess(metrics_normal["rms"], 4000)
        self.assertGreater(metrics_normal["peak"], 4500)
        self.assertEqual(metrics_normal["clipping_count"], 0)
        self.assertEqual(metrics_normal["clipping_ratio"], 0.0)

        # 2. Âm thanh bị vỡ tiếng (Clipped: 100 mẫu vượt 31000)
        clipped_samples = normal_samples.copy()
        for i in range(100):
            clipped_samples[i] = 32000
        clipped_pcm = struct.pack(f"<{num_samples}h", *clipped_samples)

        metrics_clipped = rec.analyze_pcm(clipped_pcm)
        self.assertEqual(metrics_clipped["peak"], 32000)
        self.assertEqual(metrics_clipped["clipping_count"], 100)
        self.assertAlmostEqual(metrics_clipped["clipping_ratio"], (100 / 960) * 100.0, places=1)

    def test_03_record_session_creates_wav_and_json(self):
        """Kiểm tra giải mã Opus và xuất file WAV + JSON thực tế"""
        rec = DialogueAudioRecorder(self.config_enabled)

        # Tạo gói Opus 60ms giả lập bằng encoder
        encoder = opuslib_next.Encoder(16000, 1, opuslib_next.APPLICATION_VOIP)
        num_samples = 960
        samples = [int(3000 * math.sin(2 * math.pi * 440 * i / 16000)) for i in range(num_samples)]
        pcm_bytes = struct.pack(f"<{num_samples}h", *samples)
        opus_packet = encoder.encode(pcm_bytes, 960)
        self.assertGreater(len(opus_packet), 0)

        # Gọi hàm record_session
        packets = [opus_packet, opus_packet]  # 2 frames = 120ms
        rec.record_session(
            opus_packets=packets,
            device_id="TEST_DEVICE_ESP32",
            session_id="test-session-123",
            asr_text="Bật đèn phòng khách",
            tag="STT_SUCCESS"
        )

        # Kiểm tra xem file đã được ghi ra đĩa chưa
        date_folder = [d for d in os.listdir(self.test_output_dir) if os.path.isdir(os.path.join(self.test_output_dir, d))]
        self.assertEqual(len(date_folder), 1)

        target_dir = os.path.join(self.test_output_dir, date_folder[0])
        files = os.listdir(target_dir)

        wav_files = [f for f in files if f.endswith(".wav")]
        json_files = [f for f in files if f.endswith(".json")]

        self.assertEqual(len(wav_files), 1)
        self.assertEqual(len(json_files), 1)

        # Kiểm tra file WAV hợp lệ
        wav_path = os.path.join(target_dir, wav_files[0])
        with wave.open(wav_path, "rb") as wf:
            self.assertEqual(wf.getnchannels(), 1)
            self.assertEqual(wf.getsampwidth(), 2)
            self.assertEqual(wf.getframerate(), 16000)
            self.assertEqual(wf.getnframes(), 960 * 2)

        # Kiểm tra file JSON hợp lệ
        json_path = os.path.join(target_dir, json_files[0])
        with open(json_path, "r", encoding="utf-8") as jf:
            meta = json.load(jf)
            self.assertEqual(meta["session_id"], "test-session-123")
            self.assertEqual(meta["device_id"], "TEST_DEVICE_ESP32")
            self.assertEqual(meta["packet_count"], 2)
            self.assertIn("audio_metrics", meta)
            self.assertIn("rms", meta["audio_metrics"])

    def test_04_fault_isolation_on_disk_error(self):
        """Kiểm tra cô lập lỗi: Lỗi ghi đĩa không bao giờ ném Exception làm sập ứng dụng"""
        # Trỏ output_dir vào một đường dẫn không hợp lệ (trên Windows: tên chứa ký tự cấm NUL)
        bad_config = {
            "dialogue_recorder": {
                "enabled": 1,
                "output_dir": "Z:\\invalid_path_does_not_exist\\non_writable\0"
            }
        }
        recorder = DialogueAudioRecorder(bad_config)
        # Giả lập ghi dữ liệu -> không được ném exception ra ngoài
        try:
            recorder.record_session(
                opus_packets=[b"\x00" * 40],
                device_id="TEST_DEVICE",
                session_id="session-err-test",
                asr_text="Lỗi mô phỏng",
                tag="TEST_FAULT"
            )
        except Exception as e:
            self.fail(f"record_session không được raise Exception khi gặp sự cố đĩa! Lỗi: {e}")


if __name__ == "__main__":
    unittest.main()

