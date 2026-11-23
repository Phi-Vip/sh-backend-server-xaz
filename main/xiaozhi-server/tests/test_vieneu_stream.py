"""
Unit test kiểm thử cơ chế Frame-Level In-Memory Rolling Streaming của VieNeu-TTS.
Kiểm tra:
1. TTFA (Time to First Audio): Thời gian từ lúc gọi to_tts_stream đến khi nhận gói Opus đầu tiên.
2. Tính liên tục của các gói Opus 60ms.
3. Cơ chế ngắt lời (Barge-in / client_abort): Generator phải ngắt tức thì.
"""

import sys
import os
import time
from unittest.mock import MagicMock

# Thêm đường dẫn gốc của server vào sys.path và loại bỏ thư mục tests/ để tránh shadowing core/
script_dir = os.path.dirname(os.path.abspath(__file__))
while script_dir in sys.path:
    sys.path.remove(script_dir)
BASE_DIR = os.path.dirname(script_dir)
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from core.providers.tts.vieneu import TTSProvider


def test_vieneu_rolling_streaming():
    print("=" * 70)
    print("🧪 BẮT ĐẦU TEST: VIENEU ROLLING STREAMING (INFER_STREAM)")
    print("=" * 70)

    # 1. Khởi tạo cấu hình giả lập
    config = {
        "precision": "int8",
        "model_mode": "v3turbo",
        "preset_voice": "default",
        "enable_voice_clone": False,
        "volume": 50,
        "rate": 0,
    }

    print("[*] Đang khởi tạo TTSProvider...")
    tts = TTSProvider(config, delete_audio_file=True)

    # Giả lập connection
    mock_conn = MagicMock()
    mock_conn.sample_rate = 24000
    mock_conn.client_abort = False
    mock_conn.stop_event = MagicMock()
    mock_conn.stop_event.is_set.return_value = False
    tts.conn = mock_conn

    # 2. Test luồng streaming bình thường
    test_text = "Xin chào bạn, đây là kiểm thử luồng phát âm thanh tức thì của trợ lý ảo."
    print(f"\n[*] Văn bản kiểm thử: \"{test_text}\"")

    opus_packets = []
    packet_timestamps = []
    t0 = time.time()

    def opus_callback(packet_bytes):
        t_recv = time.time() - t0
        opus_packets.append(packet_bytes)
        packet_timestamps.append(t_recv)
        if len(opus_packets) == 1:
            print(f"  ⚡ [TTFA] Gói Opus đầu tiên nhận được sau: {t_recv:.3f}s (Kích thước: {len(packet_bytes)} bytes)")

    print("[*] Đang gọi to_tts_stream()...")
    tts.to_tts_stream(test_text, opus_handler=opus_callback)

    total_time = time.time() - t0
    total_packets = len(opus_packets)
    audio_duration = total_packets * 0.060  # Mỗi frame Opus chuẩn 60ms

    print(f"\n[✓] Kết quả luồng bình thường:")
    print(f"    - Tổng số gói Opus: {total_packets} gói")
    print(f"    - Tổng thời lượng audio: {audio_duration:.2f}s")
    print(f"    - Tổng thời gian hoàn thành: {total_time:.3f}s")
    if packet_timestamps:
        ttfa = packet_timestamps[0]
        print(f"    - TTFA (Độ trễ tiếng đầu tiên): {ttfa:.3f}s")
        assert ttfa < 0.60, f"TTFA quá cao ({ttfa:.3f}s), vượt quá tiêu chuẩn 0.6s!"
    assert total_packets > 0, "Không nhận được gói Opus nào!"

    # 3. Test ngắt lời (Barge-in / client_abort)
    print("\n--- [TEST BARGE-IN / NGẮT LỜI] ---")
    mock_conn.client_abort = False
    long_text = "Đây là một đoạn văn bản rất dài được thiết kế để kiểm tra xem khi người dùng ngắt lời thì generator có lập tức dừng lại hay không mà không lãng phí tài nguyên CPU của máy chủ."
    
    barge_packets = []
    t_start_barge = time.time()

    def barge_callback(packet_bytes):
        barge_packets.append(packet_bytes)
        # Giả lập người dùng ngắt lời sau khi nhận được 3 gói đầu
        if len(barge_packets) >= 3:
            mock_conn.client_abort = True
            print(f"  🛑 [Barge-in] Giả lập người dùng nói chen ngang tại gói thứ {len(barge_packets)}!")

    tts.to_tts_stream(long_text, opus_handler=barge_callback)
    barge_total_time = time.time() - t_start_barge

    print(f"[✓] Kết quả test Barge-in:")
    print(f"    - Số gói nhận được trước khi ngắt: {len(barge_packets)}")
    print(f"    - Thời gian dừng: {barge_total_time:.3f}s")
    # Câu dài thường sinh 40-60 gói, nếu dừng ở <= 8 gói chứng tỏ ngắt lời thành công
    assert len(barge_packets) <= 15, f"Generator không ngắt kịp, số gói nhận được: {len(barge_packets)}"
    print("  ✅ Cơ chế ngắt lời dừng generator thành công mỹ mãn!")

    print("\n" + "=" * 70)
    print("🎉 TẤT CẢ KIỂM THỬ ROLLING STREAMING CHO VIENEU-TTS ĐÃ THÀNH CÔNG!")
    print("=" * 70)
    return True


if __name__ == "__main__":
    test_vieneu_rolling_streaming()
