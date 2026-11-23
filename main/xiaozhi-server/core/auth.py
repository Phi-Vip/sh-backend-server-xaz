import os
import hmac
import base64
import hashlib
import time
from typing import Optional, Dict, Any, Tuple
from core.utils.auth import AuthToken, is_token_revoked


class AuthenticationError(Exception):
    """Xác thực thất bại"""

    pass


class AuthManager:
    """
    Bộ quản lý xác thực tập trung: Hỗ trợ chuẩn AuthToken AES-GCM duy nhất (Phương án 1A)
    kèm cơ chế Dual-Verify chuyển tiếp với chuẩn cũ HMAC-SHA256 nếu UNIFIED_AES_GCM_TOKEN=false.
    """

    def __init__(self, secret_key: str, expire_seconds: int = 60 * 60 * 24 * 30):
        if not expire_seconds or expire_seconds < 0:
            self.expire_seconds = 60 * 60 * 24 * 30
        else:
            self.expire_seconds = expire_seconds
        self.secret_key = secret_key
        # Khởi tạo công cụ AuthToken AES-GCM
        self.aes_token_engine = AuthToken(secret_key)
        self.unified_only = os.getenv("UNIFIED_AES_GCM_TOKEN", "false").lower() in ("true", "1", "yes")

    def _sign(self, content: str) -> str:
        """HMAC-SHA256 cũ"""
        sig = hmac.new(
            self.secret_key.encode("utf-8"), content.encode("utf-8"), hashlib.sha256
        ).digest()
        return base64.urlsafe_b64encode(sig).decode("utf-8").rstrip("=")

    def generate_token(
        self,
        client_id: str,
        username: str,
        user_id: Optional[str] = None,
        expire_hours: Optional[int] = None,
    ) -> str:
        """
        Phát hành AuthToken chuẩn AES-GCM
        """
        hours = expire_hours or int(self.expire_seconds / 3600)
        return self.aes_token_engine.generate_token(
            device_id=username,
            user_id=user_id,
            client_id=client_id,
            expire_hours=hours,
        )

    def verify_token(
        self, token: str, client_id: Optional[str] = None, username: Optional[str] = None
    ) -> bool:
        """
        Xác thực token: Ưu tiên chuẩn 1A AuthToken AES-GCM, fallback legacy HMAC-SHA256 nếu chưa khóa cờ UNIFIED
        """
        if not token:
            return False

        clean_device = username.replace("-", ":").lower().strip() if username else None

        # 1. Thử xác thực với chuẩn mới AuthToken AES-GCM
        valid_aes, payload = self.aes_token_engine.verify_token_payload(token, check_revoked=True)
        if valid_aes and payload:
            token_dev = payload.get("device_id", "").replace("-", ":").lower().strip()
            if clean_device and token_dev != clean_device:
                return False
            return True

        # 2. Nếu không phải AES-GCM token và hệ thống cho phép Dual-Verify (chế độ chuyển tiếp)
        if not self.unified_only:
            try:
                sig_part, ts_str = token.split(".")
                ts = int(ts_str)
                if int(time.time()) - ts > self.expire_seconds:
                    return False  # Hết hạn

                expected_sig = self._sign(f"{client_id}|{username}|{ts}")
                if hmac.compare_digest(sig_part, expected_sig):
                    # Kiểm tra thu hồi mốc thời gian
                    if clean_device and is_token_revoked(clean_device, ts):
                        return False
                    return True
            except Exception:
                pass

        return False

    def get_token_payload(self, token: str) -> Optional[Dict[str, Any]]:
        """Lấy payload của AuthToken AES-GCM (chứa user_id, device_id, client_id, iat, exp) (Task 3.3)."""
        if not token:
            return None
        valid_aes, payload = self.aes_token_engine.verify_token_payload(token, check_revoked=False)
        if valid_aes and payload:
            return payload
        return None
