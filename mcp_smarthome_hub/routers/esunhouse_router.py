# -*- coding: utf-8 -*-
"""ROUTER ĐỒNG BỘ THIẾT BỊ ESUNHOUSE OEM (ESUNHOUSE ROUTER)
Tiếp nhận Webhook hoặc yêu cầu đồng bộ trực tiếp danh mục thiết bị OEM (PlatformType = 2, ví dụ: Robot 298 Pro Ultra)
từ Backend eSunhouse sang CSDL cục bộ (DeviceCache).
"""

import logging
from typing import Optional
from aiohttp import web

from storage.db import SmartHomeDAL, default_dal
from storage.models import PlatformType

logger = logging.getLogger("ESunhouseRouter")


def create_esunhouse_router(dal: SmartHomeDAL = default_dal):
    """Khởi tạo cụm route đồng bộ thiết bị eSunhouse OEM."""

    async def sync_oem_devices_handler(request: web.Request) -> web.Response:
        """API đồng bộ thiết bị Tuya OEM từ Backend eSunhouse vào hệ thống.

        Payload JSON:
            user_id (str): Mã định danh tài khoản người dùng trên eSunhouse.
            devices (list): Danh sách các thiết bị gia dụng thông minh OEM.
        """
        try:
            data = await request.json()
        except Exception:
            return web.json_response(
                {"status": "error", "message": "Payload JSON không hợp lệ."},
                status=400,
            )

        user_id = data.get("user_id")
        devices = data.get("devices")

        if not user_id:
            return web.json_response(
                {"status": "error", "message": "Thiếu tham số bắt buộc 'user_id'."},
                status=400,
            )

        if not isinstance(devices, list):
            return web.json_response(
                {"status": "error", "message": "Tham số 'devices' phải là một danh sách (list)."},
                status=400,
            )

        user_id = str(user_id).strip()
        synced_list = []

        for d in devices:
            if not isinstance(d, dict):
                continue

            dev_id = d.get("device_id") or d.get("id")
            dev_name = d.get("device_name") or d.get("name")
            category = d.get("category", "sd")
            product_id = d.get("product_id") or d.get("pid")
            is_online = bool(d.get("is_online", d.get("online", True)))
            local_key = d.get("local_key")
            local_ip = d.get("local_ip") or d.get("ip")
            raw_schema = d.get("raw_schema") or d.get("schema")

            if not dev_id or not dev_name:
                continue

            # Lưu vào DeviceCache với PlatformType = TUYA_OEM_ESUNHOUSE (2)
            dal.upsert_device(
                device_id=dev_id,
                user_id=user_id,
                device_name=dev_name,
                category=category,
                platform_type=PlatformType.TUYA_OEM_ESUNHOUSE,
                local_key=local_key,
                local_ip=local_ip,
                raw_schema=raw_schema,
                product_id=product_id,
                is_online=is_online,
            )

            synced_list.append({
                "device_id": dev_id,
                "device_name": dev_name,
                "category": category,
                "is_online": is_online,
            })
            logger.info(
                f"📥 [ESUNHOUSE SYNC] Đã đồng bộ thiết bị OEM: [{dev_name}] (ID: {dev_id}, Category: {category})"
            )

        logger.info(
            f"✨ [ESUNHOUSE SYNC] Hoàn tất đồng bộ {len(synced_list)} thiết bị OEM cho User [{user_id}]."
        )

        return web.json_response({
            "status": "success",
            "user_id": user_id,
            "synced_count": len(synced_list),
            "devices": synced_list,
            "message": f"Đã đồng bộ thành công {len(synced_list)} thiết bị từ eSunhouse.",
        })

    return {
        "sync_oem_devices": sync_oem_devices_handler,
    }
