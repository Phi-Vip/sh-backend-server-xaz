"""Tuya Sharing Manager Client (Chuẩn Tuya Device Sharing SDK / Home Assistant).

Quản lý phiên ủy quyền qua mã QR Ticket, đồng bộ thiết bị và điều khiển thiết bị
thông qua Tuya Sharing Gateway mà không phụ thuộc vào Tuya Developer Platform.
"""

from __future__ import annotations

import logging
import time
from typing import Dict, Any, List, Optional
import tuya_sharing

from storage.db import SmartHomeDAL, default_dal
from storage.models import PlatformType

logger = logging.getLogger("TuyaSharingManager")


class PersistentTokenListener(tuya_sharing.SharingTokenListener):
    """Lắng nghe sự kiện gia hạn Token tự động từ Tuya Sharing SDK và lưu vào CSDL."""

    def __init__(self, user_id: str, dal: SmartHomeDAL):
        self.user_id = user_id
        self.dal = dal

    def update_token(self, token_info: dict[str, Any]):
        logger.info(f"🔄 [TOKEN AUTO-REFRESH] Nhận Token mới từ Cloud cho User [{self.user_id}], tiến hành lưu CSDL...")
        try:
            sess = self.dal.get_sharing_session(self.user_id)
            if sess:
                session_data = sess.get("session_data", {})
                session_data["access_token"] = token_info.get("access_token", session_data.get("access_token"))
                session_data["refresh_token"] = token_info.get("refresh_token", session_data.get("refresh_token"))
                session_data["expire_time"] = token_info.get("expire_time", 7200)
                session_data["t"] = token_info.get("t", int(time.time() * 1000))
                self.dal.save_sharing_session(
                    user_id=self.user_id,
                    user_code=sess.get("user_code", ""),
                    terminal_id=sess.get("terminal_id", ""),
                    endpoint=sess.get("endpoint", ""),
                    tuya_uid=sess.get("tuya_uid", ""),
                    session_data=session_data,
                )
                logger.info(f"✅ [TOKEN AUTO-REFRESH] Đã cập nhật Token mới vào CSDL cho User [{self.user_id}] thành công!")

                # Đồng bộ Token mới vào tuya_user_credentials để TokenVault và fallback luôn nhất quán
                try:
                    from datetime import datetime, timedelta
                    exp_s = token_info.get("expire_time", 7200)
                    exp_at = datetime.utcnow() + timedelta(seconds=exp_s)
                    self.dal.save_user_credential(
                        user_id=self.user_id,
                        external_tuya_uid=sess.get("tuya_uid", ""),
                        access_token=token_info.get("access_token", session_data.get("access_token")),
                        refresh_token=token_info.get("refresh_token", session_data.get("refresh_token")),
                        expire_at=exp_at,
                        auth_source="tuya_sharing_qr",
                    )
                except Exception as e_cred:
                    logger.warning(f"⚠️ [TOKEN AUTO-REFRESH] Không thể đồng bộ sang user_credentials: {e_cred}")
        except Exception as e:
            logger.error(f"❌ [TOKEN AUTO-REFRESH] Lỗi cập nhật Token mới vào CSDL: {e}")


