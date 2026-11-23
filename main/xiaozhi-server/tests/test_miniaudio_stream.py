#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script kiểm thử độc lập và benchmarking:
Giải mã In-Memory MP3 Bitstream sang raw PCM 24kHz Mono 16-bit bằng thư viện C miniaudio.
Tối ưu hóa chuyên biệt cho mạch DAC I2S MAX98357A của XiaoZhi ESP32.

Tham chiếu: CAC_MUC_TAI_CAU_TRUC_BACKEND_SERVER_XIAOZHI.md - Mục III.3.1
"""

import sys
import os
import time
import unittest
import asyncio

# Thêm thư mục gốc của server vào sys.path
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import miniaudio
from core.utils.util import mp3_bytes_to_pcm_stream_fast, decode_mp3_to_pcm_bytes_fast
from core.utils.opus_encoder_utils import OpusEncoderUtils

SAMPLE_MP3_PATH = os.path.join(os.path.dirname(__file__), "sample_24k.mp3")


class TestMiniaudioStream(unittest.TestCase):
    sample_mp3: bytes = b""

    @classmethod
    def setUpClass(cls):
        print("\n=======================================================")
        print("  KIỂM THỬ ĐỘC LẬP & BENCHMARK: IN-MEMORY MINIAUDIO")
        print(f"  - Thư viện miniaudio version: {miniaudio.__version__}")
        print("  - Tần số mục tiêu: 24000 Hz (DAC MAX98357A)")
        print("  - Kênh: 1 (Mono) | Độ sâu mẫu: 16-bit (S16LE)")
        print("=======================================================")

        if os.path.exists(SAMPLE_MP3_PATH):
            with open(SAMPLE_MP3_PATH, "rb") as f:
                cls.sample_mp3 = f.read()
        else:
            try:
                import edge_tts

                async def fetch_sample():
                    comm = edge_tts.Communicate("Xin chào", voice="vi-VN-HoaiMyNeural", connect_timeout=5)
                    chunks = [c["data"] async for c in comm.stream() if c["type"] == "audio"]
                    return b"".join(chunks)

                cls.sample_mp3 = asyncio.run(fetch_sample())
                with open(SAMPLE_MP3_PATH, "wb") as f:
                    f.write(cls.sample_mp3)
            except Exception as e:
                raise RuntimeError(f"Không thể khởi tạo mẫu MP3 thử nghiệm: {e}")

    def test_01_miniaudio_installed(self):
        """1. Kiểm tra gói miniaudio đã cài đặt và sẵn sàng hoạt động"""
        self.assertIsNotNone(miniaudio)
        self.assertTrue(hasattr(miniaudio, "decode"))

    def test_02_decode_mp3_to_pcm_benchmark(self):
        """2. Đo lường tốc độ giải mã In-Memory MP3 sang PCM 24kHz (Benchmark < 5ms)"""
        self.assertGreater(len(self.sample_mp3), 0)

        # Đo thời gian giải mã bằng miniaudio
        t_start = time.perf_counter()
        decoded = miniaudio.decode(self.sample_mp3, nchannels=1, sample_rate=24000)
        t_elapsed_ms = (time.perf_counter() - t_start) * 1000

        pcm_bytes = decoded.samples.tobytes()

        print(f"\n[BENCHMARK] Thời gian giải mã: {t_elapsed_ms:.2f} ms")
        print(f"[BENCHMARK] Dung lượng MP3: {len(self.sample_mp3)} bytes -> PCM: {len(pcm_bytes)} bytes")
        print(f"[BENCHMARK] Tần số mẫu: {decoded.sample_rate} Hz, Số kênh: {decoded.nchannels}")

        self.assertEqual(decoded.sample_rate, 24000, "Tần số mẫu phải là 24000Hz cho MAX98357A")
        self.assertEqual(decoded.nchannels, 1, "Kênh âm thanh phải là Mono (1 channel)")
        self.assertLess(t_elapsed_ms, 15.0, f"Thời gian giải mã phải < 15ms (thực tế: {t_elapsed_ms:.2f}ms)")
        self.assertEqual(len(pcm_bytes) % 2, 0, "Dữ liệu PCM 16-bit phải chia hết cho 2 bytes/sample")

    def test_03_decode_mp3_to_pcm_bytes_fast(self):
        """3. Kiểm tra hàm tiện ích decode_mp3_to_pcm_bytes_fast trong util.py"""
        pcm = decode_mp3_to_pcm_bytes_fast(self.sample_mp3, sample_rate=24000)
        self.assertIsInstance(pcm, bytes)
        self.assertGreater(len(pcm), 0)
        self.assertEqual(len(pcm) % 2, 0)
        print(f"[DECODE_FAST] Đã decode thành công {len(pcm)} bytes raw PCM 24kHz.")

    def test_04_mp3_bytes_to_pcm_stream_fast_with_opus(self):
        """4. Kiểm tra pipeline trọn gói: MP3 -> miniaudio PCM 24kHz -> Opus Encoder (60ms frames)"""
        encoder = OpusEncoderUtils(sample_rate=24000, channels=1, frame_size_ms=60)
        opus_frames = []

        def capture_opus(frame):
            opus_frames.append(frame)

        mp3_bytes_to_pcm_stream_fast(
            self.sample_mp3,
            is_opus=True,
            callback=capture_opus,
            sample_rate=24000,
            opus_encoder=encoder,
        )

        # Kiểm tra đã sinh ra frame Opus
        self.assertGreater(len(opus_frames), 0, "Phải sinh ra ít nhất 1 frame Opus 60ms")
        for frame in opus_frames:
            self.assertIsInstance(frame, bytes)
            self.assertGreater(len(frame), 0)

        print(f"[PIPELINE] Đã đóng gói thành công {len(opus_frames)} khung Opus 60ms chuẩn 24kHz.")


if __name__ == "__main__":
    unittest.main()
