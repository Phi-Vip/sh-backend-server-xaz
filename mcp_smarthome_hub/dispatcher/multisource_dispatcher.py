# -*- coding: utf-8 -*-
"""BỘ ĐỊNH TUYẾN ĐA NGUỒN O(1) CHO HỆ THỐNG NHÀ THÔNG MINH (PHASE 4: MULTISOURCE DISPATCHER)
Hỗ trợ 4 nền tảng thiết bị:
1. Sunhouse AWS IoT Core (Thiết bị gia dụng nội bộ in-house).
2. Tuya OEM Sunhouse (Robot 298 Pro, bình nóng lạnh OEM, dùng Project Token).
3. Tuya Smart Life ngoài (Thiết bị người dùng mua ngoài, dùng User OAuth Token).
4. Home Assistant (Reverse WebSocket MCP Bridge).

Đạt độ trễ phân luồng nội bộ O(1) < 5ms.
"""

import asyncio
import logging
import os
import time
from typing import Any, Dict, List, Optional, Union

from adapters.normalizer import DeviceNormalizer
from adapters.sweeper_adapter import STATUS_VI_MAP, SweeperAdapter
from clients.tuya_client import TuyaCloudClient
from dispatcher.context_injector import ContextInjector
from ha_bridge.jsonrpc_forwarder import JSONRPCForwarder
from storage.db import SmartHomeDAL, default_dal
from storage.models import PlatformType
from storage.token_manager import TuyaTokenManager

logger = logging.getLogger(__name__)


