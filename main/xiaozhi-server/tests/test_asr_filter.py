import unittest
from core.utils.asr_filter import (
    check_asr_text_validity,
    VALID_SINGLE_WORDS,
    HALLUCINATION_BLACKLIST,
    STANDALONE_HALLUCINATIONS,
)


class TestASRFilter(unittest.TestCase):
    def test_single_word_whitelist(self):
        # Các từ 1 âm tiết hợp lệ
        valid_samples = [
            "OK", "ok", "Được", "được.", "Không", "không?", "Có", "có!",
            "Tiếp", "tiếp.", "Dừng", "Bật", "Tắt", "Mở", "Đóng", "Alo",
            "Vâng", "Dạ", "Ừ", "ừm", "1", "một", "hai", "thanks"
        ]
        for s in valid_samples:
            ok, reason = check_asr_text_validity(s)
            self.assertTrue(ok, f"Từ hợp lệ '{s}' không nên bị chặn: {reason}")

    def test_single_word_trash_and_clicks(self):
        # Các âm thanh tặc lưỡi, chép miệng, từ rác 1 âm tiết
        trash_samples = [
            "Tr.", "Tr", "Tch.", "Tch", "Tsk.", "Tsk", "Ah.", "Ah",
            "Shh.", "Shh", "Um.", "Um", "Pfft", "Grr", "Ch", "Chr"
        ]
        for s in trash_samples:
            ok, reason = check_asr_text_validity(s)
            self.assertFalse(ok, f"Từ rác '{s}' bắt buộc phải bị chặn: {reason}")
            self.assertIn("ngoài Whitelist", reason)

    def test_hallucination_blacklist(self):
        # Các cụm từ ảo giác kinh điển của Whisper
        hallucination_samples = [
            "subscribe",
            "SUBSCRIBE",
            "Hãy like và subscribe kênh của mình nhé!",
            "Nhớ ấn đăng ký kênh và bấm chuông thông báo",
            "La La School",
            "LA LA SCHOOL",
            "lala school",
            "Tập tiếp theo của La La School",
            "Ghiền Mì Gõ",
            "GHIỀN MÌ GÕ",
            "ghien mi go",
            "FAPtv cơm nguội",
            "Cảm ơn các bạn đã theo dõi video!",
            "Subtitles by SDS",
            "Phụ đề được thực hiện bởi nhóm dịch",
            "Để không bỏ lỡ những video mới nhất",
        ]
        for s in hallucination_samples:
            ok, reason = check_asr_text_validity(s)
            self.assertFalse(ok, f"Ảo giác '{s}' bắt buộc phải bị chặn: {reason}")
            self.assertIn("Blacklist", reason)

    def test_standalone_hallucinations(self):
        # Các câu ảo giác cảm ơn độc lập của Whisper khi micro chỉ có tiếng thở / khoảng lặng: chỉ độc lập là 'cảm ơn'
        standalone_samples = [
            "Cảm ơn", "Cảm ơn.", "cảm ơn!", "cảm ơn", "CẢM ƠN", "  cảm ơn.  "
        ]
        for s in standalone_samples:
            ok, reason = check_asr_text_validity(s)
            self.assertFalse(ok, f"Ảo giác cảm ơn độc lập '{s}' bắt buộc phải bị chặn: {reason}")
            self.assertIn("độc lập", reason)

    def test_commands_with_thank_you_not_blocked(self):
        # Các câu lệnh điều khiển, câu hỏi thực tế hoặc người dùng nói 'cảm ơn bạn' không bị chặn
        valid_commands = [
            "Cảm ơn bạn",
            "Bật đèn phòng khách giúp tôi, cảm ơn nhé",
            "Tắt quạt giùm mình, cảm ơn bạn",
            "Hôm nay thời tiết thế nào, cảm ơn",
            "Nói lời cảm ơn bằng tiếng Anh là gì?",
            "Cảm ơn em đã thông báo cho anh"
        ]
        for s in valid_commands:
            ok, reason = check_asr_text_validity(s)
            self.assertTrue(ok, f"Câu lệnh/lời nói thực tế '{s}' không được phép bị chặn nhầm: {reason}")

    def test_valid_multi_word_sentences(self):
        # Các câu bình thường tự nhiên của người dùng
        legit_sentences = [
            "Bật đèn phòng khách giúp tôi",
            "Hôm nay thời tiết thế nào?",
            "Mấy giờ rồi?",
            "Kể cho tôi một câu chuyện cười",
            "Tăng âm lượng lên năm mươi phần trăm"
        ]
        for s in legit_sentences:
            ok, reason = check_asr_text_validity(s)
            self.assertTrue(ok, f"Câu hợp lệ '{s}' không nên bị chặn: {reason}")

    def test_empty_or_punct_only(self):
        invalid_samples = ["", "   ", "...", "?!?,,", None]
        for s in invalid_samples:
            ok, reason = check_asr_text_validity(s)
            self.assertFalse(ok, f"Văn bản rỗng '{s}' phải trả về False: {reason}")


    def test_model_codes_and_numbers(self):
        # Các mã model, mã lỗi, số hiệu hoặc danh từ thiết bị đơn lẻ
        model_and_code_samples = [
            "HB82082", " nhmhp82082", "SHD6805", "SHB9101", "MMB82082",
            "82082", "6805", "7737", "E1", "E4", "E01", "E88",
            "bếp", "quạt", "đèn", "sunhouse", "xiaozhi", "shd", "shb"
        ]
        for s in model_and_code_samples:
            ok, reason = check_asr_text_validity(s)
            self.assertTrue(ok, f"Mã model/số/thiết bị '{s}' không được phép bị chặn: {reason}")


if __name__ == "__main__":
    unittest.main()

