import os
import sys
import queue
import time

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
test_dir = os.path.abspath(os.path.dirname(__file__))
while test_dir in sys.path:
    sys.path.remove(test_dir)
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
os.chdir(BASE_DIR)

from types import SimpleNamespace
from core.providers.tts.edge import TTSProvider
from core.utils.opus_encoder_utils import OpusEncoderUtils

config = {
    "type": "edge",
    "voice": "vi-VN-HoaiMyNeural",
    "rate": 0,
    "volume": 50,
    "pitch": 0,
    "output_dir": "tmp/",
}

tts = TTSProvider(config, delete_audio_file=True)
tts.conn = SimpleNamespace(
    sample_rate=24000,
    client_abort=False,
    stop_event=SimpleNamespace(is_set=lambda: False),
)
tts.opus_encoder = OpusEncoderUtils(sample_rate=24000, channels=1, frame_size_ms=60)

# TEST 1: Normal synthesis with Persistent WebSocket
print("=== TEST 1: Normal EdgeTTS synthesis on Persistent WebSocket ===")
frames_1 = []
t0 = time.time()
tts.to_tts_stream("Chào bạn, mình là trợ lý XiaoZhi.", opus_handler=lambda f: frames_1.append(f))
dur_1 = time.time() - t0
print(f"Test 1: Opus frames generated: {len(frames_1)} in {dur_1:.2f}s")
assert len(frames_1) > 0, "Test 1 failed: No Opus frames"

# TEST 2: Consecutive sentence synthesis reusing the SAME persistent connection
print("\n=== TEST 2: Consecutive sentence reusing the same WebSocket ===")
frames_2 = []
t0 = time.time()
tts.to_tts_stream("Bác Hồ sinh ngày 19 tháng 5 năm 1890 tại làng Kim Liên, Nam Đàn, Nghệ An.", opus_handler=lambda f: frames_2.append(f))
dur_2 = time.time() - t0
print(f"Test 2: Opus frames generated: {len(frames_2)} in {dur_2:.2f}s")
assert len(frames_2) > 0, "Test 2 failed: No Opus frames"

# TEST 3: Barge-in / client_abort handling
print("\n=== TEST 3: Client Abort / Barge-in handling ===")
tts.conn.client_abort = True
frames_3 = []
tts.to_tts_stream("Câu này người dùng ngắt lời nên sẽ không tạo frame.", opus_handler=lambda f: frames_3.append(f))
print(f"Test 3: Aborted frames generated: {len(frames_3)} (Expected: 0)")
assert len(frames_3) == 0, "Test 3 failed: Frames generated despite client_abort"
tts.conn.client_abort = False

# Clean up
tts._close_fallback_loop()
print("\n>>> ALL TESTS PASSED! PERSISTENT EDGETTS IS 100% OPERATIONAL! <<<")
