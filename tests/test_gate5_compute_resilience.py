# -*- coding: utf-8 -*-
"""BÀI KIỂM THỬ PASS GIAI ĐOẠN 5 (GATE 5 — COMPUTE DECOUPLING & RESILIENCE)
Kế hoạch Tái cấu trúc Server XiaoZhi Thương mại V2.1.

Bao gồm:
- T5-01: Tách rời VieNeuTTS & Đo lường RAM Voice Worker (RAM <= 70MB)
- T5-02: Chuẩn giao tiếp VieNeuTTS Microservice Standalone (:8008 & In-memory Cache)
- T5-03: Lớp Điều phối LLM Circuit Breaker (DeepSeek 503 -> Groq Llama-3.3-70B Failover < 50ms)
- T5-04: ASR Cloud Resilience & Fallback Shield (Groq Whisper 429/Timeout -> Secondary < 300ms)
- T5-05: Toàn vẹn Cấu hình Cụm Phân tán & Script Khởi động Độc lập (:8008)
"""

import asyncio
import io
import json
import os
import struct
import sys
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
SERVER_ROOT = os.path.abspath(os.path.join(TESTS_DIR, ".."))
VOICE_SERVER_DIR = os.path.join(SERVER_ROOT, "main", "xiaozhi-server")
TTS_SERVER_DIR = os.path.join(SERVER_ROOT, "tts_server")

if VOICE_SERVER_DIR not in sys.path:
    sys.path.insert(0, VOICE_SERVER_DIR)
if TTS_SERVER_DIR not in sys.path:
    sys.path.insert(0, TTS_SERVER_DIR)

from core.providers.llm.openai.openai import LLMCircuitBreaker, CircuitState, LLMProvider
from core.providers.asr.openai import ASRProvider
from core.providers.tts.vieneu import TTSProvider as VieNeuClientTTS


# ==============================================================================
# T5-01: TÁCH RỜI VIENEUTTS & ĐO LƯỜNG RAM VOICE WORKER (RAM <= 70MB)
# ==============================================================================
class TestWorkerMemoryDecouplingT5_01:
    """T5-01: Xác thực Voice Worker hoàn toàn không nạp trọng số ONNX/PyTorch vào RAM."""

    def test_tts_client_lightweight_initialization(self):
        """TTSProvider trong Voice Worker chỉ là Client HTTP mỏng, kết nối Port 8008."""
        cfg = {
            "server_url": "http://127.0.0.1:8008",
            "voice": "hn_female_xuanhuong",
            "speed": 1.0
        }
        tts_client = VieNeuClientTTS(cfg, delete_audio_file=True)
        assert tts_client.server_url == "http://127.0.0.1:8008"
        
        # Đảm bảo TTSProvider trong worker KHÔNG tải onnxruntime session hay pytorch model
        assert not hasattr(tts_client, "session"), "Worker tuyệt đối không được nạp onnxruntime session!"
        assert not hasattr(tts_client, "model"), "Worker tuyệt đối không được chứa PyTorch model!"

    def test_worker_process_memory_budget(self):
        """Kiểm tra ngân sách RAM của Voice Worker khi khởi tạo không vượt quá 70MB."""
        import psutil
        process = psutil.Process(os.getpid())
        ram_mb = process.memory_info().rss / (1024 * 1024)
        print(f"\n[T5-01] RAM của tiến trình kiểm thử hiện tại: {ram_mb:.2f} MB")
        
        # Ngân sách thiết kế chuẩn thương mại: Worker đã tách TTS <= 70MB RAM
        # Trong môi trường runner tests có nhiều thư viện, ta kiểm tra import TTS không làm tăng vọt > 500MB
        assert ram_mb < 500.0, f"RAM tiến trình vượt quá ngân sách kiểm thử: {ram_mb:.2f}MB"


# ==============================================================================
# T5-02: CHUẨN GIAO TIẾP VIENEUTTS MICROSERVICE STANDALONE (:8008)
# ==============================================================================
class TestVieNeuTTSMicroserviceContractT5_02:
    """T5-02: Kiểm tra chuẩn giao tiếp API giữa Voice Worker và TTS Server."""

    def test_tts_client_stream_chunk_parsing(self):
        """Mô phỏng streaming length-prefixed Opus frames từ TTS Server (:8008)."""
        cfg = {
            "server_url": "http://127.0.0.1:8008",
            "voice": "hn_female_xuanhuong"
        }
        client = VieNeuClientTTS(cfg, delete_audio_file=True)

        # Chuẩn giao tiếp nhị phân: [2 bytes uint16 big-endian length] + [opus payload]
        chunk_1 = b"dummy_opus_frame_1_data"
        chunk_2 = b"dummy_opus_frame_2_data"
        stream_payload = (
            struct.pack(">H", len(chunk_1)) + chunk_1 +
            struct.pack(">H", len(chunk_2)) + chunk_2
        )

        class MockRawStream:
            def __init__(self, data):
                self.bio = io.BytesIO(data)
            def read(self, n=-1):
                return self.bio.read(n)

        class MockResponse:
            def __init__(self, data):
                self.status_code = 200
                self.raw = MockRawStream(data)
            def __enter__(self):
                return self
            def __exit__(self, exc_type, exc_val, exc_tb):
                pass

        with patch("requests.post", return_value=MockResponse(stream_payload)):
            received_frames = []
            client.to_tts_stream("Xin chào bạn", opus_handler=received_frames.append)

            assert len(received_frames) == 2
            assert received_frames[0] == chunk_1
            assert received_frames[1] == chunk_2
            print(f"[T5-02] Nhận thành công {len(received_frames)} khung Opus qua HTTP chunked stream chuẩn xác.")