class TuyaSharingManager:
    """Quản lý các phiên tuya_sharing.Manager theo từng user_id."""

    def __init__(self):
        self._managers: Dict[str, tuya_sharing.Manager] = {}
        self._session_cache: Dict[str, Dict[str, Any]] = {}

    def register_session(
        self,
        user_id: str,
        user_code: str,
        login_result_data: Dict[str, Any],
        save_db: bool = True,
        dal: Optional[SmartHomeDAL] = None,
    ) -> tuya_sharing.Manager:
        """Đăng ký hoặc cập nhật phiên Tuya Sharing sau khi quét QR thành công."""
        token_response = {
            "t": login_result_data.get("t") or int(time.time() * 1000),
            "uid": login_result_data.get("uid", ""),
            "expire_time": login_result_data.get("expire_time", 7200),
            "access_token": login_result_data.get("access_token", ""),
            "refresh_token": login_result_data.get("refresh_token", ""),
        }
        endpoint = login_result_data.get("endpoint") or "https://apigw.iotbing.com"
        terminal_id = login_result_data.get("terminal_id") or ""
        client_id = "HA_3y9q4ak7g4ephrvke"

        active_dal = dal or default_dal
        listener = PersistentTokenListener(user_id=user_id, dal=active_dal)

        logger.info(
            f"📱 [TUYA SHARING] Khởi tạo Manager cho User [{user_id}] | "
            f"UID: {token_response['uid']} | Endpoint: {endpoint} | Terminal: {terminal_id[:12]}..."
        )

        manager = tuya_sharing.Manager(
            client_id=client_id,
            user_code=user_code,
            terminal_id=terminal_id,
            end_point=endpoint,
            token_response=token_response,
            listener=listener,
        )

        self._managers[user_id] = manager
        self._session_cache[user_id] = {
            "user_code": user_code,
            "login_result": login_result_data,
            "created_at": time.time(),
        }

        # Lưu xuống CSDL để tồn tại vĩnh viễn qua các lần restart server
        if save_db:
            try:
                active_dal.save_sharing_session(
                    user_id=user_id,
                    user_code=user_code,
                    terminal_id=terminal_id,
                    endpoint=endpoint,
                    tuya_uid=token_response.get("uid"),
                    session_data=login_result_data,
                )
                logger.info(f"💾 [TUYA SHARING] Đã lưu phiên ủy quyền của [{user_id}] vào CSDL an toàn.")
            except Exception as e_db:
                logger.error(f"⚠️ [TUYA SHARING] Lỗi lưu session vào CSDL: {e_db}")

        return manager

    def get_manager(self, user_id: str, dal: Optional[SmartHomeDAL] = None) -> Optional[tuya_sharing.Manager]:
        """Lấy manager đang hoạt động của user (tự động phân giải qua quan hệ Loa/User và khôi phục từ CSDL)."""
        active_dal = dal or default_dal
        resolved_uid = active_dal.resolve_user_id(user_id)

        if resolved_uid not in self._managers and user_id not in self._managers:
            saved = active_dal.get_sharing_session(resolved_uid)
            if saved and saved.get("session_data"):
                logger.info(f"🔄 [TUYA SHARING] Tự động khôi phục Manager từ CSDL cho User [{resolved_uid}]...")
                try:
                    self.register_session(
                        user_id=resolved_uid,
                        user_code=saved["user_code"],
                        login_result_data=saved["session_data"],
                        save_db=False,
                    )
                except Exception as e_restore:
                    logger.error(f"❌ [TUYA SHARING] Lỗi khôi phục session cho [{resolved_uid}]: {e_restore}")

        mgr = self._managers.get(resolved_uid) or self._managers.get(user_id)
        if not mgr and len(self._managers) == 1:
            mgr = next(iter(self._managers.values()))
        return mgr

    def restore_all_sessions(self, dal: Optional[SmartHomeDAL] = None) -> int:
        """Khôi phục tất cả phiên Tuya Sharing từ CSDL khi server khởi động."""
        active_dal = dal or default_dal
        sessions = active_dal.list_all_sharing_sessions()
        restored = 0
        for s in sessions:
            u_id = s.get("user_id")
            if not u_id or not s.get("session_data"):
                continue
            try:
                logger.info(f"📱 [TUYA SHARING STARTUP] Khôi phục phiên Tuya Sharing cho User [{u_id}]...")
                self.register_session(
                    user_id=u_id,
                    user_code=s["user_code"],
                    login_result_data=s["session_data"],
                    save_db=False,
                )
                self.sync_devices(u_id, dal=active_dal)
                restored += 1
            except Exception as e:
                logger.error(f"❌ [TUYA SHARING STARTUP] Không thể khôi phục phiên cho [{u_id}]: {e}")
        return restored

    def sync_devices(
        self,
        user_id: str,
        dal: Optional[SmartHomeDAL] = None,
    ) -> List[Dict[str, Any]]:
        """Đồng bộ toàn bộ thiết bị từ Tuya Sharing Gateway về CSDL Sunhouse."""
        manager = self.get_manager(user_id)
        if not manager:
            logger.warning(f"⚠️ [TUYA SHARING SYNC] Chưa có phiên Manager hoạt động cho User [{user_id}]")
            return []

        active_dal = dal or default_dal
        resolved_uid = active_dal.resolve_user_id(user_id)
        manager = self.get_manager(resolved_uid, dal=active_dal)
        if not manager:
            logger.warning(f"⚠️ [TUYA SHARING SYNC] Chưa có phiên Manager hoạt động cho User [{user_id}]")
            return []

        # Tự động kiểm tra và gia hạn Token trước khi truy vấn danh mục thiết bị
        self.check_and_refresh_token(resolved_uid, dal=active_dal)

        logger.info(f"🔄 [TUYA SHARING SYNC] Đang truy vấn danh mục thiết bị từ Tuya Sharing Gateway cho [{resolved_uid}]...")
        try:
            manager.update_device_cache()
        except Exception as e:
            err_msg = str(e)
            if "1010" in err_msg or "expired" in err_msg.lower():
                logger.error(f"❌ [TUYA SHARING SYNC] Phiên liên kết của User [{resolved_uid}] đã hết hạn (Error 1010). Vui lòng quét lại mã QR trên Web Portal.")
            else:
                logger.error(f"❌ [TUYA SHARING SYNC] Lỗi khi gọi update_device_cache: {e}")
            return []

        synced_list = []
        for dev_id, dev in manager.device_map.items():
            try:
                name = getattr(dev, "name", "Thiết bị Smart Life")
                category = getattr(dev, "category", "")
                online = getattr(dev, "online", True)
                local_key = getattr(dev, "local_key", None)
                raw_traits = getattr(dev, "status", {}) or {}

                # Trích xuất instruction set / functions nếu có
                fn_dict = getattr(dev, "function", {}) or {}
                functions_list = []
                for code, fn in fn_dict.items():
                    functions_list.append({
                        "code": getattr(fn, "code", code),
                        "type": getattr(fn, "type", "Boolean"),
                        "name": getattr(fn, "name", code),
                        "values": getattr(fn, "values", {}),
                    })

                from adapters.dp_classifier import DPClassifier

                # 1. Phân loại DP theo chuẩn DPClassifier (Lọc sạch DP rác blacklist, gom nhóm Primary & Sub)
                classified = DPClassifier.classify_functions(functions_list, category=category)
                primary_dps = classified["primary"]
                sub_dps = classified["sub_features"]
                blacklist_dps = classified["blacklist"]

                temp_schema = {
                    "category": category,
                    "functions": functions_list,
                    "status": raw_traits,
                }
                # 2. Tự động tổng hợp năng lực tiếng Việt chuẩn xác (Zero-Hardcode)
                synth_caps = DPClassifier.synthesize_capabilities(temp_schema, category=category)

                raw_schema = {
                    "category": category,
                    "functions": functions_list,
                    "status": raw_traits,
                    "classified_dps": {
                        "primary": [f.get("code") for f in primary_dps],
                        "sub_features": [f.get("code") for f in sub_dps],
                        "blacklist": [f.get("code") for f in blacklist_dps],
                    },
                    "synthesized_capabilities": synth_caps,
                }

                # 3. In Log Cây DPs Minh Bạch Chuẩn Thương Mại (Tree Logging)
                logger.info(f"📦 [TUYA SCHEMA] Đã nhận đặc tả DP chuẩn của [{name}] (ID: {dev_id}, Category: {category}):")
                if functions_list:
                    logger.info(f"   ├── 📋 Danh sách Lệnh điều khiển (Functions: {len(functions_list)} DPs):")
                    for fn in functions_list:
                        logger.info(f"   │   🔹 DP [{fn.get('code')}]: Kiểu={fn.get('type')}, Giá trị={fn.get('values')}")
                else:
                    logger.warning(f"   ├── ⚠️ Thiết bị không có Functions trong đặc tả OpenAPI/Sharing")

                if raw_traits:
                    logger.info(f"   └── 📊 Danh sách Trạng thái (Status: {len(raw_traits)} DPs):")
                    for code, val in raw_traits.items():
                        logger.info(f"       🔸 DP [{code}]: Giá trị={val}")

                # Kiểm tra công tắc nguồn
                has_power = any(
                    "switch" in f.get("code", "").lower() or "power" in f.get("code", "").lower()
                    for f in functions_list
                )
                if not has_power:
                    logger.warning(f"   ⚠️ [CẢNH BÁO NĂNG LỰC] Thiết bị [{name}] KHÔNG CÓ DP công tắc nguồn (Power Switch) từ Tuya Cloud.")
                logger.info(f"   💡 [NĂNG LỰC LLM] Tổng hợp năng lực: {synth_caps}")

                active_dal.upsert_device(
                    device_id=dev_id,
                    user_id=resolved_uid,
                    device_name=name,
                    category=category,
                    platform_type=PlatformType.TUYA_EXTERNAL_SMARTLIFE,
                    local_key=local_key,
                    is_online=online,
                    raw_schema=raw_schema,
                )
                synced_list.append({
                    "id": dev_id,
                    "device_id": dev_id,
                    "name": name,
                    "device_name": name,
                    "category": category,
                    "online": online,
                })
            except Exception as e_dev:
                logger.error(f"❌ [TUYA SHARING SYNC] Lỗi khi lưu thiết bị {dev_id}: {e_dev}", exc_info=True)

        logger.info(f"✅ [TUYA SHARING SYNC] Đã đồng bộ thành công {len(synced_list)} thiết bị về CSDL cho User [{resolved_uid}].")
        return synced_list

    def check_and_refresh_token(
        self,
        user_id: str,
        dal: Optional[SmartHomeDAL] = None,
    ) -> bool:
        """Kiểm tra và chủ động gia hạn token trước khi hết hạn."""
        active_dal = dal or default_dal
        resolved_uid = active_dal.resolve_user_id(user_id)
        manager = self.get_manager(resolved_uid, dal=active_dal) or self.get_manager(user_id, dal=active_dal)
        if not manager or not hasattr(manager, "customer_api"):
            return False

        api = manager.customer_api
        token_info = getattr(api, "token_info", None)
        if not token_info:
            return False

        now_ms = int(time.time() * 1000)
        raw_expire = getattr(token_info, "expire_time", 0)
        try:
            expire_ms = int(raw_expire)
        except (TypeError, ValueError):
            expire_ms = 0

        # Nếu token còn hạn dưới 5 phút hoặc đã quá hạn, chủ động gọi refresh
        if expire_ms - 5 * 60 * 1000 <= now_ms:
            logger.info(
                f"⏳ [TOKEN REFRESH] Token của User [{resolved_uid}] sắp hết hạn hoặc đã quá hạn, đang yêu cầu Cloud cấp mới..."
            )
            try:
                api.refresh_access_token_if_need()
                new_expire = getattr(api.token_info, "expire_time", 0)
                if new_expire > now_ms:
                    logger.info(f"🎉 [TOKEN REFRESH SUCCESS] Gia hạn Token thành công cho User [{resolved_uid}]!")
                    return True
                else:
                    logger.warning(f"⚠️ [TOKEN REFRESH FAILED] Không thể gia hạn token cho User [{resolved_uid}]")
                    return False
            except Exception as e:
                logger.error(f"❌ [TOKEN REFRESH ERROR] Lỗi khi gia hạn token cho [{resolved_uid}]: {e}")
                return False
        return True

    def unlink_session(
        self,
        user_id: str,
        dal: Optional[SmartHomeDAL] = None,
    ) -> Dict[str, Any]:
        """Hủy hoàn toàn phiên liên kết Tuya Sharing cả trong RAM và CSDL."""
        active_dal = dal or default_dal
        resolved_uid = active_dal.resolve_user_id(user_id)

        # 1. Hủy kết nối trong RAM
        for uid in [user_id, resolved_uid]:
            if uid in self._managers:
                try:
                    self._managers[uid].unload()
                except Exception:
                    pass
                del self._managers[uid]
            if uid in self._session_cache:
                del self._session_cache[uid]

        # 2. Xóa triệt để trong CSDL
        result = active_dal.unlink_tuya_account(resolved_uid)
        logger.info(f"🔌 [TUYA SHARING UNLINK] Đã hủy liên kết tài khoản Tuya cho [{resolved_uid}]: {result}")
        return result

    def send_commands(
        self,
        user_id: str,
        device_id: str,
        commands: List[Dict[str, Any]],
    ) -> bool:
        """Gửi lệnh điều khiển thiết bị qua Tuya Sharing Gateway."""
        manager = self.get_manager(user_id)
        if not manager:
            logger.error(f"❌ [TUYA SHARING CTRL] Không tìm thấy Manager cho User [{user_id}]")
            return False

        # Tự động kiểm tra và gia hạn Token trước khi gửi lệnh điều khiển
        self.check_and_refresh_token(user_id)

        logger.info(f"🚀 [TUYA SHARING CTRL] Gửi lệnh tới [{device_id}]: {commands}")
        try:
            manager.send_commands(device_id, commands)
            logger.info(f"✅ [TUYA SHARING CTRL] Đã gửi lệnh thành công tới [{device_id}]")
            return True
        except Exception as e:
            logger.error(f"❌ [TUYA SHARING CTRL] Lỗi gửi lệnh tới [{device_id}]: {e}")
            return False


# Singleton toàn cục
sharing_manager = TuyaSharingManager()
