import unittest
import sys
import os

# Add main directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.providers.tts.base import TTSProviderBase


class MockTTSProvider(TTSProviderBase):
    def __init__(self):
        # Initialize basic attributes without network/audio initialization
        self.tts_text_buff = []
        self.processed_chars = 0
        self.is_first_sentence = True
        self.tts_stop_request = False
        self.punctuations = (
            "。", ".", "？", "?", "！", "!", "；", ";", "：", ":", "\n",
        )
        self.first_sentence_punctuations = (
            "，", "~", "、", ",", "。", ".", "？", "?", "！", "!", "；", ";", "：", ":", "\n",
        )

    async def text_to_speak(self, text, output_file):
        pass


class TestSentenceSegmentation(unittest.TestCase):
    def setUp(self):
        self.tts = MockTTSProvider()

    def test_decimal_point_not_split(self):
        """Kiểm tra số thập phân (4.5 tỷ năm) không bị cắt đôi tại dấu chấm"""
        stream_text = "Trái Đất ra đời cách đây khoảng 4.5 tỷ năm, từ những mảnh vật chất va đập và kết dính vào nhau quanh Mặt Trời non trẻ."
        self.tts.tts_text_buff = [stream_text]
        
        # Câu 1 phải ngắt sau dấu phẩy (vì 4.5 được bảo vệ, và độ dài trước dấu phẩy là 41 >= 35)
        seg1 = self.tts._get_segment_text()
        self.assertEqual(seg1, "Trái Đất ra đời cách đây khoảng 4.5 tỷ năm")
        self.assertFalse(self.tts.is_first_sentence)

        # Câu 2 lấy phần còn lại đến dấu chấm cuối
        seg2 = self.tts._get_segment_text()
        self.assertEqual(seg2, "từ những mảnh vật chất va đập và kết dính vào nhau quanh Mặt Trời non trẻ")

    def test_comma_decimal_not_split(self):
        """Kiểm tra số thập phân dùng dấu phẩy kiểu Việt Nam (3,14) không bị ngắt"""
        stream_text = "Số Pi xấp xỉ bằng 3,14159 và được sử dụng rộng rãi trong toán học hiện đại."
        self.tts.tts_text_buff = [stream_text]

        seg1 = self.tts._get_segment_text()
        self.assertEqual(seg1, "Số Pi xấp xỉ bằng 3,14159 và được sử dụng rộng rãi trong toán học hiện đại")

    def test_streaming_trailing_decimal_delayed(self):
        """Kiểm tra khi token đang stream dở dạng 'khoảng 4.' thì tạm hoãn ngắt"""
        # Giả sử stream mới gửi tới 'khoảng 4.'
        self.tts.tts_text_buff = ["Trái Đất ra đời cách đây khoảng 4."]
        seg = self.tts._get_segment_text()
        self.assertIsNone(seg)  # Phải chờ token tiếp theo, không được ngắt tại '4.'

        # Token tiếp theo '5 tỷ năm, ' đến
        self.tts.tts_text_buff.append("5 tỷ năm, ")
        seg1 = self.tts._get_segment_text()
        self.assertEqual(seg1, "Trái Đất ra đời cách đây khoảng 4.5 tỷ năm")

    def test_abbreviation_shield(self):
        """Kiểm tra từ viết tắt (TP. Hồ Chí Minh, GS. Nguyễn Văn A) không bị ngắt"""
        stream_text = "Hội thảo được tổ chức tại TP. Hồ Chí Minh với sự tham gia của GS. Nam."
        self.tts.tts_text_buff = [stream_text]

        seg1 = self.tts._get_segment_text()
        self.assertEqual(seg1, "Hội thảo được tổ chức tại TP. Hồ Chí Minh với sự tham gia của GS. Nam")

    def test_numbered_list_shield(self):
        """Kiểm tra danh sách số thứ tự (1. , 2. ) không bị cắt thành số cụt"""
        stream_text = "1. Mặt Trời là trung tâm của hệ Mặt Trời. 2. Trái Đất quay xung quanh."
        self.tts.tts_text_buff = [stream_text]

        seg1 = self.tts._get_segment_text()
        self.assertEqual(seg1, "1. Mặt Trời là trung tâm của hệ Mặt Trời")

    def test_first_sentence_weak_punctuation_pacing(self):
        """Kiểm tra dấu phẩy ở câu đầu tiên nếu dưới 35 ký tự sẽ không bị ngắt cụt"""
        # "Xin chào bạn," chỉ có 12 ký tự -> chưa đủ 35 ký tự -> gom tiếp đến dấu chấm
        stream_text = "Xin chào bạn, tôi là trợ lý ảo XiaoZhi. Hôm nay bạn thế nào?"
        self.tts.tts_text_buff = [stream_text]

        seg1 = self.tts._get_segment_text()
        self.assertEqual(seg1, "Xin chào bạn, tôi là trợ lý ảo XiaoZhi")

        seg2 = self.tts._get_segment_text()
        self.assertEqual(seg2, "Hôm nay bạn thế nào?")


if __name__ == "__main__":
    unittest.main()
