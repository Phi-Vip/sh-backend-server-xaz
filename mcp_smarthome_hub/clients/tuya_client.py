"""Client REST OpenAPI Tuya Cloud v2.0 Bất Đồng Bộ.

Các tính năng cốt lõi:
- Hiện thực thuật toán chữ ký số chuẩn Tuya OpenAPI v2.0 HMAC-SHA256.
- Header chống tấn công phát lại (Anti-Replay Attack) bằng nonce UUIDv4 và timestamp mili-giây.
- Cơ chế tự phục hồi lỗi mạng qua thư viện tenacity: Thử lại tối đa 3 lần với Exponential Backoff + Random Jitter khi gặp sự cố mạng thoáng qua (502, 504, timeout).
- Cung cấp trọn bộ API điều khiển thiết bị & chuyên dụng cho Robot hút bụi (đặc tả DPs, trạng thái, gửi lệnh, lịch sử dọn, bản đồ đa tầng).
"""

import asyncio
import hashlib
import hmac
import json
import logging
import time
import urllib.parse
import uuid
from typing import Any, Dict, List, Optional, Tuple

import aiohttp
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)

logger = logging.getLogger(__name__)

# Mã băm SHA256 của chuỗi rỗng theo quy chuẩn của Tuya OpenAPI v2.0
EMPTY_BODY_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


class TuyaAPIException(Exception):
    """Ngoại lệ ném ra khi máy chủ Tuya Cloud trả về mã lỗi hoặc thông điệp lỗi nghiệp vụ."""

    def __init__(self, code: Any, msg: str, status_code: Optional[int] = None):
        super().__init__(f"Lỗi Tuya API [mã={code}]: {msg} (Mã HTTP: {status_code})")
        self.code = code
        self.msg = msg
        self.status_code = status_code


class TuyaTransientNetworkException(Exception):
    """Ngoại lệ nội bộ dùng để kích hoạt cơ chế retry của tenacity khi gặp lỗi mạng tạm thời (502/504)."""
    pass