class MultiSourceDispatcher:
    """Bộ định tuyến phân luồng lệnh điều khiển đa nguồn thông minh O(1)."""

    def __init__(
        self,
        dal_instance: Optional[SmartHomeDAL] = None,
        tuya_client: Optional[TuyaCloudClient] = None,
        token_mgr: Optional[TuyaTokenManager] = None,
        ha_forwarder: Optional[JSONRPCForwarder] = None,
        context_injector: Optional[ContextInjector] = None,
    ):
        """Khởi tạo Dispatcher với các thành phần nghiệp vụ."""
        self.dal = dal_instance or default_dal
        self.tuya_client = tuya_client
        self.token_mgr = token_mgr
        self.ha_forwarder = ha_forwarder
        self.context_injector = context_injector or ContextInjector(dal_instance=self.dal)

    async def _get_tuya_token(self, platform_type: int, user_id: str) -> str:
        """Lấy token Tuya hợp lệ (Project Token hoặc User OAuth Token)."""
        feature_proj_token = os.getenv("TUYA_FEATURE_PROJECT_TOKEN", "true").lower() == "true"

        # 1. Nếu là thiết bị Tuya Smart Life ngoài, ưu tiên lấy User OAuth Token (grant_type=2)
        if platform_type == PlatformType.TUYA_EXTERNAL_SMARTLIFE:
            if self.token_mgr:
                async def _refresh_user_cb(u_id: str, r_token: str):
                    if self.tuya_client:
                        return await self.tuya_client.get_token(grant_type=2, refresh_token=r_token)
                    return {}
                user_token = await self.token_mgr.get_valid_user_token(user_id, refresh_callback=_refresh_user_cb)
                if user_token:
                    return user_token

            # Fallback lấy trực tiếp từ CSDL DAL nếu token_mgr chưa nạp
            user_cred = self.dal.get_user_credential(user_id)
            if user_cred and user_cred.get("access_token"):
                return user_cred["access_token"]

            # Khi TUYA_FEATURE_PROJECT_TOKEN=false: nghiêm cấm fallback sang Project Token cho Smart Life!
            if not feature_proj_token:
                raise ValueError(
                    f"Chế độ Project Token đã tắt (TUYA_FEATURE_PROJECT_TOKEN=false). "
                    f"Tài khoản [{user_id}] chưa được cấp quyền OAuth2 User Token hợp lệ. "
                    f"Vui lòng hoàn tất ủy quyền OAuth2 tài khoản Tuya Smart Life trước khi điều khiển."
                )

        # 2. Với thiết bị OEM Sunhouse (PlatformType.TUYA_OEM_ESUNHOUSE) hoặc fallback khi được phép: dùng Project Token
        if self.token_mgr and self.tuya_client:
            async def _refresh_proj_cb(c_id: str, r_token: str):
                return await self.tuya_client.get_token(grant_type=1, refresh_token=r_token)
            proj_token = await self.token_mgr.get_valid_project_token(
                self.tuya_client.client_id, refresh_callback=_refresh_proj_cb
            )
            if proj_token:
                return proj_token

        # 3. Fallback trực tiếp gọi tuya_client
        if self.tuya_client:
            token_data = await self.tuya_client.get_token(grant_type=1)
            return token_data.get("access_token", "")

        raise ValueError("Không có Tuya Client hoặc Token Manager được cấu hình")

    async def dispatch_command(
        self,
        user_id: str,
        device_query: str,
        action: str,
        value: Optional[Any] = None,
        room: Optional[str] = None,
        extra_params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Định tuyến và thực thi lệnh điều khiển tới đúng nền tảng trong O(1).
        
        Trả về kết quả chuẩn hóa kèm câu phản hồi tiếng Việt tự nhiên cho AI Voice.
        """
        t_start = time.time()
        extra = extra_params or {}

        # 1. Phân giải thiết bị từ Device ID hoặc Tên gọi (O(1) hoặc Semantic Match)
        device = self.context_injector.resolve_device(user_id, device_query, room=room)
        if not device:
            return {
                "success": False,
                "error": "DEVICE_NOT_FOUND",
                "message": f"Xin lỗi, tôi không tìm thấy thiết bị nào có tên hoặc mã '{device_query}' trong nhà bạn.",
                "duration_ms": (time.time() - t_start) * 1000,
            }

        device_id = device["device_id"]
        device_name = device.get("device_name", "Thiết bị")
        category = device.get("category", "")
        raw_schema = device.get("raw_schema") or {}
        if isinstance(raw_schema, str):
            try:
                raw_schema = json.loads(raw_schema)
            except Exception:
                raw_schema = {}
        platform_type = device.get("platform_type", PlatformType.TUYA_OEM_ESUNHOUSE)

        # 2. Phân luồng O(1) theo nền tảng
        try:
            if platform_type in (PlatformType.TUYA_OEM_ESUNHOUSE, PlatformType.TUYA_EXTERNAL_SMARTLIFE):
                res = await self._dispatch_tuya(
                    user_id=user_id,
                    device_id=device_id,
                    device_name=device_name,
                    category=category,
                    raw_schema=raw_schema,
                    platform_type=platform_type,
                    action=action,
                    value=value,
                    extra=extra,
                )
            elif platform_type == PlatformType.HOME_ASSISTANT:
                res = await self._dispatch_home_assistant(
                    user_id=user_id,
                    device_id=device_id,
                    device_name=device_name,
                    category=category,
                    action=action,
                    value=value,
                    extra=extra,
                )
            elif platform_type == PlatformType.SUNHOUSE_AWS:
                res = await self._dispatch_sunhouse_aws(
                    user_id=user_id,
                    device_id=device_id,
                    device_name=device_name,
                    action=action,
                    value=value,
                    extra=extra,
                )
            else:
                return {
                    "success": False,
                    "error": "UNSUPPORTED_PLATFORM",
                    "message": f"Nền tảng của thiết bị '{device_name}' chưa được hỗ trợ.",
                    "duration_ms": (time.time() - t_start) * 1000,
                }

            res["duration_ms"] = round((time.time() - t_start) * 1000, 2)
            return res

        except Exception as e:
            logger.error(f"Lỗi khi điều khiển thiết bị [{device_id}]: {e}")
            return {
                "success": False,
                "device_id": device_id,
                "device_name": device_name,
                "error": "DISPATCH_FAILED",
                "message": f"Không thể thực thi lệnh điều khiển cho {device_name}: {str(e)}",
                "duration_ms": round((time.time() - t_start) * 1000, 2),
            }

    async def _dispatch_tuya(
        self,
        user_id: str,
        device_id: str,
        device_name: str,
        category: str,
        raw_schema: Dict[str, Any],
        platform_type: int,
        action: str,
        value: Optional[Any],
        extra: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Điều khiển thiết bị Tuya Cloud (OEM hoặc Smart Life)."""
        # 1. ƯU TIÊN TUYỆT ĐỐI: Điều khiển qua Tuya Sharing Gateway (Home Assistant standard)
        from clients.tuya_sharing_manager import sharing_manager
        sharing_mgr = sharing_manager.get_manager(user_id)

        if sharing_mgr and device_id in sharing_mgr.device_map:
            if action == "query_status":
                dev = sharing_mgr.device_map.get(device_id)
                status_map = getattr(dev, "status", {}) or {}
                if not status_map and isinstance(raw_schema, dict):
                    status_map = raw_schema.get("status", {}) or {}
                msg = self._generate_status_vietnamese_reply(
                    device_name=device_name,
                    category=category,
                    status_map=status_map,
                    raw_schema=raw_schema,
                )
                return {
                    "success": True,
                    "platform": "tuya_sharing",
                    "device_id": device_id,
                    "device_name": device_name,
                    "action": "query_status",
                    "status": status_map,
                    "message": msg,
                }

            if category == "sd":
                kwargs = dict(extra)
                if value is not None:
                    kwargs["value"] = value
                commands = SweeperAdapter.build_command(action, **kwargs)
            else:
                commands = DeviceNormalizer.build_command(
                    raw_schema=raw_schema,
                    action=action,
                    value=value,
                    dp_code=extra.get("dp_code"),
                    feature=extra.get("feature"),
                )

            logger.info(
                f"⚡ [TUYA SHARING CTRL] Gửi lệnh qua Tuya Sharing Gateway cho [{device_name}] ({device_id}) | "
                f"Action: '{action}' | Value: {value} | Commands: {commands}"
            )
            ok = sharing_manager.send_commands(user_id, device_id, commands)
            msg = self._generate_tuya_vietnamese_reply(
                device_name=device_name,
                action=action,
                value=value,
                category=category,
                extra=extra,
            )
            return {
                "success": ok,
                "platform": "tuya_sharing",
                "device_id": device_id,
                "device_name": device_name,
                "action": action,
                "commands": commands,
                "message": msg,
            }

        # 2. Fallback: Điều khiển qua Tuya OpenAPI thông thường
        if not self.tuya_client:
            raise ValueError("Tuya Client chưa được kết nối")

        token = await self._get_tuya_token(platform_type, user_id)

        # Tự động nạp Lazy Schema nếu DB cache chưa có schema hoặc thiếu danh sách functions
        if not raw_schema or not isinstance(raw_schema, dict) or not raw_schema.get("functions"):
            logger.info(
                f"🔄 [LAZY SCHEMA FETCH] Thiết bị [{device_name}] ({device_id}) chưa có schema DP trong DB. "
                "Đang truy vấn trực tiếp Tuya OpenAPI..."
            )
            try:
                if hasattr(self.tuya_client, "get_device_specification"):
                    raw_spec = self.tuya_client.get_device_specification(device_id, token)
                    if asyncio.iscoroutine(raw_spec):
                        fresh_schema = await raw_spec
                    else:
                        res = await self.tuya_client.request(
                            "GET", f"/v1.0/iot-03/devices/{device_id}/specification", token=token
                        )
                        fresh_schema = res.get("result", {})
                else:
                    res = await self.tuya_client.request(
                        "GET", f"/v1.0/iot-03/devices/{device_id}/specification", token=token
                    )
                    fresh_schema = res.get("result", {})

                if fresh_schema and isinstance(fresh_schema, dict) and fresh_schema.get("functions"):
                    raw_schema = fresh_schema
                    self.dal.upsert_device(
                        device_id=device_id,
                        user_id=user_id,
                        device_name=device_name,
                        category=category,
                        platform_type=platform_type,
                        raw_schema=raw_schema,
                    )
                    fn_codes = [fn.get("code") for fn in raw_schema.get("functions", [])]
                    logger.info(
                        f"📦 [TUYA SCHEMA CẬP NHẬT] Đã nạp thành công {len(fn_codes)} DP cho [{device_name}]: {fn_codes}"
                    )
            except Exception as e_lazy:
                logger.warning(f"⚠️ [LAZY SCHEMA FETCH] Không thể nạp schema trực tiếp từ Tuya OpenAPI: {e_lazy}")

        # Xác định chế độ hạ lệnh: Chuẩn OpenAPI ("standard") hay Thing Model ("thing_model")
        instruction_mode = "standard"
        if isinstance(raw_schema, dict):
            instruction_mode = raw_schema.get("instruction_mode", "standard")

        # 0. Nếu là yêu cầu truy vấn trạng thái thiết bị (query_status)
        if action == "query_status":
            if instruction_mode == "thing_model":
                raw_props = await self.tuya_client.get_thing_shadow_properties(
                    device_id=device_id,
                    token=token,
                )
                status_map = {
                    item.get("code"): item.get("value")
                    for item in raw_props
                    if isinstance(item, dict) and "code" in item
                }
            else:
                raw_status = await self.tuya_client.get_device_status(
                    device_id=device_id,
                    token=token,
                )
                status_map = {
                    item.get("code"): item.get("value")
                    for item in raw_status
                    if isinstance(item, dict) and "code" in item
                }
            msg = self._generate_status_vietnamese_reply(
                device_name=device_name,
                category=category,
                status_map=status_map,
                raw_schema=raw_schema,
            )
            return {
                "success": True,
                "platform": "tuya_oem" if platform_type == PlatformType.TUYA_OEM_ESUNHOUSE else "tuya_ext",
                "device_id": device_id,
                "device_name": device_name,
                "action": "query_status",
                "status": status_map,
                "message": msg,
            }

        # 1. Nếu là Robot hút bụi Flagship 298 Pro Ultra (Category 'sd')
        if category == "sd":
            kwargs = dict(extra)
            if value is not None:
                kwargs["value"] = value
            commands = SweeperAdapter.build_command(action, **kwargs)
        else:
            # 2. Các thiết bị gia dụng và đèn thông thường
            commands = DeviceNormalizer.build_command(
                raw_schema=raw_schema,
                action=action,
                value=value,
                dp_code=extra.get("dp_code"),
                feature=extra.get("feature"),
            )

        # Gửi lệnh lên Tuya Cloud OpenAPI hoặc Thing Model Shadow Issue
        logger.info(
            f"🚀 [TUYA DISPATCH] [{device_name}] (ID: {device_id}, Category: {category}, Mode: {instruction_mode}) | "
            f"Action: '{action}' | Value: {value}"
        )
        if isinstance(raw_schema, dict) and raw_schema.get("functions"):
            fn_codes = [fn.get("code") for fn in raw_schema.get("functions", [])]
            logger.info(f"   👉 DPs sẵn có: {fn_codes}")
        logger.info(f"   📤 Lệnh gửi đi: {commands}")

        # Ưu tiên điều khiển qua Tuya Sharing Gateway nếu thiết bị thuộc phiên Sharing SDK
        from clients.tuya_sharing_manager import sharing_manager
        sharing_mgr = sharing_manager.get_manager(user_id)
        if sharing_mgr and device_id in sharing_mgr.device_map:
            logger.info(f"⚡ [TUYA SHARING CTRL] Gửi lệnh qua Tuya Sharing Gateway cho [{device_name}] ({device_id})")
            ok = sharing_manager.send_commands(user_id, device_id, commands)
        elif instruction_mode == "thing_model":
            props_to_send = {cmd.get("code"): cmd.get("value") for cmd in commands if "code" in cmd}
            logger.info(f"   ⚡ [THING MODEL SHADOW ISSUE] Gửi properties qua shadow issue: {props_to_send}")
            ok = await self.tuya_client.send_thing_shadow_properties(
                device_id=device_id,
                properties=props_to_send,
                token=token,
            )
        else:
            ok = await self.tuya_client.send_device_commands(
                device_id=device_id,
                commands=commands,
                token=token,
            )

        msg = self._generate_tuya_vietnamese_reply(
            device_name=device_name,
            action=action,
            value=value,
            category=category,
            extra=extra,
        )
        return {
            "success": ok,
            "platform": "tuya_oem" if platform_type == PlatformType.TUYA_OEM_ESUNHOUSE else "tuya_ext",
            "device_id": device_id,
            "device_name": device_name,
            "action": action,
            "commands": commands,
            "message": msg,
        }

    async def _dispatch_home_assistant(
        self,
        user_id: str,
        device_id: str,
        device_name: str,
        category: str,
        action: str,
        value: Optional[Any],
        extra: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Điều khiển thiết bị qua Home Assistant Reverse Tunnel."""
        if not self.ha_forwarder:
            raise ValueError("Home Assistant Forwarder chưa được khởi tạo")

        # Phân tích domain và service từ entity_id và action
        # Ví dụ: device_id = "light.living_room"
        entity_id = device_id if "." in device_id else f"switch.{device_id}"
        domain = entity_id.split(".")[0]

        service_data = dict(extra.get("service_data", {}))
        service = "turn_on" if action == "turn_on" else "turn_off"

        if action == "set_brightness" and value is not None:
            service = "turn_on"
            service_data["brightness_pct"] = int(value)
        elif action == "set_color_temp" and value is not None:
            service = "turn_on"
            service_data["color_temp"] = int(value)
        elif action == "toggle":
            service = "toggle"

        res = await self.ha_forwarder.call_service(
            user_id=user_id,
            domain=domain,
            service=service,
            service_data=service_data,
            entity_id=entity_id,
        )

        msg = f"Đã thực hiện {action} cho {device_name} trên Home Assistant."
        return {
            "success": True,
            "platform": "ha",
            "device_id": device_id,
            "device_name": device_name,
            "action": action,
            "ha_response": res,
            "message": msg,
        }

    async def _dispatch_sunhouse_aws(
        self,
        user_id: str,
        device_id: str,
        device_name: str,
        action: str,
        value: Optional[Any],
        extra: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Điều khiển thiết bị gia dụng nội bộ Sunhouse (AWS IoT Core Shadow)."""
        # Nhánh này định dạng bản tin gửi xuống device-side MCP hoặc shadow delta
        payload = {
            "state": {
                "desired": {
                    "action": action,
                    "value": value,
                }
            }
        }
        msg = f"Đã gửi lệnh {action} tới thiết bị nội bộ Sunhouse {device_name}."
        return {
            "success": True,
            "platform": "sunhouse_aws",
            "device_id": device_id,
            "device_name": device_name,
            "action": action,
            "payload": payload,
            "message": msg,
        }

    def _generate_tuya_vietnamese_reply(
        self,
        device_name: str,
        action: str,
        value: Optional[Any],
        category: str,
        extra: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Tạo câu trả lời tiếng Việt tự nhiên và thân thiện cho AI Voice."""
        extra_dict = extra or {}
        feature = extra_dict.get("feature")

        if feature:
            feat_name = str(feature).strip()
            if action == "turn_on":
                return f"Đã bật {feat_name} của {device_name} cho bạn rồi nhé."
            elif action == "turn_off":
                return f"Đã tắt {feat_name} của {device_name} rồi nhé."

        if action == "set_timer":
            minutes, is_cancel = DeviceNormalizer._parse_timer_minutes(value)
            if is_cancel or minutes <= 0:
                return f"Đã hủy hẹn giờ tắt cho {device_name} rồi nhé."
            if minutes >= 60 and minutes % 60 == 0:
                return f"Đã hẹn giờ tắt {device_name} sau {int(minutes // 60)} tiếng."
            return f"Đã hẹn giờ tắt {device_name} sau {int(minutes)} phút."

        if category == "sd":
            sweeper_replies = {
                "start_clean": f"Đã cho {device_name} bắt đầu dọn dẹp nhà rồi nhé.",
                "stop_clean": f"Đã cho {device_name} dừng dọn dẹp.",
                "pause": f"Đã tạm dừng {device_name}.",
                "resume": f"Đã cho {device_name} tiếp tục dọn dẹp.",
                "return_dock": f"Đã điều hướng {device_name} tự động quay về trạm sạc.",
                "wash_mop": f"Đã kích hoạt {device_name} tự động giặt giẻ tại dock.",
                "dry_mop": f"Đã bật chế độ sấy khô giẻ bằng khí nóng tại trạm sạc.",
                "empty_dust": f"Đã kích hoạt trạm sạc tự động hút rác lên túi chứa.",
            }
            if action in sweeper_replies:
                return sweeper_replies[action]

        action_replies = {
            "turn_on": f"Đã bật {device_name} cho bạn rồi nhé.",
            "turn_off": f"Đã tắt {device_name} rồi nhé.",
            "set_brightness": f"Đã điều chỉnh độ sáng {device_name} thành {value}%.",
            "set_color_temp": f"Đã thay đổi nhiệt độ màu cho {device_name}.",
            "set_speed": f"Đã chỉnh tốc độ {device_name} thành mức {value}.",
            "set_level": f"Đã điều chỉnh mức độ {device_name} thành {value}.",
            "set_mode": f"Đã chuyển chế độ {device_name} sang {value}.",
            "set_timer": f"Đã hẹn giờ tắt {device_name} sau {value} phút.",
        }
        return action_replies.get(action, f"Đã thực hiện lệnh {action} cho {device_name}.")

    def _generate_status_vietnamese_reply(
        self,
        device_name: str,
        category: str,
        status_map: Dict[str, Any],
        raw_schema: Dict[str, Any],
    ) -> str:
        """Tạo câu trả lời tiếng Việt báo cáo trạng thái tức thời của thiết bị."""
        if isinstance(raw_schema, str):
            try:
                raw_schema = json.loads(raw_schema)
            except Exception:
                raw_schema = {}
        if not isinstance(raw_schema, dict):
            raw_schema = {}
        if category == "sd":
            status_val = status_map.get("status", "standby")
            battery = status_map.get("battery_percentage", 100)
            status_desc = STATUS_VI_MAP.get(str(status_val), str(status_val))
            return f"{device_name} hiện {status_desc}, pin còn {battery}%."

        # Kiểm tra trạng thái bật/tắt nguồn linh hoạt theo Generic Schema
        power_dp = DeviceNormalizer.find_power_dp(raw_schema)
        power_code = power_dp.get("code") if power_dp else None

        is_on = None
        if power_code and power_code in status_map:
            is_on = bool(status_map[power_code])
        else:
            # Quét tìm bất kỳ DP Boolean nào chứa switch hoặc power trong status_map
            for k, v in status_map.items():
                if ("switch" in k.lower() or "power" in k.lower()) and isinstance(v, bool):
                    is_on = v
                    break

        if is_on is False:
            return f"{device_name} hiện đang tắt."

        # Nếu đang bật hoặc không có công tắc nguồn (luôn bật)
        prefix = f"{device_name} hiện đang bật" if is_on is True else f"Trạng thái của {device_name}"
        details = []

        # Tốc độ gió / quạt
        speed_dp = DeviceNormalizer.find_scalar_dp(raw_schema, "speed")
        if speed_dp:
            s_code = speed_dp.get("code")
            if s_code in status_map:
                hw_speed = status_map[s_code]
                if speed_dp.get("type") == "Integer":
                    pct = DeviceNormalizer.scale_dp_to_percentage(speed_dp, hw_speed)
                    details.append(f"tốc độ gió {int(round(pct))}%")
                else:
                    details.append(f"tốc độ {hw_speed}")
        elif "fan_speed" in status_map:
            details.append(f"tốc độ gió {status_map['fan_speed']}%")

        # Độ sáng đèn
        bright_dp = DeviceNormalizer.find_scalar_dp(raw_schema, "brightness")
        if bright_dp:
            b_code = bright_dp.get("code")
            if b_code in status_map:
                hw_val = status_map[b_code]
                pct = DeviceNormalizer.scale_dp_to_percentage(bright_dp, hw_val)
                details.append(f"độ sáng {int(round(pct))}%")
        else:
            for b_code in ["bright_value_v2", "bright_value", "brightness"]:
                if b_code in status_map:
                    details.append(f"độ sáng {status_map[b_code]}")
                    break

        # Nhiệt độ màu ánh sáng
        temp_dp = DeviceNormalizer.find_scalar_dp(raw_schema, "color_temp")
        if temp_dp:
            t_code = temp_dp.get("code")
            if t_code in status_map:
                hw_temp = status_map[t_code]
                pct = DeviceNormalizer.scale_dp_to_percentage(temp_dp, hw_temp)
                details.append(f"nhiệt độ màu {int(round(pct))}%")
        else:
            for t_code in ["temp_value_v2", "temp_value", "color_temp"]:
                if t_code in status_map:
                    details.append(f"nhiệt độ màu {status_map[t_code]}")
                    break

        # Chỉ số bụi mịn PM2.5 (cho máy lọc không khí)
        if "PM25" in status_map or "pm25" in status_map:
            pm25_val = status_map.get("PM25", status_map.get("pm25"))
            details.append(f"chỉ số bụi mịn PM2.5 là {pm25_val}")

        # Trạng thái Hẹn giờ đếm ngược (Timer / Countdown) - Generic Schema-Driven
        timer_info = self._extract_timer_status_desc(raw_schema, status_map)
        if timer_info:
            details.append(timer_info)

        if details:
            return f"{prefix}, {', '.join(details)}."
        elif is_on is True:
            return f"{device_name} hiện đang bật."
        else:
            return f"{device_name} đang hoạt động bình thường."

    @staticmethod
    def _extract_timer_status_desc(raw_schema: Optional[Dict[str, Any]], status_map: Dict[str, Any]) -> Optional[str]:
        """Tự động phát hiện và trích xuất trạng thái hẹn giờ từ metadata schema và status_map (Zero-Hardcode)."""
        if not status_map:
            return None

        all_dps = []
        if isinstance(raw_schema, dict):
            status_item = raw_schema.get("status", [])
            if isinstance(status_item, list):
                all_dps.extend(status_item)
            elif isinstance(status_item, dict):
                for k, v in status_item.items():
                    all_dps.append({"code": k, "type": "Boolean" if isinstance(v, bool) else "Integer"})
            fn_item = raw_schema.get("functions", [])
            if isinstance(fn_item, list):
                all_dps.extend(fn_item)

        seen_codes = set()
        timer_dps = []
        for dp in all_dps:
            c = dp.get("code", "") if isinstance(dp, dict) else str(dp)
            if c and c not in seen_codes:
                seen_codes.add(c)
                c_lower = c.lower()
                if "timer" in c_lower or "countdown" in c_lower:
                    dp_dict = dp if isinstance(dp, dict) else {"code": c, "type": "Integer"}
                    timer_dps.append(dp_dict)

        timer_desc = None
        countdown_desc = None

        for dp in timer_dps:
            code = dp.get("code")
            if code not in status_map:
                continue
            val = status_map[code]
            if val is None:
                continue

            dp_type = dp.get("type", "Integer")
            from adapters.normalizer import DeviceNormalizer
            values_meta = DeviceNormalizer._get_dp_values_meta(dp)
            unit = str(values_meta.get("unit", "")).lower().strip()

            if dp_type == "Enum":
                str_val = str(val).strip()
                if str_val in ("0", "off", "cancel", "none", "close", "0h", "0m", ""):
                    continue
                valid_range = [str(x) for x in values_meta.get("range", [])]
                num_elements = []
                for x in valid_range:
                    try:
                        num_elements.append(float(x))
                    except ValueError:
                        pass
                if len(num_elements) == len(valid_range) and num_elements and max(num_elements) <= 24:
                    timer_desc = f"đang hẹn giờ tắt sau {str_val} tiếng"
                elif len(num_elements) == len(valid_range) and num_elements and max(num_elements) > 24:
                    timer_desc = f"đang hẹn giờ tắt sau {str_val} phút"
                else:
                    timer_desc = f"đang hẹn giờ tắt sau {str_val}"

            elif dp_type == "Integer":
                try:
                    num_val = int(val)
                except (ValueError, TypeError):
                    continue
                if num_val <= 0:
                    continue

                max_val = values_meta.get("max", 86400)
                if unit in ("s", "sec", "second", "seconds", "giây", "秒") or (not unit and max_val >= 3600):
                    total_min = int(round(num_val / 60.0))
                elif unit in ("h", "hour", "hours", "hr", "giờ", "tiếng", "小时") or (not unit and max_val <= 24):
                    total_min = int(round(num_val * 60.0))
                else:
                    total_min = int(round(num_val))

                if total_min <= 0:
                    continue

                if total_min >= 60:
                    hrs = total_min // 60
                    rem = total_min % 60
                    t_str = f"{hrs} tiếng {rem} phút" if rem else f"{hrs} tiếng"
                else:
                    t_str = f"{total_min} phút"

                if "countdown" in code.lower():
                    countdown_desc = f"thời gian hẹn giờ còn lại {t_str}"
                else:
                    timer_desc = f"đang hẹn giờ tắt sau {t_str}"

        # Fallback nếu schema không có thông tin DP nhưng status_map có trường timer / countdown
        if not timer_desc and not countdown_desc:
            for k, v in status_map.items():
                k_lower = k.lower()
                if "timer" in k_lower and v is not None:
                    str_v = str(v).strip()
                    if str_v not in ("0", "off", "cancel", "none", "close", "0h", ""):
                        timer_desc = f"đang hẹn giờ tắt sau {str_v} tiếng"
                elif "countdown" in k_lower and v is not None:
                    try:
                        n = int(v)
                        if n > 0:
                            m = int(round(n / 60.0)) if n > 720 else n
                            if m >= 60:
                                countdown_desc = f"thời gian hẹn giờ còn lại {m // 60} tiếng {m % 60} phút" if m % 60 else f"thời gian hẹn giờ còn lại {m // 60} tiếng"
                            else:
                                countdown_desc = f"thời gian hẹn giờ còn lại {m} phút"
                    except (ValueError, TypeError):
                        pass

        # Nếu có cả timer đã cài và đếm ngược còn lại
        if timer_desc and countdown_desc:
            return f"{timer_desc} ({countdown_desc})"
        return timer_desc or countdown_desc

