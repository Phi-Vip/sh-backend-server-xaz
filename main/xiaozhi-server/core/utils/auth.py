import jwt
import time
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Tuple, Optional
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.backends import default_backend
import base64


import jwt
import time
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Tuple, Optional, Dict, Any
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.backends import default_backend
import base64

# Bộ đệm bộ nhớ cho thời điểm thu hồi token {normalized_mac: (revoked_before_ts, cache_exp)}
_revocation_cache: Dict[str, Tuple[int, float]] = {}


def is_token_revoked(device_id: str, iat: int) -> bool:
    """Kiểm tra token có bị thu hồi tức thì qua mốc revoked_before không (Task 2.4)."""
    if not device_id or not iat:
        return False
    clean_mac = device_id.replace("-", ":").lower().strip()
    now = time.time()

    # 1. Đọc nhanh từ in-memory cache
    if clean_mac in _revocation_cache:
        rev_before, exp = _revocation_cache[clean_mac]
        if now < exp:
            return iat <= rev_before

    # 2. Đọc từ Redis
    try:
        redis_url = os.getenv("REDIS_URL")
        if redis_url:
            import redis
            r = redis.Redis.from_url(
                redis_url,
                decode_responses=True,
                socket_connect_timeout=0.2,
                socket_timeout=0.2,
            )
            val = r.get(f"xiaozhi:revoked_before:{clean_mac}")
            if val is not None:
                rev_ts = int(val)
                _revocation_cache[clean_mac] = (rev_ts, now + 5.0)
                return iat <= rev_ts
    except Exception:
        pass
    return False


def revoke_device_tokens(device_id: str, revoked_at: Optional[int] = None) -> int:
    """Đánh dấu thu hồi mọi token phát hành trước mốc revoked_at (Task 2.4)."""
    if not device_id:
        return 0
    clean_mac = device_id.replace("-", ":").lower().strip()
    rev_ts = revoked_at if revoked_at is not None else int(time.time())
    now = time.time()
    _revocation_cache[clean_mac] = (rev_ts, now + 5.0)

    try:
        redis_url = os.getenv("REDIS_URL")
        if redis_url:
            import redis
            r = redis.Redis.from_url(
                redis_url,
                decode_responses=True,
                socket_connect_timeout=0.5,
                socket_timeout=0.5,
            )
            # Lưu mốc thời gian thu hồi với TTL 30 ngày
            r.set(f"xiaozhi:revoked_before:{clean_mac}", rev_ts, ex=86400 * 30)
            # Phát tín hiệu Pub/Sub để ngắt kết nối WebSocket đang hoạt động tức thì (<= 500ms)
            revoke_payload = json.dumps({"device_id": clean_mac, "revoked_at": rev_ts})
            r.publish("xiaozhi:control:revoke", revoke_payload)
    except Exception:
        pass
    return rev_ts


class AuthToken:
    def __init__(self, secret_key: str):
        if isinstance(secret_key, str):
            self.secret_key = secret_key.encode()
        else:
            self.secret_key = secret_key
        # Từ secret_key dẫn xuất khóa AES-256 (32 bytes)
        self.encryption_key = self._derive_key(32)

    def _derive_key(self, length: int) -> bytes:
        """Dẫn xuất khóa đối xứng cố định từ secret"""
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

        salt = b"xiaozhi_unified_salt_2026"
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=length,
            salt=salt,
            iterations=100000,
            backend=default_backend(),
        )
        return kdf.derive(self.secret_key)

    def _encrypt_payload(self, payload: dict) -> str:
        """Sử dụng AES-GCM mã hóa toàn bộ payload"""
        payload_json = json.dumps(payload)
        iv = os.urandom(12)
        cipher = Cipher(
            algorithms.AES(self.encryption_key),
            modes.GCM(iv),
            backend=default_backend(),
        )
        encryptor = cipher.encryptor()
        ciphertext = encryptor.update(payload_json.encode()) + encryptor.finalize()
        tag = encryptor.tag
        encrypted_data = iv + ciphertext + tag
        return base64.urlsafe_b64encode(encrypted_data).decode()

    def _decrypt_payload(self, encrypted_data: str) -> dict:
        """Giải mã AES-GCM payload"""
        data = base64.urlsafe_b64decode(encrypted_data.encode())
        iv = data[:12]
        tag = data[-16:]
        ciphertext = data[12:-16]

        cipher = Cipher(
            algorithms.AES(self.encryption_key),
            modes.GCM(iv, tag),
            backend=default_backend(),
        )
        decryptor = cipher.decryptor()
        plaintext = decryptor.update(ciphertext) + decryptor.finalize()
        return json.loads(plaintext.decode())

    def generate_token(
        self,
        device_id: str,
        user_id: Optional[str] = None,
        client_id: Optional[str] = None,
        expire_hours: int = 720,  # Mặc định 30 ngày (Task 2.1)
        scope: str = "voice,vision",
    ) -> str:
        """
        Phát hành chuỗi AuthToken AES-GCM thống nhất (Phương án 1A)
        Payload đầy đủ: {user_id, device_id, client_id, iat, exp, scope}
        """
        iat = int(time.time())
        exp = iat + int(expire_hours * 3600)

        payload = {
            "user_id": user_id or "anonymous",
            "device_id": device_id,
            "client_id": client_id or "default",
            "iat": iat,
            "exp": exp,
            "scope": scope,
        }

        encrypted_payload = self._encrypt_payload(payload)
        outer_payload = {"data": encrypted_payload, "iat": iat, "exp": exp}
        token = jwt.encode(outer_payload, self.secret_key, algorithm="HS256")
        return token

    def verify_token_payload(
        self, token: str, check_revoked: bool = True
    ) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Xác thực và giải mã AuthToken AES-GCM, trả về (is_valid, payload_dict)
        """
        try:
            outer_payload = jwt.decode(token, self.secret_key, algorithms=["HS256"])
            inner_payload = self._decrypt_payload(outer_payload["data"])

            # 1. Kiểm tra thời hạn hết hạn
            if inner_payload.get("exp", 0) < time.time():
                return False, None

            # 2. Kiểm tra thu hồi tức thì qua Redis (Task 2.4)
            if check_revoked:
                dev_id = inner_payload.get("device_id", "")
                iat = inner_payload.get("iat", 0)
                if is_token_revoked(dev_id, iat):
                    return False, None

            return True, inner_payload

        except (jwt.InvalidTokenError, json.JSONDecodeError, Exception):
            return False, None

    def verify_token(
        self, token: str, check_revoked: bool = True
    ) -> Tuple[bool, Optional[str]]:
        """
        Xác thực token tương thích ngược, trả về (is_valid, device_id)
        """
        valid, payload = self.verify_token_payload(token, check_revoked=check_revoked)
        if valid and payload:
            return True, payload.get("device_id")
        return False, None