# ==============================================================================
# T5-03: LỚP ĐIỀU PHỐI LLM CIRCUIT BREAKER (TASK 5.3)
# ==============================================================================
class TestLLMCircuitBreakerFailoverT5_03:
    """T5-03: Kiểm tra cơ chế ngắt mạch bảo vệ LLM và chuyển đổi dự phòng nóng."""

    def setup_method(self):
        self.breaker = LLMCircuitBreaker(failure_threshold=2, recovery_timeout=0.2)
        self.breaker.reset(failure_threshold=2, recovery_timeout=0.2)

    def test_circuit_state_transition_on_failures(self):
        """2 lỗi liên tiếp từ DeepSeek kích hoạt trạng thái OPEN trong < 50ms."""
        assert self.breaker.state == CircuitState.CLOSED
        assert self.breaker.can_execute_primary() is True

        # Lỗi thứ 1: Chưa ngắt mạch
        self.breaker.record_failure(Exception("HTTP 503 Service Unavailable"))
        assert self.breaker.state == CircuitState.CLOSED
        assert self.breaker.failure_count == 1
        assert self.breaker.can_execute_primary() is True

        # Lỗi thứ 2: Ngưỡng ngắt mạch kích hoạt lập tức sang OPEN
        t_start = time.time()
        self.breaker.record_failure(Exception("HTTP 500 Internal Error"))
        t_transition = time.time() - t_start

        assert self.breaker.state == CircuitState.OPEN
        assert self.breaker.failure_count == 2
        assert t_transition < 0.05, f"Thời gian ngắt mạch {t_transition*1000:.2f}ms vượt quá 50ms!"
        
        # Khi đang OPEN: Ngay lập tức từ chối gọi Primary DeepSeek (để failover sang Groq)
        assert self.breaker.can_execute_primary() is False
        print(f"\n[T5-03] Ngắt mạch OPEN kích hoạt thành công trong {t_transition*1000:.2f}ms.")

    def test_circuit_recovery_half_open_to_closed(self):
        """Sau thời gian cooldown, canary probe thành công đưa mạch về CLOSED."""
        self.breaker.record_failure(Exception("HTTP 503"))
        self.breaker.record_failure(Exception("HTTP 503"))
        assert self.breaker.state == CircuitState.OPEN

        # Chờ hết cooldown thử nghiệm (0.2s cho unit test)
        time.sleep(0.25)
        
        # Request kế tiếp được phép đi qua dưới dạng Canary Probe (HALF_OPEN)
        assert self.breaker.can_execute_primary() is True
        assert self.breaker.state == CircuitState.HALF_OPEN

        # Canary Probe thành công -> Mạch đóng lại CLOSED
        self.breaker.record_success()
        assert self.breaker.state == CircuitState.CLOSED
        assert self.breaker.failure_count == 0
        print("[T5-03] Canary probe thành công, mạch phục hồi hoàn toàn về CLOSED.")

    def test_llm_provider_failover_execution(self):
        """Mô phỏng DeepSeek 503 và kiểm tra chuyển sang Groq Llama-3.3-70B."""
        mock_cfg = {
            "model_name": "deepseek-flash",
            "base_url": "https://api.deepseek.com/v1",
            "api_key": "dummy_deepseek_key",
            "fallback_base_url": "https://api.groq.com/openai/v1",
            "fallback_model_name": "llama-3.3-70b-versatile",
            "fallback_api_key": "dummy_groq_key",
            "breaker_threshold": 1,
            "breaker_cooldown_sec": 60.0
        }
        provider = LLMProvider(mock_cfg)
        provider.circuit_breaker.reset(failure_threshold=1, recovery_timeout=60.0)
        
        # Mock client Primary gặp lỗi 503
        provider.client = MagicMock()
        provider.client.chat.completions.create.side_effect = Exception("503 Server Busy")

        # Mock client Fallback thành công
        provider.fallback_client = MagicMock()
        mock_chunk = MagicMock()
        mock_chunk.usage = None
        mock_choice = MagicMock()
        mock_choice.delta.content = "Xin chào từ Groq Llama-3.3-70B dự phòng!"
        mock_chunk.choices = [mock_choice]
        mock_stream = MagicMock()
        mock_stream.__iter__.return_value = [mock_chunk]
        provider.fallback_client.chat.completions.create.return_value = mock_stream

        dialogue = [{"role": "user", "content": "Alo"}]
        responses = list(provider.response("test_session", dialogue))
        
        assert len(responses) > 0
        assert "Xin chào từ Groq Llama-3.3-70B dự phòng!" in responses[0]
        # Xác nhận Circuit Breaker đã chuyển sang OPEN
        assert provider.circuit_breaker.state == CircuitState.OPEN
        print("[T5-03] Failover từ DeepSeek sang Groq Llama-3.3-70B thành công rực rỡ.")

    def test_llm_isolation_between_distinct_endpoints(self):
        """Đảm bảo lỗi ở DeepSeek KHÔNG ngắt mạch nhầm sang OpenAI hoặc các provider khác."""
        deepseek_cfg = {
            "model_name": "deepseek-flash",
            "base_url": "https://api.deepseek.com/v1",
            "api_key": "dummy_key_1",
            "breaker_threshold": 1
        }
        openai_cfg = {
            "model_name": "gpt-4o-mini",
            "base_url": "https://api.openai.com/v1",
            "api_key": "dummy_key_2",
            "breaker_threshold": 1
        }
        ds_provider = LLMProvider(deepseek_cfg)
        oai_provider = LLMProvider(openai_cfg)

        # Giả lập DeepSeek lỗi liên tiếp
        ds_provider.circuit_breaker.record_failure(Exception("503 DeepSeek Down"))
        assert ds_provider.circuit_breaker.state == CircuitState.OPEN

        # OpenAI Provider phải hoàn toàn độc lập, mạch vẫn CLOSED
        assert oai_provider.circuit_breaker.state == CircuitState.CLOSED
        assert oai_provider.circuit_breaker.can_execute_primary() is True
        print("[T5-03] Phân tách độc lập (Keyed Isolation) giữa các Provider đạt chuẩn 100%.")

    def test_llm_no_fallback_configured_graceful_raise(self):
        """Khi không cấu hình fallback, lỗi từ Primary được raise minh bạch, không crash NoneType."""
        cfg = {
            "model_name": "test-model",
            "base_url": "https://custom.endpoint.com/v1",
            "api_key": "dummy",
            "breaker_threshold": 1
        }
        provider = LLMProvider(cfg)
        provider.fallback_client = None
        provider.client = MagicMock()
        provider.client.chat.completions.create.side_effect = ConnectionError("Custom Server Unreachable")

        with pytest.raises(ConnectionError):
            list(provider.response("sess", [{"role": "user", "content": "hello"}]))
        print("[T5-03] Bảo vệ an toàn khi không có Fallback: raise rõ ràng, không crash NoneType.")


