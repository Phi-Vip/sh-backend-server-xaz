"""MCP SmartHome & Home Assistant Hub (mcp_smarthome_hub).

Máy chủ MCP Endpoint độc lập (Port 8005) chuyên trách quản lý, định tuyến và điều khiển
toàn bộ hệ sinh thái thiết bị IoT:
- Sunhouse OEM (Robot 298 Pro Ultra 32 DPs & All-in-One Dock qua Tuya Cloud).
- Thiết bị Tuya Smart Life ngoài thị trường.
- Máy chủ Home Assistant Hub cục bộ qua Reverse WebSocket Tunnel (wss://.../ha/tunnel).
- Thiết bị Sunhouse AWS IoT Core.
"""

from .storage import (
    TokenVault,
    vault,
    Base,
    PlatformType,
    User,
    Speaker,
    TuyaProjectToken,
    TuyaUserCredential,
    HomeAssistantCredential,
    DeviceCache,
    PairingSession,
    SmartHomeDAL,
    dal,
    TuyaTokenManager,
    token_manager,
)

from .clients import (
    TuyaCloudClient,
    TuyaAPIException,
    TuyaPulsarConsumer,
    decrypt_tuya_pulsar_payload,
    is_pulsar_event_duplicate,
)

from .adapters import (
    DeviceNormalizer,
    SweeperAdapter,
)

__all__ = [
    # Tầng Lưu trữ & Bảo mật DAL (Giai đoạn 1)
    "TokenVault",
    "vault",
    "Base",
    "PlatformType",
    "User",
    "Speaker",
    "TuyaProjectToken",
    "TuyaUserCredential",
    "HomeAssistantCredential",
    "DeviceCache",
    "PairingSession",
    "SmartHomeDAL",
    "dal",
    "TuyaTokenManager",
    "token_manager",
    # Tầng Kết nối Đám mây & Sự kiện (Giai đoạn 2)
    "TuyaCloudClient",
    "TuyaAPIException",
    "TuyaPulsarConsumer",
    "decrypt_tuya_pulsar_payload",
    "is_pulsar_event_duplicate",
    # Tầng Chuẩn hóa Schema & Adapter Robot (Giai đoạn 2)
    "DeviceNormalizer",
    "SweeperAdapter",
]

