# -*- coding: utf-8 -*-
"""BỘ LỌC PHÂN HẠNG DATAPOINT (DP) THÔNG MINH & TỰ ĐỘNG TỔNG HỢP NĂNG LỰC THIẾT BỊ.
(COMMERCIAL-GRADE DYNAMIC TRAITS & VOICE-ELIGIBILITY DP CLASSIFIER)

Nhiệm vụ:
1. Lọc sạch 100% DP rác kỹ thuật ngầm (System Blacklist) để không gây tràn token prompt LLM.
2. Phân loại DPs thành 3 nhóm chuẩn xác:
   - Primary Controls (Tính năng chính): Bật/tắt chính, dải đại lượng vận hành chính.
   - Sub-Features (Tính năng phụ hợp lệ): Đèn phụ quạt, hẹn giờ đếm ngược, đảo gió, khóa trẻ em, chế độ.
   - System Blacklist (Kỹ thuật ngầm): Loại bỏ triệt để khỏi ngữ cảnh LLM.
3. Tự động sinh mô tả năng lực tiếng Việt tự nhiên, súc tích (Dynamic Capability Synthesizer)
   thay thế hoàn toàn từ điển tĩnh cứng nhắc.
4. Cung cấp bộ so khớp mục tiêu con (Sub-target DP Matcher) cho tham số `feature`.
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# Danh sách đen các mã DP hoặc tiền tố/hậu tố kỹ thuật ngầm tuyệt đối không gửi LLM
SYSTEM_BLACKLIST_CODES: Set[str] = {
    "relay_status",
    "power_memory",
    "do_not_disturb",
    "cycle_timing",
    "random_timing",
    "cycle_time",
    "random_time",
    "control_data",
    "rhythm_mode",
    "sleep_mode",
    "wakeup_mode",
    "power_on",
    "fault",
    "alarm_switch",
    "overcharge_switch",
    "add_ele",
    "cur_current",
    "cur_power",
    "cur_voltage",
}

# Tiền tố/hậu tố nhận diện telemetry và đo lường chỉ đọc
READONLY_TELEMETRY_PREFIXES = ("cur_", "add_", "total_", "ele_")


def is_blacklisted_dp(code: str) -> bool:
    """Kiểm tra xem mã DP có thuộc nhóm kỹ thuật ngầm / telemetry hay không."""
    code_lower = code.lower()
    if code_lower in SYSTEM_BLACKLIST_CODES:
        return True
    for prefix in READONLY_TELEMETRY_PREFIXES:
        if code_lower.startswith(prefix):
            return True
    if "timing" in code_lower or "memory" in code_lower:
        return True
    return False


class DPClassifier:
    """Bộ phân loại DP thông minh và tổng hợp năng lực chuẩn thương mại."""

    @staticmethod
    def classify_functions(
        functions: List[Dict[str, Any]],
        category: str = "",
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Phân loại mảng functions của thiết bị thành 3 nhóm: primary, sub_features, blacklist."""
        primary: List[Dict[str, Any]] = []
        sub_features: List[Dict[str, Any]] = []
        blacklist: List[Dict[str, Any]] = []

        cat = category.lower()

        for fn in functions:
            code = fn.get("code", "")
            code_lower = code.lower()
            dp_type = fn.get("type", "")

            # 1. Kiểm tra danh sách đen
            if is_blacklisted_dp(code_lower) or dp_type.lower() == "raw":
                blacklist.append(fn)
                continue

            # 2. Xử lý theo từng dòng thiết bị (Category)
            # Dòng Quạt (fskg, fs)
            if cat in ("fskg", "fs"):
                if code_lower in ("switch_fan", "switch"):
                    primary.append(fn)
                elif "speed" in code_lower:
                    primary.append(fn)
                elif "backlight" in code_lower or "light" in code_lower:
                    sub_features.append(fn)
                elif "countdown" in code_lower or "timer" in code_lower:
                    sub_features.append(fn)
                elif code_lower in ("child_lock", "swing", "shake", "mode"):
                    sub_features.append(fn)
                else:
                    sub_features.append(fn)

            # Dòng Đèn (dj)
            elif cat == "dj":
                if code_lower in ("switch_led", "switch"):
                    primary.append(fn)
                elif "bright" in code_lower or "temp" in code_lower:
                    primary.append(fn)
                elif code_lower in ("work_mode", "mode", "colour_data_v2", "colour_data", "scene_data_v2"):
                    sub_features.append(fn)
                elif "countdown" in code_lower or "timer" in code_lower:
                    sub_features.append(fn)
                else:
                    sub_features.append(fn)

            # Dòng Ổ cắm / Công tắc (cz, kg)
            elif cat in ("cz", "kg"):
                if "switch" in code_lower or "power" in code_lower:
                    primary.append(fn)
                elif "countdown" in code_lower or "timer" in code_lower:
                    sub_features.append(fn)
                else:
                    sub_features.append(fn)

            # Dòng Điều hòa (kt)
            elif cat == "kt":
                if code_lower in ("switch", "temp_set", "mode"):
                    primary.append(fn)
                elif "speed" in code_lower or code_lower in ("eco", "sleep", "child_lock", "clean"):
                    sub_features.append(fn)
                elif "countdown" in code_lower or "timer" in code_lower:
                    sub_features.append(fn)
                else:
                    sub_features.append(fn)

            # Dòng Máy lọc không khí (kj)
            elif cat == "kj":
                if code_lower in ("switch", "power"):
                    primary.append(fn)
                elif "speed" in code_lower or "fan_speed" in code_lower:
                    primary.append(fn)
                elif "mode" in code_lower:
                    sub_features.append(fn)
                elif code_lower in ("uv", "anion", "light", "lock", "child_lock", "filter_reset"):
                    sub_features.append(fn)
                elif "countdown" in code_lower or "timer" in code_lower:
                    sub_features.append(fn)
                else:
                    sub_features.append(fn)

            # Phân loại tổng quát (Generic Fallback)
            else:
                if dp_type == "Boolean" and ("switch" in code_lower or "power" in code_lower):
                    if not primary:
                        primary.append(fn)
                    else:
                        sub_features.append(fn)
                elif dp_type == "Integer":
                    if "countdown" in code_lower or "timer" in code_lower:
                        sub_features.append(fn)
                    else:
                        primary.append(fn)
                else:
                    sub_features.append(fn)

        return {
            "primary": primary,
            "sub_features": sub_features,
            "blacklist": blacklist,
        }

    @classmethod
    def synthesize_capabilities(
        cls,
        raw_schema: Optional[Dict[str, Any]],
        category: str = "",
    ) -> str:
        """Tự động sinh chuỗi mô tả năng lực tiếng Việt tự nhiên và súc tích từ raw_schema.

        Thay thế hoàn toàn từ điển tĩnh category_capabilities.
        """
        if not raw_schema or not isinstance(raw_schema, dict):
            return cls._fallback_capabilities(category)

        functions = raw_schema.get("functions", [])
        if not functions or not isinstance(functions, list):
            return cls._fallback_capabilities(category)

        classified = cls.classify_functions(functions, category=category)
        primary = classified["primary"]
        sub = classified["sub_features"]

        caps: List[str] = []
        cat = category.lower()

        # 1. Quạt (fskg, fs)
        if cat in ("fskg", "fs"):
            has_fan_switch = any("switch" in f.get("code", "").lower() for f in primary)
            if has_fan_switch:
                caps.append("Bật/tắt cánh quạt")
            has_speed = any("speed" in f.get("code", "").lower() for f in primary)
            if has_speed:
                caps.append("chỉnh tốc độ gió (1-100%)")

            # Tính năng phụ
            for fn in sub:
                c = fn.get("code", "").lower()
                if "backlight" in c or "light" in c:
                    caps.append("bật/tắt đèn quạt (backlight)")
                elif "countdown" in c or "timer" in c:
                    caps.append("hẹn giờ tắt (countdown)")
                elif "swing" in c or "shake" in c:
                    caps.append("đảo gió")
                elif "child_lock" in c:
                    caps.append("khóa trẻ em")

        # 2. Đèn (dj)
        elif cat == "dj":
            has_led_switch = any("switch" in f.get("code", "").lower() for f in primary)
            if has_led_switch:
                caps.append("Bật/tắt đèn")
            has_bright = any("bright" in f.get("code", "").lower() for f in primary)
            if has_bright:
                caps.append("chỉnh độ sáng (1-100%)")
            has_temp = any("temp" in f.get("code", "").lower() for f in primary)
            if has_temp:
                caps.append("đổi nhiệt độ màu ấm/trắng")

            # Tính năng phụ
            for fn in sub:
                c = fn.get("code", "").lower()
                if "work_mode" in c or "mode" in c:
                    caps.append("đổi chế độ (trắng, màu, cảnh, nhạc)")
                elif "countdown" in c or "timer" in c:
                    caps.append("hẹn giờ tắt (countdown)")

        # 3. Ổ cắm / Công tắc (cz, kg)
        elif cat in ("cz", "kg"):
            caps.append("Bật/tắt điện")
            for fn in sub:
                c = fn.get("code", "").lower()
                if "countdown" in c or "timer" in c:
                    caps.append("hẹn giờ tắt (countdown)")

        # 4. Điều hòa (kt)
        elif cat == "kt":
            caps.append("Bật/tắt điều hòa")
            caps.append("chỉnh nhiệt độ")
            for fn in sub:
                c = fn.get("code", "").lower()
                if "speed" in c:
                    caps.append("tốc độ gió")
                elif "mode" in c:
                    caps.append("chế độ lạnh/ấm")
                elif "countdown" in c or "timer" in c:
                    caps.append("hẹn giờ tắt")

        # 5. Máy lọc không khí (kj)
        elif cat == "kj":
            has_power = any("switch" in f.get("code", "").lower() or "power" in f.get("code", "").lower() for f in primary)
            if has_power:
                caps.append("Bật/tắt máy lọc không khí")
            has_speed = any("speed" in f.get("code", "").lower() for f in primary + sub)
            if has_speed:
                caps.append("chỉnh cấp tốc độ gió")
            for fn in sub:
                c = fn.get("code", "").lower()
                if "mode" in c:
                    caps.append("chế độ lọc")
                elif "uv" in c:
                    caps.append("khử khuẩn UV")
                elif "anion" in c:
                    caps.append("ion âm")
                elif "countdown" in c or "timer" in c:
                    caps.append("hẹn giờ tắt")
                elif "lock" in c:
                    caps.append("khóa trẻ em")
                elif "filter" in c:
                    caps.append("reset màng lọc")

        # 5. Tổng quát cho các thiết bị khác
        else:
            all_voiceable = primary + sub
            for fn in all_voiceable:
                c = fn.get("code", "").lower()
                t = fn.get("type", "")
                if t == "Boolean":
                    caps.append(f"bật/tắt {c}")
                elif t == "Integer":
                    if "countdown" in c:
                        caps.append("hẹn giờ tắt")
                    else:
                        caps.append(f"điều chỉnh {c}")
                elif t == "Enum":
                    caps.append(f"chế độ {c}")

        if not caps:
            return cls._fallback_capabilities(category)

        # Lọc trùng lặp năng lực nhưng vẫn bảo toàn thứ tự xuất hiện
        unique_caps = []
        for c in caps:
            if c not in unique_caps:
                unique_caps.append(c)

        # Định dạng câu tiếng Việt
        res = ", ".join(unique_caps)
        # Viết hoa chữ cái đầu tiên
        return res[0].upper() + res[1:] if res else "Bật/tắt và điều chỉnh"

    @staticmethod
    def _fallback_capabilities(category: str) -> str:
        """Trả về mô tả mặc định nếu không có schema chi tiết."""
        defaults = {
            "dj": "Bật/tắt đèn, tăng giảm độ sáng 0-100%, đổi màu RGB, đổi nhiệt độ màu",
            "fskg": "Bật/tắt quạt, chỉnh tốc độ gió 1-100%, bật/tắt đèn quạt, hẹn giờ tắt",
            "fs": "Bật/tắt quạt, chỉnh tốc độ gió, hẹn giờ tắt",
            "cz": "Bật/tắt ổ cắm điện, hẹn giờ tắt",
            "kg": "Bật/tắt công tắc điện",
            "kt": "Bật/tắt điều hòa, chỉnh nhiệt độ, tốc độ gió",
            "kj": "Bật/tắt máy lọc không khí, chỉnh tốc độ gió, chế độ lọc, khử khuẩn UV, hẹn giờ tắt",
            "cl": "Đóng/mở rèm cửa, chỉnh phần trăm độ mở",
            "sd": "Dọn dẹp, tạm dừng, về sạc, giặt sấy giẻ, chỉnh lực hút",
        }
        return defaults.get(category.lower(), "Bật/tắt và điều chỉnh thiết bị")

    @classmethod
    def match_sub_feature_dp(
        cls,
        functions: List[Dict[str, Any]],
        feature: str,
        action: str = "turn_on",
    ) -> Optional[Dict[str, Any]]:
        """Tìm DP phụ dựa trên tham số feature từ câu nói của người dùng.

        Ví dụ:
        - feature='đèn' / 'backlight' / 'đèn nền' -> DP 'backlight_switch'
        - feature='quạt' / 'cánh' / 'fan' -> DP 'switch_fan'
        """
        if not feature or not functions:
            return None

        feat_lower = feature.lower().strip()

        # Từ khóa chỉ đèn / ánh sáng phụ
        light_keywords = ("đèn", "light", "backlight", "nền", "hắt", "led", "chiếu sáng")
        # Từ khóa chỉ quạt / cánh
        fan_keywords = ("quạt", "fan", "cánh", "gió")

        # 1. Người dùng nhắc tới Đèn trên thiết bị
        if any(k in feat_lower for k in light_keywords):
            for fn in functions:
                c = fn.get("code", "").lower()
                if "backlight" in c or (c.startswith("switch_led") and "fan" in [f.get("code", "") for f in functions]):
                    return fn
            # Nếu không có backlight_switch, thử switch_led
            for fn in functions:
                c = fn.get("code", "").lower()
                if "switch_led" in c or c == "light":
                    return fn

        # 2. Người dùng nhắc tới Quạt trên thiết bị
        if any(k in feat_lower for k in fan_keywords):
            for fn in functions:
                c = fn.get("code", "").lower()
                if "switch_fan" in c or c == "fan":
                    return fn

        # 3. Người dùng nhắc tới Đèn UV / Khử khuẩn
        uv_keywords = ("uv", "khử khuẩn", "diệt khuẩn", "tia uv")
        if any(k in feat_lower for k in uv_keywords):
            for fn in functions:
                c = fn.get("code", "").lower()
                if "uv" in c:
                    return fn

        # 4. Người dùng nhắc tới Màng lọc / Reset lọc
        filter_keywords = ("màng lọc", "filter", "lưới lọc", "reset lọc")
        if any(k in feat_lower for k in filter_keywords):
            for fn in functions:
                c = fn.get("code", "").lower()
                if "filter" in c:
                    return fn

        # 5. So khớp trực tiếp tên mã DP
        for fn in functions:
            c = fn.get("code", "").lower()
            if feat_lower in c or c in feat_lower:
                return fn

        return None

    @classmethod
    def match_timer_dp(
        cls,
        functions: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """Tìm DP đếm ngược / hẹn giờ (countdown / timer). Ưu tiên DP có quyền ghi (rw / wr)."""
        if not functions:
            return None

        # Ưu tiên các DP có quyền ghi (access_mode != "ro")
        writable_candidates = [
            fn for fn in functions
            if fn.get("access_mode", "rw") in ("rw", "wr")
        ]
        target_list = writable_candidates if writable_candidates else functions

        for fn in target_list:
            c = fn.get("code", "").lower()
            if "countdown" in c or "timer" in c:
                return fn

        return None

