"""Đặc Tả Tập Lệnh & Adapter Cho Flagship Robot Hút Bụi 298 Pro Ultra & Trạm Sạc All-in-One.

Đóng gói và quản lý trọn vẹn 32 Datapoints (DPs):
- Nhóm điều khiển cơ bản: power_go, pause, mode, direction_control, suction, cistern, switch_charge, seek.
- Nhóm trạm sạc đa năng All-in-One Dock: dust_collection (hút rác lên túi 3L), collection_mode, mop_clean,
  wash_frequency, hot_water_wash (giặt nước nóng 60°C), mop_dry (sấy khí nóng), dry_time.
- Nhóm cảm biến thông minh & AI: carpet_clean_mode (tự nâng giẻ 10.5mm), carpet_turbo (tăng áp 20.000Pa),
  ai_obstacle_avoidance (tránh chướng ngại vật AI).
- Nhóm trạng thái, chẩn đoán & phụ kiện: status, water_tank_status, giải mã mã lỗi Bitmap (DP 11),
  tuổi thọ phụ kiện (filter, edge_brush, roll_brush) và các lệnh đặt lại phụ kiện.
"""

from typing import Any, Dict, List, Optional, Tuple

# Bảng ánh xạ trạng thái hoạt động của Robot sang câu nói tiếng Việt tự nhiên
STATUS_VI_MAP = {
    "cleaning": "đang dọn dẹp nhà",
    "paused": "đang tạm dừng",
    "charging": "đang sạc pin tại trạm",
    "charge_done": "đã sạc đầy pin",
    "mop_washing": "đang tự động giặt giẻ tại dock",
    "dust_emptying": "đang tự động hút rác lên túi chứa tại trạm",
    "drying": "đang sấy khô giẻ bằng khí nóng",
    "standby": "đang ở chế độ chờ",
    "goto_charge": "đang di chuyển về dock sạc",
    "fault": "đang gặp sự cố kỹ thuật",
}

# Bảng ánh xạ chế độ làm sạch sang tiếng Việt
MODE_VI_MAP = {
    "smart": "dọn dẹp thông minh toàn nhà",
    "zone": "dọn dẹp theo vùng chỉ định",
    "room": "dọn dẹp theo phòng",
    "spot": "dọn dẹp điểm",
    "mop_only": "chỉ lau nhà",
    "sweep_and_mop": "vừa quét vừa lau",
}

# Bảng giải mã mã lỗi Bitmap DP 11 của Robot 298 Pro Ultra sang nguyên nhân sự cố
FAULT_BITMAP_REASONS = {
    1 << 0: "Kẹt chổi quét chính",
    1 << 1: "Bánh xe bị lơ lửng hoặc kênh",
    1 << 2: "Kẹt cảm biến laser LDS chống va đập",
    1 << 3: "Hộp chứa bụi trên robot đã đầy",
    1 << 4: "Robot bị vướng thảm không di chuyển được",
    1 << 5: "Cảm biến chống rơi bị bẩn, cần vệ sinh",
}


# Cờ Feature Flag: Tạm thời đóng băng/ẩn thiết bị Robot hút bụi (category 'sd')
# trong giai đoạn nghiên cứu phát triển (R&D) phần cứng chưa xuất xưởng
ENABLE_SWEEPER_RND = False


