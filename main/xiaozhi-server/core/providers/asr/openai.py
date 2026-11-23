import time
import os
import asyncio
import socket
import urllib3.util.connection as urllib3_cn
from config.logger import setup_logging
from typing import Optional, Tuple, List
from core.providers.asr.dto.dto import InterfaceType
from core.providers.asr.base import ASRProviderBase

import requests

TAG = __name__
logger = setup_logging()

# Ép buộc urllib3 chỉ phân giải và kết nối qua IPv4 (tránh 75% packet loss & timeout trên IPv6 nhà mạng VN)
urllib3_cn.allowed_gai_family = lambda: socket.AF_INET


class ASRProvider(ASRProviderBase):
    """
    ASR Provider chuẩn thương mại:
    - Primary: Groq Whisper Large V3 Turbo (~250-500ms, 0% CPU server).
    - IPv4 Fast-Track: Ép buộc socket IPv4 để triệt tiêu tình trạng lag/treo do rớt gói trên IPv6.
    - Persistent Session & Connection Pool: Tái sử dụng kết nối HTTP Keep-Alive, bỏ qua DNS và TLS handshake cho các lượt nói tiếp theo.
    - Asynchronous Execution: Chạy requests qua ThreadPoolExecutor không chặn Event Loop.
    """
    def __init__(self, config: dict, delete_audio_file: bool):
        self.interface_type = InterfaceType.NON_STREAM
        self.api_key = config.get("api_key")
        self.api_url = config.get("base_url")
        self.model = config.get("model_name")        
        self.output_dir = config.get("output_dir", "tmp/")
        self.language = config.get("language")
        self.prompt = config.get("prompt")
        self.temperature = config.get("temperature")
        self.delete_audio_file = delete_audio_file

        # Cấu hình Fallback Shield (Chỉ kích hoạt nếu được cấu hình tường minh trong YAML)
        self.fallback_url = config.get("fallback_base_url")
        self.fallback_key = config.get("fallback_api_key")
        self.fallback_model = config.get("fallback_model_name", "whisper-1")

        os.makedirs(self.output_dir, exist_ok=True)

        # Khởi tạo Persistent HTTP Session với Connection Pooling & Keep-Alive
        self.session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=5,
            pool_maxsize=10,
            max_retries=1,
            pool_block=False
        )
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        logger.bind(tag=TAG).info("[ASR Groq] Đã khởi tạo ASRProvider (IPv4 Shield + HTTP Keep-Alive Session)")

    def requires_file(self) -> bool:
        return True

    def _sync_request(self, url: str, key: str, model: str, file_path: str, timeout_sec: float = 8.0) -> Tuple[int, str]:
        """Thực hiện HTTP POST đồng bộ trong luồng riêng của Executor sử dụng Persistent Session"""
        headers = {
            "Authorization": f"Bearer {key}",
        }
        data = {
            "model": model
        }
        if self.language:
            data["language"] = self.language
        if self.prompt:
            data["prompt"] = self.prompt
        if self.temperature is not None:
            data["temperature"] = str(self.temperature)

        with open(file_path, "rb") as audio_file:
            files = {"file": audio_file}
            response = self.session.post(
                url,
                files=files,
                data=data,
                headers=headers,
                timeout=(3.0, timeout_sec)
            )
            return response.status_code, response.text

    async def speech_to_text(self, opus_data: List[bytes], session_id: str, artifacts=None) -> Tuple[Optional[str], Optional[str]]:
        file_path = None
        try:
            if artifacts is None:
                return "", None
            file_path = artifacts.file_path
            logger.bind(tag=TAG).info(f"ASR File: {file_path}")

            loop = asyncio.get_running_loop()
            start_time = time.time()

            # 1. Thử gọi Primary ASR (Groq Whisper Large V3 Turbo)
            primary_success = False
            status_code = 0
            resp_text = ""
            
            try:
                status_code, resp_text = await loop.run_in_executor(
                    None,
                    self._sync_request,
                    self.api_url,
                    self.api_key,
                    self.model,
                    file_path,
                    8.0  # Timeout ổn định cho Primary ASR
                )
                if status_code == 200:
                    primary_success = True
                    elapsed = time.time() - start_time
                    import json
                    text = json.loads(resp_text).get("text", "")
                    logger.bind(tag=TAG).info(f"[ASR Primary] Groq Turbo nhận dạng thành công trong {elapsed:.3f}s: '{text}'")
                    return text, file_path
                else:
                    logger.bind(tag=TAG).warning(
                        f"[ASR Primary Warning] Groq trả về HTTP {status_code}: {resp_text[:120]}"
                    )
            except Exception as e_primary:
                logger.bind(tag=TAG).warning(f"[ASR Primary Timeout/Error]: {e_primary}")

            # [TẠM THỜI VÔ HIỆU HÓA FALLBACK THEO YÊU CẦU]
            # Không kích hoạt fallback sang OpenAI để tránh lỗi 401 do khác biệt API key
            return "", None

        except Exception as e:
            logger.bind(tag=TAG).error(f"语音识别失败: {e}")
            return "", None

    async def close(self):
        """Giải phóng connection pool của session khi kết thúc"""
        try:
            if hasattr(self, "session") and self.session:
                self.session.close()
        except Exception:
            pass
        await super().close()
