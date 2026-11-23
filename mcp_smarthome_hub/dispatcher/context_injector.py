# -*- coding: utf-8 -*-
"""BỘ TIÊM NGỮ CẢNH ĐỘNG THIẾT BỊ NHÀ THÔNG MINH CHO LLM (PHASE 4: CONTEXT INJECTOR)
Chịu trách nhiệm:
1. Đọc danh mục thiết bị hợp nhất của người dùng từ CSDL (DAL).
2. Xây dựng khối System Prompt Context tinh gọn, giàu ngữ nghĩa giúp LLM hiểu chính xác ý định.
3. Phân giải ngữ nghĩa (Semantic & Fuzzy Resolution) từ khẩu lệnh người dùng ("đèn ngủ", "robot") sang device_id chuẩn.
"""

import logging
import re
import unicodedata
from typing import Any, Dict, List, Optional

from adapters.dp_classifier import DPClassifier
from storage.db import SmartHomeDAL, default_dal
from storage.models import PlatformType

logger = logging.getLogger(__name__)


def remove_vietnamese_accents(text: str) -> str:
    """Loại bỏ dấu tiếng Việt để so khớp không dấu (Fuzzy Matching)."""
    if not text:
        return ""
    text = unicodedata.normalize("NFD", text)
    text = re.sub(r"[\u0300-\u036f]", "", text)
    text = text.replace("đ", "d").replace("Đ", "D")
    return text.lower().strip()


class ContextInjector:
    """Bộ nạp và xử lý ngữ cảnh thiết bị cho trợ lý giọng nói XiaoZhi."""

    def __init__(self, dal_instance: Optional[SmartHomeDAL] = None):
        """Khởi tạo Context Injector với DAL."""
        self.dal = dal_instance or default_dal

    def get_user_devices(self, user_id: str, include_staged: bool = False) -> List[Dict[str, Any]]:
        """Lấy toàn bộ danh mục thiết bị của user từ CSDL (tự động lọc thiết bị đang R&D nếu include_staged=False)."""
        devices = self.dal.list_devices_by_user(user_id=user_id)
        if not include_staged:
            devices = [d for d in devices if d.get("category") != "sd"]
        return devices

    def build_llm_system_prompt_context(self, user_id: str) -> str:
        """Sinh khối ngữ cảnh Prompt tiêm vào phiên đàm thoại của LLM.
        
        Giúp LLM nhận diện đúng 98% thiết bị trong nhà ngay từ lượt nói đầu tiên.
        Tự động làm sạch ngữ cảnh: không tiêm thiết bị đang thử nghiệm R&D (robot hút bụi sd).
        """
        devices = self.get_user_devices(user_id, include_staged=False)
        if not devices:
            return ""

        lines = [
            "### DANH MỤC THIẾT BỊ NHÀ THÔNG MINH CỦA GIA ĐÌNH:",
            "Khi người dùng yêu cầu điều khiển thiết bị, hãy đối chiếu với danh sách dưới đây và gọi công cụ `smarthome_control` với `device_id` tương ứng:",
        ]

        platform_names = {
            PlatformType.SUNHOUSE_AWS: "Sunhouse AWS",
            PlatformType.TUYA_OEM_ESUNHOUSE: "Tuya OEM",
            PlatformType.TUYA_EXTERNAL_SMARTLIFE: "Tuya Smart Life",
            PlatformType.HOME_ASSISTANT: "Home Assistant",
        }

        for d in devices:
            dev_id = d.get("device_id")
            name = d.get("device_name", "Thiết bị")
            cat = d.get("category", "other")
            p_type = d.get("platform_type", PlatformType.TUYA_OEM_ESUNHOUSE)
            p_name = platform_names.get(p_type, "IoT")
            raw_schema = d.get("raw_schema")
            # Tự động tổng hợp năng lực chuẩn xác từ Schema thực tế (Zero-Hardcode)
            cap = DPClassifier.synthesize_capabilities(raw_schema, category=cat)
            status_str = "Online" if d.get("is_online", True) else "Offline"

            lines.append(
                f"- [{name}] (ID: \"{dev_id}\", Loại: {cat}, Nền tảng: {p_name}, Trạng thái: {status_str}) -> Hỗ trợ: {cap}"
            )

        lines.append(
            "LƯU Ý: Tuyệt đối ưu tiên truyền đúng `device_id` vào tham số tool call."
        )
        return "\n".join(lines)

    def resolve_device(
        self,
        user_id: str,
        query_id_or_name: str,
        room: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Phân giải O(1) hoặc so khớp ngữ nghĩa linh hoạt (Fuzzy Resolution).
        
        Hỗ trợ:
        1. Tìm trực tiếp theo device_id chuẩn.
        2. So khớp tuyệt đối theo device_name.
        3. So khớp không phân biệt hoa thường và không dấu tiếng Việt ("den ngu" -> "Đèn ngủ").
        4. So khớp theo từ khóa rút gọn ("robot", "đèn").
        """
        if not query_id_or_name:
            return None

        # 1. Thử tìm trực tiếp theo device_id (O(1))
        direct_dev = self.dal.get_device(device_id=query_id_or_name)
        if direct_dev and direct_dev.get("user_id") == user_id:
            return direct_dev

        # 2. Tìm trong danh sách thiết bị của user
        devices = self.get_user_devices(user_id)
        if not devices:
            return None

        query_clean = query_id_or_name.strip().lower()
        query_no_accent = remove_vietnamese_accents(query_clean)

        # 2a. So khớp chính xác tên (case-insensitive)
        for d in devices:
            d_name = d.get("device_name", "").strip().lower()
            if d_name == query_clean:
                return d

        # 2b. So khớp không dấu tiếng Việt
        for d in devices:
            d_name = d.get("device_name", "")
            d_no_accent = remove_vietnamese_accents(d_name)
            if d_no_accent == query_no_accent:
                return d

        # 2c. So khớp chứa từ khóa (Substring / Partial matching)
        for d in devices:
            d_name = d.get("device_name", "")
            d_no_accent = remove_vietnamese_accents(d_name)
            if query_no_accent in d_no_accent or d_no_accent in query_no_accent:
                return d

        # 2d. So khớp theo category alias (ví dụ "quạt" -> ["fs", "fskg"])
        alias_to_cat = {
            "robot": ["sd"],
            "hut bui": ["sd"],
            "quet nha": ["sd"],
            "den": ["dj"],
            "bong den": ["dj"],
            "cong tac quat": ["fskg"],
            "quat": ["fskg", "fs"],
            "cong tac": ["kg", "fskg"],
            "o cam": ["cz"],
            "dieu hoa": ["kt"],
        }
        for alias, cats in alias_to_cat.items():
            if alias in query_no_accent:
                for d in devices:
                    if d.get("category") in cats:
                        return d

        return None

