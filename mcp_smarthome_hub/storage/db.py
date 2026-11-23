"""Data Access Layer (DAL) cho Hệ sinh thái Smarthome Đa người dùng.

Tự động mã hóa AES-256-GCM khi ghi vào DB và giải mã khi đọc ra,
đảm bảo kiểm tra trực tiếp CSDL không bao giờ lộ token hoặc local_key ở dạng plaintext.
"""

import os
import json
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from sqlalchemy import create_engine, select, update, delete
from sqlalchemy.orm import sessionmaker, Session

from .models import (
    Base,
    PlatformType,
    extract_mac_and_device_id,
    User,
    Speaker,
    TuyaProjectToken,
    TuyaUserCredential,
    HomeAssistantCredential,
    DeviceCache,
    PairingSession,
    TuyaSharingSession,
    AgentProfile,
)
from .token_vault import vault


class SmartHomeDAL:
    """Tầng truy cập dữ liệu (DAL) an toàn cho Smarthome."""

    def __init__(self, db_url: Optional[str] = None):
        if not db_url:
            # Kiểm tra cờ USE_POSTGRES_DB để tự động chuyển sang PostgreSQL 16
            use_pg = os.getenv("USE_POSTGRES_DB", "false").lower() in ["true", "1"]
            if use_pg:
                db_url = os.getenv("DATABASE_URL") or os.getenv("SMART_HOME_DB_URL")
            if not db_url:
                db_url = os.getenv("SMART_HOME_DB_URL")
            if not db_url:
                db_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "data")
                os.makedirs(db_dir, exist_ok=True)
                db_path = os.path.abspath(os.path.join(db_dir, "smarthome.db"))
                db_url = f"sqlite:///{db_path}"

        self.db_url = db_url
        engine_kwargs = {
            "echo": False,
            "future": True,
        }
        if "sqlite" in self.db_url:
            engine_kwargs["connect_args"] = {"check_same_thread": False}
        elif "postgresql" in self.db_url:
            # Cấu hình Connection Pool chuẩn PgBouncer / PostgreSQL 16
            engine_kwargs["pool_size"] = int(os.getenv("DB_POOL_SIZE", "50"))
            engine_kwargs["max_overflow"] = int(os.getenv("DB_MAX_OVERFLOW", "20"))
            engine_kwargs["pool_pre_ping"] = True
            engine_kwargs["pool_recycle"] = 300

        self.engine = create_engine(self.db_url, **engine_kwargs)
        self.SessionFactory = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.init_db()

    def init_db(self):
        """Khởi tạo toàn bộ các bảng trong CSDL và cập nhật schema nếu cần."""
        Base.metadata.create_all(self.engine)
        try:
            from sqlalchemy import text
            with self.engine.connect() as conn:
                if "sqlite" in self.db_url:
                    conn.execute(text("ALTER TABLE speakers ADD COLUMN device_id VARCHAR(64)"))
                    conn.commit()
        except Exception:
            pass

    def get_session(self) -> Session:
        """Lấy phiên làm việc SQLAlchemy."""
        return self.SessionFactory()

    # =========================================================================
    # User Operations
    # =========================================================================

    def upsert_user(self, user_id: str, pseudonym_tuya_uid: Optional[str] = None) -> User:
        """Thêm mới hoặc cập nhật thông tin người dùng."""
        if not pseudonym_tuya_uid:
            pseudonym_tuya_uid = vault.hash_user_id(user_id)

        with self.get_session() as session:
            user = session.get(User, user_id)
            if not user:
                user = User(
                    user_id=user_id,
                    pseudonym_tuya_uid=pseudonym_tuya_uid,
                    created_at=datetime.utcnow(),
                )
                session.add(user)
            else:
                user.pseudonym_tuya_uid = pseudonym_tuya_uid
            session.commit()
            session.refresh(user)
            return user

    def get_user(self, user_id: str) -> Optional[User]:
        """Truy vấn thông tin người dùng theo user_id."""
        with self.get_session() as session:
            return session.get(User, user_id)

    # =========================================================================
    # Speaker Operations
    # =========================================================================

    def upsert_speaker(
        self,
        speaker_mac: str,
        user_id: str,
        device_id: Optional[str] = None,
        device_name: str = "Loa Sunhouse",
        home_id: Optional[str] = None,
    ) -> Speaker:
        """Gán hoặc cập nhật thông tin Loa thông minh Sunhouse với User ID."""
        mac, dev_id = extract_mac_and_device_id(speaker_mac or device_id)
        final_device_id = device_id or dev_id

        # Đảm bảo user tồn tại
        self.upsert_user(user_id)

        with self.get_session() as session:
            speaker = session.get(Speaker, mac)
            if not speaker:
                speaker = Speaker(
                    speaker_mac=mac,
                    device_id=final_device_id,
                    user_id=user_id,
                    device_name=device_name,
                    home_id=home_id,
                    is_active=True,
                    created_at=datetime.utcnow(),
                )
                session.add(speaker)
            else:
                speaker.user_id = user_id
                speaker.device_id = final_device_id
                speaker.device_name = device_name
                speaker.home_id = home_id
                speaker.is_active = True
            session.commit()
            session.refresh(speaker)
            return speaker

    def get_speaker(self, identifier: Optional[str] = None) -> Optional[Speaker]:
        """Lấy thông tin loa theo địa chỉ MAC hoặc Device ID phần cứng."""
        if not identifier:
            return None
        mac, _ = extract_mac_and_device_id(identifier)
        with self.get_session() as session:
            spk = None
            if mac:
                spk = session.get(Speaker, mac)
            if not spk and identifier:
                stmt = select(Speaker).where(Speaker.device_id == identifier)
                spk = session.execute(stmt).scalar_one_or_none()
            return spk

    def get_first_speaker(self) -> Optional[Speaker]:
        """Lấy loa đầu tiên hoặc gần nhất trong hệ thống CSDL (không phụ thuộc hardcode MAC)."""
        with self.get_session() as session:
            stmt = select(Speaker).order_by(Speaker.created_at.desc())
            return session.execute(stmt).scalars().first()

    def get_user_by_speaker(self, identifier: str) -> Optional[User]:
        """Tìm chủ sở hữu của Loa Sunhouse theo MAC hoặc Device ID."""
        spk = self.get_speaker(identifier)
        if spk and spk.user:
            return spk.user
        return None

    def delete_speaker(self, identifier: str) -> bool:
        """Xóa hoặc hủy ghép nối Loa thông minh Sunhouse theo MAC hoặc Device ID."""
        mac, _ = extract_mac_and_device_id(identifier)
        with self.get_session() as session:
            spk = None
            if mac:
                spk = session.get(Speaker, mac)
            if not spk and identifier:
                stmt = select(Speaker).where(Speaker.device_id == identifier)
                spk = session.execute(stmt).scalar_one_or_none()
            if spk:
                session.delete(spk)
                session.commit()
                return True
            return False

    def resolve_user_id(self, identifier: Optional[str] = None) -> str:
        """Tự động phân giải định danh bất kỳ (MAC, Device ID, hoặc User ID) thành User ID chuẩn trong CSDL.
        
        Quy tắc phân giải quan hệ thực thể (Zero Hardcoding):
        1. Nếu identifier rỗng:
           - Tra cứu chủ sở hữu của Loa đầu tiên/gần nhất trong bảng `speakers`.
           - Hoặc lấy User đầu tiên có phiên ủy quyền / thiết bị trong CSDL.
           - Nếu chưa có dữ liệu nào, trả về 'default_user'.
        2. Nếu identifier là MAC hoặc Hardware Device ID của Loa:
           - Tra cứu bảng `speakers`: lấy `speaker.user_id`.
        3. Nếu identifier tồn tại trực tiếp trong bảng `users`:
           - Trả về chính user_id đó.
        4. Nếu identifier là chuỗi bất kỳ:
           - Thử tra cứu xem có trùng device_id hoặc speaker_mac trong bảng `speakers` không.
           - Nếu trong hệ thống gia đình chỉ có duy nhất 1 User sở hữu phiên kết nối Tuya:
             Tự động map về tài khoản đó (single-home hub).
        """
        if not identifier or str(identifier).strip() in ("None", "undefined", "null", ""):
            first_spk = self.get_first_speaker()
            if first_spk:
                if first_spk.user_id:
                    return first_spk.user_id
                if first_spk.device_id:
                    return first_spk.device_id

            with self.get_session() as session:
                sess = session.execute(select(TuyaSharingSession)).scalars().first()
                if sess and sess.user_id:
                    return sess.user_id
                first_u = session.execute(select(User)).scalars().first()
                if first_u and first_u.user_id:
                    return first_u.user_id
            return "default_user"

        clean_id = str(identifier).strip()

        # 1. Tra cứu trực tiếp theo MAC hoặc Device ID phần cứng của Loa
        spk = self.get_speaker(clean_id)
        if spk and spk.user_id:
            return spk.user_id

        # 2. Kiểm tra xem clean_id có tồn tại trong bảng users không
        with self.get_session() as session:
            u = session.get(User, clean_id)
            if u:
                return u.user_id

            # 3. Tra cứu theo quan hệ speaker nếu clean_id khớp bất kỳ trường nào của speaker
            stmt = select(Speaker).where((Speaker.device_id == clean_id) | (Speaker.speaker_mac == clean_id))
            spk_match = session.execute(stmt).scalar_one_or_none()
            if spk_match and spk_match.user_id:
                return spk_match.user_id

            # 4. Fallback: Nếu trong CSDL chỉ có duy nhất 1 User sở hữu phiên ủy quyền Tuya
            active_sessions = session.execute(select(TuyaSharingSession)).scalars().all()
            if len(active_sessions) == 1 and active_sessions[0].user_id:
                return active_sessions[0].user_id

        return clean_id

    # =========================================================================
    # Dynamic Agent Profile Operations (Task 3.1 - Giai đoạn 3)
    # =========================================================================
    def get_agent_profile(self, identifier: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Lấy cấu hình Agent động (prompt, assistant_name, giọng đọc TTS...) theo MAC hoặc Device ID (Task 3.1)."""
        if not identifier:
            return None
        mac, dev_id = extract_mac_and_device_id(identifier)
        target_mac = mac or dev_id or identifier.strip().lower()
        with self.get_session() as session:
            stmt = select(AgentProfile).where(
                (AgentProfile.speaker_mac == target_mac) | (AgentProfile.speaker_mac == identifier)
            )
            profile = session.execute(stmt).scalar_one_or_none()
            if not profile:
                # Nếu chưa cấu hình profile riêng nhưng loa đã đăng ký, lấy default dựa theo speaker
                speaker = self.get_speaker(identifier)
                if speaker:
                    return {
                        "speaker_mac": speaker.speaker_mac,
                        "user_id": speaker.user_id,
                        "assistant_name": "default",
                        "prompt": None,
                        "tts_voice_id": "default",
                        "llm_model_profile": "default",
                        "enabled_plugins": None,
                        "updated_at": speaker.created_at.isoformat() if hasattr(speaker.created_at, "isoformat") else str(speaker.created_at),
                    }
                return None

            plugins_data = None
            if profile.enabled_plugins:
                try:
                    plugins_data = json.loads(profile.enabled_plugins)
                except Exception:
                    plugins_data = profile.enabled_plugins

            return {
                "speaker_mac": profile.speaker_mac,
                "user_id": profile.user_id,
                "assistant_name": profile.assistant_name,
                "prompt": profile.prompt,
                "tts_voice_id": profile.tts_voice_id,
                "llm_model_profile": profile.llm_model_profile,
                "enabled_plugins": plugins_data,
                "updated_at": profile.updated_at.isoformat() if hasattr(profile.updated_at, "isoformat") else str(profile.updated_at),
            }

    def upsert_agent_profile(
        self,
        speaker_mac: str,
        user_id: Optional[str] = None,
        assistant_name: Optional[str] = None,
        prompt: Optional[str] = None,
        tts_voice_id: Optional[str] = None,
        llm_model_profile: Optional[str] = None,
        enabled_plugins: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Cập nhật hoặc tạo mới hồ sơ Agent cá nhân hóa cho từng thiết bị Loa (Task 3.1)."""
        mac, _ = extract_mac_and_device_id(speaker_mac)
        target_mac = mac or speaker_mac.strip().lower()

        # Đảm bảo speaker đã tồn tại, nếu chưa có thì tạo theo target_mac
        speaker = self.get_speaker(target_mac)
        final_user_id = user_id or (speaker.user_id if speaker else None) or "default_user"
        if not speaker:
            self.upsert_speaker(speaker_mac=target_mac, user_id=final_user_id)

        plugins_str = None
        if enabled_plugins is not None:
            if isinstance(enabled_plugins, (dict, list)):
                plugins_str = json.dumps(enabled_plugins, ensure_ascii=False)
            else:
                plugins_str = str(enabled_plugins)

        with self.get_session() as session:
            stmt = select(AgentProfile).where(AgentProfile.speaker_mac == target_mac)
            profile = session.execute(stmt).scalar_one_or_none()
            if not profile:
                profile = AgentProfile(
                    speaker_mac=target_mac,
                    user_id=final_user_id,
                    assistant_name=assistant_name or "default",
                    prompt=prompt,
                    tts_voice_id=tts_voice_id or "default",
                    llm_model_profile=llm_model_profile or "default",
                    enabled_plugins=plugins_str,
                    updated_at=datetime.utcnow(),
                )
                session.add(profile)
            else:
                if user_id:
                    profile.user_id = user_id
                if assistant_name is not None:
                    profile.assistant_name = assistant_name
                if prompt is not None:
                    profile.prompt = prompt
                if tts_voice_id is not None:
                    profile.tts_voice_id = tts_voice_id
                if llm_model_profile is not None:
                    profile.llm_model_profile = llm_model_profile
                if plugins_str is not None:
                    profile.enabled_plugins = plugins_str
                profile.updated_at = datetime.utcnow()
            session.commit()
            session.refresh(profile)

            return {
                "speaker_mac": profile.speaker_mac,
                "user_id": profile.user_id,
                "assistant_name": profile.assistant_name,
                "prompt": profile.prompt,
                "tts_voice_id": profile.tts_voice_id,
                "llm_model_profile": profile.llm_model_profile,
                "enabled_plugins": profile.enabled_plugins,
                "updated_at": profile.updated_at.isoformat() if hasattr(profile.updated_at, "isoformat") else str(profile.updated_at),
            }

    # =========================================================================
    # Tuya Project Token Operations (grant_type=1)
    # =========================================================================

    def save_project_token(
        self,
        client_id: str,
        access_token: str,
        refresh_token: str,
        expire_at: datetime,
    ) -> None:
        """Lưu Project-level Token (grant_type=1) với mã hóa AES-256-GCM."""
        enc_access = vault.encrypt(access_token)
        enc_refresh = vault.encrypt(refresh_token)

        with self.get_session() as session:
            token_obj = session.get(TuyaProjectToken, client_id)
            if not token_obj:
                token_obj = TuyaProjectToken(
                    client_id=client_id,
                    access_token_encrypted=enc_access,
                    refresh_token_encrypted=enc_refresh,
                    expire_at=expire_at,
                    updated_at=datetime.utcnow(),
                )
                session.add(token_obj)
            else:
                token_obj.access_token_encrypted = enc_access
                token_obj.refresh_token_encrypted = enc_refresh
                token_obj.expire_at = expire_at
                token_obj.updated_at = datetime.utcnow()
            session.commit()

    def get_project_token(self, client_id: str) -> Optional[Dict[str, Any]]:
        """Lấy và giải mã Project-level Token."""
        with self.get_session() as session:
            token_obj = session.get(TuyaProjectToken, client_id)
            if not token_obj:
                return None

            return {
                "client_id": token_obj.client_id,
                "access_token": vault.decrypt(token_obj.access_token_encrypted),
                "refresh_token": vault.decrypt(token_obj.refresh_token_encrypted),
                "expire_at": token_obj.expire_at,
                "updated_at": token_obj.updated_at,
            }

    # =========================================================================
    # Tuya User Credential Operations (grant_type=2)
    # =========================================================================

    def save_user_credential(
        self,
        user_id: str,
        external_tuya_uid: str,
        access_token: str,
        refresh_token: str,
        expire_at: datetime,
        auth_source: str = "oauth2",
    ) -> None:
        """Lưu User-level OAuth Token (grant_type=2) đã mã hóa AES-256-GCM."""
        self.upsert_user(user_id)
        enc_access = vault.encrypt(access_token)
        enc_refresh = vault.encrypt(refresh_token)

        with self.get_session() as session:
            stmt = select(TuyaUserCredential).where(TuyaUserCredential.user_id == user_id)
            cred = session.execute(stmt).scalar_one_or_none()
            if not cred:
                cred = TuyaUserCredential(
                    user_id=user_id,
                    external_tuya_uid=external_tuya_uid,
                    access_token_encrypted=enc_access,
                    refresh_token_encrypted=enc_refresh,
                    expire_at=expire_at,
                    auth_source=auth_source,
                    updated_at=datetime.utcnow(),
                )
                session.add(cred)
            else:
                cred.external_tuya_uid = external_tuya_uid
                cred.access_token_encrypted = enc_access
                cred.refresh_token_encrypted = enc_refresh
                cred.expire_at = expire_at
                cred.auth_source = auth_source
                cred.updated_at = datetime.utcnow()
            session.commit()

    def get_user_credential(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Lấy và giải mã User-level OAuth Token."""
        with self.get_session() as session:
            stmt = select(TuyaUserCredential).where(TuyaUserCredential.user_id == user_id)
            cred = session.execute(stmt).scalar_one_or_none()
            if not cred:
                return None

            return {
                "user_id": cred.user_id,
                "external_tuya_uid": cred.external_tuya_uid,
                "access_token": vault.decrypt(cred.access_token_encrypted),
                "refresh_token": vault.decrypt(cred.refresh_token_encrypted),
                "expire_at": cred.expire_at,
                "auth_source": cred.auth_source,
                "updated_at": cred.updated_at,
            }

    def save_sharing_session(
        self,
        user_id: str,
        user_code: str,
        terminal_id: str,
        endpoint: str,
        tuya_uid: Optional[str],
        session_data: Dict[str, Any],
    ) -> None:
        """Lưu phiên ủy quyền Tuya Sharing Gateway đã mã hóa vào CSDL."""
        self.upsert_user(user_id)
        raw_json = json.dumps(session_data, ensure_ascii=False)
        enc_data = vault.encrypt(raw_json)

        with self.get_session() as session:
            stmt = select(TuyaSharingSession).where(TuyaSharingSession.user_id == user_id)
            sess = session.execute(stmt).scalar_one_or_none()
            if not sess:
                sess = TuyaSharingSession(
                    user_id=user_id,
                    user_code=user_code,
                    terminal_id=terminal_id,
                    endpoint=endpoint,
                    tuya_uid=tuya_uid,
                    session_data_encrypted=enc_data,
                    updated_at=datetime.utcnow(),
                )
                session.add(sess)
            else:
                sess.user_code = user_code
                sess.terminal_id = terminal_id
                sess.endpoint = endpoint
                sess.tuya_uid = tuya_uid
                sess.session_data_encrypted = enc_data
                sess.updated_at = datetime.utcnow()
            session.commit()

    def get_sharing_session(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Lấy phiên ủy quyền Tuya Sharing Gateway của một user (tự động phân giải thực thể)."""
        target_uid = self.resolve_user_id(user_id)
        with self.get_session() as session:
            stmt = select(TuyaSharingSession).where(TuyaSharingSession.user_id == target_uid)
            sess = session.execute(stmt).scalar_one_or_none()
            if not sess and target_uid != user_id:
                stmt = select(TuyaSharingSession).where(TuyaSharingSession.user_id == user_id)
                sess = session.execute(stmt).scalar_one_or_none()

            if not sess:
                all_sessions = session.execute(select(TuyaSharingSession)).scalars().all()
                if len(all_sessions) == 1:
                    sess = all_sessions[0]

            if not sess:
                return None

            raw_json = vault.decrypt(sess.session_data_encrypted)
            data = json.loads(raw_json) if raw_json else {}
            return {
                "user_id": sess.user_id,
                "user_code": sess.user_code,
                "terminal_id": sess.terminal_id,
                "endpoint": sess.endpoint,
                "tuya_uid": sess.tuya_uid,
                "session_data": data,
                "updated_at": sess.updated_at,
            }

    def list_all_sharing_sessions(self) -> List[Dict[str, Any]]:
        """Lấy toàn bộ các phiên Tuya Sharing Gateway đang lưu để khôi phục khi server khởi động."""
        with self.get_session() as session:
            stmt = select(TuyaSharingSession)
            rows = session.execute(stmt).scalars().all()
            res = []
            for sess in rows:
                raw_json = vault.decrypt(sess.session_data_encrypted)
                data = json.loads(raw_json) if raw_json else {}
                res.append({
                    "user_id": sess.user_id,
                    "user_code": sess.user_code,
                    "terminal_id": sess.terminal_id,
                    "endpoint": sess.endpoint,
                    "tuya_uid": sess.tuya_uid,
                    "session_data": data,
                    "updated_at": sess.updated_at,
                })
            return res

    # =========================================================================
    # Device Cache Operations
    # =========================================================================

    def upsert_device(
        self,
        device_id: str,
        user_id: str,
        device_name: str,
        category: str,
        platform_type: int = PlatformType.TUYA_OEM_ESUNHOUSE,
        local_key: Optional[str] = None,
        local_ip: Optional[str] = None,
        raw_schema: Optional[Any] = None,
        product_id: Optional[str] = None,
        tuya_home_id: Optional[str] = None,
        is_online: bool = True,
    ) -> None:
        """Lưu hoặc cập nhật thông tin thiết bị vào bộ nhớ đệm (Device Cache).

        Tự động mã hóa `local_key` bằng AES-256-GCM.
        """
        self.upsert_user(user_id)
        enc_local_key = vault.encrypt(local_key) if local_key else None

        raw_schema_str = None
        if raw_schema is not None:
            if isinstance(raw_schema, (dict, list)):
                raw_schema_str = json.dumps(raw_schema, ensure_ascii=False)
            else:
                raw_schema_str = str(raw_schema)

        with self.get_session() as session:
            device = session.get(DeviceCache, device_id)
            if not device:
                device = DeviceCache(
                    device_id=device_id,
                    user_id=user_id,
                    tuya_home_id=tuya_home_id,
                    product_id=product_id,
                    device_name=device_name,
                    category=category,
                    platform_type=platform_type,
                    local_key_encrypted=enc_local_key,
                    local_ip=local_ip,
                    is_online=is_online,
                    raw_schema=raw_schema_str,
                    updated_at=datetime.utcnow(),
                )
                session.add(device)
            else:
                device.user_id = user_id
                device.device_name = device_name
                device.category = category
                device.platform_type = platform_type
                if enc_local_key is not None:
                    device.local_key_encrypted = enc_local_key
                if local_ip is not None:
                    device.local_ip = local_ip
                if raw_schema_str is not None:
                    device.raw_schema = raw_schema_str
                if product_id is not None:
                    device.product_id = product_id
                if tuya_home_id is not None:
                    device.tuya_home_id = tuya_home_id
                device.is_online = is_online
                device.updated_at = datetime.utcnow()
            session.commit()

    def get_device(self, device_id: str) -> Optional[Dict[str, Any]]:
        """Lấy thông tin thiết bị từ cache và giải mã local_key."""
        with self.get_session() as session:
            device = session.get(DeviceCache, device_id)
            if not device:
                return None

            local_key = vault.decrypt(device.local_key_encrypted) if device.local_key_encrypted else None
            schema_obj = None
            if device.raw_schema:
                try:
                    schema_obj = json.loads(device.raw_schema)
                except Exception:
                    schema_obj = device.raw_schema

            return {
                "device_id": device.device_id,
                "user_id": device.user_id,
                "tuya_home_id": device.tuya_home_id,
                "product_id": device.product_id,
                "device_name": device.device_name,
                "category": device.category,
                "platform_type": device.platform_type,
                "local_key": local_key,
                "local_ip": device.local_ip,
                "is_online": device.is_online,
                "raw_schema": schema_obj,
                "updated_at": device.updated_at,
            }

    def delete_device(self, device_id: str) -> bool:
        """Xóa một thiết bị khỏi DeviceCache.

        Args:
            device_id: Mã định danh thiết bị cần xóa.

        Returns:
            bool: True nếu đã xóa thành công, False nếu không tìm thấy thiết bị.
        """
        with self.get_session() as session:
            device = session.get(DeviceCache, device_id)
            if device:
                session.delete(device)
                session.commit()
                return True
            return False

    def purge_devices(self, device_ids: List[str]) -> int:
        """Xóa hàng loạt thiết bị khỏi DeviceCache theo danh sách device_id.

        Args:
            device_ids: Danh sách các device_id cần xóa.

        Returns:
            int: Số lượng thiết bị đã xóa.
        """
        if not device_ids:
            return 0
        with self.get_session() as session:
            stmt = delete(DeviceCache).where(DeviceCache.device_id.in_(device_ids))
            res = session.execute(stmt)
            session.commit()
            return res.rowcount or 0

    def get_user_devices(
        self,
        user_id: str,
        platform_type: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Lấy danh sách thiết bị của một người dùng, tự động phân giải qua quan hệ Loa/Chủ sở hữu."""
        target_uid = self.resolve_user_id(user_id)
        with self.get_session() as session:
            stmt = select(DeviceCache).where(DeviceCache.user_id == target_uid)
            if platform_type is not None:
                stmt = stmt.where(DeviceCache.platform_type == platform_type)

            devices = session.execute(stmt).scalars().all()
            if not devices and target_uid != user_id:
                stmt = select(DeviceCache).where(DeviceCache.user_id == user_id)
                if platform_type is not None:
                    stmt = stmt.where(DeviceCache.platform_type == platform_type)
                devices = session.execute(stmt).scalars().all()

            if not devices:
                all_devices = session.execute(select(DeviceCache)).scalars().all()
                unique_users = {d.user_id for d in all_devices}
                if len(unique_users) == 1:
                    devices = all_devices
            result = []
            for d in devices:
                local_key = vault.decrypt(d.local_key_encrypted) if d.local_key_encrypted else None
                schema_obj = None
                if d.raw_schema:
                    try:
                        schema_obj = json.loads(d.raw_schema)
                    except Exception:
                        schema_obj = d.raw_schema

                result.append({
                    "device_id": d.device_id,
                    "user_id": d.user_id,
                    "tuya_home_id": d.tuya_home_id,
                    "product_id": d.product_id,
                    "device_name": d.device_name,
                    "category": d.category,
                    "platform_type": d.platform_type,
                    "local_key": local_key,
                    "local_ip": d.local_ip,
                    "is_online": d.is_online,
                    "raw_schema": schema_obj,
                    "updated_at": d.updated_at,
                })
            return result

    list_devices_by_user = get_user_devices

    # =========================================================================
    # Home Assistant Credential Operations (Phase 3)
    # =========================================================================

    def save_ha_credential(
        self,
        user_id: str,
        token: str,
        endpoint_url: str = "http://homeassistant.local:8123",
        tunnel_id: Optional[str] = None,
    ) -> HomeAssistantCredential:
        """Lưu hoặc cập nhật thông tin chứng thực Home Assistant Reverse Tunnel."""
        if not tunnel_id:
            import uuid
            tunnel_id = f"tunnel_{uuid.uuid4().hex[:12]}"

        encrypted_token = vault.encrypt(token)
        with self.get_session() as session:
            stmt = select(HomeAssistantCredential).where(HomeAssistantCredential.user_id == user_id)
            cred = session.execute(stmt).scalar_one_or_none()
            if not cred:
                cred = HomeAssistantCredential(
                    user_id=user_id,
                    ha_endpoint_url=endpoint_url,
                    ha_token_encrypted=encrypted_token,
                    tunnel_id=tunnel_id,
                    is_online=False,
                    updated_at=datetime.utcnow(),
                )
                session.add(cred)
            else:
                cred.ha_endpoint_url = endpoint_url
                cred.ha_token_encrypted = encrypted_token
                cred.tunnel_id = tunnel_id
                cred.updated_at = datetime.utcnow()

            session.commit()
            session.refresh(cred)
            return cred

    def get_ha_credential(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Lấy và giải mã thông tin chứng thực Home Assistant."""
        with self.get_session() as session:
            stmt = select(HomeAssistantCredential).where(HomeAssistantCredential.user_id == user_id)
            cred = session.execute(stmt).scalar_one_or_none()
            if not cred:
                return None

            return {
                "id": cred.id,
                "user_id": cred.user_id,
                "ha_endpoint_url": cred.ha_endpoint_url,
                "token": vault.decrypt(cred.ha_token_encrypted),
                "tunnel_id": cred.tunnel_id,
                "is_online": cred.is_online,
                "updated_at": cred.updated_at,
            }

    def verify_ha_bearer_token(self, bearer_token: str) -> Optional[str]:
        """Thẩm định Bearer Token gửi từ HA Client, trả về user_id nếu hợp lệ."""
        if not bearer_token:
            return None

        with self.get_session() as session:
            stmt = select(HomeAssistantCredential)
            all_creds = session.execute(stmt).scalars().all()
            for cred in all_creds:
                try:
                    decrypted_token = vault.decrypt(cred.ha_token_encrypted)
                    if decrypted_token == bearer_token:
                        return cred.user_id
                except Exception:
                    continue
        return None

    def set_ha_online_status(self, user_id: str, is_online: bool):
        """Cập nhật trạng thái trực tuyến của đường hầm Home Assistant."""
        with self.get_session() as session:
            stmt = select(HomeAssistantCredential).where(HomeAssistantCredential.user_id == user_id)
            cred = session.execute(stmt).scalar_one_or_none()
            if cred:
                cred.is_online = is_online
                cred.updated_at = datetime.utcnow()
                session.commit()

    def revoke_ha_credential(self, user_id: str) -> bool:
        """Thu hồi toàn bộ quyền kết nối Home Assistant của user."""
        with self.get_session() as session:
            stmt = select(HomeAssistantCredential).where(HomeAssistantCredential.user_id == user_id)
            cred = session.execute(stmt).scalar_one_or_none()
            if cred:
                session.delete(cred)
                session.commit()
                return True
        return False

    # =========================================================================
    # Pairing Session Operations
    # =========================================================================

    def create_pairing_session(
        self,
        pairing_code: str,
        speaker_mac: str,
        expire_seconds: int = 300,
    ) -> PairingSession:
        """Tạo mã ghép nối ngắn hạn (PIN 4-6 số)."""
        expire_at = datetime.utcnow() + timedelta(seconds=expire_seconds)
        with self.get_session() as session:
            sess = session.get(PairingSession, pairing_code)
            if not sess:
                sess = PairingSession(
                    pairing_code=pairing_code,
                    speaker_mac=speaker_mac,
                    status="pending",
                    expire_at=expire_at,
                    created_at=datetime.utcnow(),
                )
                session.add(sess)
            else:
                sess.speaker_mac = speaker_mac
                sess.status = "pending"
                sess.expire_at = expire_at
            session.commit()
            session.refresh(sess)
            return sess

    def claim_pairing_session(
        self,
        pairing_code: str,
        user_id: Optional[str] = None,
    ) -> Optional[Speaker]:
        """Xác nhận mã ghép nối, liên kết Loa với user_id (mặc định lấy device_id làm user_id nếu để trống)."""
        with self.get_session() as session:
            sess = session.get(PairingSession, pairing_code)
            if not sess or sess.status != "pending" or sess.expire_at < datetime.utcnow():
                return None

            mac, dev_id = extract_mac_and_device_id(sess.speaker_mac)
            final_user_id = (user_id or "").strip() or dev_id

            sess.user_id = final_user_id
            sess.status = "claimed"
            session.commit()

        # Cập nhật bảng speakers
        return self.upsert_speaker(speaker_mac=mac, user_id=final_user_id, device_id=dev_id)

    def get_active_pairing_session(self, speaker_mac: str) -> Optional[PairingSession]:
        """Lấy phiên ghép nối đang chờ (pending) và chưa hết hạn của Loa."""
        if not speaker_mac:
            return None
        mac, dev_id = extract_mac_and_device_id(speaker_mac)
        now = datetime.utcnow()
        with self.get_session() as session:
            stmt = (
                select(PairingSession)
                .where(
                    (PairingSession.speaker_mac == mac)
                    | (PairingSession.speaker_mac == dev_id)
                    | (PairingSession.speaker_mac == speaker_mac),
                    PairingSession.status == "pending",
                    PairingSession.expire_at > now,
                )
                .order_by(PairingSession.created_at.desc())
            )
            return session.execute(stmt).scalars().first()

    def clean_expired_pairing_sessions(self) -> int:
        """Tự động dọn dẹp các session ghép nối đã hết hạn (chuyển status='expired')."""
        now = datetime.utcnow()
        with self.get_session() as session:
            stmt = select(PairingSession).where(
                PairingSession.status == "pending",
                PairingSession.expire_at <= now,
            )
            expired = session.execute(stmt).scalars().all()
            count = len(expired)
            for s in expired:
                s.status = "expired"
            session.commit()
            return count

    # =========================================================================
    # Database Purge & Maintenance Operations
    # =========================================================================

    def delete_sharing_session(self, user_id: str) -> bool:
        """Xóa phiên Tuya Sharing Gateway (QR 1-chạm) của user_id."""
        with self.get_session() as session:
            stmt = select(TuyaSharingSession).where(TuyaSharingSession.user_id == user_id)
            row = session.execute(stmt).scalar_one_or_none()
            if row:
                session.delete(row)
                session.commit()
                return True
            return False

    def delete_user_credential(self, user_id: str) -> bool:
        """Xóa thông tin xác thực Tuya OAuth2 trong TokenVault của user_id."""
        with self.get_session() as session:
            stmt = select(TuyaUserCredential).where(TuyaUserCredential.user_id == user_id)
            row = session.execute(stmt).scalar_one_or_none()
            if row:
                session.delete(row)
                session.commit()
                return True
            return False

    def unlink_tuya_account(self, user_id: str) -> Dict[str, Any]:
        """Hủy liên kết tài khoản Tuya / Smart Life của user: xóa phiên QR, credential OAuth và cache thiết bị."""
        resolved_uid = self.resolve_user_id(user_id)
        with self.get_session() as session:
            sh_count = session.execute(
                delete(TuyaSharingSession).where(TuyaSharingSession.user_id.in_([user_id, resolved_uid]))
            ).rowcount or 0
            cred_count = session.execute(
                delete(TuyaUserCredential).where(TuyaUserCredential.user_id.in_([user_id, resolved_uid]))
            ).rowcount or 0
            dev_count = session.execute(
                delete(DeviceCache).where(DeviceCache.user_id.in_([user_id, resolved_uid]))
            ).rowcount or 0
            session.commit()
            return {
                "user_id": user_id,
                "deleted_sharing_sessions": sh_count,
                "deleted_credentials": cred_count,
                "deleted_devices": dev_count,
            }

    def clean_database(self, keep_speakers: bool = True) -> Dict[str, int]:
        """Làm sạch toàn bộ tàn dư của chế độ test demo trong CSDL (smarthome.db).

        Xóa toàn bộ:
        - DeviceCache (bộ đệm thiết bị cũ)
        - TuyaUserCredential (thông tin xác thực người dùng cũ)
        - TuyaSharingSession (phiên ủy quyền QR cũ)
        - TuyaProjectToken (token dự án cũ)
        - PairingSession (phiên ghép nối cũ)
        """
        with self.get_session() as session:
            d_count = session.execute(delete(DeviceCache)).rowcount or 0
            u_count = session.execute(delete(TuyaUserCredential)).rowcount or 0
            sh_count = session.execute(delete(TuyaSharingSession)).rowcount or 0
            p_count = session.execute(delete(TuyaProjectToken)).rowcount or 0
            s_count = session.execute(delete(PairingSession)).rowcount or 0
            if not keep_speakers:
                session.execute(delete(Speaker))
            session.commit()
            return {
                "deleted_devices": d_count,
                "deleted_user_creds": u_count,
                "deleted_sharing_sessions": sh_count,
                "deleted_project_tokens": p_count,
                "deleted_pairing_sessions": s_count,
            }


# Global instance
dal = SmartHomeDAL()
default_dal = dal

