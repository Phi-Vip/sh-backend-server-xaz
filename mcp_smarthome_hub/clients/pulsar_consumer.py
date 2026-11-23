"""Bộ Đón Nhận Sự Kiện Apache Pulsar MQ & Động Cơ Giải Mã Tuya.

Các tính năng cốt lõi:
- Giải mã bản tin sự kiện thời gian thực của Tuya cho cả 2 chuẩn:
  * pv='1.0.0': AES-128-ECB với đệm PKCS7.
  * pv='2.0': AES-128-GCM với 12 bytes IV đầu và 16 bytes Auth Tag cuối.
- Thuật toán trích xuất khóa giải mã: Cắt đúng 16 ký tự ở giữa chuỗi AccessSecret[8:24].
- Khử trùng lặp bản tin theo dataId thông qua Redis SET NX EX 600 (hoặc bộ nhớ đệm nội bộ).
- Cảnh báo chủ động qua Loa (Proactive Voice Alert): Phát hiện Robot 298 Pro Ultra gặp sự cố (fault != 0)
  hoặc trạm sạc cạn/đầy nước để kích hoạt Loa thông báo bằng tiếng Việt tự nhiên.
- Thẩm định chữ ký X-Tuya-Signature cho kênh Webhook HTTP callback dự phòng.
"""

import base64
import hashlib
import hmac
import json
import logging
import time
from typing import Any, Callable, Coroutine, Dict, List, Optional, Set

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

logger = logging.getLogger(__name__)


def decrypt_tuya_pulsar_payload(envelope: Dict[str, Any], access_secret: str) -> Dict[str, Any]:
    """Giải mã gói tin sự kiện Tuya Pulsar nhận được từ hàng đợi thông điệp.

    Quy tắc cốt lõi: Trích xuất đúng 16 bytes UTF-8 từ vị trí index 8 đến 24 của AccessSecret:
    secret_key_16 = access_secret[8:24].encode("utf-8")
    """
    if len(access_secret) < 24:
        raise ValueError("access_secret phải có độ dài tối thiểu 24 ký tự")

    secret_key_16 = access_secret[8:24].encode("utf-8")
    raw_data = envelope.get("data")
    if not raw_data:
        raise ValueError("Thiếu trường 'data' trong gói tin Pulsar")

    cipher_bytes = base64.b64decode(raw_data)
    pv = envelope.get("pv", "1.0.0")

    if pv == "2.0":
        # Chuẩn AES-128-GCM: 12 bytes đầu là IV/Nonce, 16 bytes cuối là Auth Tag
        if len(cipher_bytes) < 28:
            raise ValueError("Dữ liệu mã hóa quá ngắn đối với AES-128-GCM (tối thiểu 28 bytes)")
        iv = cipher_bytes[:12]
        tag = cipher_bytes[-16:]
        ciphertext = cipher_bytes[12:-16]

        decryptor = Cipher(
            algorithms.AES(secret_key_16),
            modes.GCM(iv, tag),
        ).decryptor()
        plain_bytes = decryptor.update(ciphertext) + decryptor.finalize()
    else:
        # Chuẩn AES-128-ECB kèm giải đệm PKCS7 (pv == "1.0.0")
        decryptor = Cipher(
            algorithms.AES(secret_key_16),
            modes.ECB(),
        ).decryptor()
        padded_bytes = decryptor.update(cipher_bytes) + decryptor.finalize()
        unpadder = padding.PKCS7(128).unpadder()
        plain_bytes = unpadder.update(padded_bytes) + unpadder.finalize()

    return json.loads(plain_bytes.decode("utf-8"))