class SweeperAdapter:
    """Adapter chuyên sâu cho dòng Robot hút bụi Flagship 298 Pro Ultra (Mã phân loại Tuya: 'sd')."""

    CATEGORY = "sd"

    # Định danh các mã Datapoint (DP Codes)
    DP_POWER_GO = "power_go"
    DP_PAUSE = "pause"
    DP_MODE = "mode"
    DP_DIRECTION = "direction_control"
    DP_STATUS = "status"
    DP_SUCTION = "suction"
    DP_CISTERN = "cistern"
    DP_SWITCH_CHARGE = "switch_charge"
    DP_SEEK = "seek"
    DP_FAULT = "fault"
    DP_DUST_COLLECTION = "dust_collection"
    DP_COLLECTION_MODE = "collection_mode"
    DP_MOP_CLEAN = "mop_clean"
    DP_WASH_FREQ = "wash_frequency"
    DP_HOT_WATER_WASH = "hot_water_wash"
    DP_MOP_DRY = "mop_dry"
    DP_DRY_TIME = "dry_time"
    DP_WATER_TANK_STATUS = "water_tank_status"
    DP_CARPET_CLEAN_MODE = "carpet_clean_mode"
    DP_CARPET_TURBO = "carpet_turbo"
    DP_AI_OBSTACLE = "ai_obstacle_avoidance"
    DP_BATTERY = "battery_percentage"
    DP_FILTER = "filter"
    DP_EDGE_BRUSH = "edge_brush"
    DP_ROLL_BRUSH = "roll_brush"
    DP_RESET_FILTER = "reset_filter"
    DP_RESET_EDGE_BRUSH = "reset_edge_brush"
    DP_RESET_ROLL_BRUSH = "reset_roll_brush"

    @classmethod
    def build_command(cls, action: str, **kwargs) -> List[Dict[str, Any]]:
        """Sinh danh sách lệnh DP Tuya chuẩn hóa tương ứng với khẩu lệnh ý định giọng nói.

        Các hành động hỗ trợ:
        - start_clean, stop_clean, pause, resume: Khởi động, dừng, tạm dừng, tiếp tục dọn
        - return_dock, seek: Về trạm sạc, phát âm thanh tìm robot
        - set_mode: Đặt chế độ (smart, zone, room, spot, mop_only, sweep_and_mop)
        - set_suction: Chỉnh lực hút (quiet, normal, strong, max 20.000Pa)
        - set_water_level: Chỉnh mức tiết nước (closed, low, middle, high)
        - empty_dust: Hút rác lên túi chứa tại dock
        - wash_mop: Về trạm giặt giẻ (hỗ trợ bật giặt nước nóng 60°C)
        - dry_mop: Sấy khô giẻ khí nóng (hẹn giờ 2h/3h/4h)
        - set_carpet_mode: Chế độ thảm (auto_lift tự nâng giẻ 10.5mm, avoid, ignore)
        - enable_carpet_turbo: Tự động tăng áp cực đại khi lên thảm
        - reset_consumable: Đặt lại tuổi thọ phụ kiện (filter, edge_brush, roll_brush)
        """
        act = action.strip().lower()

        if act in ("start_clean", "start", "clean"):
            return [{"code": cls.DP_POWER_GO, "value": True}]

        if act in ("stop_clean", "stop"):
            return [{"code": cls.DP_POWER_GO, "value": False}]

        if act == "pause":
            return [{"code": cls.DP_PAUSE, "value": True}]

        if act == "resume":
            return [{"code": cls.DP_PAUSE, "value": False}]

        if act in ("return_dock", "charge", "dock", "ve_sac"):
            return [{"code": cls.DP_SWITCH_CHARGE, "value": True}]

        if act in ("seek", "find", "tim_robot"):
            return [{"code": cls.DP_SEEK, "value": True}]

        if act == "set_mode":
            mode_val = kwargs.get("mode", "smart").lower()
            valid_modes = ["smart", "zone", "room", "spot", "mop_only", "sweep_and_mop"]
            if mode_val not in valid_modes:
                mode_val = "smart"
            return [{"code": cls.DP_MODE, "value": mode_val}]

        if act == "set_suction":
            suction_val = kwargs.get("level", "normal").lower()
            valid_suctions = ["quiet", "normal", "strong", "max"]
            if suction_val not in valid_suctions:
                suction_val = "normal"
            return [{"code": cls.DP_SUCTION, "value": suction_val}]

        if act == "set_water_level":
            water_val = kwargs.get("level", "middle").lower()
            valid_waters = ["closed", "low", "middle", "high"]
            if water_val not in valid_waters:
                water_val = "middle"
            return [{"code": cls.DP_CISTERN, "value": water_val}]

        # Các lệnh liên quan đến Trạm sạc đa năng All-in-One Dock
        if act in ("empty_dust", "hut_rac"):
            return [{"code": cls.DP_DUST_COLLECTION, "value": True}]

        if act in ("wash_mop", "giat_gie"):
            cmds = [{"code": cls.DP_MOP_CLEAN, "value": True}]
            if kwargs.get("hot_water", False):
                cmds.append({"code": cls.DP_HOT_WATER_WASH, "value": True})
            return cmds

        if act in ("dry_mop", "say_gie"):
            cmds = [{"code": cls.DP_MOP_DRY, "value": True}]
            dry_time = kwargs.get("dry_time")
            if dry_time in ("2h", "3h", "4h"):
                cmds.append({"code": cls.DP_DRY_TIME, "value": dry_time})
            return cmds

        if act == "set_carpet_mode":
            mode = kwargs.get("mode", "auto_lift").lower()
            if mode not in ("auto_lift", "avoid", "ignore"):
                mode = "auto_lift"
            return [{"code": cls.DP_CARPET_CLEAN_MODE, "value": mode}]

        if act == "enable_carpet_turbo":
            enable = bool(kwargs.get("enable", True))
            return [{"code": cls.DP_CARPET_TURBO, "value": enable}]

        if act == "reset_consumable":
            part = kwargs.get("part", "filter").lower()
            if part == "filter":
                return [{"code": cls.DP_RESET_FILTER, "value": True}]
            elif "edge" in part:
                return [{"code": cls.DP_RESET_EDGE_BRUSH, "value": True}]
            elif "roll" in part:
                return [{"code": cls.DP_RESET_ROLL_BRUSH, "value": True}]
            else:
                raise ValueError(f"Tên linh kiện phụ kiện không hợp lệ: {part}")

        raise ValueError(f"Hành động điều khiển Robot chưa được hỗ trợ: {action}")

    @classmethod
    def parse_status(cls, raw_status_list: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Chuyển đổi danh sách trạng thái thô từ Tuya thành từ điển mã-giá trị sạch."""
        status_dict = {}
        for item in raw_status_list:
            code = item.get("code")
            if code:
                status_dict[code] = item.get("value")
        return status_dict

    @classmethod
    def decode_fault_bitmap(cls, fault_int: int) -> List[str]:
        """Giải mã số nguyên Bitmap DP 11 thành danh sách nguyên nhân lỗi tiếng Việt rõ ràng."""
        if not isinstance(fault_int, int) or fault_int <= 0:
            return []

        reasons = []
        for bit_mask, desc in FAULT_BITMAP_REASONS.items():
            if fault_int & bit_mask:
                reasons.append(desc)
        return reasons

    @classmethod
    def check_critical_alerts(cls, status_dict: Dict[str, Any]) -> List[str]:
        """Kiểm tra các sự cố khẩn cấp hoặc tình trạng bình nước cần cảnh báo người dùng ngay."""
        alerts = []

        # 1. Kiểm tra sự cố Bitmap (kẹt chổi, kênh bánh, kẹt laser...)
        fault = status_dict.get(cls.DP_FAULT)
        if isinstance(fault, int) and fault > 0:
            faults = cls.decode_fault_bitmap(fault)
            if faults:
                alerts.append(f"Robot gặp sự cố: {', '.join(faults)}")

        # 2. Kiểm tra trạng thái bình chứa nước tại trạm sạc
        tank = status_dict.get(cls.DP_WATER_TANK_STATUS)
        if tank == "clean_water_empty":
            alerts.append("Trạm sạc đã hết nước sạch, cần châm thêm")
        elif tank == "dirty_water_full":
            alerts.append("Bình chứa nước bẩn tại trạm đã đầy, cần đổ ngay")
        elif tank == "tank_missing":
            alerts.append("Trạm sạc chưa được lắp bình nước")

        return alerts

    @classmethod
    def get_voice_status_summary(cls, status_dict: Dict[str, Any]) -> str:
        """Tạo câu phản hồi tóm tắt trạng thái hoàn chỉnh bằng tiếng Việt tự nhiên cho Loa."""
        # Ưu tiên kiểm tra các cảnh báo khẩn trước
        alerts = cls.check_critical_alerts(status_dict)
        if alerts:
            return f"Chú ý: {'; '.join(alerts)}. Bạn vui lòng xử lý nhé."

        # Trạng thái làm việc bình thường
        status_code = status_dict.get(cls.DP_STATUS, "standby")
        status_vi = STATUS_VI_MAP.get(status_code, status_code)
        battery = status_dict.get(cls.DP_BATTERY)
        mode = status_dict.get(cls.DP_MODE)
        mode_vi = MODE_VI_MAP.get(mode, "")

        parts = [f"Robot hút bụi hiện {status_vi}"]
        if mode_vi and status_code in ("cleaning", "paused"):
            parts.append(f"ở chế độ {mode_vi}")
        if battery is not None:
            parts.append(f"(pin còn {battery}%)")

        return " ".join(parts) + "."