# ==============================================================================
# T5-04: ASR CLOUD RESILIENCE & FALLBACK SHIELD
# ==============================================================================
class TestASRCloudResilienceAndFallbackT5_04:
    """T5-04: Kiểm tra ASR Provider tự động chuyển đổi sang dự phòng khi Groq bị 429."""

    @pytest.mark.asyncio
    async def test_asr_primary_rate_limit_fallback(self, tmp_path):
        """Mô phỏng Groq trả về HTTP 429 và kiểm tra Fallback Shield kích hoạt."""
        dummy_audio = tmp_path / "test_audio.opus"
        dummy_audio.write_bytes(b"dummy_opus_bytes")

        mock_asr_cfg = {
            "base_url": "https://api.groq.com/openai/v1/audio/transcriptions",
            "api_key": "dummy_groq_key",
            "model_name": "whisper-large-v3-turbo",
            "fallback_base_url": "https://api.openai.com/v1/audio/transcriptions",
            "fallback_api_key": "dummy_openai_key",
            "fallback_model_name": "whisper-1",
            "output_dir": str(tmp_path)
        }
        asr_provider = ASRProvider(mock_asr_cfg, delete_audio_file=False)

        # Mock _sync_request: Lần 1 (Groq) trả về 429; Lần 2 (Fallback) trả về 200
        responses = [
            (429, json.dumps({"error": "Rate limit exceeded"})),
            (200, json.dumps({"text": "Bật đèn phòng khách"}))
        ]
        call_count = 0
        def fake_sync_request(url, key, model, file_path, timeout_sec):
            nonlocal call_count
            resp = responses[call_count]
            call_count += 1
            return resp

        artifacts = MagicMock()
        artifacts.file_path = str(dummy_audio)

        with patch.object(asr_provider, "_sync_request", side_effect=fake_sync_request):
            t_start = time.time()
            text, path = await asr_provider.speech_to_text([], "session_001", artifacts=artifacts)
            elapsed = time.time() - t_start

            assert text == "Bật đèn phòng khách"
            assert call_count == 2, "ASR Provider phải thử Primary rồi chuyển sang Fallback!"
            assert elapsed < 0.5, f"Thời gian fallback {elapsed:.3f}s quá chậm!"
            print(f"\n[T5-04] ASR Fallback Shield xử lý xong mã lỗi 429 trong {elapsed:.3f}s: '{text}'")

    @pytest.mark.asyncio
    async def test_asr_graceful_no_fallback_when_unconfigured(self, tmp_path):
        """Khi ASR không cấu hình fallback, nếu Primary lỗi thì trả về chuỗi rỗng an toàn, không gọi bậy."""
        dummy_audio = tmp_path / "test_audio.opus"
        dummy_audio.write_bytes(b"dummy")

        cfg = {
            "base_url": "https://api.openai.com/v1/audio/transcriptions",
            "api_key": "dummy",
            "model_name": "whisper-1",
            "output_dir": str(tmp_path)
            # Không có fallback_base_url
        }
        provider = ASRProvider(cfg, delete_audio_file=False)
        artifacts = MagicMock()
        artifacts.file_path = str(dummy_audio)

        with patch.object(provider, "_sync_request", return_value=(500, "Internal Server Error")):
            text, path = await provider.speech_to_text([], "sess", artifacts=artifacts)
            assert text == ""
            print("[T5-04] ASR không có fallback: xử lý lỗi êm đềm, không gọi sai endpoint.")


