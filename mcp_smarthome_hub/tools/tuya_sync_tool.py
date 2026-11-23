# -*- coding: utf-8 -*-
"""CÔNG CỤ MCP ĐỒNG BỘ THIẾT BỊ TUYA THEO YÊU CẦU (ON-DEMAND SYNC TOOL)
Cung cấp công cụ MCP 'tuya_sync_devices' cho LLM của XiaoZhi Voice Core.
Thay thế hoàn toàn cơ chế quét ngầm định kỳ 1 phút/lần, chỉ đồng bộ khi:
1. Server khởi động / Loa kết nối lần đầu.
2. Người dùng ra lệnh giọng nói yêu cầu đồng bộ.
"""

import logging
import time
from typing import Any, Dict, List, Optional

from storage.db import SmartHomeDAL, default_dal
from clients.tuya_client import TuyaCloudClient
from sync.device_syncer import sync_tuya_devices

logger = logging.getLogger(__name__)


class TuyaSyncTool:
    """Công cụ MCP đồng bộ danh mục thiết bị Tuya Smart Life theo yêu cầu."""

    def __init__(self, dal: SmartHomeDAL = default_dal, tuya_client: Optional[TuyaCloudClient] = None):
        self.dal = dal
        self.tuya_client = tuya_client

    @property
    def tool_definition(self) -> Dict[str, Any]:
        """Đặc tả JSON Schema của công cụ cho LLM."""
        return {
            "name": "tuya_sync_devices",
            "description": (
                "Đồng bộ và quét lại danh mục thiết bị nhà thông minh Tuya Smart Life "
                "(bóng đèn, ổ cắm, công tắc, quạt...) từ máy chủ Tuya Cloud về CSDL hệ thống. "
                "BẮT BUỘC gọi tool này khi người dùng nói: 'đồng bộ thiết bị tuya', 'đồng bộ tuya', 'tuy a', "
                "'quét lại thiết bị tuya', 'cập nhật thiết bị tuya', 'tìm thiết bị tuya mới', 'đồng bộ bóng đèn', "
                "'đồng bộ ổ cắm', 'đồng bộ quạt', 'quét thiết bị mới', hoặc khi người dùng yêu cầu 'đồng bộ tất cả thiết bị trong nhà'."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "force": {
                        "type": "boolean",
                        "description": "Bắt buộc làm mới dữ liệu từ máy chủ đám mây (mặc định là true).",
                    }
                },
            },
        }

    async def execute(self, user_id: Optional[str] = None, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Thực thi đồng bộ thiết bị từ Tuya Cloud."""
        start_time = time.time()
        target_user = self.dal.resolve_user_id(user_id)

        try:
            from clients.tuya_sharing_manager import sharing_manager
            if sharing_manager.get_manager(target_user):
                logger.info(f"🔄 [TUYA SYNC TOOL] Đồng bộ thiết bị qua Tuya Sharing Gateway cho User [{target_user}]...")
                synced = sharing_manager.sync_devices(user_id=target_user, dal=self.dal)
            elif self.tuya_client:
                synced = await sync_tuya_devices(dal=self.dal, tuya_client=self.tuya_client, user_id=target_user)
            else:
                msg = "Hệ thống chưa kết nối tới Tuya Cloud nên chưa thể đồng bộ thiết bị."
                return {
                    "success": False,
                    "action": "tuya_sync_devices",
                    "message": msg,
                    "duration_ms": round((time.time() - start_time) * 1000, 2),
                }

            # Tạm thời loại bỏ robot hút bụi (category 'sd') đang phát triển chưa hoàn thiện
            synced = [d for d in synced if d.get("category") != "sd"]
            count = len(synced)

            if synced:
                dev_reports = []
                for d in synced:
                    cat = d.get("category", "")
                    t_name = "thiết bị"
                    if cat == "dj":
                        t_name = "đèn"
                    elif cat == "cz":
                        t_name = "ổ cắm"
                    elif cat == "fskg":
                        t_name = "công tắc quạt"
                    dev_reports.append(f"{d.get('device_name')} ({t_name})")
                joined = ", ".join(dev_reports)
                res_text = f"Đã đồng bộ xong các thiết bị Tuya Smart Life từ đám mây! Hiện tại có {count} thiết bị gồm: {joined}. Tất cả đều sẵn sàng hoạt động."
            else:
                res_text = "Đã quét máy chủ Tuya Cloud nhưng chưa phát hiện thiết bị nào liên kết với tài khoản."

            duration_ms = round((time.time() - start_time) * 1000, 2)
            logger.info(f"✅ [TUYA SYNC TOOL] Đã đồng bộ {count} thiết bị trong {duration_ms}ms")

            return {
                "success": True,
                "action": "tuya_sync_devices",
                "count": count,
                "devices": synced,
                "message": res_text,
                "duration_ms": duration_ms,
            }
        except Exception as e:
            logger.error(f"❌ [TUYA SYNC TOOL] Lỗi khi đồng bộ thiết bị Tuya: {e}")
            return {
                "success": False,
                "action": "tuya_sync_devices",
                "message": f"Quá trình đồng bộ gặp lỗi: {e}",
                "duration_ms": round((time.time() - start_time) * 1000, 2),
            }