def encrypt_tuya_pulsar_payload(
    payload_dict: Dict[str, Any],
    access_secret: str,
    pv: str = "2.0",
    iv: Optional[bytes] = None,
) -> Dict[str, Any]:
    """Hàm bổ trợ mã hóa bản tin sự kiện giả lập phục vụ kiểm thử tự động (Unit Test)."""
    import os

    secret_key_16 = access_secret[8:24].encode("utf-8")
    plain_bytes = json.dumps(payload_dict, separators=(",", ":")).encode("utf-8")

    if pv == "2.0":
        iv_bytes = iv if iv else os.urandom(12)
        encryptor = Cipher(
            algorithms.AES(secret_key_16),
            modes.GCM(iv_bytes),
        ).encryptor()
        ciphertext = encryptor.update(plain_bytes) + encryptor.finalize()
        tag = encryptor.tag
        combined = iv_bytes + ciphertext + tag
    else:
        padder = padding.PKCS7(128).padder()
        padded_bytes = padder.update(plain_bytes) + padder.finalize()
        encryptor = Cipher(
            algorithms.AES(secret_key_16),
            modes.ECB(),
        ).encryptor()
        combined = encryptor.update(padded_bytes) + encryptor.finalize()

    return {
        "data": base64.b64encode(combined).decode("utf-8"),
        "pv": pv,
        "t": int(time.time() * 1000),
    }


async def is_pulsar_event_duplicate(
    data_id: str,
    redis_client: Optional[Any] = None,
    local_cache: Optional[Dict[str, float]] = None,
    ttl_seconds: int = 600,
) -> bool:
    """Kiểm tra khử trùng lặp bản tin sự kiện theo dataId (Đảm bảo tính Idempotency).

    Trả về True nếu bản tin BỊ TRÙNG LẶP (đã xử lý), False nếu là bản tin MỚI.
    """
    if not data_id:
        return False

    if redis_client:
        try:
            # Ghi khóa Redis: SET key:pulsar:{dataId} 1 NX EX {ttl_seconds}
            key = f"key:pulsar:{data_id}"
            res = await redis_client.set(key, "1", nx=True, ex=ttl_seconds)
            return res is None
        except Exception as e:
            logger.warning(f"Lỗi kiểm tra trùng lặp trên Redis: {e}. Đang chuyển sang bộ nhớ tạm.")

    if local_cache is not None:
        now = time.time()
        # Dọn dẹp các mục đã hết hạn
        expired = [k for k, exp in local_cache.items() if exp < now]
        for k in expired:
            del local_cache[k]

        if data_id in local_cache:
            return True
        local_cache[data_id] = now + ttl_seconds
        return False

    return False


