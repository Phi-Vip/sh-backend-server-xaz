"""Cơ sở dữ liệu Đa người dùng (Multi-Tenant Database Models) cho Hệ sinh thái Smarthome.

Hỗ trợ đầy đủ 4 loại nền tảng (PlatformType):
1: sunhouse_aws (Thiết bị gia dụng nội bộ Sunhouse qua AWS IoT Core)
2: tuya_oem_esunhouse (Thiết bị OEM chip Tuya - Robot 298 Pro Ultra qua App eSunhouse)
3: tuya_external_smartlife (Thiết bị Tuya / Smart Life trôi nổi ngoài thị trường)
4: home_assistant (Thực thể Home Assistant kết nối qua WebSocket Tunnel)
"""

from datetime import datetime
from enum import IntEnum
from sqlalchemy import Column, String, Integer, Boolean, DateTime, Text, ForeignKey, Index
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class PlatformType(IntEnum):
    """Mã định danh nền tảng thiết bị trong hệ sinh thái Sunhouse & XiaoZhi."""
    SUNHOUSE_AWS = 1
    TUYA_OEM_ESUNHOUSE = 2
    TUYA_EXTERNAL_SMARTLIFE = 3
    HOME_ASSISTANT = 4


def extract_mac_and_device_id(identifier: str | None = None) -> tuple[str, str]:
    """Phân tách và chuẩn hóa cặp (mac, device_id) từ thông số thực tế backend nhận được từ ESP32.

    ESP32 gửi lên header Device-Id chính là địa chỉ MAC của chip (ví dụ: '12:34:56:78:9a:bc').
    Hàm này chuẩn hóa chuỗi về định dạng MAC chuẩn mà backend và ESP32 cùng giao tiếp.
    Nếu không có identifier truyền vào, trả về ("", "") và để tầng DAL/Router xử lý động.
    """
    if not identifier:
        return "", ""

    raw = str(identifier).strip()
    clean = raw.lower()
    if "_" in raw:
        candidate = raw.split("_")[-1].lower()
        if len(candidate) == 12:
            mac = ":".join(candidate[i:i+2] for i in range(0, 12, 2))
            return mac, mac
    hex_clean = clean.replace(":", "").replace("-", "")
    if len(hex_clean) == 12:
        mac = ":".join(hex_clean[i:i+2] for i in range(0, 12, 2))
        return mac, mac
    return clean, raw


class User(Base):
    """Bảng quản lý tài khoản người dùng đa người dùng."""
    __tablename__ = "users"

    user_id = Column(String(64), primary_key=True)
    pseudonym_tuya_uid = Column(String(128), unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    speakers = relationship("Speaker", back_populates="user", cascade="all, delete-orphan")
    tuya_credentials = relationship("TuyaUserCredential", back_populates="user", cascade="all, delete-orphan")
    ha_credentials = relationship("HomeAssistantCredential", back_populates="user", cascade="all, delete-orphan")
    devices = relationship("DeviceCache", back_populates="user", cascade="all, delete-orphan")
    sharing_sessions = relationship("TuyaSharingSession", back_populates="user", cascade="all, delete-orphan")


class Speaker(Base):
    """Bảng ánh xạ Loa thông minh XiaoZhi (ESP32-S3)."""
    __tablename__ = "speakers"

    speaker_mac = Column(String(32), primary_key=True)
    device_id = Column(String(64), nullable=True, index=True)
    user_id = Column(String(64), ForeignKey("users.user_id"), nullable=False, index=True)
    device_name = Column(String(128), default="Loa thông minh XiaoZhi")
    home_id = Column(String(64), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="speakers")
    agent_profile = relationship("AgentProfile", back_populates="speaker", uselist=False, cascade="all, delete-orphan")


class AgentProfile(Base):
    """Bảng cấu hình Agent động theo từng loa thông minh (Task 3.1 - Giai đoạn 3)."""
    __tablename__ = "agent_profiles"

    speaker_mac = Column(String(32), ForeignKey("speakers.speaker_mac", ondelete="CASCADE"), primary_key=True)
    user_id = Column(String(64), ForeignKey("users.user_id"), nullable=False, index=True)
    assistant_name = Column(String(64), default="default")
    prompt = Column(Text, nullable=True)
    tts_voice_id = Column(String(64), default="default")  # EdgeTTS / CloudTTS / VieneuTTS voice
    llm_model_profile = Column(String(64), default="default")
    enabled_plugins = Column(Text, nullable=True)  # JSON string
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    speaker = relationship("Speaker", back_populates="agent_profile")
    user = relationship("User")



class TuyaProjectToken(Base):
    """Bảng lưu Project-level Token (grant_type=1) dùng chung cho toàn hệ thống thiết bị OEM."""
    __tablename__ = "tuya_project_tokens"

    client_id = Column(String(64), primary_key=True)
    access_token_encrypted = Column(Text, nullable=False)
    refresh_token_encrypted = Column(Text, nullable=False)
    expire_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TuyaUserCredential(Base):
    """Bảng lưu OAuth User-level Token (grant_type=2) cho thiết bị Smart Life ngoài thị trường."""
    __tablename__ = "tuya_user_credentials"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), ForeignKey("users.user_id"), nullable=False, index=True)
    external_tuya_uid = Column(String(64), nullable=False, index=True)
    access_token_encrypted = Column(Text, nullable=False)
    refresh_token_encrypted = Column(Text, nullable=False)
    expire_at = Column(DateTime, nullable=False)
    auth_source = Column(String(32), default="oauth2")  # 'oauth2' hoặc 'qr_ticket'
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="tuya_credentials")