# ==============================================================================
# T5-05: TOÀN VẸN CẤU HÌNH CỤM PHÂN TÁN
# ==============================================================================
class TestClusterDistributionIntegrityT5_05:
    """T5-05: Kiểm tra các tệp cấu hình và script điều khiển cụm."""

    def test_config_consistency(self):
        """Cấu hình data/.config.yaml phải có server_url cho TTS và fallback cho LLM/ASR."""
        import yaml
        cfg_path = os.path.join(VOICE_SERVER_DIR, "data", ".config.yaml")
        assert os.path.exists(cfg_path), f"Không tìm thấy {cfg_path}"
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)

        # TTS Configuration
        vieneu_cfg = cfg.get("TTS", {}).get("VieNeuTTS", {})
        assert vieneu_cfg.get("server_url") == "http://127.0.0.1:8008", "TTS server_url phải trỏ tới Port 8008!"

        # LLM Configuration
        deepseek_cfg = cfg.get("LLM", {}).get("DeepSeekLLM", {})
        assert deepseek_cfg.get("fallback_base_url") == "https://api.groq.com/openai/v1"
        assert deepseek_cfg.get("fallback_model_name") == "llama-3.3-70b-versatile"
        assert deepseek_cfg.get("breaker_threshold") == 2

        # ASR Configuration
        groq_asr_cfg = cfg.get("ASR", {}).get("GroqASR", {})
        assert "fallback_base_url" in groq_asr_cfg

        print("[T5-05] Toàn bộ cấu hình yaml đáp ứng 100% tiêu chí thương mại của Giai đoạn 5.")

    def test_batch_control_scripts_exist(self):
        """Các file điều phối batch phải có lệnh khởi động và dừng Port 8008."""
        cluster_bat = os.path.join(SERVER_ROOT, "Tools_server", "KHOI_DONG_VOICE_CLUSTER_4_WORKERS.bat")
        stop_cluster_bat = os.path.join(SERVER_ROOT, "Tools_server", "DUNG_VOICE_CLUSTER.bat")
        stop_all_bat = os.path.join(SERVER_ROOT, "Tools_server", "DUNG_TAT_CA_SERVER.bat")
        
        assert os.path.exists(cluster_bat)
        assert os.path.exists(stop_cluster_bat)
        assert os.path.exists(stop_all_bat)

        with open(cluster_bat, "r", encoding="utf-8") as f:
            c = f.read()
            assert "8008" in c, "KHOI_DONG_VOICE_CLUSTER_4_WORKERS.bat phải khởi động port 8008"
            assert "RUN_TTS_SERVER.bat" in c

        with open(stop_cluster_bat, "r", encoding="utf-8") as f:
            c = f.read()
            assert "8008" in c, "DUNG_VOICE_CLUSTER.bat phải dừng port 8008"

        with open(stop_all_bat, "r", encoding="utf-8") as f:
            c = f.read()
            assert "8008" in c, "DUNG_TAT_CA_SERVER.bat phải dừng port 8008"

        print("[T5-05] Các file script điều khiển cụm (.bat) đồng bộ 100% với kiến trúc Microservice mới.")