class TuyaCloudClient:
    """Client giao tiếp bất đồng bộ với Cổng điện toán đám mây Tuya Cloud OpenAPI."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        base_url: str = "https://openapi-sg.tuya.com",
        session: Optional[aiohttp.ClientSession] = None,
        timeout_seconds: float = 5.0,
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.base_url = base_url.rstrip("/")
        self._session = session
        self._owns_session = False
        self.timeout_seconds = timeout_seconds

    async def _get_session(self) -> aiohttp.ClientSession:
        """Khởi tạo hoặc tái sử dụng aiohttp.ClientSession với timeout an toàn."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
            self._session = aiohttp.ClientSession(timeout=timeout)
            self._owns_session = True
        return self._session

    async def close(self) -> None:
        """Đóng phiên HTTP nội bộ an toàn nếu do client tự khởi tạo."""
        if self._owns_session and self._session and not self._session.closed:
            await self._session.close()

    def calc_sign(
        self,
        method: str,
        path_and_query: str,
        body_bytes: bytes,
        t: str,
        nonce: str,
        access_token: Optional[str] = None,
    ) -> Tuple[str, str]:
        """Tính toán chữ ký số chuẩn HMAC-SHA256 của Tuya OpenAPI v2.0.

        Công thức:
        stringToSign = HTTPMethod + "\\n" + Content-SHA256 + "\\n" + Headers + "\\n" + Url
        str_to_hash = client_id + [access_token] + t + nonce + stringToSign
        sign = HMAC-SHA256(str_to_hash, client_secret).upper()
        """
        if not body_bytes:
            content_sha256 = EMPTY_BODY_SHA256
        else:
            content_sha256 = hashlib.sha256(body_bytes).hexdigest().lower()

        # Trong các lệnh gọi thông thường, Tuya không yêu cầu ký thêm custom headers
        headers_str = ""
        string_to_sign = f"{method.upper()}\n{content_sha256}\n{headers_str}\n{path_and_query}"

        if access_token:
            str_to_hash = f"{self.client_id}{access_token}{t}{nonce}{string_to_sign}"
        else:
            str_to_hash = f"{self.client_id}{t}{nonce}{string_to_sign}"

        sign = hmac.new(
            self.client_secret.encode("utf-8"),
            str_to_hash.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest().upper()

        return sign, content_sha256

    async def request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
        token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Thực thi gửi HTTP request với cơ chế tự phục hồi tenacity (thử lại tối đa 3 lần)."""
        session = await self._get_session()

        # Chuẩn hóa đường dẫn URL và tham số query
        clean_path = path if path.startswith("/") else f"/{path}"
        if params:
            query_str = urllib.parse.urlencode(
                sorted([(k, str(v)) for k, v in params.items() if v is not None])
            )
            path_and_query = f"{clean_path}?{query_str}" if query_str else clean_path
        else:
            path_and_query = clean_path

        full_url = f"{self.base_url}{path_and_query}"

        # Chuyển đổi nội dung body sang dạng byte
        if json_body is not None:
            body_bytes = json.dumps(json_body, separators=(",", ":")).encode("utf-8")
        else:
            body_bytes = b""

        # Khối tenacity retry cho các lỗi mạng tạm thời (502, 503, 504, aiohttp timeout)
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_random_exponential(multiplier=0.1, max=0.4),
            retry=retry_if_exception_type((TuyaTransientNetworkException, aiohttp.ClientError, asyncio.TimeoutError)),
            reraise=True,
        ):
            with attempt:
                # Mỗi lần gửi sinh nonce ngẫu nhiên mới và timestamp mới để chống Replay
                nonce = str(uuid.uuid4())
                t = str(int(time.time() * 1000))
                sign, _ = self.calc_sign(
                    method=method,
                    path_and_query=path_and_query,
                    body_bytes=body_bytes,
                    t=t,
                    nonce=nonce,
                    access_token=token,
                )

                headers = {
                    "client_id": self.client_id,
                    "sign": sign,
                    "t": t,
                    "sign_method": "HMAC-SHA256",
                    "nonce": nonce,
                }
                if token:
                    headers["access_token"] = token
                if json_body is not None:
                    headers["Content-Type"] = "application/json"

                try:
                    logger.info(f"🌐 [TUYA HTTP REQUEST] {method.upper()} {clean_path}")
                    async with session.request(
                        method=method.upper(),
                        url=full_url,
                        headers=headers,
                        data=body_bytes if body_bytes else None,
                    ) as resp:
                        if resp.status in (502, 503, 504):
                            logger.warning(
                                f"Tuya HTTP {resp.status} khi gọi {path_and_query}. Đang kích hoạt thử lại..."
                            )
                            raise TuyaTransientNetworkException(f"HTTP {resp.status}")

                        response_text = await resp.text()
                        try:
                            data = json.loads(response_text)
                        except Exception:
                            raise TuyaAPIException(
                                code=resp.status,
                                msg=f"Máy chủ trả về JSON không hợp lệ: {response_text[:100]}",
                                status_code=resp.status,
                            )

                        logger.info(
                            f"📥 [TUYA HTTP RESPONSE] {method.upper()} {clean_path} -> HTTP {resp.status} "
                            f"({len(response_text)} bytes) | Success: {data.get('success', False)}"
                        )

                        if not data.get("success", False):
                            code = data.get("code")
                            msg = data.get("msg", "Lỗi Tuya Cloud không xác định")
                            raise TuyaAPIException(code=code, msg=msg, status_code=resp.status)

                        return data

                except (aiohttp.ClientError, asyncio.TimeoutError) as err:
                    logger.warning(f"Lỗi mạng khi gọi Tuya {path_and_query}: {err}. Đang kích hoạt thử lại...")
                    raise

        raise TuyaAPIException(code="MAX_RETRIES", msg="Thất bại sau 3 lần thử lại")

    # =========================================================================
    # CÁC API NGHIỆP VỤ CỐT LÕI (BUSINESS APIs)
    # =========================================================================

    async def get_token(
        self,
        grant_type: int = 1,
        refresh_token: Optional[str] = None,
        code: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Cấp phát hoặc làm mới Token cấp Dự án (Project) hoặc Người dùng (User OAuth).

        grant_type=1: Project Token (dùng chung cho các thiết bị OEM Sunhouse).
        grant_type=2: User OAuth Token (cho thiết bị Smart Life ngoài của người dùng).
        """
        if grant_type == 1:
            res = await self.request("GET", "/v1.0/token", params={"grant_type": 1})
            return res.get("result", {})
        elif refresh_token:
            res = await self.request("GET", f"/v1.0/token/{refresh_token}")
            return res.get("result", {})
        elif code:
            res = await self.request(
                "GET", "/v1.0/token", params={"grant_type": 2, "code": code}
            )
            return res.get("result", {})
        else:
            raise ValueError("Tham số cấp token không hợp lệ")

    async def get_user_devices(self, tuya_uid: str, token: str) -> List[Dict[str, Any]]:
        """GET /v1.0/users/{tuya_uid}/devices - Lấy danh sách thiết bị thuộc sở hữu của người dùng."""
        res = await self.request("GET", f"/v1.0/users/{tuya_uid}/devices", token=token)
        return res.get("result", [])

    async def get_associated_user_devices(self, token: str) -> List[Dict[str, Any]]:
        """GET /v1.0/iot-01/associated-users/devices - Lấy toàn bộ thiết bị liên kết với dự án (từ App Smart Life)."""
        res = await self.request("GET", "/v1.0/iot-01/associated-users/devices", token=token)
        result = res.get("result", {})
        if isinstance(result, dict) and "devices" in result:
            return result.get("devices", [])
        elif isinstance(result, list):
            return result
        return []

    async def get_device_info(self, device_id: str, token: str) -> Dict[str, Any]:
        """GET /v1.0/iot-03/devices/{device_id} - Truy vấn thông tin định danh phần cứng, IP, trạng thái online."""
        res = await self.request("GET", f"/v1.0/iot-03/devices/{device_id}", token=token)
        return res.get("result", {})

    async def get_device_specification(self, device_id: str, token: str) -> Dict[str, Any]:
        """GET /v1.0/iot-03/devices/{device_id}/specification - Lấy toàn bộ đặc tả kỹ thuật (Specification)
        gồm cả tập lệnh (functions), tập trạng thái (status) và dải giá trị (values min/max/step).

        Tự động fallback sang GET /v1.0/devices/{device_id}/functions nếu cần.
        """
        try:
            res = await self.request(
                "GET", f"/v1.0/iot-03/devices/{device_id}/specification", token=token
            )
            result = res.get("result", {})
            if result and (result.get("functions") or result.get("status")):
                return result
        except Exception as e_spec:
            logger.debug(f"Không lấy được từ /specification: {e_spec}. Đang thử fallback sang /functions...")

        # Fallback 1: GET /v1.0/devices/{device_id}/functions (Standard Functions)
        try:
            res_fn = await self.request(
                "GET", f"/v1.0/devices/{device_id}/functions", token=token
            )
            result_fn = res_fn.get("result", {})
            if result_fn and result_fn.get("functions"):
                return result_fn
        except Exception as e_fn:
            logger.debug(f"Không lấy được từ /functions: {e_fn}. Đang thử fallback sang /specifications...")

        # Fallback 2: GET /v1.0/iot-03/devices/{device_id}/specifications (tương thích ngược)
        try:
            res_old = await self.request(
                "GET", f"/v1.0/iot-03/devices/{device_id}/specifications", token=token
            )
            return res_old.get("result", {})
        except Exception:
            return {}

    async def get_device_functions(self, device_id: str, token: str) -> Dict[str, Any]:
        """GET /v1.0/devices/{device_id}/functions - Lấy toàn bộ tập lệnh điều khiển chuẩn (Standard Functions)."""
        res = await self.request("GET", f"/v1.0/devices/{device_id}/functions", token=token)
        return res.get("result", {})

    async def get_device_specifications(self, device_id: str, token: str) -> Dict[str, Any]:
        """GET /v1.0/iot-03/devices/{device_id}/specifications - Tương thích ngược."""
        res = await self.request(
            "GET", f"/v1.0/iot-03/devices/{device_id}/specifications", token=token
        )
        return res.get("result", {})

    async def get_device_status(self, device_id: str, token: str) -> List[Dict[str, Any]]:
        """GET /v1.0/iot-03/devices/{device_id}/status - Truy vấn trạng thái tức thời của toàn bộ DPs."""
        res = await self.request("GET", f"/v1.0/iot-03/devices/{device_id}/status", token=token)
        return res.get("result", [])

    async def send_device_commands(
        self, device_id: str, commands: List[Dict[str, Any]], token: str
    ) -> bool:
        """POST /v1.0/iot-03/devices/{device_id}/commands - Gửi tập lệnh điều khiển Datapoints chuẩn.

        Định dạng danh sách lệnh: [{'code': 'power_go', 'value': True}, ...]
        """
        res = await self.request(
            "POST",
            f"/v1.0/iot-03/devices/{device_id}/commands",
            json_body={"commands": commands},
            token=token,
        )
        return bool(res.get("result", False))

    async def get_thing_model(self, device_id: str, token: str) -> Dict[str, Any]:
        """GET /v2.0/cloud/thing/{device_id}/model - Lấy toàn bộ mô hình thiết bị (Thing Model) gồm tất cả DPs gốc."""
        res = await self.request("GET", f"/v2.0/cloud/thing/{device_id}/model", token=token)
        return res.get("result", {})

    async def get_thing_shadow_properties(self, device_id: str, token: str) -> List[Dict[str, Any]]:
        """GET /v2.0/cloud/thing/{device_id}/shadow/properties - Lấy danh sách thuộc tính bóng mây (Shadow Properties) của tất cả DPs gốc."""
        res = await self.request("GET", f"/v2.0/cloud/thing/{device_id}/shadow/properties", token=token)
        return res.get("result", {}).get("properties", [])

    async def send_thing_shadow_properties(
        self, device_id: str, properties: Dict[str, Any], token: str
    ) -> bool:
        """POST /v2.0/cloud/thing/{device_id}/shadow/properties/issue - Hạ lệnh điều khiển qua DP Mode / Thing Model."""
        res = await self.request(
            "POST",
            f"/v2.0/cloud/thing/{device_id}/shadow/properties/issue",
            json_body={"properties": json.dumps(properties)},
            token=token,
        )
        return bool(res.get("success", False))

    async def get_sweeper_records(
        self, device_id: str, token: str, page_no: int = 1, page_size: int = 5
    ) -> Dict[str, Any]:
        """GET /v1.0/sweeper/devices/{device_id}/records - Tra cứu lịch sử các phiên dọn dẹp của Robot."""
        params = {"page_no": page_no, "page_size": page_size}
        res = await self.request(
            "GET", f"/v1.0/sweeper/devices/{device_id}/records", params=params, token=token
        )
        return res.get("result", {})

    async def get_sweeper_multimaps(self, device_id: str, token: str) -> List[Dict[str, Any]]:
        """GET /v1.0/sweeper/devices/{device_id}/maps - Tra cứu danh sách các bản đồ đa tầng đã lưu."""
        res = await self.request("GET", f"/v1.0/sweeper/devices/{device_id}/maps", token=token)
        return res.get("result", [])
