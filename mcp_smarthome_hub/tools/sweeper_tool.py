# -*- coding: utf-8 -*-
"""CÔNG CỤ MCP CHUYÊN DỤNG CHO ROBOT HÚT BỤI 298 PRO ULTRA & TRẠM SẠC DOCK (PHASE 4: SWEEPER TOOL)
Cung cấp công cụ Function Calling 'sweeper_control' cho LLM của XiaoZhi Voice Core.
Bao phủ 32 DPs: dọn dẹp, giặt sấy giẻ, lực hút 20.000Pa, tự nâng giẻ khi gặp thảm...
Tích hợp cơ chế Hard Timeout 1.5s bảo vệ tuyệt đối luồng đàm thoại âm thanh.
"""

import asyncio
import logging
from typing import Any, Dict, Optional

from dispatcher.multisource_dispatcher import MultiSourceDispatcher

logger = logging.getLogger(__name__)

HARD_TIMEOUT_SECONDS = 1.5


class SweeperControlTool:
    """Công cụ MCP điều khiển chuyên sâu Flagship Robot hút bụi 298 Pro Ultra."""

    def __init__(self, dispatcher: MultiSourceDispatcher):
        """Khởi tạo công cụ với bộ định tuyến đa nguồn."""
        self.dispatcher = dispatcher

    @property
    def tool_definition(self) -> Dict[str, Any]:
        """Đặc tả JSON Schema của công cụ cho LLM."""
        return {
            "name": "sweeper_control",
            "description": "Điều khiển chuyên sâu cho Robot hút bụi thông minh và Trạm sạc All-in-One Dock (bắt đầu dọn, dừng, về sạc, giặt giẻ nước nóng 60°C, sấy khí nóng, hút rác lên túi chứa tại trạm, chỉnh lực hút, hỏi lịch sử).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "device_id": {
                        "type": "string",
                        "description": "Mã định danh duy nhất của Robot hút bụi.",
                    },
                    "action": {
                        "type": "string",
                        "enum": [
                            "start_clean",
                            "stop_clean",
                            "pause",
                            "resume",
                            "return_dock",
                            "seek",
                            "set_mode",
                            "set_suction",
                            "set_water_level",
                            "empty_dust",
                            "wash_mop",
                            "dry_mop",
                            "query_status",
                            "query_history",
                        ],
                        "description": "Hành động điều khiển Robot hoặc trạm sạc Dock.",
                    },
                    "suction": {
                        "type": "string",
                        "enum": ["quiet", "normal", "strong", "max"],
                        "description": "Mức lực hút (quiet=nhẹ, normal=vừa, strong=mạnh, max=cực đại 20.000Pa).",
                    },
                    "hot_water": {
                        "type": "boolean",
                        "description": "Bật chế độ giặt giẻ bằng nước nóng 60°C diệt khuẩn tại trạm sạc.",
                    },
                    "dry_time": {
                        "type": "string",
                        "enum": ["2h", "3h", "4h"],
                        "description": "Thời gian hẹn giờ sấy khô giẻ bằng khí nóng.",
                    },
                },
                "required": ["action"],
            },
        }

    async def execute(
        self,
        user_id: str,
        arguments: Dict[str, Any],
        timeout: float = HARD_TIMEOUT_SECONDS,
    ) -> Dict[str, Any]:
        """Thực thi lệnh điều khiển Robot với cơ chế bảo vệ Hard Timeout 1.5s."""
        device_id = arguments.get("device_id") or "robot"
        action = arguments.get("action", "start_clean")

        extra_params = {}
        if "suction" in arguments:
            extra_params["suction"] = arguments["suction"]
        if "hot_water" in arguments:
            extra_params["hot_water"] = arguments["hot_water"]
        if "dry_time" in arguments:
            extra_params["dry_time"] = arguments["dry_time"]

        try:
            result = await asyncio.wait_for(
                self.dispatcher.dispatch_command(
                    user_id=user_id,
                    device_query=device_id,
                    action=action,
                    extra_params=extra_params,
                ),
                timeout=timeout,
            )
            return result

        except asyncio.TimeoutError:
            logger.warning(
                f"⚡ [HARD TIMEOUT]: Lệnh Robot '{action}' vượt quá {timeout}s! Đã ngắt để bảo vệ luồng đàm thoại."
            )
            return {
                "success": False,
                "error": "HARD_TIMEOUT",
                "message": "Robot hút bụi đang phản hồi hơi chậm, bạn kiểm tra lại kết nối Wi-Fi của robot nhé.",
            }
        except Exception as e:
            logger.error(f"Lỗi khi thực thi sweeper_control: {e}")
            return {
                "success": False,
                "error": "EXECUTION_ERROR",
                "message": f"Có lỗi khi điều khiển robot: {str(e)}",
            }

