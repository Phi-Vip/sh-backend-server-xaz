# -*- coding: utf-8 -*-
"""SCRIPT DI TRÚ DỮ LIỆU TỪ SQLITE SANG POSTGRESQL 16 (TASK 1.1)
Dự án: Tái cấu trúc Server XiaoZhi Thương mại v2.1
Chức năng:
1. Đọc dữ liệu từ SQLite `smarthome.db`.
2. Tạo cấu trúc bảng và di trú dữ liệu sang PostgreSQL 16.
3. Đối soát 100% số lượng bản ghi (Row Count) giữa hai cơ sở dữ liệu.
4. Thẩm định toàn vẹn TokenVault: Giải mã thành công 100% bản ghi AES-256-GCM.
"""

import os
import sys
import logging
from typing import Dict, Any, Tuple
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
HUB_ROOT = os.path.dirname(CURRENT_DIR)
SERVER_ROOT = os.path.dirname(HUB_ROOT)

if HUB_ROOT not in sys.path:
    sys.path.insert(0, HUB_ROOT)

from storage.models import (
    Base,
    User,
    Speaker,
    TuyaProjectToken,
    TuyaUserCredential,
    HomeAssistantCredential,
    DeviceCache,
    PairingSession,
    TuyaSharingSession,
)
from storage.token_vault import vault

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("MigrateSqliteToPg")


def run_migration(
    sqlite_url: str,
    pg_url: str,
    verify_token_vault: bool = True,
) -> Dict[str, Any]:
    """Thực hiện di trú toàn bộ dữ liệu từ SQLite sang PostgreSQL.

    Args:
        sqlite_url: URL kết nối SQLite nguồn (vd: sqlite:///.../smarthome.db)
        pg_url: URL kết nối PostgreSQL đích (vd: postgresql://.../xiaozhi_db)
        verify_token_vault: Kiểm tra giải mã AES-256-GCM TokenVault

    Returns:
        Dict chứa thống kê số bản ghi từng bảng, kết quả đối soát và trạng thái.
    """
    logger.info(f"Bắt đầu di trú: {sqlite_url} -> {pg_url}")

    src_engine = create_engine(sqlite_url, connect_args={"check_same_thread": False})
    dst_engine = create_engine(pg_url)

    # 1. Tạo toàn bộ schema trên PostgreSQL đích
    Base.metadata.create_all(dst_engine)

    SrcSession = sessionmaker(bind=src_engine)
    DstSession = sessionmaker(bind=dst_engine)

    models_to_migrate = [
        User,
        Speaker,
        TuyaProjectToken,
        TuyaUserCredential,
        HomeAssistantCredential,
        DeviceCache,
        PairingSession,
        TuyaSharingSession,
    ]

    stats = {}

    with SrcSession() as src_sess, DstSession() as dst_sess:
        for model in models_to_migrate:
            table_name = model.__tablename__
            rows = src_sess.scalars(select(model)).all()
            src_count = len(rows)

            migrated_count = 0
            for row in rows:
                # Merge row vào DB đích
                dst_sess.merge(row)
                migrated_count += 1

            dst_sess.commit()

            # Đối soát lại số lượng trên DB đích
            dst_count = len(dst_sess.scalars(select(model)).all())

            stats[table_name] = {
                "source_count": src_count,
                "target_count": dst_count,
                "match": src_count == dst_count,
            }
            logger.info(
                f"Bảng {table_name:<25}: Source={src_count} -> Target={dst_count} [Match: {src_count == dst_count}]"
            )

        # 2. Kiểm tra giải mã TokenVault AES-256-GCM
        vault_verified = True
        vault_records_checked = 0

        if verify_token_vault:
            # Kiểm tra Tuya User Credentials
            user_creds = dst_sess.scalars(select(TuyaUserCredential)).all()
            for cred in user_creds:
                vault_records_checked += 1
                try:
                    dec_access = vault.decrypt(cred.access_token_encrypted)
                    dec_refresh = vault.decrypt(cred.refresh_token_encrypted)
                    if not dec_access or not dec_refresh:
                        vault_verified = False
                        break
                except Exception as e:
                    logger.error(f"Lỗi giải mã TokenVault cho user {cred.user_id}: {e}")
                    vault_verified = False
                    break

            # Kiểm tra Tuya Project Tokens
            project_tokens = dst_sess.scalars(select(TuyaProjectToken)).all()
            for tok in project_tokens:
                vault_records_checked += 1
                try:
                    dec_access = vault.decrypt(tok.access_token_encrypted)
                    dec_refresh = vault.decrypt(tok.refresh_token_encrypted)
                    if not dec_access or not dec_refresh:
                        vault_verified = False
                        break
                except Exception as e:
                    logger.error(f"Lỗi giải mã TokenVault cho project {tok.client_id}: {e}")
                    vault_verified = False
                    break

        all_matched = all(s["match"] for s in stats.values())
        result = {
            "success": all_matched and vault_verified,
            "all_matched": all_matched,
            "vault_verified": vault_verified,
            "vault_records_checked": vault_records_checked,
            "tables": stats,
        }

        logger.info(
            f"Di trú hoàn tất! Thành công: {result['success']} (Đối soát bảng: {all_matched}, TokenVault: {vault_verified})"
        )
        return result


if __name__ == "__main__":
    from dotenv import load_dotenv

    env_path = os.path.join(SERVER_ROOT, ".env")
    if os.path.exists(env_path):
        load_dotenv(env_path)

    default_sqlite = f"sqlite:///{os.path.abspath(os.path.join(SERVER_ROOT, 'data', 'smarthome.db'))}"
    default_pg = os.getenv("DATABASE_URL", "postgresql://xiaozhi_user:xiaozhi_pass@localhost:6432/xiaozhi_db")

    run_migration(default_sqlite, default_pg)
