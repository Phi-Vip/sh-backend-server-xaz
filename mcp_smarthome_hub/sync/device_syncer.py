# -*- coding: utf-8 -*-
"""BỘ ĐỒNG BỘ THIẾT BỊ ĐÁM MÂY TUYA (TUYA CLOUD DEVICE SYNCER)
Tự động đồng bộ các thiết bị liên kết với dự án (từ App Smart Life) về CSDL Cục bộ (smarthome.db)
giúp MCP Server và XiaoZhi AI Voice luôn nắm bắt được thiết bị mới thêm vào trong thời gian thực.
"""

import asyncio
import json
import logging
import os
from typing import Any, Dict, List, Optional

from storage.db import SmartHomeDAL, default_dal
from storage.models import PlatformType
from clients.tuya_client import TuyaCloudClient

logger = logging.getLogger("TuyaDeviceSyncer")


async def sync_tuya_devices(
    dal: SmartHomeDAL = default_dal,
    tuya_client: Optional[TuyaCloudClient] = None,
    user_id: str = "user_real_phi",
) -> List[Dict[str, Any]]:
    """Đồng bộ danh sách thiết bị liên kết từ Tuya Cloud về CSDL Cục bộ."""
    if not tuya_client:
        logger.warning("[TUYA SYNC] TuyaCloudClient chưa được khởi tạo, bỏ qua đồng bộ.")
        return []

    try:
        # 1. Lấy token mới nhất từ Tuya Cloud
        token_info = await tuya_client.get_token(grant_type=1)
        token = token_info.get("access_token")
        if not token:
            logger.error("[TUYA SYNC] Không lấy được Access Token từ Tuya Cloud.")
            return []

        # 2. Kiểm tra cờ tính năng TUYA_FEATURE_PROJECT_TOKEN
        feature_proj_token = os.getenv("TUYA_FEATURE_PROJECT_TOKEN", "true").lower() == "true"
        user_cred = dal.get_user_credential(user_id)

        # Nếu Project Token bị tắt mà user chưa liên kết OAuth2 -> Không nạp thiết bị ngoài
        if not feature_proj_token and not user_cred:
            logger.info(
                f"ℹ️ [TUYA SYNC] Chế độ Project Token đã tắt (TUYA_FEATURE_PROJECT_TOKEN=false) "
                f"và User [{user_id}] chưa liên kết OAuth2. Bỏ qua nạp thiết bị Smart Life ngoài."
            )
            return []

        # 3. Truy vấn danh sách thiết bị:
        # A. Kiểm tra nếu người dùng đã liên kết qua OAuth2 User-level Token (grant_type=2)
        oauth_devices = []
        if user_cred and user_cred.get("external_tuya_uid") and user_cred.get("access_token"):
            tuya_uid = user_cred["external_tuya_uid"]
            oauth_token = user_cred["access_token"]
            try:
                logger.info(f"🔑 [TUYA SYNC] Đang lấy thiết bị người dùng qua OAuth2 Token cho UID [{tuya_uid}]...")
                oauth_devices = await tuya_client.get_user_devices(tuya_uid=tuya_uid, token=oauth_token)
                logger.info(f"🔑 [TUYA SYNC] Lấy được {len(oauth_devices)} thiết bị từ tài khoản OAuth2 UID [{tuya_uid}].")
            except Exception as e_user:
                logger.warning(f"⚠️ [TUYA SYNC] Lỗi khi lấy thiết bị qua OAuth User Token: {e_user}")

        # B. Truy vấn danh sách thiết bị liên kết qua API dự án /v1.0/iot-01/associated-users/devices
        project_devices = []
        if feature_proj_token or not oauth_devices:
            try:
                project_devices = await tuya_client.get_associated_user_devices(token=token)
            except Exception as e_proj:
                logger.warning(f"⚠️ [TUYA SYNC] Lỗi khi lấy associated devices: {e_proj}")

        # Hợp nhất danh bạ thiết bị (khử trùng ID)
        all_dev_map = {}
        for d in (project_devices or []):
            if d.get("id"):
                all_dev_map[d.get("id")] = d
        for d in (oauth_devices or []):
            if d.get("id"):
                all_dev_map[d.get("id")] = d

        devices = list(all_dev_map.values())

        # Nếu Project Token bị tắt nhưng User có OAuth2 credential, chỉ lấy thiết bị thuộc UID của User
        if not feature_proj_token and user_cred:
            tuya_uid = user_cred.get("external_tuya_uid")
            if tuya_uid:
                devices = [d for d in devices if not d.get("uid") or d.get("uid") == tuya_uid]
        if not devices:
            logger.info("[TUYA SYNC] Không có thiết bị liên kết nào trên Tuya Cloud.")
            # Dọn dẹp toàn bộ thiết bị Tuya Smart Life của user nếu trên Cloud hoàn toàn không còn thiết bị
            existing_tuya_devices = dal.get_user_devices(
                user_id=user_id, platform_type=int(PlatformType.TUYA_EXTERNAL_SMARTLIFE)
            )
            for old_d in existing_tuya_devices:
                old_id = old_d.get("device_id")
                if old_id:
                    logger.info(
                        f"🗑️ [TUYA PURGE] Thiết bị [{old_d.get('device_name')}] (ID: {old_id}) "
                        f"không còn trên Tuya Cloud. Xóa khỏi CSDL cục bộ..."
                    )
                    dal.delete_device(old_id)
            return []

        logger.info(f"🔄 [TUYA SYNC] Tìm thấy {len(devices)} thiết bị trên Tuya Cloud. Bắt đầu đồng bộ...")
        synced_devices = []

        for d in devices:
            dev_id = d.get("id")
            dev_name = d.get("name")
            category = d.get("category", "")
            product_id = d.get("product_id")
            is_online = d.get("online", True)
            local_key = d.get("local_key")
            ip = d.get("ip")

            # 3. Lấy đặc tả schema DP chuẩn (GET /v1.0/iot-03/devices/{dev_id}/specification)
            raw_schema = None
            try:
                logger.info(f"📡 [TUYA OPENAPI] Gửi GET /v1.0/iot-03/devices/{dev_id}/specification lấy schema DP chuẩn...")
                if hasattr(tuya_client, "get_device_specification"):
                    raw_spec = tuya_client.get_device_specification(dev_id, token=token)
                    if asyncio.iscoroutine(raw_spec):
                        raw_schema = await raw_spec
                    else:
                        res = await tuya_client.request("GET", f"/v1.0/iot-03/devices/{dev_id}/specification", token=token)
                        raw_schema = res.get("result", {})
                else:
                    res = await tuya_client.request("GET", f"/v1.0/iot-03/devices/{dev_id}/specification", token=token)
                    raw_schema = res.get("result", {})
            except Exception as e_spec:
                logger.warning(f"⚠️ [TUYA SYNC] Không lấy được schema từ Tuya OpenAPI cho '{dev_name}' ({e_spec}), dùng status mặc định.")
                raw_schema = {"status": d.get("status", [])}

            functions = raw_schema.get("functions", []) if isinstance(raw_schema, dict) else []
            status_list = raw_schema.get("status", []) if isinstance(raw_schema, dict) else []

            # 3b. CƠ CHẾ FALLBACK HAI TẦNG (TWO-TIER HYBRID SCHEMA RESOLUTION)
            # Kiểm tra xem Standard Specification có bị thiếu hụt không (dưới 3 DP hoặc thiếu DP công tắc nguồn)
            has_power_dp = any(
                "switch" in fn.get("code", "").lower() or "power" in fn.get("code", "").lower()
                for fn in functions
            )
            is_incomplete = (len(functions) == 0) or (len(functions) < 3 and not has_power_dp)

            if is_incomplete:
                logger.warning(
                    f"⚠️ [TUYA TWO-TIER FALLBACK] Thiết bị [{dev_name}] (ID: {dev_id}, Category: {category}) "
                    f"có Standard Specification không đầy đủ ({len(functions)} DPs, thiếu công tắc nguồn). "
                    f"Kích hoạt truy vấn Thing Model nâng cao qua GET /v2.0/cloud/thing/{dev_id}/model..."
                )
                try:
                    thing_res = await tuya_client.get_thing_model(dev_id, token=token)
                    model_str = thing_res.get("model", "{}") if isinstance(thing_res, dict) else "{}"
                    model_data = json.loads(model_str) if isinstance(model_str, str) else model_str
                    services = model_data.get("services", [])
                    model_props = services[0].get("properties", []) if services else []

                    if model_props:
                        logger.info(
                            f"✨ [TUYA THING MODEL] Khôi phục thành công {len(model_props)} DPs gốc phần cứng từ Thing Model!"
                        )
                        TYPE_MAP = {
                            "bool": "Boolean",
                            "value": "Integer",
                            "enum": "Enum",
                            "string": "String",
                            "bitmap": "Bitmap",
                            "raw": "Raw",
                            "json": "Json",
                        }

                        converted_functions = []
                        converted_status = []
                        for prop in model_props:
                            p_code = prop.get("code", "")
                            p_id = prop.get("abilityId")
                            p_name = prop.get("name", "")
                            type_spec = prop.get("typeSpec", {})
                            raw_type = type_spec.get("type", "bool").lower()
                            mapped_type = TYPE_MAP.get(raw_type, "String")
                            access_mode = prop.get("accessMode", "rw").lower()

                            values_dict = {}
                            if mapped_type == "Integer":
                                values_dict = {
                                    "min": type_spec.get("min", 0),
                                    "max": type_spec.get("max", 100),
                                    "scale": type_spec.get("scale", 0),
                                    "step": type_spec.get("step", 1),
                                    "unit": type_spec.get("unit", ""),
                                }
                            elif mapped_type == "Enum":
                                values_dict = {
                                    "range": type_spec.get("range", []),
                                    "unit": type_spec.get("unit", ""),
                                }
                            elif mapped_type == "Bitmap":
                                values_dict = {
                                    "label": type_spec.get("label", []),
                                    "maxlen": type_spec.get("maxlen", 1),
                                }

                            item = {
                                "code": p_code,
                                "name": p_name,
                                "type": mapped_type,
                                "values": json.dumps(values_dict, ensure_ascii=False),
                                "dp_id": p_id,
                                "access_mode": access_mode,
                            }
                            # Chỉ đưa thuộc tính có quyền ghi (rw, wr) vào Functions điều khiển
                            if access_mode in ("rw", "wr"):
                                converted_functions.append(item)
                            # Mọi thuộc tính (kể cả chỉ đọc ro) đều đưa vào Status
                            converted_status.append(item)

                        raw_schema = {
                            "category": category,
                            "functions": converted_functions,
                            "status": converted_status,
                            "instruction_mode": "thing_model",
                            "source": "thing_model_fallback",
                        }
                        functions = converted_functions
                        status_list = converted_status
                except Exception as e_model:
                    logger.error(f"❌ [TUYA TWO-TIER FALLBACK] Lỗi khi nạp Thing Model cho [{dev_name}]: {e_model}")
            else:
                if isinstance(raw_schema, dict):
                    raw_schema["instruction_mode"] = "standard"

            logger.info(f"📦 [TUYA SCHEMA] Đã nhận đặc tả DP chuẩn của [{dev_name}] (ID: {dev_id}, Category: {category}):")
            if functions:
                logger.info(f"   ├── 📋 Danh sách Lệnh điều khiển (Functions: {len(functions)} DPs):")
                for fn in functions:
                    logger.info(f"   │   🔹 DP [{fn.get('code')}]: Kiểu={fn.get('type')}, Giá trị={fn.get('values')}")
            else:
                logger.warning(f"   ├── ⚠️ Thiết bị không có Functions trong đặc tả OpenAPI")

            if status_list:
                logger.info(f"   └── 📊 Danh sách Trạng thái (Status: {len(status_list)} DPs):")
                for st in status_list:
                    logger.info(f"       🔸 DP [{st.get('code')}]: Kiểu={st.get('type')}, Giá trị={st.get('values')}")

            # 4. Lưu hoặc cập nhật vào CSDL cục bộ qua DAL
            dal.upsert_device(
                device_id=dev_id,
                user_id=user_id,
                device_name=dev_name,
                category=category,
                platform_type=PlatformType.TUYA_EXTERNAL_SMARTLIFE,
                local_key=local_key,
                local_ip=ip,
                raw_schema=raw_schema,
                product_id=product_id,
                is_online=is_online,
            )

            synced_devices.append({
                "device_id": dev_id,
                "device_name": dev_name,
                "category": category,
                "is_online": is_online,
            })
            logger.info(f"   ✅ Đã lưu thiết bị vào DB: [{dev_name}] (ID: {dev_id}, Loại: {category})\n")

        # 5. CƠ CHẾ ĐỐI SOÁT & DỌN DẸP THIẾT BỊ ĐÃ BỊ GỠ BỎ (RECONCILIATION / PURGE STALE DEVICES)
        cloud_device_ids = {d.get("id") for d in devices if d.get("id")}
        existing_tuya_devices = dal.get_user_devices(
            user_id=user_id,
            platform_type=int(PlatformType.TUYA_EXTERNAL_SMARTLIFE),
        )
        purged_count = 0
        for local_dev in existing_tuya_devices:
            local_id = local_dev.get("device_id")
            if local_id and local_id not in cloud_device_ids:
                dev_name = local_dev.get("device_name", local_id)
                logger.info(
                    f"🗑️ [TUYA PURGE] Thiết bị [{dev_name}] (ID: {local_id}) "
                    f"đã bị gỡ bỏ khỏi Smart Life / Tuya Cloud. Tiến hành xóa khỏi CSDL cục bộ..."
                )
                if dal.delete_device(local_id):
                    purged_count += 1

        if purged_count > 0:
            logger.info(
                f"✨ [TUYA PURGE] Đã dọn dẹp thành công {purged_count} thiết bị không còn tồn tại trên Tuya Cloud.\n"
            )

        return synced_devices

    except Exception as e:
        logger.error(f"[TUYA SYNC] Lỗi trong quá trình đồng bộ thiết bị Tuya: {e}")
        return []

