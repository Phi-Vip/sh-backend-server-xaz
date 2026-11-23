# -*- coding: utf-8 -*-
"""CÔNG CỤ MCP UNIFIED CHO AI VOICE (PHASE 4: SMARTHOME CONTROL TOOL)
Cung cấp công cụ Function Calling 'smarthome_control' cho LLM của XiaoZhi Voice Core.
Tích hợp cơ chế Hard Timeout 1.5s bảo vệ tuyệt đối luồng đàm thoại thời gian thực,
không bao giờ làm nghẽn hoặc đơ pipeline âm thanh.
"""

import asyncio
import logging
import time
from typing import Any, Dict, Optional

from dispatcher.multisource_dispatcher import MultiSourceDispatcher

logger = logging.getLogger(__name__)

HARD_TIMEOUT_SECONDS = 1.5


class SmartHomeControlTool:
    """Công cụ MCP hợp nhất điều khiển thiết bị nhà thông minh đa nguồn."""

    def __init__(self, dispatcher: MultiSourceDispatcher):
        """Khởi tạo công cụ với bộ định tuyến đa nguồn."""
        self.dispatcher = dispatcher

    @property
    def tool_definition(self) -> Dict[str, Any]:
        """Đặc tả JSON Schema của công cụ cho LLM."""
        return {
            "name": "smarthome_control",
            "description": "Điều khiển bật/tắt, tăng giảm độ sáng, chỉnh màu sắc, nhiệt độ, tốc độ hoặc tra cứu trạng thái/danh sách thiết bị nhà thông minh trong gia đình.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "device_id": {
                        "type": "string",
                        "description": "Mã định danh duy nhất của thiết bị (lấy từ danh mục trong ngữ cảnh). Có thể bỏ trống nếu hỏi về tất cả thiết bị.",
                    },
                    "device_name": {
                        "type": "string",
                        "description": "Tên thiết bị bằng tiếng Việt nếu không có device_id (ví dụ: 'đèn phòng ngủ', 'ổ cắm quạt'). Có thể bỏ trống nếu hỏi về tất cả thiết bị.",
                    },
                    "action": {
                        "type": "string",
                        "enum": [
                            "turn_on",
                            "turn_off",
                            "set_level",
                            "set_brightness",
                            "set_color_temp",
                            "set_speed",
                            "set_mode",
                            "set_timer",
                            "query_status",
                            "query_all_devices",
                            "sync_devices",
                        ],
                        "description": (
                            "Hành động điều khiển: turn_on (bật), turn_off (tắt), "
                            "set_level (điều chỉnh mức độ/phần trăm), "
                            "set_brightness (độ sáng), set_color_temp (nhiệt độ màu), set_speed (tốc độ quạt), "
                            "set_mode (chế độ hoạt động), "
                            "set_timer (hẹn giờ tắt đếm ngược, ví dụ value=30 là 30 phút), "
                            "query_status (hỏi trạng thái một thiết bị), "
                            "query_all_devices (liệt kê/báo cáo/kiểm tra tất cả thiết bị có trong nhà), "
                            "sync_devices (quét lại, đồng bộ thiết bị mới từ app)."
                        ),
                    },
                    "feature": {
                        "type": "string",
                        "description": "Bộ phận hoặc tính năng con cần điều khiển trên thiết bị (ví dụ: 'đèn', 'quạt', 'đèn nền', 'đèn hắt'). Bỏ trống nếu điều khiển tính năng chính.",
                    },
                    "value": {
                        "type": ["string", "number"],
                        "description": "Giá trị cần điều chỉnh (ví dụ: 80, 50, 'white', 'warm', hoặc số phút hẹn giờ).",
                    },
                    "room": {
                        "type": "string",
                        "description": "Tên phòng của thiết bị nếu có (ví dụ: 'Phòng khách', 'Phòng ngủ').",
                    },
                },
                "required": ["action"],
            },
        }

    async def _handle_query_all_devices(self, user_id: str, force_sync: bool = False) -> Dict[str, Any]:
        """Báo cáo danh sách thiết bị. Chỉ gọi API Tuya Cloud khi force_sync=True hoặc khi CSDL trống."""
        start_time = time.time()

        # 1. Chỉ đồng bộ từ Cloud khi người dùng yêu cầu đồng bộ (force_sync=True)
        # hoặc khi CSDL hoàn toàn chưa có thiết bị nào
        raw_devices = self.dispatcher.dal.list_devices_by_user(user_id)
        # Tạm thời loại bỏ robot hút bụi (category 'sd') đang phát triển chưa hoàn thiện
        local_devices = [d for d in raw_devices if d.get("category") != "sd"]
        should_sync = force_sync or (len(local_devices) == 0)

        if should_sync and hasattr(self.dispatcher, "tuya_client") and self.dispatcher.tuya_client:
            try:
                from sync.device_syncer import sync_tuya_devices
                logger.info(f"🔄 [SYNC-ON-DEMAND] Thực hiện đồng bộ thiết bị từ Tuya Cloud (force_sync={force_sync})...")
                await sync_tuya_devices(
                    dal=self.dispatcher.dal,
                    tuya_client=self.dispatcher.tuya_client,
                    user_id=user_id,
                )
                # Đọc lại từ CSDL sau khi đồng bộ và lọc bỏ robot hút bụi
                local_devices = [d for d in self.dispatcher.dal.list_devices_by_user(user_id) if d.get("category") != "sd"]
            except Exception as e:
                logger.warning(f"Lỗi khi đồng bộ thiết bị từ Tuya Cloud: {e}")

        # 2. Xử lý khi CSDL không có thiết bị
        if not local_devices:
            return {
                "success": True,
                "action": "sync_devices" if force_sync else "query_all_devices",
                "devices": [],
                "message": "Hiện tại hệ thống chưa ghi nhận thiết bị nào trong nhà. Bạn hãy mở ứng dụng Smart Life để liên kết thiết bị, sau đó bảo tôi 'đồng bộ thiết bị' nhé.",
                "duration_ms": round((time.time() - start_time) * 1000, 2),
            }

        # 3. Tạo câu thoại báo cáo tiếng Việt tự nhiên
        device_reports = []
        for d in local_devices:
            d_name = d.get("device_name", "Thiết bị")
            d_cat = d.get("category", "")
            d_online = d.get("is_online", True)

            type_label = "thiết bị"
            if d_cat == "dj":
                type_label = "đèn"
            elif d_cat == "cz":
                type_label = "ổ cắm"
            elif d_cat == "fskg":
                type_label = "công tắc quạt"
            elif d_cat == "sd":
                type_label = "robot hút bụi"

            online_str = "trực tuyến" if d_online else "ngoại tuyến"
            device_reports.append(f"{d_name} ({type_label}, {online_str})")

        count = len(local_devices)
        joined_list = ", ".join(device_reports)

        if force_sync:
            msg = f"Đã đồng bộ xong! Hiện tại hệ thống nhận diện được {count} thiết bị trong nhà gồm {joined_list}. Tất cả đều sẵn sàng hoạt động."
        else:
            msg = f"Báo cáo với bạn: hiện tại trong nhà có {count} thiết bị gồm {joined_list}. Tất cả đều sẵn sàng nhận lệnh điều khiển."

        return {
            "success": True,
            "action": "sync_devices" if force_sync else "query_all_devices",
            "count": count,
            "devices": [
                {"id": d.get("device_id"), "name": d.get("device_name"), "category": d.get("category")}
                for d in local_devices
            ],
            "message": msg,
            "duration_ms": round((time.time() - start_time) * 1000, 2),
        }

    async def execute(
        self,
        user_id: str,
        arguments: Dict[str, Any],
        timeout: float = HARD_TIMEOUT_SECONDS,
    ) -> Dict[str, Any]:
        """Thực thi công cụ với cơ chế bảo vệ Hard Timeout 1.5s nghiêm ngặt."""
        device_id = arguments.get("device_id")
        device_name = arguments.get("device_name")
        device_query = device_id or device_name
        action = arguments.get("action", "")
        feature = arguments.get("feature")
        value = arguments.get("value")
        room = arguments.get("room")

        # Kiểm tra nếu là câu hỏi về toàn bộ thiết bị trong nhà hoặc đồng bộ
        norm_query = ""
        if device_query:
            from dispatcher.context_injector import remove_vietnamese_accents
            norm_query = remove_vietnamese_accents(str(device_query)).lower().strip()

        is_sync_request = (
            action == "sync_devices"
            or any(w in norm_query for w in ["dong bo", "quet lai", "cap nhat", "sync", "tim thiet bi"])
        )

        is_all_query = (
            is_sync_request
            or action in ["query_all_devices", "list_devices"]
            or (action == "query_status" and (not device_query or any(w in norm_query for w in ["tat ca", "toan bo", "he thong", "cac thiet bi", "danh sach", "co nhung", "trong nha"])))
            or any(w in norm_query for w in ["tat ca thiet bi", "toan bo thiet bi", "tat ca", "cac thiet bi"])
        )

        if is_all_query:
            return await self._handle_query_all_devices(user_id, force_sync=is_sync_request)

        if not device_query:
            return {
                "success": False,
                "error": "MISSING_DEVICE",
                "message": "Bạn muốn điều khiển thiết bị nào trong nhà vậy?",
            }

        # Kiểm tra cô lập thiết bị đa người dùng (Task 3.3 - Multi-tenant Device Isolation)
        target_dev_id = device_id or str(device_query)
        if target_dev_id and hasattr(self.dispatcher, "dal"):
            dev_record = self.dispatcher.dal.get_device(target_dev_id)
            if dev_record:
                dev_owner = dev_record.get("user_id")
                resolved_caller = self.dispatcher.dal.resolve_user_id(user_id)
                if dev_owner and resolved_caller and dev_owner != resolved_caller:
                    logger.warning(
                        f"🚨 [SECURITY ALERT - MULTI-TENANT ISOLATION]: User '{resolved_caller}' "
                        f"cố tình gửi lệnh điều khiển thiết bị '{target_dev_id}' thuộc sở hữu của User '{dev_owner}'!"
                    )
                    return {
                        "success": False,
                        "error": "FORBIDDEN",
                        "code": 403,
                        "message": "Access Denied: You do not own this device (403 Forbidden)",
                    }

        try:
            extra = {}
            if feature:
                extra["feature"] = feature

            # Bọc lệnh điều khiển trong Hard Timeout
            result = await asyncio.wait_for(
                self.dispatcher.dispatch_command(
                    user_id=user_id,
                    device_query=device_query,
                    action=action,
                    value=value,
                    room=room,
                    extra_params=extra if extra else None,
                ),
                timeout=timeout,
            )
            return result

        except asyncio.TimeoutError:
            logger.warning(
                f"⚡ [HARD TIMEOUT]: Lệnh '{action}' tới '{device_query}' vượt quá {timeout}s! Đã ngắt để bảo vệ luồng đàm thoại."
            )
            return {
                "success": False,
                "error": "HARD_TIMEOUT",
                "message": f"Thiết bị {device_name or device_query} phản hồi hơi chậm, bạn kiểm tra lại kết nối mạng giúp tôi nhé.",
            }
        except Exception as e:
            logger.error(f"Lỗi khi thực thi smarthome_control: {e}")
            return {
                "success": False,
                "error": "EXECUTION_ERROR",
                "message": f"Có lỗi xảy ra khi điều khiển {device_name or device_query}: {str(e)}",
            }

