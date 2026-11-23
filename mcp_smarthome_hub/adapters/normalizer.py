# -*- coding: utf-8 -*-
"""ĐỘNG CƠ CHUẨN HÓA SCHEMA TỔNG QUÁT (GENERIC SCHEMA ENGINE) - CHUẨN TUYA OPENAPI.

Khắc phục triệt để cơ chế phỏng đoán hoặc mảng ứng viên tĩnh (Zero-Hardcode).
Tự động phân tích trường raw_schema JSON (functions & status) trả về từ Tuya Cloud OpenAPI:
- Nhận diện DP Công tắc nguồn: Lọc hàm type == "Boolean" có chứa tiền tố 'switch' hoặc 'power'
  (tự động khớp switch_fan, switch_led, switch_1..4, power_go, switch_spray mà không cần hardcode).
- Nhận diện DP Đại lượng (Tốc độ, Độ sáng, Nhiệt độ màu, Độ mở): Lọc hàm type == "Integer"
  theo từ khóa ngữ nghĩa và tự động đọc dải min, max, step, scale từ metadata values của Tuya.
- Bộ Quy Đổi Ngữ Nghĩa Khẩu Ngữ Đa Năng (Semantic-to-Range Mapper): Quy đổi ngôn ngữ tự nhiên
  tiếng Việt ('mạnh', 'vừa', 'nhẹ', 'tối đa', 'mờ', 'sáng rõ'...) sang dải số nguyên phần cứng,
  khắc phục triệt để lỗi ValueError: could not convert string to float.
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)

# Từ điển quy đổi ngữ nghĩa khẩu ngữ tiếng Việt sang tỷ lệ phần trăm (0.0 - 100.0%)
SEMANTIC_SPEED_WORDS: Dict[str, float] = {
    "yên tĩnh": 25.0,
    "nhẹ": 25.0,
    "yếu": 25.0,
    "êm": 25.0,
    "chậm": 25.0,
    "số 1": 25.0,
    "thấp": 25.0,
    "bình thường": 50.0,
    "vừa": 50.0,
    "trung bình": 50.0,
    "số 2": 50.0,
    "mạnh": 75.0,
    "cao": 75.0,
    "lớn": 75.0,
    "nhanh": 75.0,
    "số 3": 75.0,
    "tối đa": 100.0,
    "cực đại": 100.0,
    "hết cỡ": 100.0,
    "hết công suất": 100.0,
    "max": 100.0,
}

SEMANTIC_BRIGHTNESS_WORDS: Dict[str, float] = {
    "mờ": 20.0,
    "tối": 20.0,
    "dịu": 20.0,
    "nhẹ": 20.0,
    "vừa": 50.0,
    "trung bình": 50.0,
    "sáng rõ": 80.0,
    "rõ": 80.0,
    "sáng": 80.0,
    "sáng nhất": 100.0,
    "sáng tối đa": 100.0,
    "tối đa": 100.0,
    "cực đại": 100.0,
    "max": 100.0,
}

SEMANTIC_TEMP_WORDS: Dict[str, float] = {
    "ấm": 20.0,
    "vàng": 20.0,
    "ấm áp": 20.0,
    "trung tính": 50.0,
    "tự nhiên": 50.0,
    "trắng": 80.0,
    "lạnh": 80.0,
    "sáng trắng": 80.0,
}

# Ánh xạ từ vựng tiếng Việt khẩu ngữ sang giá trị Enum Tuya
ENUM_SEMANTIC_MAP: Dict[str, str] = {
    "yên tĩnh": "quiet",
    "nhẹ": "quiet",
    "bình thường": "normal",
    "vừa": "normal",
    "mạnh": "strong",
    "tối đa": "max",
    "cực đại": "max",
    "thấp": "low",
    "ít": "low",
    "trung bình": "middle",
    "nhiều": "high",
    "cao": "high",
    "đóng": "closed",
    "tắt nước": "closed",
}


class DeviceNormalizer:
    """Động cơ chuẩn hóa schema tổng quát theo đặc tả Tuya Cloud OpenAPI (Zero-Hardcode)."""

    @staticmethod
    def _parse_values_field(values_data: Union[str, Dict[str, Any]]) -> Dict[str, Any]:
        """Phân tích trường 'values' từ chuỗi JSON hoặc đối tượng dict."""
        if isinstance(values_data, dict):
            return values_data
        if isinstance(values_data, str):
            try:
                return json.loads(values_data)
            except Exception:
                return {}
        return {}

    @classmethod
    def get_supported_functions(cls, raw_schema: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Trích xuất danh sách các hàm điều khiển (functions) từ raw_schema hoặc status."""
        if not raw_schema:
            return []
        fns = raw_schema.get("functions")
        if fns and isinstance(fns, list) and len(fns) > 0:
            return fns
        # Dự phòng: nếu functions rỗng, sử dụng danh sách status
        st = raw_schema.get("status")
        if st and isinstance(st, list):
            return st
        return []

    @classmethod
    def find_function_dp(
        cls, raw_schema: Dict[str, Any], candidate_codes: List[str]
    ) -> Optional[Dict[str, Any]]:
        """Tìm hàm DP theo danh sách mã ưu tiên (giữ tương thích ngược)."""
        functions = cls.get_supported_functions(raw_schema)
        fn_map = {fn.get("code"): fn for fn in functions if "code" in fn}

        for code in candidate_codes:
            if code in fn_map:
                return fn_map[code]
        return None

    @classmethod
    def find_power_dp(cls, raw_schema: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Tự động nhận diện DP điều khiển nguồn (Boolean) chuẩn Tuya OpenAPI.

        Khớp mọi DP Boolean có mã chứa 'switch' hoặc 'power' (switch_fan, switch_led, switch_1..4, power_go...).
        Ưu tiên các công tắc chính; nếu chỉ có 1 DP Boolean thì tự động chọn làm nguồn.
        """
        functions = cls.get_supported_functions(raw_schema)
        bool_dps = [fn for fn in functions if fn.get("type") == "Boolean"]
        if not bool_dps:
            return None

        # 1. Tìm các DP có chứa từ khóa 'switch' hoặc 'power'
        power_candidates = [
            fn for fn in bool_dps
            if "switch" in fn.get("code", "").lower() or "power" in fn.get("code", "").lower()
        ]

        if power_candidates:
            # Ưu tiên các mã công tắc tiêu biểu nếu có nhiều DP
            primary_priority = ["switch_fan", "switch_led", "switch_1", "switch", "power_go", "power"]
            for prio_code in primary_priority:
                for fn in power_candidates:
                    if fn.get("code") == prio_code:
                        return fn
            return power_candidates[0]

        # 2. Nếu thiết bị chỉ có đúng 1 DP Boolean duy nhất, đó chính là công tắc nguồn
        if len(bool_dps) == 1:
            return bool_dps[0]

        return None

    @classmethod
    def find_scalar_dp(cls, raw_schema: Dict[str, Any], semantic_type: str) -> Optional[Dict[str, Any]]:
        """Tự động nhận diện DP kiểu Integer hoặc Enum dựa trên từ khóa ngữ nghĩa."""
        functions = cls.get_supported_functions(raw_schema)
        s_type = semantic_type.lower()

        # 1. Tốc độ gió / Quạt (speed / wind)
        if s_type in ("speed", "wind"):
            # Ưu tiên tìm DP Integer trước (ví dụ fan_speed, wind_speed)
            for fn in functions:
                code = fn.get("code", "").lower()
                if fn.get("type") == "Integer" and ("speed" in code or "wind" in code):
                    return fn
            # Sau đó tìm DP Enum (ví dụ fan_speed_enum)
            for fn in functions:
                code = fn.get("code", "").lower()
                if fn.get("type") == "Enum" and ("speed" in code or "wind" in code):
                    return fn
            return None

        # 2. Độ sáng đèn (brightness / bright)
        if s_type in ("brightness", "bright"):
            for fn in functions:
                code = fn.get("code", "").lower()
                if fn.get("type") == "Integer" and ("bright" in code or "light" in code):
                    return fn
            return None

        # 3. Nhiệt độ màu ánh sáng (color_temp / temp)
        if s_type in ("color_temp", "temp"):
            for fn in functions:
                code = fn.get("code", "").lower()
                if fn.get("type") == "Integer" and ("temp" in code or "colour" in code or "color" in code):
                    return fn
            return None

        # 4. Mức độ tổng quát (level / percent)
        if s_type in ("level", "percent"):
            # Ưu tiên: Độ sáng -> Tốc độ -> Bất kỳ DP Integer nào
            bright = cls.find_scalar_dp(raw_schema, "brightness")
            if bright:
                return bright
            speed = cls.find_scalar_dp(raw_schema, "speed")
            if speed:
                return speed
            for fn in functions:
                if fn.get("type") == "Integer":
                    return fn
            return None

        return None

    @classmethod
    def find_mode_dp(cls, raw_schema: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Tự động nhận diện DP Chế độ hoạt động (Enum)."""
        functions = cls.get_supported_functions(raw_schema)
        for fn in functions:
            code = fn.get("code", "").lower()
            if fn.get("type") == "Enum" and ("mode" in code or "scene" in code or "work" in code):
                return fn
        return None

    @classmethod
    def parse_semantic_value_to_percentage(
        cls, value: Optional[Any], semantic_type: str = "generic"
    ) -> float:
        """Quy đổi giá trị đầu vào (số, chuỗi phần trăm, hoặc khẩu ngữ tiếng Việt) thành tỷ lệ 0.0 - 100.0%."""
        if value is None:
            if semantic_type in ("brightness", "bright"):
                return 100.0
            return 50.0

        # Nếu là số nguyên hoặc số thực
        if isinstance(value, (int, float)):
            val = float(value)
            return max(0.0, min(100.0, val))

        # Nếu là chuỗi
        s_val = str(value).strip().lower()

        # Loại bỏ ký tự '%' nếu có (ví dụ "40%" -> "40")
        clean_num = s_val.replace("%", "").strip()
        try:
            val = float(clean_num)
            return max(0.0, min(100.0, val))
        except ValueError:
            pass

        # Tra cứu từ vựng tiếng Việt khẩu ngữ theo loại ngữ nghĩa
        s_type = semantic_type.lower()
        if s_type in ("speed", "wind") and s_val in SEMANTIC_SPEED_WORDS:
            return SEMANTIC_SPEED_WORDS[s_val]
        if s_type in ("brightness", "bright") and s_val in SEMANTIC_BRIGHTNESS_WORDS:
            return SEMANTIC_BRIGHTNESS_WORDS[s_val]
        if s_type in ("color_temp", "temp") and s_val in SEMANTIC_TEMP_WORDS:
            return SEMANTIC_TEMP_WORDS[s_val]

        # Tra cứu dự phòng trong toàn bộ kho từ vựng
        if s_val in SEMANTIC_SPEED_WORDS:
            return SEMANTIC_SPEED_WORDS[s_val]
        if s_val in SEMANTIC_BRIGHTNESS_WORDS:
            return SEMANTIC_BRIGHTNESS_WORDS[s_val]
        if s_val in SEMANTIC_TEMP_WORDS:
            return SEMANTIC_TEMP_WORDS[s_val]

        # Kiểm tra nếu chuỗi có chứa từ khóa số (ví dụ "số 1", "số 2", "số 3")
        digit_match = re.search(r"\d+", s_val)
        if digit_match:
            try:
                num = float(digit_match.group())
                if num <= 8:  # Số cấp quạt 1-8
                    return max(0.0, min(100.0, (num / 8.0) * 100.0))
                return max(0.0, min(100.0, num))
            except Exception:
                pass

        logger.warning(f"Không nhận diện được khẩu ngữ '{value}', sử dụng mức mặc định 50%")
        return 50.0

    @classmethod
    def _get_dp_values_meta(cls, dp_meta: Dict[str, Any]) -> Dict[str, Any]:
        """Trích xuất và phân tích metadata giá trị từ trường 'values' hoặc 'scopes' của Tuya."""
        raw_val = dp_meta.get("values")
        if not raw_val:
            raw_val = dp_meta.get("scopes")
        return cls._parse_values_field(raw_val or {})

    @classmethod
    def scale_percentage_to_dp(
        cls,
        dp_meta: Dict[str, Any],
        percent: float,
    ) -> int:
        """Quy đổi phần trăm (0.0 đến 100.0%) sang dải số nguyên phần cứng của thiết bị (min, max, step).

        Ví dụ:
        - Đèn phòng ngủ: min=10, max=1000 -> 50% = 505
        - Quạt phòng ngủ: min=1, max=100 -> 75% = 75
        """
        values_meta = cls._get_dp_values_meta(dp_meta)
        min_val = values_meta.get("min", 0)
        max_val = values_meta.get("max", 100)
        step = values_meta.get("step", 1)

        clamped_pct = max(0.0, min(100.0, float(percent)))
        raw_val = min_val + (clamped_pct / 100.0) * (max_val - min_val)

        if step > 1:
            raw_val = round((raw_val - min_val) / step) * step + min_val

        return int(max(min_val, min(max_val, round(raw_val))))

    @classmethod
    def scale_dp_to_percentage(
        cls,
        dp_meta: Dict[str, Any],
        hw_value: int,
    ) -> float:
        """Quy đổi giá trị số nguyên phần cứng ngược lại tỷ lệ phần trăm 0.0 - 100.0% để phản hồi người dùng."""
        values_meta = cls._get_dp_values_meta(dp_meta)
        min_val = values_meta.get("min", 0)
        max_val = values_meta.get("max", 100)

        if max_val <= min_val:
            return 0.0

        clamped = max(min_val, min(max_val, hw_value))
        return round(((clamped - min_val) / (max_val - min_val)) * 100.0, 1)

    @classmethod
    def match_enum_value(
        cls,
        dp_meta: Dict[str, Any],
        requested_value: str,
    ) -> Optional[str]:
        """So khớp khẩu lệnh tiếng Việt hoặc chuỗi đầu vào với dải Enum mà thiết bị hỗ trợ."""
        values_meta = cls._get_dp_values_meta(dp_meta)
        valid_range: List[str] = values_meta.get("range", [])
        if not valid_range:
            return requested_value

        norm_req = str(requested_value).strip().lower()
        if norm_req in valid_range:
            return norm_req

        mapped_alias = ENUM_SEMANTIC_MAP.get(norm_req)
        if mapped_alias and mapped_alias in valid_range:
            return mapped_alias

        # Xử lý trường hợp dải enum là chuỗi số (ví dụ: ['1', '2', '3'] hoặc ['0', '1', '2', '3'])
        if all(str(x).isdigit() for x in valid_range):
            # Nếu người dùng nói khẩu ngữ tính từ ("nhẹ", "vừa", "mạnh", "tối đa")
            if norm_req in SEMANTIC_SPEED_WORDS:
                pct = SEMANTIC_SPEED_WORDS[norm_req]
                idx = int(round((pct / 100.0) * (len(valid_range) - 1)))
                return str(valid_range[max(0, min(len(valid_range) - 1, idx))])

            # Nếu chuỗi chứa số (ví dụ "số 2", "mức 3", "cấp 1")
            digit_match = re.search(r"\d+", norm_req)
            if digit_match:
                d = digit_match.group()
                if d in valid_range:
                    return d

        for item in valid_range:
            if item in norm_req or norm_req in item:
                return item

        return None

    @classmethod
    def _parse_timer_minutes(cls, value: Optional[Any]) -> Tuple[float, bool]:
        """Phân tích đầu vào thời gian thành (số_phút, is_cancel).
        
        Quy ước:
        - 0, "0", "hủy", "tắt" -> (0.0, True)
        - "2 tiếng", "2h", "2 giờ" -> (120.0, False)
        - "30 phút", "30p" -> (30.0, False)
        - Số nguyên/thực 120 -> (120.0, False)
        """
        if value is None:
            return 30.0, False

        s_val = str(value).lower().strip()
        if s_val in ("0", "cancel", "hủy", "tắt", "off", "stop", "none", "0h", "0m"):
            return 0.0, True

        # Nếu có từ khóa giờ/tiếng (ví dụ "2 tiếng", "2.5 giờ", "1h")
        if any(h in s_val for h in ("tiếng", "giờ", "h", "hour", "hours")):
            m = re.search(r"(\d+(\.\d+)?)", s_val)
            if m:
                return float(m.group(1)) * 60.0, False

        # Nếu có từ khóa phút
        m = re.search(r"(\d+(\.\d+)?)", s_val)
        if m:
            num = float(m.group(1))
            return (0.0, True) if num <= 0 else (num, False)

        try:
            num = float(value)
            return (0.0, True) if num <= 0 else (num, False)
        except Exception:
            return 30.0, False

    @classmethod
    def _match_time_string_enum(cls, valid_range: List[str], minutes: float) -> Optional[str]:
        """Khớp chuỗi thời gian enum như ['1h', '2h', '30m', 'cancel']."""
        parsed_options = []
        for opt in valid_range:
            o_lower = opt.lower().strip()
            if o_lower in ("0", "off", "cancel", "none", "close"):
                parsed_options.append((0.0, opt))
            elif "h" in o_lower:
                m = re.search(r"(\d+(\.\d+)?)", o_lower)
                if m:
                    parsed_options.append((float(m.group(1)) * 60.0, opt))
            elif "m" in o_lower or "min" in o_lower:
                m = re.search(r"(\d+(\.\d+)?)", o_lower)
                if m:
                    parsed_options.append((float(m.group(1)), opt))
        if parsed_options:
            best_opt = min(parsed_options, key=lambda x: abs(x[0] - minutes))
            return best_opt[1]
        return None

    @classmethod
    def build_command(
        cls,
        raw_schema: Dict[str, Any],
        action: str,
        value: Optional[Any] = None,
        dp_code: Optional[str] = None,
        feature: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Xây dựng tập lệnh chuẩn Tuya [{'code': code, 'value': val}] từ khẩu lệnh ý định giọng nói.

        Áp dụng Động Cơ Generic Schema & Dynamic Traits: Tự động trích xuất metadata từ Tuya Cloud, Zero Hardcode.
        """
        # 1. Trường hợp chỉ định trực tiếp mã DP cụ thể
        if dp_code:
            dp_meta = cls.find_function_dp(raw_schema, [dp_code])
            if dp_meta:
                dp_type = dp_meta.get("type")
                if dp_type == "Integer":
                    pct = cls.parse_semantic_value_to_percentage(value, "generic")
                    scaled = cls.scale_percentage_to_dp(dp_meta, pct)
                    return [{"code": dp_code, "value": scaled}]
                elif dp_type == "Enum":
                    matched = cls.match_enum_value(dp_meta, str(value))
                    if matched:
                        return [{"code": dp_code, "value": matched}]
            return [{"code": dp_code, "value": value}]

        # 1b. Trường hợp có chỉ định bộ phận hoặc tính năng con (Sub-feature target)
        if feature:
            from adapters.dp_classifier import DPClassifier
            functions = raw_schema.get("functions", []) if isinstance(raw_schema, dict) else []
            sub_dp = DPClassifier.match_sub_feature_dp(functions, feature=feature, action=action)
            if sub_dp:
                s_code = sub_dp["code"]
                s_type = sub_dp.get("type", "Boolean")
                if action in ("turn_on", "turn_off"):
                    return [{"code": s_code, "value": (action == "turn_on")}]
                elif s_type == "Integer":
                    pct = cls.parse_semantic_value_to_percentage(value, "generic")
                    scaled = cls.scale_percentage_to_dp(sub_dp, pct)
                    return [{"code": s_code, "value": scaled}]
                elif s_type == "Enum":
                    matched = cls.match_enum_value(sub_dp, str(value))
                    return [{"code": s_code, "value": matched or value}]
                else:
                    return [{"code": s_code, "value": value}]

        # 2. Hành động Bật / Tắt nguồn (turn_on / turn_off)
        if action in ("turn_on", "turn_off"):
            power_dp = cls.find_power_dp(raw_schema)
            if not power_dp:
                from adapters.dp_classifier import DPClassifier
                cat = raw_schema.get("category", "") if isinstance(raw_schema, dict) else ""
                caps = DPClassifier.synthesize_capabilities(raw_schema, category=cat)
                if caps:
                    raise ValueError(f"Thiết bị hiện chỉ hỗ trợ các tính năng: {caps}. Tính năng bật/tắt nguồn chính chưa được nhà sản xuất mở quyền qua liên kết ngoài.")
                raise ValueError(f"Không tìm thấy DP điều khiển nguồn trong schema cho hành động {action}")
            bool_val = True if action == "turn_on" else False
            return [{"code": power_dp["code"], "value": bool_val}]

        # 2b. Hành động Hẹn giờ tắt đếm ngược (set_timer) - Generic Schema-Driven
        if action == "set_timer":
            from adapters.dp_classifier import DPClassifier
            functions = raw_schema.get("functions", []) if isinstance(raw_schema, dict) else []
            timer_dp = DPClassifier.match_timer_dp(functions)
            if not timer_dp:
                raise ValueError("Thiết bị không hỗ trợ tính năng hẹn giờ tắt")

            dp_type = timer_dp.get("type", "Integer")
            values_meta = cls._get_dp_values_meta(timer_dp)
            unit = str(values_meta.get("unit", "")).lower().strip()

            minutes, is_cancel = cls._parse_timer_minutes(value)

            # Phân nhánh 1: DP dạng Enum (ví dụ Máy lọc không khí: ['0', '1', ..., '12'])
            if dp_type == "Enum":
                valid_range = [str(x) for x in values_meta.get("range", [])]
                if not valid_range:
                    return [{"code": timer_dp["code"], "value": str(int(minutes))}]

                # Nếu là yêu cầu hủy/tắt hẹn giờ
                if is_cancel or minutes <= 0:
                    for cancel_val in ("0", "off", "cancel", "none", "close"):
                        if cancel_val in valid_range:
                            return [{"code": timer_dp["code"], "value": cancel_val}]
                    return [{"code": timer_dp["code"], "value": valid_range[0]}]

                # Kiểm tra dải range là số (ví dụ ['0', '1', '2', ..., '12'] hoặc ['15', '30', '60'])
                num_elements = []
                for x in valid_range:
                    try:
                        num_elements.append(float(x))
                    except ValueError:
                        pass

                if len(num_elements) == len(valid_range) and num_elements:
                    max_num = max(num_elements)
                    # Nếu max <= 24: đây là Enum đại diện cho SỐ GIỜ (Hours)
                    if max_num <= 24:
                        hours = max(1.0, round(minutes / 60.0))
                        non_zero = [x for x in valid_range if x not in ("0", "0.0")]
                        if non_zero:
                            best_val = min(non_zero, key=lambda x: abs(float(x) - hours))
                            return [{"code": timer_dp["code"], "value": best_val}]
                    else:
                        # Nếu max > 24: đây là Enum đại diện cho SỐ PHÚT (Minutes)
                        non_zero = [x for x in valid_range if x not in ("0", "0.0")]
                        if non_zero:
                            best_val = min(non_zero, key=lambda x: abs(float(x) - minutes))
                            return [{"code": timer_dp["code"], "value": best_val}]

                # Nếu là chuỗi có đơn vị (ví dụ ['1h', '2h', '30m'])
                matched_val = cls._match_time_string_enum(valid_range, minutes)
                if matched_val:
                    return [{"code": timer_dp["code"], "value": matched_val}]

                return [{"code": timer_dp["code"], "value": valid_range[-1] if minutes > 0 else valid_range[0]}]

            # Phân nhánh 2: DP dạng Integer (ví dụ Quạt trần countdown_fan unit="s", Ổ cắm countdown_1 unit="s")
            min_val = values_meta.get("min", 0)
            max_val = values_meta.get("max", 86400)

            if is_cancel or minutes <= 0:
                return [{"code": timer_dp["code"], "value": min_val}]

            if unit in ("s", "sec", "second", "seconds", "giây", "秒"):
                target_val = int(round(minutes * 60.0))
            elif unit in ("min", "m", "minute", "minutes", "phút", "分钟"):
                target_val = int(round(minutes))
            elif unit in ("h", "hour", "hours", "hr", "giờ", "tiếng", "小时"):
                target_val = max(1, int(round(minutes / 60.0)))
            else:
                # Nếu không khai báo unit, tự động suy luận theo max_val
                if max_val >= 3600:
                    target_val = int(round(minutes * 60.0))
                elif max_val <= 24:
                    target_val = max(1, int(round(minutes / 60.0)))
                else:
                    target_val = int(round(minutes))

            clamped = max(min_val, min(max_val, target_val))
            return [{"code": timer_dp["code"], "value": clamped}]

        # 3. Điều chỉnh tốc độ quạt (set_speed)
        if action == "set_speed":
            speed_dp = cls.find_scalar_dp(raw_schema, "speed")
            if not speed_dp:
                raise ValueError("Thiết bị không hỗ trợ tính năng điều chỉnh tốc độ")
            dp_type = speed_dp.get("type")
            if dp_type == "Enum":
                matched = cls.match_enum_value(speed_dp, str(value))
                if not matched:
                    raise ValueError(f"Giá trị tốc độ '{value}' không hợp lệ với dải enum của thiết bị")
                return [{"code": speed_dp["code"], "value": matched}]
            elif dp_type == "Integer":
                pct = cls.parse_semantic_value_to_percentage(value, "speed")
                scaled = cls.scale_percentage_to_dp(speed_dp, pct)
                return [{"code": speed_dp["code"], "value": scaled}]
            else:
                return [{"code": speed_dp["code"], "value": value}]

        # 4. Điều chỉnh độ sáng đèn (set_brightness)
        if action == "set_brightness":
            bright_dp = cls.find_scalar_dp(raw_schema, "brightness")
            if not bright_dp:
                raise ValueError("Thiết bị không hỗ trợ tính năng điều chỉnh độ sáng")
            pct = cls.parse_semantic_value_to_percentage(value, "brightness")
            scaled = cls.scale_percentage_to_dp(bright_dp, pct)
            return [{"code": bright_dp["code"], "value": scaled}]

        # 5. Điều chỉnh nhiệt độ màu (set_color_temp)
        if action == "set_color_temp":
            temp_dp = cls.find_scalar_dp(raw_schema, "color_temp")
            if not temp_dp:
                raise ValueError("Thiết bị không hỗ trợ tính năng điều chỉnh nhiệt độ màu")
            pct = cls.parse_semantic_value_to_percentage(value, "color_temp")
            scaled = cls.scale_percentage_to_dp(temp_dp, pct)
            return [{"code": temp_dp["code"], "value": scaled}]

        # 6. Điều chỉnh mức độ tổng quát (set_level)
        if action == "set_level":
            # Tự động chọn DP phù hợp nhất (Độ sáng nếu là Đèn, Tốc độ nếu là Quạt, hoặc DP Integer đầu tiên)
            scalar_dp = cls.find_scalar_dp(raw_schema, "level")
            if not scalar_dp:
                raise ValueError("Thiết bị không hỗ trợ tính năng điều chỉnh mức độ")
            pct = cls.parse_semantic_value_to_percentage(value, "generic")
            if scalar_dp.get("type") == "Integer":
                scaled = cls.scale_percentage_to_dp(scalar_dp, pct)
                return [{"code": scalar_dp["code"], "value": scaled}]
            elif scalar_dp.get("type") == "Enum":
                matched = cls.match_enum_value(scalar_dp, str(value))
                return [{"code": scalar_dp["code"], "value": matched or value}]

        # 7. Đổi chế độ hoạt động (set_mode)
        if action == "set_mode":
            mode_dp = cls.find_mode_dp(raw_schema)
            if not mode_dp:
                raise ValueError("Thiết bị không hỗ trợ tính năng chuyển chế độ")
            matched = cls.match_enum_value(mode_dp, str(value))
            if not matched:
                raise ValueError(f"Chế độ '{value}' không hợp lệ với thiết bị")
            return [{"code": mode_dp["code"], "value": matched}]

        raise ValueError(f"Hành động giọng nói chưa được hỗ trợ: {action}")
