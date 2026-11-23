import unittest
import os
import sys

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
os.chdir(BASE_DIR)

from core.providers.tts.edge import TTSProvider
from core.providers.tts.dto.dto import SentenceType

class TestOptimizedEdgeTTS(unittest.TestCase):
    def setUp(self):
        config = {
            "voice": "vi-VN-HoaiMyNeural",
            "volume": 50,
            "rate": 0,
            "pitch": 0,
        }
        self.tts = TTSProvider(config, delete_audio_file=True)

    def tearDown(self):
        if hasattr(self, "tts"):
            self.tts._close_fallback_loop()

    def test_segmentation_punctuations(self):
        """Kiểm tra EdgeTTS không ngắt câu tại dấu phẩy"""
        self.assertNotIn(",", self.tts.first_sentence_punctuations)
        self.assertNotIn("，", self.tts.first_sentence_punctuations)
        self.assertIn(".", self.tts.first_sentence_punctuations)
        self.assertIn("?", self.tts.first_sentence_punctuations)
        self.assertIn("!", self.tts.first_sentence_punctuations)

    def test_to_tts_stream_single_sentence(self):
        """Kiểm tra tổng hợp câu có dấu phẩy nguyên vẹn"""
        text = "Bác Hồ sinh ngày 19 tháng 5 năm 1890 tại làng Kim Liên, huyện Nam Đàn, tỉnh Nghệ An nhé."
        frames = []
        self.tts.to_tts_stream(text, opus_handler=lambda f: frames.append(f))
        self.assertGreater(len(frames), 0, "Phải có frame opus được tạo ra")
        print(f"\n[Test 1] Generated {len(frames)} Opus frames for single sentence with comma.")

    def test_to_tts_stream_consecutive_sentences(self):
        """Kiểm tra 2 câu liên tiếp với Safety Pacing không bị Microsoft chặn"""
        s1 = "Bác Hồ sinh ngày 19 tháng 5 năm 1890 tại làng Kim Liên, huyện Nam Đàn, tỉnh Nghệ An."
        s2 = "Người là vị lãnh tụ thiên tài của Đảng và nhân dân Việt Nam."
        
        frames_1 = []
        self.tts.to_tts_stream(s1, opus_handler=lambda f: frames_1.append(f))
        self.assertGreater(len(frames_1), 0)
        print(f"[Test 2] S1 generated {len(frames_1)} Opus frames.")

        frames_2 = []
        self.tts.to_tts_stream(s2, opus_handler=lambda f: frames_2.append(f))
        self.assertGreater(len(frames_2), 0)
        print(f"[Test 2] S2 generated {len(frames_2)} Opus frames.")

if __name__ == "__main__":
    unittest.main()
