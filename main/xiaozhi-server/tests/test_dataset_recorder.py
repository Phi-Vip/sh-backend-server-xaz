import os
import sys
import shutil
import unittest
import opuslib_next

current_dir = os.path.dirname(os.path.abspath(__file__))
server_root = os.path.dirname(current_dir)
if server_root not in sys.path:
    sys.path.insert(0, server_root)

from core.utils.dataset_recorder import DatasetRecorder, get_dataset_recorder

class TestDatasetRecorder(unittest.TestCase):
    def setUp(self):
        self.test_output_dir = os.path.join(server_root, "data", "test_wake_word_dataset")
        self.config = {
            "dataset_collector": {
                "enabled": 1,
                "output_dir": self.test_output_dir
            }
        }
        self.encoder = opuslib_next.Encoder(16000, 1, opuslib_next.APPLICATION_VOIP)

    def tearDown(self):
        if os.path.exists(self.test_output_dir):
            shutil.rmtree(self.test_output_dir, ignore_errors=True)

    def _make_dummy_opus_packets(self, count, fill_byte=b'\x01'):
        packets = []
        for _ in range(count):
            pcm = fill_byte * (960 * 2)
            pkt = self.encoder.encode(pcm, 960)
            packets.append(pkt)
        return packets

    def test_instant_spike_tail_slicing(self):
        """Kiểm tra instant_spike chỉ lấy đúng 1.0s (16,000 samples) mới nhất từ đuôi danh sách gói"""
        import wave
        recorder = DatasetRecorder(self.config)
        # 30 gói (13 gói cũ + 17 gói mới)
        packets = self._make_dummy_opus_packets(30, b'\x05')
        meta = {
            "trigger_type": "instant_spike",
            "score": 0.88,
            "packet_count": 17,
            "total_frames": 1,
            "total_samples": 16000,
            "label": "Xin chào sunhouse"
        }
        recorder.record(packets, meta=meta, device_id="test_device")

        # Xác minh file WAV đã được tạo trong thư mục instant_spikes
        found_files = []
        for root, _, files in os.walk(self.test_output_dir):
            for f in files:
                if f.endswith(".wav") and "SPIKE_SCORE_0.88" in f:
                    found_files.append(os.path.join(root, f))
        self.assertEqual(len(found_files), 1)

        with wave.open(found_files[0], "rb") as wf:
            self.assertEqual(wf.getnchannels(), 1)
            self.assertEqual(wf.getsampwidth(), 2)
            self.assertEqual(wf.getframerate(), 16000)
            self.assertEqual(wf.getnframes(), 16000)

    def test_smoothed_detect_two_frames(self):
        """Kiểm tra smoothed_detect (34 gói) lưu đủ 2 frame âm thanh kích hoạt FRAME1 và FRAME2, mỗi file 16,000 mẫu"""
        import wave
        recorder = DatasetRecorder(self.config)
        # 50 gói (16 gói cũ + 34 gói mới)
        packets = self._make_dummy_opus_packets(50, b'\x04')
        meta = {
            "trigger_type": "smoothed_detect",
            "score": 0.92,
            "packet_count": 34,
            "total_frames": 2,
            "total_samples": 32000,
            "frame_1": {"score": 0.88, "label": "Xin chào sunhouse"},
            "frame_2": {"score": 0.95, "label": "Xin chào sunhouse"}
        }
        recorder.record(packets, meta=meta, device_id="test_device")

        found_f1 = []
        found_f2 = []
        for root, _, files in os.walk(self.test_output_dir):
            for f in files:
                if f.endswith(".wav") and "FRAME1_SCORE_0.88" in f:
                    found_f1.append(os.path.join(root, f))
                elif f.endswith(".wav") and "FRAME2_SCORE_0.95" in f:
                    found_f2.append(os.path.join(root, f))
        self.assertEqual(len(found_f1), 1, "FRAME1 file phải tồn tại")
        self.assertEqual(len(found_f2), 1, "FRAME2 file phải tồn tại")

        for wav_path in (found_f1[0], found_f2[0]):
            with wave.open(wav_path, "rb") as wf:
                self.assertEqual(wf.getnchannels(), 1)
                self.assertEqual(wf.getsampwidth(), 2)
                self.assertEqual(wf.getframerate(), 16000)
                self.assertEqual(wf.getnframes(), 16000)

    def test_legacy_two_frame_smoothed_detect(self):
        """Kiểm tra smoothed_detect legacy (2 frames) lưu đúng 2 file FRAME1 và FRAME2"""
        recorder = DatasetRecorder(self.config)
        # 50 gói (16 gói cũ + 34 gói mới)
        packets = self._make_dummy_opus_packets(50, b'\x02')
        meta = {
            "trigger_type": "smoothed_detect",
            "packet_count": 34,
            "total_frames": 2,
            "frame_1": {"score": 0.82, "label": "Xin chào sunhouse"},
            "frame_2": {"score": 0.95, "label": "Xin chào sunhouse"}
        }
        recorder.record(packets, meta=meta, device_id="test_device")

        found_f1 = []
        found_f2 = []
        for root, _, files in os.walk(self.test_output_dir):
            for f in files:
                if f.endswith(".wav") and "FRAME1_SCORE_0.82" in f:
                    found_f1.append(os.path.join(root, f))
                elif f.endswith(".wav") and "FRAME2_SCORE_0.95" in f:
                    found_f2.append(os.path.join(root, f))
        self.assertEqual(len(found_f1), 1)
        self.assertEqual(len(found_f2), 1)

    def test_triplet_spike_capture(self):
        """Kiểm tra triplet_spike lưu đúng 3 gói âm thanh 1.0s liền kề (PRE, CENTER, POST)"""
        import wave
        recorder = DatasetRecorder(self.config)
        # 70 gói (20 gói cũ + 50 gói mới)
        packets = self._make_dummy_opus_packets(70, b'\x03')
        meta = {
            "trigger_type": "triplet_spike",
            "score": 0.86,
            "packet_count": 50,
            "total_frames": 3,
            "frame_duration_ms": 1000,
            "label": "Xin chào sunhouse"
        }
        recorder.record(packets, meta=meta, device_id="test_device")

        found_pre = []
        found_center = []
        found_post = []
        for root, _, files in os.walk(self.test_output_dir):
            for f in files:
                if f.endswith(".wav") and "PRE_-250MS_SCORE_0.86" in f:
                    found_pre.append(os.path.join(root, f))
                elif f.endswith(".wav") and "CENTER_0MS_SCORE_0.86" in f:
                    found_center.append(os.path.join(root, f))
                elif f.endswith(".wav") and "POST_+250MS_SCORE_0.86" in f:
                    found_post.append(os.path.join(root, f))

        self.assertEqual(len(found_pre), 1, "PRE file phải tồn tại")
        self.assertEqual(len(found_center), 1, "CENTER file phải tồn tại")
        self.assertEqual(len(found_post), 1, "POST file phải tồn tại")

        # Kiểm tra độ dài mỗi file WAV phải đúng 16,000 mẫu = 1.0s @ 16kHz
        for wav_path in (found_pre[0], found_center[0], found_post[0]):
            with wave.open(wav_path, "rb") as wf:
                self.assertEqual(wf.getnchannels(), 1)
                self.assertEqual(wf.getsampwidth(), 2)
                self.assertEqual(wf.getframerate(), 16000)
                self.assertEqual(wf.getnframes(), 16000)

if __name__ == "__main__":
    unittest.main()