def verify_tuya_webhook_signature(
    client_id: str,
    access_secret: str,
    t: str,
    nonce: str,
    body_bytes: bytes,
    signature_header: str,
) -> bool:
    """Thẩm định tính hợp lệ của chữ ký X-Tuya-Signature cho Webhook HTTP dự phòng.

    str_to_hash = client_id + t + nonce + SHA256(body)
    sign = HMAC-SHA256(str_to_hash, access_secret).upper()
    """
    if body_bytes:
        content_sha256 = hashlib.sha256(body_bytes).hexdigest().lower()
    else:
        content_sha256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

    str_to_hash = f"{client_id}{t}{nonce}{content_sha256}"
    expected_sign = hmac.new(
        access_secret.encode("utf-8"),
        str_to_hash.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest().upper()

    return hmac.compare_digest(expected_sign, signature_header.upper())


class TuyaPulsarConsumer:
    """Bộ tiếp nhận và phân luồng xử lý các sự kiện giải mã từ Tuya Pulsar MQ."""

    def __init__(
        self,
        access_secret: str,
        redis_client: Optional[Any] = None,
        on_status_update: Optional[Callable[[str, List[Dict[str, Any]]], Coroutine]] = None,
        on_proactive_alert: Optional[Callable[[str, str, Dict[str, Any]], Coroutine]] = None,
    ):
        self.access_secret = access_secret
        self.redis_client = redis_client
        self.on_status_update = on_status_update
        self.on_proactive_alert = on_proactive_alert
        self._local_dedup_cache: Dict[str, float] = {}

    async def process_envelope(self, envelope: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Giải mã, khử trùng lặp và kích hoạt xử lý nghiệp vụ cho một bản tin Pulsar."""
        data_id = envelope.get("dataId")
        if data_id:
            is_dup = await is_pulsar_event_duplicate(
                data_id, self.redis_client, self._local_dedup_cache
            )
            if is_dup:
                logger.info(f"Bản tin sự kiện Pulsar bị trùng lặp, đã bỏ qua: {data_id}")
                return None

        # Giải mã nội dung bản tin
        payload = decrypt_tuya_pulsar_payload(envelope, self.access_secret)
        protocol = payload.get("protocol")
        dev_id = payload.get("devId") or payload.get("deviceId")

        if protocol == 4:  # deviceReport: Báo cáo cập nhật trạng thái Datapoints
            status_list = payload.get("status", [])
            await self._handle_device_report(dev_id, status_list, payload)
        elif protocol == 20:  # deviceOnline / Offline: Thiết bị kết nối/ngắt kết nối
            status = payload.get("status")
            logger.info(f"Thiết bị {dev_id} thay đổi trạng thái kết nối: {status}")

        return payload

    async def _handle_device_report(
        self, dev_id: str, status_list: List[Dict[str, Any]], raw_payload: Dict[str, Any]
    ) -> None:
        """Xử lý báo cáo trạng thái DPs và kiểm tra kích hoạt Cảnh báo Chủ động qua Loa."""
        if self.on_status_update:
            try:
                await self.on_status_update(dev_id, status_list)
            except Exception as e:
                logger.error(f"Lỗi trong callback cập nhật trạng thái của thiết bị {dev_id}: {e}")

        # Trích xuất danh sách DP thành từ điển mã-giá trị
        dps = {item.get("code"): item.get("value") for item in status_list if "code" in item}

        alert_parts = []
        # Điều kiện 1: Mã lỗi Bitmap của Robot khác 0
        fault = dps.get("fault")
        if isinstance(fault, int) and fault > 0:
            fault_reasons = []
            if fault & 1:
                fault_reasons.append("kẹt chổi quét")
            if fault & 2:
                fault_reasons.append("bánh xe bị lơ lửng")
            if fault & 4:
                fault_reasons.append("kẹt cảm biến laser LDS")
            if fault & 8:
                fault_reasons.append("hộp bụi đã đầy")
            if fault & 16:
                fault_reasons.append("vướng thảm")

            reason_str = ", ".join(fault_reasons) if fault_reasons else "gặp sự cố kỹ thuật"
            alert_parts.append(f"Thông báo từ robot hút bụi: Robot đang bị {reason_str}. Bạn vui lòng kiểm tra giúp tôi nhé!")

        # Điều kiện 2: Trạng thái bình nước của trạm sạc All-in-One Dock
        water_tank = dps.get("water_tank_status")
        if water_tank == "dirty_water_full":
            alert_parts.append("Thông báo từ trạm sạc robot: Bình nước bẩn đã đầy. Bạn vui lòng đổ nước bẩn giúp tôi nhé!")
        elif water_tank == "clean_water_empty":
            alert_parts.append("Thông báo từ trạm sạc robot: Bình nước sạch đã hết. Bạn vui lòng châm thêm nước sạch giúp tôi nhé!")
        elif water_tank == "tank_missing":
            alert_parts.append("Thông báo từ trạm sạc robot: Chưa lắp bình nước vào trạm. Bạn kiểm tra lại bình nước nhé!")

        # Kích hoạt callback phát cảnh báo bằng giọng nói tiếng Việt
        if alert_parts and self.on_proactive_alert:
            combined_message = " ".join(alert_parts)
            try:
                await self.on_proactive_alert(dev_id, combined_message, dps)
            except Exception as e:
                logger.error(f"Lỗi trong callback phát cảnh báo chủ động cho {dev_id}: {e}")
