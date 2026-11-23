"""Package Adapters chuẩn hóa Schema và đặc tả thiết bị Nhà Thông Minh.

Xuất các thành phần:
- DeviceNormalizer: Bộ chuẩn hóa lệnh động và quy đổi thang đo theo schema thiết bị.
- SweeperAdapter: Adapter chuyên sâu cho Flagship Robot hút bụi 298 Pro Ultra (32 DPs & All-in-One Dock).
"""

from .normalizer import DeviceNormalizer
from .sweeper_adapter import SweeperAdapter
from .dp_classifier import DPClassifier

__all__ = [
    "DeviceNormalizer",
    "SweeperAdapter",
    "DPClassifier",
]
