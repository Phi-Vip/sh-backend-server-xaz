"""
ASR Filter Module: Bộ lọc chống ảo giác (Hallucination) và tạp âm cho Whisper STT
Cung cấp:
1. VALID_SINGLE_WORDS: Whitelist các từ 1 âm tiết / từ đơn hợp lệ trong giao tiếp AI (tiếng Việt & từ mượn).
   Nếu kết quả nhận diện chỉ có 1 từ duy nhất, từ đó BẮT BUỘC phải nằm trong Whitelist này mới được gửi sang LLM.
   Ngược lại (ví dụ 'Tch', 'Tr', 'Tsk', 'Ah', 'Shh' do tặc lưỡi/chép miệng) sẽ bị loại bỏ hoàn toàn.
2. HALLUCINATION_BLACKLIST: Blacklist các câu/cụm từ ảo giác kinh điển của Whisper (như 'subscribe', 'La La School', 'Ghiền Mì Gõ'...).
   Nếu văn bản chứa các cụm từ này sẽ bị chặn ngay lập tức, không gửi sang LLM.
"""

import re
from typing import Tuple

# ==============================================================================
# 1. WHITELIST: TỪ 1 ÂM TIẾT / TỪ ĐƠN ĐƯỢC PHÉP (ALLOWLIST)
# ==============================================================================
# Bạn có thể tự do thêm hoặc bớt các từ 1 âm tiết phù hợp với nhu cầu sử dụng của bạn:
VALID_SINGLE_WORDS = {
    # --- [A. Khẳng định / Đồng ý / Đồng thuận] ---
    "có", "được", "ừ", "uh", "ừm", "uhm", "vâng", "dạ", "rồi", "đúng", "chuẩn", "chính",
    "ok", "okay", "oke", "okie", "k", "yes", "yep", "chắc", "rõ",

    # --- [B. Phủ định / Từ chối / Không đồng thuận] ---
    "không", "hông", "hổng", "ko", "kô", "chưa", "thôi", "đừng", "sai", "hủy", "huỷ", "bỏ", "no", "nope",

    # --- [C. Điều khiển hội thoại / Luồng tương tác] ---
    "tiếp", "dừng", "ngừng", "ngắt", "nghỉ", "lại", "nói", "kể", "hết", "xong", "chậm", "nhanh",

    # --- [D. Lệnh điều khiển thiết bị Smarthome 1 âm tiết & danh từ thiết bị] ---
    "bật", "tắt", "mở", "đóng", "tăng", "giảm", "lên", "xuống", "đổi", "chuyển", "sáng", "tối",
    "bếp", "quạt", "đèn", "nhạc", "loa", "tivi", "máy", "nồi", "chảo", "ấm", "lọc", "nước",
    "khóa", "cửa", "chuông", "phòng", "nhà", "wifi", "bluetooth", "điện", "gas", "hút",

    # --- [E. Số đếm / Lựa chọn Menu / Đơn vị] ---
    "không", "một", "mốt", "hai", "ba", "bốn", "tư", "năm", "sáu", "bảy", "bẩy", "tám", "chín", "mười",
    "0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "nhất", "nhì",
    "độ", "w", "v", "lít", "kg", "gam", "phút", "giây", "giờ",

    # --- [F. Chào hỏi / Gọi đáp / Thưa gửi] ---
    "ơi", "ê", "alo", "chào", "hi", "hello",

    # --- [G. Từ để hỏi ngắn / Hành động nghiệp vụ] ---
    "sao", "gì", "ai", "đâu", "lỗi", "hỏi", "tìm", "xem", "check", "giúp", "chỉ", "đo", "đặt", "chọn", "gọi", "đọc",

    # --- [H. Xã giao ngắn & Tên hệ thống / Tiền tố model] ---
    "thanks", "thank", "sunhouse", "xiaozhi", "bot", "ai", "app", "web", "iot",
    "shd", "shb", "sha", "shr", "mmb", "htd", "apb", "st", "shg", "sbd",
}

