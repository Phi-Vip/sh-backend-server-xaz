import httpx
import openai
import json
import hashlib
import time
import os
import enum
from typing import Optional, Dict, Any
from openai.types import CompletionUsage
from config.logger import setup_logging
from core.utils.util import check_model_key
from core.providers.llm.base import LLMProviderBase
from urllib.parse import urlparse

TAG = __name__
logger = setup_logging()

# Cac domain can vo hieu hoa che do suy luan reasoning/thinking (de phan xa giong noi tuc thi)
THINKING_DISABLED_DOMAINS = {
    "aliyuncs.com": {"enable_thinking": False},
    "deepseek.com": {"thinking": {"type": "disabled"}},
    "bigmodel.cn": {"thinking": {"type": "disabled"}},
    "moonshot.cn": {"thinking": {"type": "disabled"}},
    "volces.com": {"thinking": {"type": "disabled"}},
}


class CircuitState(enum.Enum):
    CLOSED = "CLOSED"        # Hoat dong binh thuong qua Primary LLM (DeepSeek)
    OPEN = "OPEN"            # Ngat mach, chuyen tuc thi sang Fallback LLM (Groq Llama-3.3-70B)
    HALF_OPEN = "HALF_OPEN"  # Gui canary probe thu nghiem sau thoi gian cooldown