class HomeAssistantCredential(Base):
    """Bảng lưu trữ thông tin kết nối đường hầm Home Assistant Reverse WebSocket."""
    __tablename__ = "ha_credentials"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), ForeignKey("users.user_id"), nullable=False, index=True)
    ha_endpoint_url = Column(String(256), nullable=False)
    ha_token_encrypted = Column(Text, nullable=False)
    tunnel_id = Column(String(64), nullable=False)
    is_online = Column(Boolean, default=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="ha_credentials")


class DeviceCache(Base):
    """Bộ nhớ đệm danh mục thiết bị hợp nhất của toàn bộ hệ thống."""
    __tablename__ = "device_cache"

    device_id = Column(String(64), primary_key=True)
    user_id = Column(String(64), ForeignKey("users.user_id"), nullable=False, index=True)
    tuya_home_id = Column(String(64), nullable=True)
    product_id = Column(String(64), nullable=True)  # PID từ Tuya Cloud
    device_name = Column(String(128), nullable=False)
    category = Column(String(32), nullable=False)  # 'sd' (robot), 'kg' (công tắc), 'dj' (đèn)...
    platform_type = Column(Integer, nullable=False, default=PlatformType.TUYA_OEM_ESUNHOUSE)
    local_key_encrypted = Column(Text, nullable=True)  # Dùng cho Phase 2 Tuya LAN TCP 6668
    local_ip = Column(String(64), nullable=True)
    is_online = Column(Boolean, default=True)
    raw_schema = Column(Text, nullable=True)  # JSON đặc tả DPs từ /specifications
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="devices")

    __table_args__ = (
        Index("idx_device_user_platform", "user_id", "platform_type"),
    )


class PairingSession(Base):
    """Bảng quản lý phiên ghép nối Loa qua mã PIN ngắn hạn hoặc QR OLED."""
    __tablename__ = "pairing_sessions"

    pairing_code = Column(String(16), primary_key=True)
    speaker_mac = Column(String(32), index=True, nullable=False)
    user_id = Column(String(64), nullable=True)
    status = Column(String(32), default="pending")  # 'pending', 'claimed', 'expired'
    expire_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class TuyaSharingSession(Base):
    """Bảng lưu trữ phiên ủy quyền Tuya Sharing SDK / Home Assistant."""
    __tablename__ = "tuya_sharing_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), ForeignKey("users.user_id"), nullable=False, unique=True, index=True)
    user_code = Column(String(64), nullable=False)
    terminal_id = Column(String(64), nullable=False)
    endpoint = Column(String(256), nullable=False)
    tuya_uid = Column(String(64), nullable=True)
    session_data_encrypted = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="sharing_sessions")

