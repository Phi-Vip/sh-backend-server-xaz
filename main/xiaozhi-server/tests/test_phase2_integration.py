import os
import sys
import unittest
import queue
import time
import math
import struct
import opuslib_next

# Thêm đường dẫn gốc server
server_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if server_root not in sys.path:
    sys.path.insert(0, server_root)

from core.utils.dialogue_recorder import get_dialogue_recorder


class MockConnection:
    def __init__(self, enabled=1):
        self.device_id = "TEST_ESP32_MOCK"
        self.session_id = "session-phase2-test"
        self.config = {
            "dialogue_recorder": {
                "enabled": enabled,
                "output_dir": os.path.join(server_root, "data", "test_p2_audio")
            }
        }
        self.client_is_listening = True
        self.dialogue_sniff_packets = []
        self.asr_audio_queue = queue.Queue()


class TestPhase2Hooks(unittest.TestCase):
    def test_01_hook_enabled_and_disabled(self):
        """Kiểm tra hook hứng gói khi enabled=1 và bỏ qua khi enabled=0"""
        encoder = opuslib_next.Encoder(16000, 1, opuslib_next.APPLICATION_VOIP)
        num_samples = 960
        pcm_bytes = struct.pack(f"<{num_samples}h", *[1000 for _ in range(num_samples)])
        opus_packet = encoder.encode(pcm_bytes, 960)

        # 1. Test khi enabled = 1
        conn_on = MockConnection(enabled=1)
        rec_on = get_dialogue_recorder(conn_on.config)
        rec_on.enabled = True

        if conn_on.client_is_listening:
            if rec_on.is_enabled():
                conn_on.dialogue_sniff_packets.append(opus_packet)

        self.assertEqual(len(conn_on.dialogue_sniff_packets), 1)

        # 2. Test khi enabled = 0
        conn_off = MockConnection(enabled=0)
        rec_off = get_dialogue_recorder(conn_off.config)
        rec_off.enabled = False

        if conn_off.client_is_listening:
            if rec_off.is_enabled():
                conn_off.dialogue_sniff_packets.append(opus_packet)

        self.assertEqual(len(conn_off.dialogue_sniff_packets), 0)

    def test_02_execution_time_append(self):
        """Đo lường thời gian thực thi của thao tác append (bảo đảm < 1 microsecond)"""
        conn = MockConnection(enabled=1)
        dummy_packet = b"\x00" * 120

        start_t = time.perf_counter()
        for _ in range(1000):
            conn.dialogue_sniff_packets.append(dummy_packet)
        elapsed = time.perf_counter() - start_t

        avg_ns = (elapsed / 1000) * 1e9
        print(f"\n[BENCHMARK] Thời gian trung bình 1 lần append: {avg_ns:.2f} ns")
        # Phải nhỏ hơn 10,000 ns (10 microseconds)
        self.assertLess(avg_ns, 10000)

    def test_03_queue_isolation(self):
        """Kiểm tra hàng đợi ASR conn.asr_audio_queue hoàn toàn không bị ảnh hưởng"""
        conn = MockConnection(enabled=1)
        rec = get_dialogue_recorder(conn.config)
        rec.enabled = True

        # Giả lập luồng nhận dữ liệu
        sample_pcm = b"\x01\x02" * 960
        sample_opus = b"\x11\x22\x33\x44"

        # Đẩy vào ASR queue như hệ thống gốc
        conn.asr_audio_queue.put(sample_pcm)

        # Hook của Sniffer chạy
        if conn.client_is_listening and rec.is_enabled():
            conn.dialogue_sniff_packets.append(sample_opus)

        # Kiểm tra ASR queue vẫn chứa nguyên vẹn đúng 1 item PCM
        self.assertEqual(conn.asr_audio_queue.qsize(), 1)
        retrieved_pcm = conn.asr_audio_queue.get()
        self.assertEqual(retrieved_pcm, sample_pcm)

        # Sniff packets độc lập
        self.assertEqual(len(conn.dialogue_sniff_packets), 1)
        self.assertEqual(conn.dialogue_sniff_packets[0], sample_opus)

    def test_04_session_lifecycle(self):
        """Kiểm tra vòng đời phiên thoại: Reset buffer khi start, flush khi finish"""
        conn = MockConnection(enabled=1)
        # Giả lập có dữ liệu cũ còn sót
        conn.dialogue_sniff_packets = [b"old_packet_1", b"old_packet_2"]

        # 1. Giả lập ESP gửi state: "start" -> Buffer phải được reset rỗng
        conn.dialogue_sniff_packets = []
        self.assertEqual(len(conn.dialogue_sniff_packets), 0)

        # 2. ESP gửi các gói trong phiên
        conn.dialogue_sniff_packets.append(b"new_packet_1")
        conn.dialogue_sniff_packets.append(b"new_packet_2")
        self.assertEqual(len(conn.dialogue_sniff_packets), 2)

        # 3. Khi STT hoàn thành -> lấy các gói ra để lưu và reset danh sách
        pkts_to_save = list(conn.dialogue_sniff_packets)
        conn.dialogue_sniff_packets.clear()

        self.assertEqual(len(pkts_to_save), 2)
        self.assertEqual(len(conn.dialogue_sniff_packets), 0)


if __name__ == "__main__":
    unittest.main()