class LLMCircuitBreaker:
    """
    Lớp Điều phối LLM Circuit Breaker (Task 5.3):
    - Chuẩn thương mại chịu tải: Bảo vệ hệ thống khỏi sự cố sập nguồn hoặc timeout của DeepSeek.
    - Phân tách theo từng endpoint/model (Keyed Isolation) để không ảnh hưởng chéo giữa các provider khác nhau.
    - Ngưỡng kích hoạt: 2 lỗi liên tiếp (HTTP 500/502/503/504/429 hoặc Timeout/ConnectionError).
    - Thời gian ngắt mạch: < 50ms (chuyển sang Fallback ngay, không bị treo).
    - Cooldown thử hồi: 60 giây (canary probe).
    """
    _breakers: Dict[str, "LLMCircuitBreaker"] = {}

    @classmethod
    def get_breaker(cls, key: str = "default", failure_threshold: int = 2, recovery_timeout: float = 60.0) -> "LLMCircuitBreaker":
        if key not in cls._breakers:
            cls._breakers[key] = cls(failure_threshold, recovery_timeout)
        else:
            cls._breakers[key].failure_threshold = failure_threshold
            cls._breakers[key].recovery_timeout = recovery_timeout
        return cls._breakers[key]

    def __init__(self, failure_threshold: int = 2, recovery_timeout: float = 60.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.last_state_change = time.time()

    def reset(self, failure_threshold: Optional[int] = None, recovery_timeout: Optional[float] = None):
        """Reset trạng thái mạch và cập nhật ngưỡng cấu hình"""
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.last_state_change = time.time()
        if failure_threshold is not None:
            self.failure_threshold = failure_threshold
        if recovery_timeout is not None:
            self.recovery_timeout = recovery_timeout

    def can_execute_primary(self) -> bool:
        now = time.time()
        if self.state == CircuitState.CLOSED:
            return True
        elif self.state == CircuitState.OPEN:
            if now - self.last_failure_time >= self.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
                self.last_state_change = now
                logger.bind(tag=TAG).info(
                    f"[CIRCUIT_BREAKER] Cooldown ket thuc ({self.recovery_timeout}s). Chuyen sang HALF_OPEN de gui canary probe..."
                )
                return True
            return False
        elif self.state == CircuitState.HALF_OPEN:
            return True
        return False

    def record_success(self):
        if self.state != CircuitState.CLOSED:
            logger.bind(tag=TAG).info(
                f"[CIRCUIT_BREAKER] Canary probe thanh cong! Mach phuc hoi tu {self.state.value} -> CLOSED."
            )
        self.state = CircuitState.CLOSED
        self.failure_count = 0

    def record_failure(self, error: Exception):
        self.last_failure_time = time.time()
        self.failure_count += 1
        logger.bind(tag=TAG).warning(
            f"[CIRCUIT_BREAKER] Ghi nhan loi tu Primary LLM ({error}). So loi lien tiep: {self.failure_count}/{self.failure_threshold}"
        )
        if self.state == CircuitState.HALF_OPEN or self.failure_count >= self.failure_threshold:
            if self.state != CircuitState.OPEN:
                self.state = CircuitState.OPEN
                self.last_state_change = time.time()
                logger.bind(tag=TAG).error(
                    f"[CIRCUIT_BREAKER ALERT] Da kich hoat ngat mach OPEN! Tat ca request se chuyen ngay (<50ms) sang Fallback LLM trong {self.recovery_timeout}s."
                )


class LLMProvider(LLMProviderBase):
    def __init__(self, config):
        self.model_name = config.get("model_name")
        self.api_key = config.get("api_key")
        if "base_url" in config:
            self.base_url = config.get("base_url")
        else:
            self.base_url = config.get("url")
        
        timeout_config = config.get("timeout")
        if isinstance(timeout_config, dict):
            custom_timeout = httpx.Timeout(
                pool=timeout_config.get("pool", 2.0),
                connect=timeout_config.get("connect", 3.0),
                write=timeout_config.get("write", 5.0),
                read=timeout_config.get("read", 60.0)
            )
        elif isinstance(timeout_config, (int, float)) and timeout_config > 0:
            custom_timeout = httpx.Timeout(timeout_config)
        else:
            custom_timeout = httpx.Timeout(300)

        param_defaults = {
            "max_tokens": int,
            "temperature": lambda x: round(float(x), 1),
            "top_p": lambda x: round(float(x), 1),
            "frequency_penalty": lambda x: round(float(x), 1),
        }

        for param, converter in param_defaults.items():
            value = config.get(param)
            try:
                setattr(
                    self,
                    param,
                    converter(value) if value not in (None, "") else None,
                )
            except (ValueError, TypeError):
                setattr(self, param, None)

        logger.debug(
            f"Intent params init: {self.temperature}, {self.max_tokens}, {self.top_p}, {self.frequency_penalty}"
        )

        if self.api_key:
            model_key_msg = check_model_key("LLM", self.api_key)
            if model_key_msg:
                logger.bind(tag=TAG).error(model_key_msg)
        self.client = openai.OpenAI(api_key=self.api_key, base_url=self.base_url, timeout=custom_timeout)

        # Task 5.3: Circuit Breaker & Fallback Shield Configuration (Phân tách theo endpoint)
        breaker_key = f"{self.base_url}:{self.model_name}"
        self.circuit_breaker = LLMCircuitBreaker.get_breaker(
            key=breaker_key,
            failure_threshold=int(config.get("breaker_threshold", 2)),
            recovery_timeout=float(config.get("breaker_cooldown_sec", 60.0))
        )
        self.fallback_base_url = config.get("fallback_base_url")
        self.fallback_model_name = config.get("fallback_model_name", "llama-3.3-70b-versatile")
        self.fallback_api_key = config.get("fallback_api_key")

        # Chỉ tự động nạp key nếu module có cấu hình fallback_base_url rõ ràng
        if self.fallback_base_url and not self.fallback_api_key:
            try:
                import yaml
                cfg_path = os.path.join(os.path.dirname(__file__), "../../../../data/.config.yaml")
                if os.path.exists(cfg_path):
                    with open(cfg_path, "r", encoding="utf-8") as f:
                        gcfg = yaml.safe_load(f)
                        self.fallback_api_key = gcfg.get("LLM", {}).get("GroqLLM", {}).get("api_key")
                        if not self.fallback_api_key:
                            self.fallback_api_key = gcfg.get("ASR", {}).get("GroqASR", {}).get("api_key")
            except Exception:
                pass

        if self.fallback_base_url and not self.fallback_api_key:
            self.fallback_api_key = os.environ.get("GROQ_API_KEY", "")

        # Khởi tạo client dự phòng nếu có đủ thông số và không bị trùng với chính nó
        if self.fallback_api_key and self.fallback_base_url and self.fallback_base_url != self.base_url:
            self.fallback_client = openai.OpenAI(
                api_key=self.fallback_api_key,
                base_url=self.fallback_base_url,
                timeout=custom_timeout
            )
            logger.bind(tag=TAG).info(
                f"[CIRCUIT_BREAKER INIT] Khiên dự phòng LLM Fallback sẵn sàng cho {self.model_name} -> {self.fallback_model_name} ({self.fallback_base_url})"
            )
        else:
            self.fallback_client = None

    @staticmethod
    def normalize_dialogue(dialogue):
        for msg in dialogue:
            if "role" in msg and "content" not in msg:
                msg["content"] = ""
        return dialogue

    def _apply_thinking_disabled(self, request_params: dict):
        parsed_url = urlparse(self.base_url)
        domain = parsed_url.netloc
        model_name = (self.model_name or "").lower()
        
        for disabled_domain, params in THINKING_DISABLED_DOMAINS.items():
            if disabled_domain in domain or (disabled_domain == "deepseek.com" and "deepseek" in model_name):
                request_params.setdefault("extra_body", {}).update(params)
                logger.bind(tag=TAG).info(f"Da kich hoat {params} cho mo hinh {self.model_name} (domain: {domain})")
                break

    def _log_token_usage(self, usage):
        if not usage:
            return
            
        def get_val(obj, key, default=0):
            if isinstance(obj, dict):
                return obj.get(key, default)
            return getattr(obj, key, default)

        total_prompt_tokens = get_val(usage, "prompt_tokens", 0)
        
        cached_tokens = get_val(usage, "prompt_cache_hit_tokens", None)
        if cached_tokens is None:
            prompt_tokens_details = get_val(usage, "prompt_tokens_details", None)
            cached_tokens = get_val(prompt_tokens_details, "cached_tokens", 0) if prompt_tokens_details else 0
        cached_tokens = cached_tokens or 0
            
        miss_tokens = get_val(usage, "prompt_cache_miss_tokens", None)
        if miss_tokens is None:
            miss_tokens = max(0, total_prompt_tokens - cached_tokens)
            
        completion_tokens = get_val(usage, "completion_tokens", 0) or 0
        total_tokens = get_val(usage, "total_tokens", total_prompt_tokens + completion_tokens) or (total_prompt_tokens + completion_tokens)
        hit_ratio = (cached_tokens / total_prompt_tokens * 100) if total_prompt_tokens > 0 else 0
        
        logger.bind(tag=TAG).info(
            f"[TOKEN_USAGE] "
            f"Input: {total_prompt_tokens} tokens "
            f"[Da Cache: {cached_tokens} | Chua Cache: {miss_tokens} ({hit_ratio:.1f}%)] | "
            f"Output: {completion_tokens} tokens | "
            f"Tong: {total_tokens} tokens"
        )

    def _build_request_params(self, dialogue, functions=None, **kwargs) -> dict:
        request_params = {
            "model": self.model_name,
            "messages": dialogue,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if functions:
            request_params["tools"] = functions

        optional_params = {
            "max_tokens": kwargs.get("max_tokens", self.max_tokens),
            "temperature": kwargs.get("temperature", self.temperature),
            "top_p": kwargs.get("top_p", self.top_p),
            "frequency_penalty": kwargs.get("frequency_penalty", self.frequency_penalty),
        }

        for key, value in optional_params.items():
            if value is not None:
                request_params[key] = value

        if "tool_choice" in kwargs and kwargs["tool_choice"] is not None:
            request_params["tool_choice"] = kwargs["tool_choice"]

        return request_params

    def response(self, session_id, dialogue, **kwargs):
        dialogue = self.normalize_dialogue(dialogue)
        request_params = self._build_request_params(dialogue, **kwargs)
        self._apply_thinking_disabled(request_params)

        has_fallback = self.fallback_client is not None
        can_call_primary = self.circuit_breaker.can_execute_primary()
        use_fallback = has_fallback and (not can_call_primary)
        responses = None

        if not use_fallback:
            try:
                responses = self.client.chat.completions.create(**request_params)
                self.circuit_breaker.record_success()
            except Exception as e:
                self.circuit_breaker.record_failure(e)
                if has_fallback:
                    logger.bind(tag=TAG).warning(
                        f"[CIRCUIT_BREAKER FAILOVER] Primary LLM lỗi ({e}). Chuyển tức thì sang Fallback {self.fallback_model_name}..."
                    )
                    use_fallback = True
                else:
                    raise e

        if use_fallback and self.fallback_client:
            fb_params = dict(request_params)
            fb_params["model"] = self.fallback_model_name
            if "extra_body" in fb_params:
                fb_params.pop("extra_body", None)
            logger.bind(tag=TAG).info(
                f"[CIRCUIT_BREAKER ACTIVE] Điều hướng tức thì (<50ms) tới Fallback LLM: {self.fallback_model_name}"
            )
            responses = self.fallback_client.chat.completions.create(**fb_params)

        is_active = True
        try:            
            for chunk in (responses or []):
                if getattr(chunk, "usage", None):
                    self._log_token_usage(chunk.usage)
                try:
                    delta = chunk.choices[0].delta if getattr(chunk, "choices", None) else None
                    content = getattr(delta, "content", "") if delta else ""
                except IndexError:
                    content = ""
                if content:
                    if "<think>" in content:
                        is_active = False
                        content = content.split("<think>")[0]
                    if "</think>" in content:
                        is_active = True
                        content = content.split("</think>")[-1]
                    if is_active:
                        yield content
        finally:
            if responses is not None and hasattr(responses, "close"):
                responses.close()

    def response_with_functions(self, session_id, dialogue, functions=None, **kwargs):
        dialogue = self.normalize_dialogue(dialogue)
        request_params = self._build_request_params(dialogue, functions=functions, **kwargs)
        self._apply_thinking_disabled(request_params)

        # Trich xuat chan doan Prompt Cache Hit
        tools_summary = [f.get("function", {}).get("name", "") for f in (functions or []) if isinstance(f, dict)]
        tools_json = json.dumps(functions, sort_keys=True, ensure_ascii=False) if functions else ""
        tools_hash = hashlib.md5(tools_json.encode()).hexdigest()[:10] if tools_json else "NONE"
        sys_content = dialogue[0].get("content", "") if dialogue and dialogue[0].get("role") == "system" else ""
        sys_hash = hashlib.md5(sys_content.encode()).hexdigest()[:10] if sys_content else "NONE"
        msgs_summary = []
        for i, m in enumerate(dialogue):
            r = m.get("role", "")
            clen = len(m.get("content") or "")
            tc = [t.get("function", {}).get("name", "") for t in (m.get("tool_calls") or []) if isinstance(t, dict)]
            tid = m.get("tool_call_id", "")
            msgs_summary.append(f"{i}:{r}(len={clen}{',tc=' + '+'.join(tc) if tc else ''}{',tid=' + tid if tid else ''})")
            
        logger.bind(tag=TAG).info(
            f"[CACHE_HIT_TRACKER] SysLen={len(sys_content)}, SysMD5={sys_hash} | "
            f"ToolsCnt={len(functions or [])}, ToolsMD5={tools_hash} (tools={','.join(tools_summary[:5])}...) | "
            f"MsgsCnt={len(dialogue)}: [{', '.join(msgs_summary)}] | "
            f"ExtraBody={request_params.get('extra_body')} | "
            f"ToolChoice={request_params.get('tool_choice')}"
        )

        has_fallback = self.fallback_client is not None
        can_call_primary = self.circuit_breaker.can_execute_primary()
        use_fallback = has_fallback and (not can_call_primary)
        stream = None

        if not use_fallback:
            try:
                stream = self.client.chat.completions.create(**request_params)
                self.circuit_breaker.record_success()
            except Exception as e:
                self.circuit_breaker.record_failure(e)
                if has_fallback:
                    logger.bind(tag=TAG).warning(
                        f"[CIRCUIT_BREAKER FAILOVER] Primary LLM lỗi ({e}). Chuyển sang Fallback {self.fallback_model_name}..."
                    )
                    use_fallback = True
                else:
                    raise e

        if use_fallback and self.fallback_client:
            fb_params = dict(request_params)
            fb_params["model"] = self.fallback_model_name
            if "extra_body" in fb_params:
                fb_params.pop("extra_body", None)
            logger.bind(tag=TAG).info(
                f"[CIRCUIT_BREAKER ACTIVE] Điều hướng tức thì (<50ms) tới Fallback LLM: {self.fallback_model_name}"
            )
            stream = self.fallback_client.chat.completions.create(**fb_params)

        is_active = True
        try:
            for chunk in (stream or []):
                if getattr(chunk, "usage", None):
                    self._log_token_usage(chunk.usage)
                if getattr(chunk, "choices", None):
                    delta = chunk.choices[0].delta
                    content = getattr(delta, "content", "")
                    tool_calls = getattr(delta, "tool_calls", None)
                    if content:
                        if "<think>" in content:
                            is_active = False
                            content = content.split("<think>")[0]
                        if "</think>" in content:
                            is_active = True
                            content = content.split("</think>")[-1]
                        if not is_active:
                            content = ""
                    yield content, tool_calls
        finally:
            if stream is not None and hasattr(stream, "close"):
                stream.close()