# ==============================================================================
# 2. BLACKLIST: CÁC CỤM TỪ ẢO GIÁC ĐIỂN HÌNH CỦA WHISPER (HALLUCINATIONS)
# ==============================================================================
# Các cụm từ này xuất hiện do Whisper học từ phụ đề YouTube tiếng Việt khi gặp khoảng lặng/tạp âm.
# Bất kỳ câu nào chứa các cụm từ này (substring) đều bị loại bỏ ngay lập tức.
# Bạn có thể thêm hoặc bớt các cụm từ tại đây:
HALLUCINATION_BLACKLIST = [
    # --- [A. Kêu gọi Subscribe / Đăng ký kênh YouTube] ---
    "subscribe", "subcribe", "đăng ký kênh", "hãy đăng ký", "nhớ đăng ký", "ấn đăng ký",
    "like và sub", "like and sub", "like & sub",
    "nhớ bấm chuông", "nhấn chuông", "bấm chuông", "chuông thông báo",

    # --- [B. Web-drama / Kênh YouTube trong tập dữ liệu Whisper] ---
    "la la school", "lala school",
    "ghiền mì gõ", "ghien mi go",
    "faptv", "fap tv",
    "big cat", "bigcat",
    "kem xôi", "kem xoi",
    "điền quân", "dien quan",
    "vtv go", "vtvgo", "vtv digital",

    # --- [C. Lời chào kết video / Lời chúc rập khuôn trong phụ đề] ---
    "cảm ơn các bạn đã theo dõi", "cảm ơn các bạn đã xem",
    "cảm ơn đã theo dõi", "cảm ơn đã xem video",
    "cảm ơn mọi người đã theo dõi", "cảm ơn mọi người đã xem",
    "cảm ơn quý vị đã theo dõi", "cảm ơn quý vị đã xem",
    "hẹn gặp lại các bạn trong", "hẹn gặp lại các bạn ở", "hẹn gặp lại các bạn",
    "chúc các bạn một ngày tốt lành", "chúc các bạn nghe nhạc vui vẻ", "chúc các bạn xem video vui vẻ",
    "đón xem tập tiếp theo", "mời các bạn đón xem",
    "để không bỏ lỡ những video", "để không bỏ lỡ các video", "để không bỏ lỡ video",
    "không bỏ lỡ những video", "không bỏ lỡ video",
    "đừng bỏ lỡ những video", "đừng bỏ lỡ video",
    "video hấp dẫn", "video mới nhất",
    "thank you for watching", "thanks for watching",

    # --- [D. Watermark phụ đề / Bản quyền] ---
    "subtitles by", "subtitle by", "transcribed by", "translated by",
    "phụ đề bởi", "phụ đề được thực hiện", "thực hiện phụ đề",
    "bản quyền thuộc về", "copyright by",
]

# ==============================================================================
# 3. STANDALONE BLACKLIST: CÁC CÂU/CỤM TỪ ẢO GIÁC ĐƠN LẬP (EXACT MATCH)
# ==============================================================================
# Whisper rất hay tự sinh duy nhất từ 'cảm ơn' khi gặp khoảng lặng/tiếng thở.
# QUY TẮC CỐT LÕI: CHỈ chặn khi TOÀN BỘ câu nhận diện chỉ độc lập là 'cảm ơn' (không phân biệt hoa/thường, dấu câu).
# Nếu câu chứa mệnh lệnh hoặc nội dung thực tế (ví dụ: "Bật đèn giúp tôi, cảm ơn nhé"),
# hệ thống VẪN CHO QUA bình thường để không chặn nhầm câu lệnh của người dùng.
STANDALONE_HALLUCINATIONS = {
    "cảm ơn",
}


def check_asr_text_validity(raw_text: str) -> Tuple[bool, str]:
    """
    Kiểm tra văn bản ASR có hợp lệ để gửi LLM hay không.
    Trả về:
        (True, reason): Nếu văn bản hợp lệ
        (False, reason): Nếu văn bản bị loại bỏ (ảo giác hoặc từ rác)
    """
    if not raw_text or not isinstance(raw_text, str):
        return False, "Văn bản rỗng hoặc không đúng định dạng"

    # Chuẩn hóa: loại bỏ toàn bộ dấu câu, ký tự đặc biệt, chuyển về chữ thường
    cleaned = re.sub(r'[^\w\s]', ' ', raw_text).strip().lower()
    cleaned = re.sub(r'\s+', ' ', cleaned)
    words = cleaned.split()

    if not words:
        return False, "Không có nội dung sau khi bỏ ký tự đặc biệt"

    # 1. Kiểm tra Blacklist ảo giác (Không phân biệt hoa thường: 'La La School', 'la la school'...)
    for pattern in HALLUCINATION_BLACKLIST:
        if pattern and pattern.strip().lower() in cleaned:
            return False, f"Chứa cụm từ ảo giác trong Blacklist: '{pattern}'"

    # 2. Kiểm tra ảo giác cảm ơn độc lập (Standalone Hallucinations):
    # Whisper hay tự sinh "Cảm ơn.", "Cảm ơn bạn." khi micro chỉ có tiếng thở/khoảng lặng.
    if cleaned in STANDALONE_HALLUCINATIONS:
        return False, f"Câu ảo giác cảm ơn độc lập: '{cleaned}'"

    # 3. Kiểm tra từ đơn (Nếu kết quả nhận dạng chỉ có đúng 1 từ)
    if len(words) == 1:
        single_word = words[0]

        # QUY TẮC CỐT LÕI: Nếu từ chứa chữ số (Mã model: 'HB82082', 'nhmhp82082', 'SHD6805';
        # Số hiệu: '82082', '6805'; Mã lỗi: 'E1', 'E4'...), tuyệt đối KHÔNG PHẢI tạp âm tặc lưỡi.
        # Chuyển ngay cho LLM và MCP Tool xử lý.
        if re.search(r'\d', single_word):
            return True, f"Mã model/số hiệu/mã lỗi chứa chữ số hợp lệ: '{single_word}'"

        valid_words_lower = {w.strip().lower() for w in VALID_SINGLE_WORDS}
        if single_word in valid_words_lower:
            return True, f"Từ đơn hợp lệ trong Whitelist: '{single_word}'"
        else:
            return False, f"Từ đơn ngoài Whitelist: '{single_word}' (nghi vấn tiếng tặc lưỡi/click mic/ảo giác)"

    # 3. Câu từ 2 từ trở lên không chứa từ cấm -> Hợp lệ
    return True, f"Hợp lệ ({len(words)} từ)"
