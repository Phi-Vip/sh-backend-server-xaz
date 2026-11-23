"""Token Vault - Bộ mã hóa/giải mã an toàn AES-256-GCM cho Token & Khóa nội bộ.

Tuân thủ nghiêm ngặt:
1. Chuẩn mã hóa chứng thực AES-256-GCM (12-byte Nonce, 16-byte Auth Tag).
2. Quy định bảo vệ dữ liệu cá nhân Nghị định 356/2025/NĐ-CP (Ẩn danh hóa UID dạng sh_{SHA256}).
"""

import os
import base64
import hashlib
from typing import Optional
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes


class TokenVault:
    """Bộ bảo mật Token Vault dùng thuật toán AES-256-GCM."""

    _DEFAULT_SALT = b"sunhouse_xiaozhi_vault_salt_v2"

    def __init__(self, master_key: Optional[bytes] = None):
        """Khởi tạo TokenVault với master key 256-bit (32 bytes).

        Nếu không truyền master_key, đọc từ biến môi trường SMART_HOME_VAULT_KEY
        hoặc sinh từ khóa mặc định nội bộ an toàn cho môi trường test/dev.
        """
        if master_key is None:
            env_key = os.getenv("SMART_HOME_VAULT_KEY")
            if env_key:
                master_key = self._derive_key(env_key.encode("utf-8"))
            else:
                # Key mặc định cho môi trường R&D / Test nội bộ
                master_key = self._derive_key(b"sunhouse_xiaozhi_default_master_secret_2026")
        else:
            if isinstance(master_key, str):
                master_key = master_key.encode("utf-8")
            if len(master_key) != 32:
                master_key = self._derive_key(master_key)

        self._key = master_key
        self._aesgcm = AESGCM(self._key)

    @classmethod
    def _derive_key(cls, passphrase: bytes, salt: bytes = _DEFAULT_SALT) -> bytes:
        """Dẫn xuất khóa 256-bit từ passphrase bằng PBKDF2-HMAC-SHA256."""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100_000,
        )
        return kdf.derive(passphrase)

    def encrypt(self, plaintext: str) -> str:
        """Mã hóa chuỗi plaintext thành ciphertext Base64 bằng AES-256-GCM.

        Định dạng gói tin: [12-byte Nonce] + [Ciphertext + 16-byte Auth Tag].
        """
        if not plaintext:
            return ""

        nonce = os.urandom(12)  # 12 bytes standard IV for AES-GCM
        data_bytes = plaintext.encode("utf-8")
        ciphertext = self._aesgcm.encrypt(nonce, data_bytes, None)
        # Kết hợp nonce (12 bytes) + ciphertext (kèm auth tag 16 bytes)
        payload = nonce + ciphertext
        return base64.b64encode(payload).decode("utf-8")

    def decrypt(self, ciphertext_b64: str) -> str:
        """Giải mã chuỗi Base64 bằng AES-256-GCM. Thẩm định toàn vẹn Auth Tag."""
        if not ciphertext_b64:
            return ""

        raw_bytes = base64.b64decode(ciphertext_b64.encode("utf-8"))
        if len(raw_bytes) < 28:  # 12 bytes nonce + 16 bytes tag tối thiểu
            raise ValueError("Ciphertext quá ngắn hoặc không đúng định dạng AES-GCM")

        nonce = raw_bytes[:12]
        ciphertext = raw_bytes[12:]
        decrypted_bytes = self._aesgcm.decrypt(nonce, ciphertext, None)
        return decrypted_bytes.decode("utf-8")

    @staticmethod
    def hash_user_id(user_id: str, salt: str = "sunhouse_salt_2026") -> str:
        """Sinh UID ẩn danh một chiều tuân thủ Nghị định 356/2025/NĐ-CP.

        Format: sh_{SHA256(user_id + salt)}
        Đảm bảo phía Tuya Cloud Singapore không thể truy ngược danh tính cá nhân.
        """
        raw = f"{user_id}:{salt}".encode("utf-8")
        digest = hashlib.sha256(raw).hexdigest()
        return f"sh_{digest}"


# Singleton instance tiện dụng
vault = TokenVault()

