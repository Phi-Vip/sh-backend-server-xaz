# -*- coding: utf-8 -*-
"""ROUTER CỔNG QUẢN TRỊ DỰ PHÒNG CHO KỸ SƯ DEV (SMARTHOME DEVELOPER WEB PORTAL)
Phong cách thiết kế UI/UX đồng bộ chuẩn Sunhouse Console:
1. Tông màu sáng hiện đại (Light Mode SaaS: #f8fafc backdrop, #ffffff panels, Sunhouse Blue #1677ff).
2. Thanh điều hướng Top Navigation Bar chuẩn Sunhouse Console (Logo Bot, Nav Tabs, User Profile Initial).
3. Thẻ Loa / Agent Card (Loa Sunhouse) với Avatar chữ 'S', 3 cột thông số (Role, OAuth2, MCP Status).
4. Sử dụng Device ID thực tế nhận từ ESP32 (địa chỉ MAC phần cứng) và User ID linh hoạt.
5. Modal Ghép nối Loa qua PIN 6 số và Cấu hình User ID linh hoạt.
6. Bảng danh mục thiết bị gia dụng CSDL đồng bộ trực quan.
"""

import json
import logging
import os
import time
from datetime import datetime, timedelta
from typing import Optional
from aiohttp import web

from storage.db import SmartHomeDAL, default_dal
from storage.models import extract_mac_and_device_id, Speaker
from storage.token_manager import TuyaTokenManager, token_manager
from clients.tuya_client import TuyaCloudClient

logger = logging.getLogger("PortalRouter")


def create_portal_router(
    dal: SmartHomeDAL = default_dal,
    tuya_client: Optional[TuyaCloudClient] = None,
    token_mgr: Optional[TuyaTokenManager] = None,
):
    """Khởi tạo cụm router phục vụ Developer Web Portal giao diện Sunhouse Console."""

    async def portal_page_handler(request: web.Request) -> web.Response:
        """Endpoint GET /portal - Render giao diện Web Dashboard Sunhouse Console."""
        # 1. Trích xuất Device ID chuẩn phần cứng từ query param hoặc từ Loa đã lưu trong CSDL
        raw_dev_id = request.query.get("device_id")
        speaker = None
        if raw_dev_id:
            mac, device_id = extract_mac_and_device_id(raw_dev_id)
            speaker = dal.get_speaker(mac)
        else:
            speaker = dal.get_first_speaker()
            if speaker:
                device_id = speaker.device_id or speaker.speaker_mac
                mac = speaker.speaker_mac
            else:
                device_id = "Chưa ghép nối"
                mac = ""

        speaker_name = (
            speaker.device_name
            if (speaker and speaker.device_name)
            else (f"Loa Sunhouse ({mac[-5:] if len(mac) >= 5 else 'Agent'})" if mac else "Loa Sunhouse")
        )
        if "xiaozhi" in speaker_name.lower():
            speaker_name = (
                speaker_name.replace("Loa XiaoZhi", "Loa Sunhouse")
                .replace("XiaoZhi", "Sunhouse")
                .replace("xiaozhi", "Sunhouse")
            )
            if speaker:
                dal.upsert_speaker(
                    speaker_mac=speaker.speaker_mac,
                    user_id=speaker.user_id,
                    device_id=speaker.device_id,
                    device_name=speaker_name,
                    home_id=speaker.home_id,
                )
        avatar_char = "S" if "sunhouse" in speaker_name.lower() else ((speaker_name[0] if speaker_name else "S").upper())

        # 2. Xác định User ID: Nếu loa đã gán thì dùng user của loa, nếu chưa thì mặc định = device_id
        req_user_id = request.query.get("user_id")

        if req_user_id:
            user_id = req_user_id.strip()
        elif speaker and speaker.user_id:
            user_id = speaker.user_id
        elif device_id and device_id != "Chưa ghép nối":
            user_id = device_id  # Mặc định User ID trùng với Device ID phần cứng!
        else:
            user_id = dal.resolve_user_id(None)

        is_default_user = (user_id == device_id)
        user_badge_text = "Mặc định (= Device ID) 🔒 Bất biến" if is_default_user else "Tài khoản tùy chỉnh (Gia đình)"

        # 3. Tra cứu Token / Phiên ủy quyền của User (hỗ trợ cả Tuya Sharing QR và OAuth2)
        sharing_sess = dal.get_sharing_session(user_id)
        cred = dal.get_user_credential(user_id)
        has_oauth_token = False
        token_expired = False
        time_left = 7200
        ext_uid = "N/A"
        user_email = ""

        # Ưu tiên 1: Phiên Tuya Sharing Gateway (Mã QR 1-chạm kết nối Smart Life)
        if sharing_sess:
            ext_uid = sharing_sess.get("tuya_uid", "N/A")
            session_data = sharing_sess.get("session_data", {})
            user_email = session_data.get("username", "")
            t_ms = session_data.get("t") or int(time.time() * 1000)
            exp_s = session_data.get("expire_time", 7200)
            exp_at_ms = t_ms + exp_s * 1000
            now_ms = int(time.time() * 1000)
            left_s = int((exp_at_ms - now_ms) / 1000)
            time_left = max(0, left_s)

            if left_s > 0:
                has_oauth_token = True
                token_expired = False
            else:
                # Thử tự động gia hạn token trước khi kết luận expired
                from clients.tuya_sharing_manager import sharing_manager
                refreshed = sharing_manager.check_and_refresh_token(user_id=user_id, dal=dal)
                if refreshed:
                    has_oauth_token = True
                    token_expired = False
                    new_sess = dal.get_sharing_session(user_id)
                    if new_sess:
                        session_data = new_sess.get("session_data", {})
                        t_ms = session_data.get("t", int(time.time() * 1000))
                        exp_s = session_data.get("expire_time", 7200)
                        time_left = max(0, int(((t_ms + exp_s * 1000) - int(time.time() * 1000)) / 1000))
                else:
                    has_oauth_token = False
                    token_expired = True

            # Đồng bộ sang tuya_user_credentials để TokenVault và các fallback luôn có token mới nhất
            if has_oauth_token and session_data.get("access_token"):
                try:
                    exp_at = datetime.utcnow() + timedelta(seconds=time_left)
                    dal.save_user_credential(
                        user_id=user_id,
                        external_tuya_uid=ext_uid,
                        access_token=session_data["access_token"],
                        refresh_token=session_data.get("refresh_token", ""),
                        expire_at=exp_at,
                        auth_source="tuya_sharing_qr",
                    )
                except Exception as e_sync:
                    logger.warning(f"Không thể đồng bộ sharing token vào user_credentials: {e_sync}")

        # Ưu tiên 2: Phiên Tuya OAuth 2.0 (TokenVault chuẩn Cloud Developer)
        elif cred and cred.get("access_token"):
            ext_uid = cred.get("external_tuya_uid", "N/A")
            if cred.get("expire_at"):
                left_s = int((cred["expire_at"] - datetime.utcnow()).total_seconds())
                time_left = max(0, left_s)
                if left_s <= 0:
                    token_expired = True
                    has_oauth_token = False
                else:
                    has_oauth_token = True
            else:
                has_oauth_token = True

        # Cờ tính năng Tuya
        flag_proj_token = os.getenv("TUYA_FEATURE_PROJECT_TOKEN", "true").lower() == "true"
        flag_oauth2_code = os.getenv("TUYA_FEATURE_OAUTH2_CODE", "false").lower() == "true"

        # Định dạng chuỗi trạng thái & màu sắc hiển thị
        if has_oauth_token:
            tuya_status_text = "ĐÃ KẾT NỐI OAUTH2"
            tuya_status_color = "#059669"
            tuya_badge_cls = "active"
            tuya_sub_text = user_email if user_email else f"UID: {ext_uid}"
            tuya_sub_tooltip = f"UID: {ext_uid}" + (f" ({user_email})" if user_email else "")
            banner_status_text = f"ĐÃ KẾT NỐI OAUTH2 (UID: {ext_uid})"
        elif token_expired:
            tuya_status_text = "PHIÊN KẾT NỐI HẾT HẠN"
            tuya_status_color = "#d97706"
            tuya_badge_cls = "warning"
            tuya_sub_text = "Cần quét lại mã QR (Error 1010)"
            tuya_sub_tooltip = "Phiên ủy quyền Tuya đã hết hạn, cần quét lại mã QR để cấp quyền mới."
            banner_status_text = "PHIÊN KẾT NỐI HẾT HẠN (Cần quét lại mã QR)"
        else:
            tuya_status_text = "CHƯA KẾT NỐI TÀI KHOẢN SMART LIFE NGOÀI"
            tuya_status_color = "#64748b"
            tuya_badge_cls = "inactive"
            tuya_sub_text = "Chưa kết nối Smart Life" if not flag_proj_token else "Dùng Project Token"
            tuya_sub_tooltip = "Chưa kết nối tài khoản Smart Life cá nhân."
            banner_status_text = "CHƯA KẾT NỐI TÀI KHOẢN SMART LIFE NGOÀI"

        # 4. Tra cứu danh sách thiết bị Smart Home
        devices = dal.list_devices_by_user(user_id)
        device_rows = ""
        for idx, d in enumerate(devices, 1):
            category = d.get("category", "")
            if category == "dj":
                icon_svg = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 14c.2-1 .7-1.7 1.5-2.5 1-.9 1.5-2.2 1.5-3.5A6 6 0 0 0 6 8c0 1 .2 2.2 1.5 3.5.7.7 1.3 1.5 1.5 2.5"/><path d="M9 18h6M10 22h4"/></svg>'
            elif category in ("fs", "fskg"):
                icon_svg = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M12 9V3M12 21v-6M9 12H3M21 12h-6"/></svg>'
            elif category == "kg":
                icon_svg = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2v10M18.4 6.6a9 9 0 1 1-12.8 0"/></svg>'
            elif category == "sd":
                icon_svg = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="18" height="18" x="3" y="3" rx="2"/><path d="M7 7h.01M17 7h.01M7 17h.01M17 17h.01M12 12h.01"/></svg>'
            else:
                icon_svg = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="20" height="14" x="2" y="5" rx="2"/><line x1="2" y1="10" x2="22" y2="10"/></svg>'

            plat_badge = "Tuya Smart Life" if d.get("platform_type") == 3 else ("Tuya OEM" if d.get("platform_type") == 2 else "Home Assistant")
            online_cls = "badge-online" if d.get("is_online") else "badge-offline"
            online_txt = "Trực tuyến" if d.get("is_online") else "Ngoại tuyến"
            dev_id = d.get('device_id', '')
            device_rows += f"""
            <tr>
                <td class="col-num">{idx}</td>
                <td>
                    <div class="device-cell">
                        <div class="device-icon-box">{icon_svg}</div>
                        <span class="device-name">{d.get('device_name')}</span>
                    </div>
                </td>
                <td>
                    <div class="copy-cell" onclick="copyToClipboard('{dev_id}', this)" title="Bấm để sao chép Device ID">
                        <code class="code-tag">{dev_id}</code>
                        <span class="copy-hint-icon">
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect width="14" height="14" x="8" y="8" rx="2" ry="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/></svg>
                        </span>
                    </div>
                </td>
                <td><span class="badge-plat">{plat_badge}</span></td>
                <td>
                    <span class="{online_cls}">
                        <span class="dot-status"></span>
                        <span>{online_txt}</span>
                    </span>
                </td>
            </tr>
            """

        if not devices:
            device_rows = """
            <tr>
                <td colspan="5" class="empty-table-cell">
                    <div class="empty-table-box">
                        <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" class="empty-icon"><rect width="20" height="14" x="2" y="5" rx="2"/><line x1="2" y1="10" x2="22" y2="10"/></svg>
                        <p class="empty-table-text">Chưa có thiết bị nào trong cơ sở dữ liệu của người dùng này.</p>
                        <span class="empty-table-sub">Bấm "Đồng Bộ Thiết Bị" để nạp danh mục thiết bị từ nền tảng Tuya Cloud.</span>
                    </div>
                </td>
            </tr>
            """

        # 5. Tra cứu danh sách Loa đã liên kết
        with dal.get_session() as s:
            speakers = s.query(Speaker).filter(Speaker.user_id == user_id).all()
            if not speakers and not req_user_id:
                speakers = s.query(Speaker).all()
            speaker_count = len(speakers)

        # TUYỆT ĐỐI KHÔNG tự tạo loa ảo SimpleNamespace khi CSDL không có loa hoặc sau khi hủy liên kết!
        # Khi loa đã bị xóa/hủy liên kết, speaker_count = 0 và giao diện hiển thị trạng thái trống (empty-card).

        # Xây dựng danh sách Card động cho từng Loa của User (Fleet Management)
        speaker_cards_html = ""
        if not speakers:
            speaker_cards_html = """
            <div class="agent-card empty-card" style="grid-column: 1 / -1;">
                <div class="empty-icon-box">
                    <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect width="14" height="20" x="5" y="2" rx="3"/><circle cx="12" cy="14" r="3.5"/><circle cx="12" cy="6" r="1" fill="currentColor"/></svg>
                </div>
                <h4 class="empty-title">Chưa có Loa thông minh nào được liên kết</h4>
                <p class="empty-desc">
                    Hãy cấp nguồn cho Loa Sunhouse (ESP32-S3), quan sát mã PIN 6 số trên màn hình OLED hoặc lắng nghe loa đọc số, sau đó bấm nút bên dưới để ghép nối tức thì.
                </p>
                <button class="btn-primary" onclick="openPinModal()">
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
                    <span>Ghép Nối Loa ESP32 Mới</span>
                </button>
            </div>
            """
        else:
            for spk in speakers:
                s_name = spk.device_name or "Loa Sunhouse"
                s_mac = spk.speaker_mac
                s_dev_id = spk.device_id or s_mac
                s_avatar = "S" if "sunhouse" in s_name.lower() else (s_name[0].upper() if s_name else "S")
                s_user = spk.user_id or user_id
                speaker_cards_html += f"""
                <div class="agent-card" id="speaker-card-{s_mac.replace(':', '')}">
                    <div class="card-header">
                        <div class="card-identity">
                            <div class="card-avatar">
                                <span class="avatar-letter">{s_avatar}</span>
                                <span class="avatar-indicator"></span>
                            </div>
                            <div class="card-meta">
                                <div class="card-title-row">
                                    <h3 class="card-title">{s_name}</h3>
                                    <span class="badge-pill-accent">Loa AI Sunhouse</span>
                                </div>
                                <div class="card-hw-row">
                                    <span class="hw-label">MAC:</span>
                                    <div class="copy-cell" onclick="copyToClipboard('{s_mac}', this)" title="Bấm để sao chép MAC">
                                        <code class="code-tag">{s_mac}</code>
                                        <span class="copy-hint-icon">
                                            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect width="14" height="14" x="8" y="8" rx="2" ry="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/></svg>
                                        </span>
                                    </div>
                                    <span class="status-indicator-live">
                                        <span class="dot-live"></span>
                                        <span>Hoạt động</span>
                                    </span>
                                </div>
                            </div>
                        </div>
                        <div class="card-actions-menu">
                            <button class="btn-icon-subtle" data-mac="{s_mac}" data-name="{s_name}" data-user="{s_user}" onclick="openUserModalForSpeaker(this.dataset.mac, this.dataset.name, this.dataset.user)" title="Cài đặt & Đổi tên Loa" aria-label="Cài đặt Loa">
                                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/><path d="m15 5 4 4"/></svg>
                            </button>
                            <button class="btn-icon-subtle danger" data-mac="{s_mac}" data-name="{s_name}" onclick="handleDeleteSpeakerDirect(this.dataset.mac, this.dataset.name)" title="Hủy liên kết / Xóa Loa" aria-label="Xóa Loa">
                                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/></svg>
                            </button>
                        </div>
                    </div>

                    <!-- 3 CỘT THÔNG SỐ TRONG CARD (CÂN ĐỐI, CÓ DIVIDER, KHÔNG BỊ TRÀN) -->
                    <div class="info-metrics-grid">
                        <div class="metric-item">
                            <span class="metric-label">
                                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
                                <span>Chủ Sở Hữu (User ID)</span>
                            </span>
                            <span class="metric-value" title="{s_user}">{s_user}</span>
                            <span class="metric-sub" title="{user_badge_text}">{user_badge_text}</span>
                        </div>

                        <div class="metric-item">
                            <span class="metric-label">
                                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="18" height="11" x="3" y="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
                                <span>Tuya Smart Life</span>
                            </span>
                            <span class="metric-value" style="color:{tuya_status_color}; font-weight:700;">
                                <span class="dot-status" style="background:{tuya_status_color}; width:6px; height:6px;"></span>
                                <span>{tuya_status_text}</span>
                            </span>
                            <span class="metric-sub" title="{tuya_sub_tooltip}">{tuya_sub_text}</span>
                        </div>

                        <div class="metric-item">
                            <span class="metric-label">
                                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="20" height="8" x="2" y="3" rx="2"/><rect width="20" height="8" x="2" y="13" rx="2"/><circle cx="6" cy="7" r="1" fill="currentColor"/><circle cx="6" cy="17" r="1" fill="currentColor"/></svg>
                                <span>Giao thức Hub</span>
                            </span>
                            <span class="metric-value" style="color:var(--emerald); font-weight:700;">
                                <span class="dot-status" style="background:var(--emerald); width:6px; height:6px;"></span>
                                <span>Port 8005 Active</span>
                            </span>
                            <span class="metric-sub" title="Mã hóa AES-256-GCM TokenVault">Mã hóa AES-256-GCM</span>
                        </div>
                    </div>
                </div>
                """

        html = f"""<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="color-scheme" content="light">
    <title>Sunhouse Console - MCP Smarthome Hub</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {{
            --sunhouse-blue: #005baa;
            --sunhouse-blue-hover: #004885;
            --sunhouse-blue-subtle: #f0f7ff;
            --sunhouse-blue-border: #bfdbfe;
            --navy-slate: #0f172a;
            --navy-slate-soft: #1e293b;
            --text-primary: #0f172a;
            --text-secondary: #475569;
            --text-muted: #94a3b8;
            --bg-body: #f8fafc;
            --bg-card: #ffffff;
            --border-color: #e2e8f0;
            --border-light: #f1f5f9;
            --emerald: #059669;
            --emerald-subtle: #ecfdf5;
            --emerald-border: #a7f3d0;
            --amber: #d97706;
            --amber-subtle: #fffbeb;
            --amber-border: #fde68a;
            --rose: #dc2626;
            --rose-subtle: #fef2f2;
            --rose-border: #fecaca;
            --radius-sm: 6px;
            --radius-md: 10px;
            --radius-lg: 14px;
            --radius-xl: 18px;
            --shadow-xs: 0 1px 2px 0 rgba(15, 23, 42, 0.04);
            --shadow-card: 0 1px 3px 0 rgba(15, 23, 42, 0.05), 0 1px 2px -1px rgba(15, 23, 42, 0.05);
            --shadow-card-hover: 0 10px 15px -3px rgba(15, 23, 42, 0.07), 0 4px 6px -4px rgba(15, 23, 42, 0.03);
            --shadow-modal: 0 25px 50px -12px rgba(15, 23, 42, 0.25);
            --font-sans: 'Plus Jakarta Sans', 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            --font-mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
        }}

        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}

        body {{
            font-family: var(--font-sans);
            background-color: var(--bg-body);
            color: var(--text-primary);
            line-height: 1.5;
            -webkit-font-smoothing: antialiased;
            -moz-osx-font-smoothing: grayscale;
        }}

        /* 1. TOP NAVBAR (Executive Header) */
        .navbar {{
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
            border-bottom: 1px solid var(--border-color);
            height: 64px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 0 32px;
            position: sticky;
            top: 0;
            z-index: 50;
        }}

        .nav-left {{
            display: flex;
            align-items: center;
            gap: 12px;
        }}

        .brand-logo {{
            display: flex;
            align-items: center;
            gap: 10px;
            text-decoration: none;
            color: var(--text-primary);
        }}

        .brand-icon-box {{
            width: 36px;
            height: 36px;
            background: linear-gradient(135deg, #005baa 0%, #0284c7 100%);
            border-radius: 9px;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #ffffff;
            box-shadow: 0 2px 6px rgba(0, 91, 170, 0.25);
        }}

        .brand-name {{
            font-size: 17px;
            font-weight: 700;
            letter-spacing: -0.02em;
            color: var(--navy-slate);
        }}

        .brand-pill {{
            font-size: 11px;
            font-weight: 600;
            color: var(--sunhouse-blue);
            background: var(--sunhouse-blue-subtle);
            border: 1px solid var(--sunhouse-blue-border);
            padding: 2px 8px;
            border-radius: 12px;
            letter-spacing: 0.02em;
        }}

        .nav-tabs {{
            display: flex;
            align-items: center;
            gap: 4px;
            background: #f1f5f9;
            padding: 4px;
            border-radius: 10px;
            border: 1px solid var(--border-color);
        }}

        .nav-tab {{
            padding: 6px 14px;
            border-radius: 7px;
            font-size: 13px;
            font-weight: 500;
            text-decoration: none;
            color: var(--text-secondary);
            transition: all 0.15s ease;
            display: flex;
            align-items: center;
            gap: 7px;
        }}

        .nav-tab:hover {{
            color: var(--text-primary);
        }}

        .nav-tab.active {{
            background: #ffffff;
            color: var(--sunhouse-blue);
            font-weight: 600;
            box-shadow: var(--shadow-xs);
        }}

        .nav-right {{
            display: flex;
            align-items: center;
            gap: 14px;
        }}

        .user-avatar {{
            width: 34px;
            height: 34px;
            border-radius: 50%;
            background: var(--sunhouse-blue-subtle);
            color: var(--sunhouse-blue);
            font-weight: 700;
            font-size: 13px;
            display: flex;
            align-items: center;
            justify-content: center;
            border: 1px solid var(--sunhouse-blue-border);
            cursor: pointer;
            transition: transform 0.15s ease;
        }}

        .user-avatar:hover {{
            transform: scale(1.05);
        }}

        /* 2. MAIN LAYOUT */
        .main-container {{
            max-width: 1160px;
            margin: 0 auto;
            padding: 32px 24px 64px 24px;
        }}

        /* 3. SECTION HEADER */
        .section-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 24px;
            flex-wrap: wrap;
            gap: 16px;
        }}

        .section-title-group {{
            display: flex;
            align-items: center;
            gap: 12px;
        }}

        .section-icon-badge {{
            width: 42px;
            height: 42px;
            background: #ffffff;
            border: 1px solid var(--border-color);
            border-radius: 11px;
            display: flex;
            align-items: center;
            justify-content: center;
            color: var(--sunhouse-blue);
            box-shadow: var(--shadow-xs);
        }}

        .section-title {{
            font-size: 19px;
            font-weight: 700;
            letter-spacing: -0.02em;
            color: var(--navy-slate);
        }}

        .section-count {{
            font-size: 13px;
            color: var(--text-secondary);
            margin-top: 1px;
        }}

        .section-actions {{
            display: flex;
            align-items: center;
            gap: 12px;
        }}

        .search-box {{
            position: relative;
            display: flex;
            align-items: center;
        }}

        .search-input {{
            background: #ffffff;
            border: 1px solid var(--border-color);
            border-radius: var(--radius-md);
            padding: 8px 12px 8px 36px;
            font-size: 13px;
            color: var(--text-primary);
            width: 260px;
            transition: all 0.15s ease;
            outline: none;
            font-family: inherit;
        }}

        .search-input:focus {{
            border-color: var(--sunhouse-blue);
            box-shadow: 0 0 0 3px rgba(0, 91, 170, 0.12);
        }}

        .search-icon {{
            position: absolute;
            left: 12px;
            color: var(--text-muted);
            pointer-events: none;
            display: flex;
            align-items: center;
        }}

        /* BUTTONS */
        .btn-primary {{
            background: var(--sunhouse-blue);
            color: #ffffff;
            border: none;
            padding: 8px 18px;
            border-radius: var(--radius-md);
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
            display: inline-flex;
            align-items: center;
            gap: 7px;
            transition: all 0.15s ease;
            box-shadow: 0 2px 4px rgba(0, 91, 170, 0.2);
            font-family: inherit;
        }}

        .btn-primary:hover {{
            background: var(--sunhouse-blue-hover);
            transform: translateY(-1px);
        }}

        .btn-primary.emerald {{
            background: var(--emerald);
            box-shadow: 0 2px 4px rgba(5, 150, 105, 0.2);
        }}

        .btn-primary.emerald:hover {{
            background: #047857;
        }}

        .btn-outline {{
            background: #ffffff;
            border: 1px solid var(--border-color);
            color: var(--text-secondary);
            padding: 8px 16px;
            border-radius: var(--radius-md);
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
            display: inline-flex;
            align-items: center;
            gap: 7px;
            transition: all 0.15s ease;
            font-family: inherit;
        }}

        .btn-outline:hover {{
            background: var(--bg-body);
            color: var(--navy-slate);
            border-color: #cbd5e1;
        }}

        .btn-outline.danger {{
            color: var(--rose);
            border-color: var(--rose-border);
            background: #ffffff;
        }}

        .btn-outline.danger:hover {{
            background: var(--rose-subtle);
        }}

        .btn-outline.sm, .btn-primary.sm {{
            padding: 6px 12px;
            font-size: 12px;
        }}

        .btn-icon-subtle {{
            background: transparent;
            border: 1px solid transparent;
            color: var(--text-secondary);
            cursor: pointer;
            padding: 6px;
            border-radius: var(--radius-sm);
            display: inline-flex;
            align-items: center;
            justify-content: center;
            transition: all 0.15s ease;
        }}

        .btn-icon-subtle:hover {{
            background: var(--border-light);
            color: var(--text-primary);
            border-color: var(--border-color);
        }}

        .btn-icon-subtle.danger:hover {{
            background: var(--rose-subtle);
            color: var(--rose);
            border-color: var(--rose-border);
        }}

        /* 4. FLEET CARDS GRID */
        .cards-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(480px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}

        @media (max-width: 640px) {{
            .cards-grid {{ grid-template-columns: 1fr; }}
        }}

        .agent-card {{
            background: #ffffff;
            border: 1px solid var(--border-color);
            border-radius: var(--radius-lg);
            padding: 22px;
            box-shadow: var(--shadow-card);
            transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
        }}

        .agent-card:hover {{
            box-shadow: var(--shadow-card-hover);
            border-color: #cbd5e1;
            transform: translateY(-2px);
        }}

        .card-header {{
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
        }}

        .card-identity {{
            display: flex;
            align-items: center;
            gap: 14px;
        }}

        .card-avatar {{
            width: 48px;
            height: 48px;
            border-radius: 12px;
            background: linear-gradient(135deg, #005baa 0%, #0284c7 100%);
            color: #ffffff;
            font-weight: 800;
            font-size: 20px;
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: 0 4px 10px rgba(0, 91, 170, 0.2);
            position: relative;
        }}

        .card-meta {{
            display: flex;
            flex-direction: column;
            gap: 3px;
        }}

        .card-title-row {{
            display: flex;
            align-items: center;
            gap: 8px;
        }}

        .card-title {{
            font-size: 16px;
            font-weight: 700;
            color: var(--navy-slate);
        }}

        .badge-pill-accent {{
            font-size: 11px;
            font-weight: 600;
            color: var(--sunhouse-blue);
            background: var(--sunhouse-blue-subtle);
            border: 1px solid var(--sunhouse-blue-border);
            padding: 1px 8px;
            border-radius: 10px;
        }}

        .card-hw-row {{
            font-size: 12px;
            color: var(--text-secondary);
            display: flex;
            align-items: center;
            gap: 8px;
        }}

        .hw-label {{
            font-weight: 500;
            color: var(--text-muted);
        }}

        .copy-cell {{
            display: inline-flex;
            align-items: center;
            gap: 5px;
            cursor: pointer;
            padding: 2px 6px;
            border-radius: 5px;
            transition: background 0.15s ease;
        }}

        .copy-cell:hover {{
            background: var(--border-light);
        }}

        .code-tag {{
            background: #f1f5f9;
            color: var(--navy-slate-soft);
            padding: 2px 6px;
            border-radius: 4px;
            font-family: var(--font-mono);
            font-size: 11.5px;
            font-weight: 500;
        }}

        .copy-hint-icon {{
            color: var(--text-muted);
            display: inline-flex;
        }}

        .status-indicator-live {{
            display: inline-flex;
            align-items: center;
            gap: 5px;
            font-size: 11px;
            color: var(--emerald);
            font-weight: 600;
        }}

        .dot-live {{
            width: 7px;
            height: 7px;
            border-radius: 50%;
            background: var(--emerald);
            box-shadow: 0 0 0 2px rgba(5, 150, 105, 0.2);
            animation: pulseDot 2s infinite ease-in-out;
        }}

        @keyframes pulseDot {{
            0%, 100% {{ transform: scale(1); opacity: 1; }}
            50% {{ transform: scale(1.2); opacity: 0.7; }}
        }}

        .card-actions-menu {{
            display: flex;
            align-items: center;
            gap: 4px;
        }}

        /* 3-COLUMN METRICS GRID WITH DIVIDERS & SAFE TRUNCATION */
        .info-metrics-grid {{
            background: var(--bg-body);
            border: 1px solid var(--border-color);
            border-radius: var(--radius-md);
            padding: 14px 16px;
            margin-top: 16px;
            display: grid;
            grid-template-columns: 1fr 1.3fr 1fr;
            gap: 14px;
            align-items: start;
        }}

        @media (max-width: 600px) {{
            .info-metrics-grid {{
                grid-template-columns: 1fr;
                gap: 12px;
            }}
            .metric-item:not(:last-child) {{
                border-right: none !important;
                border-bottom: 1px solid var(--border-color);
                padding-right: 0 !important;
                padding-bottom: 10px;
            }}
        }}

        .metric-item {{
            min-width: 0;
            display: flex;
            flex-direction: column;
            gap: 4px;
        }}

        .metric-item:not(:last-child) {{
            border-right: 1px solid var(--border-color);
            padding-right: 14px;
        }}

        .metric-label {{
            font-size: 11.5px;
            color: var(--text-secondary);
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 6px;
            min-width: 0;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}

        .metric-value {{
            font-size: 13px;
            font-weight: 700;
            color: var(--navy-slate);
            min-width: 0;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            display: flex;
            align-items: center;
            gap: 6px;
        }}

        .metric-sub {{
            font-size: 11px;
            color: var(--text-muted);
            min-width: 0;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            line-height: 1.3;
        }}

        /* EMPTY CARD */
        .empty-card {{
            text-align: center;
            padding: 44px 20px;
            background: #ffffff;
            border: 2px dashed #cbd5e1;
            border-radius: var(--radius-lg);
        }}

        .empty-icon-box {{
            width: 56px;
            height: 56px;
            background: var(--sunhouse-blue-subtle);
            color: var(--sunhouse-blue);
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0 auto 14px auto;
        }}

        .empty-title {{
            font-size: 16px;
            font-weight: 700;
            color: var(--navy-slate);
            margin-bottom: 6px;
        }}

        .empty-desc {{
            font-size: 13px;
            color: var(--text-secondary);
            max-width: 480px;
            margin: 0 auto 18px auto;
            line-height: 1.5;
        }}

        /* 5. INTEGRATION BANNER (Enterprise Card) */
        .integration-banner {{
            background: #ffffff;
            border: 1px solid var(--border-color);
            border-radius: var(--radius-lg);
            padding: 24px 28px;
            margin-bottom: 30px;
            box-shadow: var(--shadow-card);
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 20px;
        }}

        .integration-main {{
            max-width: 680px;
        }}

        .integration-header {{
            display: flex;
            align-items: flex-start;
            gap: 14px;
        }}

        .integration-icon-badge {{
            width: 40px;
            height: 40px;
            background: var(--sunhouse-blue-subtle);
            color: var(--sunhouse-blue);
            border: 1px solid var(--sunhouse-blue-border);
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            flex-shrink: 0;
            margin-top: 2px;
        }}

        .integration-title-row {{
            display: flex;
            align-items: center;
            gap: 10px;
            flex-wrap: wrap;
            margin-bottom: 6px;
        }}

        .integration-title {{
            font-size: 16px;
            font-weight: 700;
            color: var(--navy-slate);
        }}

        .integration-desc {{
            font-size: 13px;
            color: var(--text-secondary);
            line-height: 1.5;
            margin-bottom: 10px;
        }}

        .integration-flags {{
            display: flex;
            align-items: center;
            gap: 8px;
            flex-wrap: wrap;
        }}

        .flag-chip {{
            font-size: 11px;
            font-weight: 600;
            padding: 2px 9px;
            border-radius: 6px;
            background: var(--bg-body);
            color: var(--text-secondary);
            border: 1px solid var(--border-color);
        }}

        .flag-chip.active {{
            background: var(--emerald-subtle);
            color: var(--emerald);
            border-color: var(--emerald-border);
        }}

        .flag-chip.inactive {{
            background: var(--rose-subtle);
            color: var(--rose);
            border-color: var(--rose-border);
        }}

        .integration-actions {{
            display: flex;
            align-items: center;
            gap: 10px;
            flex-wrap: wrap;
        }}

        .status-badge-pill {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 3px 10px;
            border-radius: 20px;
            font-size: 11.5px;
            font-weight: 600;
        }}

        .status-badge-pill.active {{
            background: var(--emerald-subtle);
            color: var(--emerald);
            border: 1px solid var(--emerald-border);
        }}

        .status-badge-pill.warning {{
            background: var(--amber-subtle);
            color: var(--amber);
            border: 1px solid var(--amber-border);
        }}

        .status-badge-pill.inactive {{
            background: var(--border-light);
            color: var(--text-secondary);
            border: 1px solid var(--border-color);
        }}

        .dot-status {{
            width: 7px;
            height: 7px;
            border-radius: 50%;
            background: currentColor;
        }}

        /* 6. DATA TABLE PANEL */
        .table-panel {{
            background: #ffffff;
            border: 1px solid var(--border-color);
            border-radius: var(--radius-lg);
            padding: 24px;
            box-shadow: var(--shadow-card);
        }}

        .panel-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 18px;
            flex-wrap: wrap;
            gap: 12px;
        }}

        .panel-title-row {{
            display: flex;
            align-items: center;
            gap: 8px;
        }}

        .panel-icon-badge {{
            color: var(--sunhouse-blue);
            display: flex;
            align-items: center;
        }}

        .panel-title {{
            font-size: 16px;
            font-weight: 700;
            color: var(--navy-slate);
        }}

        .panel-sub {{
            font-size: 12.5px;
            color: var(--text-secondary);
            margin-top: 2px;
        }}

        .table-responsive {{
            overflow-x: auto;
            border: 1px solid var(--border-color);
            border-radius: var(--radius-md);
        }}

        .data-table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
            text-align: left;
        }}

        .data-table th {{
            background: var(--bg-body);
            color: var(--text-secondary);
            font-weight: 600;
            padding: 12px 16px;
            border-bottom: 1px solid var(--border-color);
            font-size: 11.5px;
            text-transform: uppercase;
            letter-spacing: 0.03em;
        }}

        .data-table td {{
            padding: 13px 16px;
            border-bottom: 1px solid var(--border-light);
            vertical-align: middle;
        }}

        .data-table tr:last-child td {{
            border-bottom: none;
        }}

        .data-table tr:hover td {{
            background: #fafcff;
        }}

        .col-num {{
            color: var(--text-muted);
            font-weight: 500;
        }}

        .device-cell {{
            display: flex;
            align-items: center;
            gap: 10px;
        }}

        .device-icon-box {{
            width: 32px;
            height: 32px;
            background: var(--border-light);
            border-radius: 7px;
            display: flex;
            align-items: center;
            justify-content: center;
            color: var(--navy-slate-soft);
            flex-shrink: 0;
        }}

        .device-name {{
            font-weight: 600;
            color: var(--navy-slate);
        }}

        .badge-plat {{
            background: var(--sunhouse-blue-subtle);
            color: var(--sunhouse-blue);
            padding: 3px 9px;
            border-radius: 6px;
            font-size: 11.5px;
            font-weight: 600;
            border: 1px solid var(--sunhouse-blue-border);
        }}

        .badge-online {{
            color: var(--emerald);
            font-weight: 600;
            display: inline-flex;
            align-items: center;
            gap: 6px;
            font-size: 12px;
        }}

        .badge-offline {{
            color: var(--text-muted);
            font-weight: 500;
            display: inline-flex;
            align-items: center;
            gap: 6px;
            font-size: 12px;
        }}

        .empty-table-cell {{
            text-align: center;
            padding: 48px 20px;
        }}

        .empty-table-box {{
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 6px;
        }}

        .empty-table-box .empty-icon {{
            color: var(--text-muted);
            margin-bottom: 4px;
        }}

        .empty-table-text {{
            font-weight: 600;
            color: var(--navy-slate-soft);
            font-size: 14px;
        }}

        .empty-table-sub {{
            font-size: 12px;
            color: var(--text-muted);
        }}

        /* 7. MODERN WEB GUIDANCE: NATIVE <dialog> MODALS */
        dialog:modal {{
            border: 1px solid var(--border-color);
            border-radius: var(--radius-xl);
            box-shadow: var(--shadow-modal);
            padding: 0;
            background: #ffffff;
            width: calc(100% - 32px);
            max-width: 480px;
            outline: none;
            overscroll-behavior: contain;
            margin: auto;
        }}

        dialog::backdrop {{
            background: rgba(15, 23, 42, 0.45);
            backdrop-filter: blur(8px);
            -webkit-backdrop-filter: blur(8px);
            overflow: hidden;
            overscroll-behavior: contain;
        }}

        .dialog-content {{
            padding: 24px;
        }}

        .dialog-header {{
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-bottom: 18px;
        }}

        .dialog-header-left {{
            display: flex;
            align-items: flex-start;
            gap: 12px;
        }}

        .dialog-icon-badge {{
            width: 38px;
            height: 38px;
            background: var(--sunhouse-blue-subtle);
            color: var(--sunhouse-blue);
            border: 1px solid var(--sunhouse-blue-border);
            border-radius: 9px;
            display: flex;
            align-items: center;
            justify-content: center;
            flex-shrink: 0;
        }}

        .dialog-icon-badge.emerald {{
            background: var(--emerald-subtle);
            color: var(--emerald);
            border-color: var(--emerald-border);
        }}

        .dialog-title {{
            font-size: 17px;
            font-weight: 700;
            color: var(--navy-slate);
        }}

        .dialog-subtitle {{
            font-size: 12.5px;
            color: var(--text-secondary);
            margin-top: 2px;
            line-height: 1.4;
        }}

        .btn-dialog-close {{
            background: transparent;
            border: none;
            color: var(--text-muted);
            cursor: pointer;
            padding: 4px;
            border-radius: 6px;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: all 0.15s ease;
        }}

        .btn-dialog-close:hover {{
            background: var(--border-light);
            color: var(--navy-slate);
        }}

        .form-group {{
            margin-bottom: 16px;
        }}

        .form-group.center {{
            text-align: center;
        }}

        .form-label {{
            display: block;
            font-size: 12px;
            font-weight: 600;
            color: var(--navy-slate-soft);
            margin-bottom: 6px;
        }}

        .form-label.center {{
            letter-spacing: 0.04em;
        }}

        .form-input {{
            width: 100%;
            background: #ffffff;
            border: 1px solid var(--border-color);
            padding: 10px 14px;
            border-radius: var(--radius-md);
            font-size: 13.5px;
            color: var(--text-primary);
            outline: none;
            transition: all 0.15s ease;
            font-family: inherit;
        }}

        .form-input:focus {{
            border-color: var(--sunhouse-blue);
            box-shadow: 0 0 0 3px rgba(0, 91, 170, 0.12);
        }}

        .form-input.readonly {{
            background: #f8fafc;
            color: var(--text-secondary);
            font-family: var(--font-mono);
            font-size: 12.5px;
        }}

        .form-hint {{
            font-size: 11px;
            color: var(--text-muted);
            margin-top: 4px;
        }}

        .form-tip {{
            font-size: 11.5px;
            color: var(--text-secondary);
            margin-top: 6px;
        }}

        .form-tip kbd {{
            background: #f1f5f9;
            padding: 2px 6px;
            border-radius: 4px;
            border: 1px solid #cbd5e1;
            font-family: var(--font-mono);
            font-size: 11px;
        }}

        .dialog-footer {{
            display: flex;
            justify-content: flex-end;
            gap: 10px;
            margin-top: 22px;
        }}

        .dialog-footer.between {{
            justify-content: space-between;
            align-items: center;
        }}

        .dialog-footer-actions {{
            display: flex;
            gap: 8px;
        }}

        /* OTP 6-DIGIT GRID */
        .otp-grid {{
            display: flex;
            gap: 8px;
            justify-content: center;
            margin: 16px 0;
        }}

        .otp-digit {{
            width: 48px;
            height: 56px;
            font-size: 24px;
            font-weight: 700;
            text-align: center;
            color: var(--sunhouse-blue);
            background: var(--bg-body);
            border: 2px solid var(--border-color);
            border-radius: var(--radius-md);
            outline: none;
            transition: all 0.15s ease;
            font-family: inherit;
        }}

        .otp-digit:focus {{
            border-color: var(--sunhouse-blue);
            background: #ffffff;
            box-shadow: 0 0 0 4px rgba(0, 91, 170, 0.12);
            transform: translateY(-2px);
        }}

        .otp-digit.filled {{
            border-color: var(--sunhouse-blue);
            background: var(--sunhouse-blue-subtle);
        }}

        .otp-digit.shake {{
            animation: otpShake 0.4s ease-in-out;
            border-color: var(--rose);
        }}

        @keyframes otpShake {{
            0%, 100% {{ transform: translateX(0); }}
            20%, 60% {{ transform: translateX(-5px); }}
            40%, 80% {{ transform: translateX(5px); }}
        }}

        /* DANGER ZONE */
        .danger-zone {{
            margin-top: 20px;
            padding-top: 16px;
            border-top: 1px dashed var(--rose-border);
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 12px;
        }}

        .danger-zone-text {{
            display: flex;
            flex-direction: column;
            gap: 2px;
        }}

        .danger-title {{
            font-size: 13px;
            font-weight: 700;
            color: var(--rose);
        }}

        .danger-desc {{
            font-size: 11px;
            color: var(--text-secondary);
        }}

        /* QR CODE GUIDE & CONTAINER */
        .qr-guide-box {{
            background: var(--bg-body);
            border: 1px solid var(--border-color);
            border-radius: var(--radius-md);
            padding: 14px 16px;
            margin-bottom: 16px;
            font-size: 12.5px;
            color: var(--navy-slate-soft);
            line-height: 1.5;
            display: flex;
            flex-direction: column;
            gap: 6px;
        }}

        .guide-step {{
            display: flex;
            align-items: flex-start;
            gap: 8px;
        }}

        .step-num {{
            width: 18px;
            height: 18px;
            border-radius: 50%;
            background: var(--sunhouse-blue);
            color: #ffffff;
            font-size: 10.5px;
            font-weight: 700;
            display: flex;
            align-items: center;
            justify-content: center;
            flex-shrink: 0;
            margin-top: 2px;
        }}

        .input-with-button {{
            display: flex;
            gap: 8px;
        }}

        .input-with-button .form-input {{
            flex: 1;
        }}

        .qr-result-container {{
            text-align: center;
            margin: 16px 0;
        }}

        .qr-frame {{
            background: #ffffff;
            border: 2px dashed var(--emerald-border);
            border-radius: var(--radius-lg);
            padding: 16px;
            display: inline-block;
            box-shadow: 0 4px 12px rgba(5, 150, 105, 0.08);
            margin-bottom: 12px;
        }}

        .qr-frame img {{
            width: 200px;
            height: 200px;
            display: block;
            margin: 0 auto;
        }}

        .qr-timer-badge {{
            font-size: 12.5px;
            font-weight: 600;
            color: var(--emerald);
            margin-bottom: 8px;
        }}

        .qr-status-pill {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            background: var(--amber-subtle);
            color: var(--amber);
            font-size: 12px;
            font-weight: 600;
            padding: 5px 14px;
            border-radius: 20px;
            border: 1px solid var(--amber-border);
        }}

        /* TOAST NOTIFICATION */
        .toast-container {{
            position: fixed;
            top: 24px;
            right: 24px;
            z-index: 99999;
            display: flex;
            flex-direction: column;
            gap: 10px;
            pointer-events: none;
        }}

        .toast-item {{
            pointer-events: auto;
            display: flex;
            align-items: center;
            gap: 12px;
            min-width: 300px;
            max-width: 440px;
            padding: 12px 16px;
            border-radius: var(--radius-md);
            background: #ffffff;
            box-shadow: 0 10px 25px -5px rgba(15, 23, 42, 0.15), 0 8px 10px -6px rgba(15, 23, 42, 0.05);
            border: 1px solid var(--border-color);
            border-left: 4px solid var(--sunhouse-blue);
            font-size: 13px;
            color: var(--navy-slate);
            transform: translateX(120%);
            opacity: 0;
            transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
        }}

        .toast-item.show {{
            transform: translateX(0);
            opacity: 1;
        }}

        .toast-item.success {{ border-left-color: var(--emerald); }}
        .toast-item.error {{ border-left-color: var(--rose); }}
        .toast-item.warning {{ border-left-color: var(--amber); }}
        .toast-item.info {{ border-left-color: var(--sunhouse-blue); }}

        .toast-icon {{ display: flex; align-items: center; flex-shrink: 0; }}
        .toast-content {{ flex: 1; }}
        .toast-title {{ font-weight: 700; font-size: 13.5px; color: var(--navy-slate); }}
        .toast-desc {{ color: var(--text-secondary); font-size: 12px; line-height: 1.4; margin-top: 1px; }}

        .toast-close {{
            background: none;
            border: none;
            color: var(--text-muted);
            cursor: pointer;
            padding: 2px;
            display: flex;
            align-items: center;
        }}

        .toast-close:hover {{ color: var(--navy-slate); }}

        .spinner-sm {{
            width: 15px;
            height: 15px;
            border: 2px solid rgba(255, 255, 255, 0.4);
            border-top-color: #ffffff;
            border-radius: 50%;
            animation: spin 0.7s linear infinite;
            display: inline-block;
        }}

        @keyframes spin {{
            to {{ transform: rotate(360deg); }}
        }}
    </style>
</head>
<body>

    <!-- 1. TOP NAVBAR (Sunhouse Console Style) -->
    <header class="navbar">
        <div class="nav-left">
            <a href="/portal" class="brand-logo">
                <div class="brand-icon-box">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>
                </div>
                <span class="brand-name">Sunhouse Console</span>
            </a>
            <span class="brand-pill">Sunhouse SmartHome MCP Hub</span>
        </div>

        <nav class="nav-tabs">
            <a href="/portal?user_id={user_id}{f'&device_id={device_id}' if (device_id and device_id != 'Chưa ghép nối' and speaker) else ''}" class="nav-tab active">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="14" height="20" x="5" y="2" rx="3"/><circle cx="12" cy="14" r="3.5"/><circle cx="12" cy="6" r="1" fill="currentColor"/></svg>
                <span>Agents</span>
            </a>
            <a href="javascript:void(0)" onclick="alert('Tính năng Voice Clone sẽ hỗ trợ trong phiên bản tiếp theo!')" class="nav-tab">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2v20M17 5v14M22 9v6M7 5v14M2 9v6"/></svg>
                <span>Voice Clone</span>
            </a>
            <a href="javascript:void(0)" onclick="alert('Knowledge Base RAG cho tài liệu hướng dẫn Sunhouse!')" class="nav-tab">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1-2.5-2.5Z"/><path d="M6 6h10M6 10h10"/></svg>
                <span>Knowledge Base</span>
            </a>
            <a href="javascript:void(0)" onclick="window.open('/health', '_blank')" class="nav-tab">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>
                <span>Firmware / Health</span>
            </a>
        </nav>

        <div class="nav-right">
            <div class="user-avatar" title="Tài khoản: {user_id}" onclick="openUserModal()">
                {avatar_char}
            </div>
        </div>
    </header>

    <!-- 2. MAIN CONTAINER -->
    <main class="main-container">

        <!-- SECTION SUB-HEADER -->
        <div class="section-header">
            <div class="section-title-group">
                <div class="section-icon-badge">
                    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="14" height="20" x="5" y="2" rx="3"/><circle cx="12" cy="14" r="3.5"/><circle cx="12" cy="6" r="1" fill="currentColor"/></svg>
                </div>
                <div>
                    <h2 class="section-title">Agents & Loa Thông Minh</h2>
                    <div class="section-count">{speaker_count} agent / thiết bị đang kích hoạt</div>
                </div>
            </div>

            <div class="section-actions">
                <div class="search-box">
                    <span class="search-icon">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
                    </span>
                    <input type="text" class="search-input" id="agentSearchInput" placeholder="Tìm kiếm loa hoặc thiết bị..." onkeyup="filterAgentsAndDevices()" />
                </div>
                <button class="btn-primary" onclick="openPinModal()">
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
                    <span>Ghép Nối Loa ESP32</span>
                </button>
            </div>
        </div>

        <!-- DANH SÁCH LOA THÔNG MINH (DYNAMIC FLEET CARDS) -->
        <div class="cards-grid" id="speakersGrid">
            {speaker_cards_html}
        </div>

        <!-- BANNER THÔNG BÁO TRẠNG THÁI TASK 2 OAUTH 2.0 -->
        <div class="integration-banner">
            <div class="integration-main">
                <div class="integration-header">
                    <div class="integration-icon-badge">
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect width="18" height="11" x="3" y="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
                    </div>
                    <div>
                        <div class="integration-title-row">
                            <h3 class="integration-title">Nền Tảng Tuya Smart Life (OAuth 2.0 & Sharing QR)</h3>
                            <span class="status-badge-pill {tuya_badge_cls}">
                                <span class="dot-status"></span>
                                {banner_status_text}
                            </span>
                        </div>
                        <p class="integration-desc">
                            <strong>TASK 2: Luồng Tuya OAuth 2.0</strong> - Luồng xác thực chuẩn quốc tế (Google Home / Alexa). Token được mã hóa bảo mật <strong>AES-256-GCM</strong> trong TokenVault và tự động tiêm ngữ cảnh danh mục thiết bị vào LLM System Prompt của Loa Sunhouse khi tiếp nhận lệnh giọng nói.
                        </p>
                        <div class="integration-flags">
                            <span class="flag-chip {'active' if flag_oauth2_code else 'inactive'}">
                                OAuth 2.0: {'Bật' if flag_oauth2_code else 'Tắt'}
                            </span>
                            <span class="flag-chip {'active' if not flag_proj_token else 'inactive'}">
                                Project Token Fallback: {'Bật' if flag_proj_token else 'Đã Tắt (Bảo Mật)'}
                            </span>
                            {f'<span class="flag-chip active">Tài khoản: {user_email}</span>' if user_email else ''}
                        </div>
                    </div>
                </div>
            </div>
            <div class="integration-actions">
                <button class="btn-primary emerald" onclick="openQrModal()" title="Liên kết tài khoản Smart Life bằng cách quét mã QR chuẩn 1-chạm">
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect width="5" height="5" x="3" y="3" rx="1"/><rect width="5" height="5" x="16" y="3" rx="1"/><rect width="5" height="5" x="3" y="16" rx="1"/><path d="M21 16h-3a2 2 0 0 0-2 2v3"/><path d="M21 21v.01"/><path d="M12 7v3a2 2 0 0 1-2 2H7"/><path d="M3 12h.01"/><path d="M12 3h.01"/><path d="M12 16v.01"/><path d="M16 12h1"/><path d="M21 12v.01"/><path d="M12 21v-1"/></svg>
                    <span>Quét Mã QR Smart Life (1-Chạm)</span>
                </button>
                <button class="btn-outline" onclick="syncDevices()">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/></svg>
                    <span>Đồng Bộ Thiết Bị</span>
                </button>
                <button class="btn-outline danger" onclick="handleUnlinkTuya()" title="Hủy liên kết tài khoản Smart Life khỏi Loa Sunhouse">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18.36 6.64a9 9 0 1 1-12.73 0"/><line x1="12" y1="2" x2="12" y2="12"/></svg>
                    <span>🔌 Hủy Liên Kết Smart Life</span>
                </button>
            </div>
        </div>

        <!-- BẢNG DANH MỤC THIẾT BỊ GIA DỤNG TRONG CSDL -->
        <div class="table-panel">
            <div class="panel-header">
                <div>
                    <div class="panel-title-row">
                        <div class="panel-icon-badge">
                            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect width="18" height="18" x="3" y="3" rx="2"/><path d="M3 9h18M9 21V9"/></svg>
                        </div>
                        <h3 class="panel-title">Danh Sách Thiết Bị Nhà Thông Minh Trong CSDL</h3>
                    </div>
                    <p class="panel-sub">Dữ liệu được nạp tự động vào LLM Context của Loa Sunhouse để xử lý lệnh điều khiển bằng giọng nói.</p>
                </div>
                <button class="btn-outline" onclick="syncDevices()">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/></svg>
                    <span>Làm mới danh sách</span>
                </button>
            </div>

            <div class="table-responsive">
                <table class="data-table" id="devicesTable">
                    <thead>
                        <tr>
                            <th style="width: 44px;">#</th>
                            <th>Tên Thiết Bị</th>
                            <th>Mã Device ID</th>
                            <th>Nền Tảng Liên Kết</th>
                            <th style="width: 140px;">Trạng Thái</th>
                        </tr>
                    </thead>
                    <tbody>
                        {device_rows}
                    </tbody>
                </table>
            </div>
        </div>

    </main>

    <!-- DIALOG 1: GHÉP NỐI LOA QUA CỤM 6 Ô OTP (MODERN WEB GUIDANCE) -->
    <dialog id="pinModal" aria-labelledby="pinModalTitle">
        <div class="dialog-content">
            <div class="dialog-header">
                <div class="dialog-header-left">
                    <div class="dialog-icon-badge">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="14" height="20" x="5" y="2" rx="3"/><circle cx="12" cy="14" r="3.5"/><circle cx="12" cy="6" r="1" fill="currentColor"/></svg>
                    </div>
                    <div>
                        <h3 class="dialog-title" id="pinModalTitle">Ghép Nối Loa ESP32 Mới</h3>
                        <p class="dialog-subtitle">Nhập mã PIN 6 số hiển thị trên màn hình OLED hoặc lắng nghe loa đọc số.</p>
                    </div>
                </div>
                <button type="button" class="btn-dialog-close" onclick="closeModals()" aria-label="Đóng dialog">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                </button>
            </div>
            
            <form onsubmit="handleClaimPinModal(event)">
                <div class="form-group center">
                    <label class="form-label center">MÃ XÁC THỰC 6 CHỮ SỐ</label>
                    <div class="otp-grid" id="otpGrid">
                        <input type="text" class="otp-digit" maxlength="1" data-index="0" inputmode="numeric" autocomplete="one-time-code" />
                        <input type="text" class="otp-digit" maxlength="1" data-index="1" inputmode="numeric" autocomplete="off" />
                        <input type="text" class="otp-digit" maxlength="1" data-index="2" inputmode="numeric" autocomplete="off" />
                        <input type="text" class="otp-digit" maxlength="1" data-index="3" inputmode="numeric" autocomplete="off" />
                        <input type="text" class="otp-digit" maxlength="1" data-index="4" inputmode="numeric" autocomplete="off" />
                        <input type="text" class="otp-digit" maxlength="1" data-index="5" inputmode="numeric" autocomplete="off" />
                    </div>
                    <input type="hidden" id="modalPinInput" value="" />
                    <p class="form-tip">Hỗ trợ dán trực tiếp: Nhấn <kbd>Ctrl + V</kbd> khi đang chọn ô bất kỳ.</p>
                </div>

                <div class="form-group">
                    <label class="form-label" for="modalPinUserInput">Tài khoản sở hữu (User ID):</label>
                    <input type="text" id="modalPinUserInput" class="form-input" value="{user_id}" placeholder="{device_id}" />
                    <p class="form-hint">Mặc định gắn vào tài khoản hiện tại. Có thể nhập User ID gia đình khác.</p>
                </div>

                <div class="dialog-footer">
                    <button type="button" class="btn-outline" onclick="closeModals()">Hủy bỏ</button>
                    <button type="submit" id="btnConfirmPin" class="btn-primary">
                        <span id="btnPinSpinner" class="spinner-sm" style="display:none;"></span>
                        <span id="btnPinText">Xác Nhận Ghép Nối</span>
                    </button>
                </div>
            </form>
        </div>
    </dialog>

    <!-- DIALOG 2: CẤU HÌNH & QUẢN LÝ LOA THÔNG MINH -->
    <dialog id="userModal" aria-labelledby="modalUserTitle">
        <div class="dialog-content">
            <div class="dialog-header">
                <div class="dialog-header-left">
                    <div class="dialog-icon-badge">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/></svg>
                    </div>
                    <div>
                        <h3 class="dialog-title" id="modalUserTitle">Cài Đặt & Đổi Tên Loa</h3>
                        <p class="dialog-subtitle">Quản lý tên nhận diện trong nhà và tài khoản gia đình điều khiển loa.</p>
                    </div>
                </div>
                <button type="button" class="btn-dialog-close" onclick="closeModals()" aria-label="Đóng dialog">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                </button>
            </div>

            <form onsubmit="handleUpdateUserModal(event)">
                <div class="form-group">
                    <label class="form-label" for="modalSpeakerNameInput">Tên Định Danh Thiết Bị:</label>
                    <input type="text" id="modalSpeakerNameInput" class="form-input" value="{speaker_name}" placeholder="Ví dụ: Loa Phòng Khách, Loa Sunhouse S1" required />
                    <p class="form-hint">Tên định danh hiển thị của chiếc loa này trong gia đình.</p>
                </div>

                <div class="form-group">
                    <label class="form-label" for="modalNewUserInput">Chủ Sở Hữu (User ID):</label>
                    <input type="text" id="modalNewUserInput" class="form-input" value="{user_id}" placeholder="Ví dụ: user_phi, sđt hoặc gia_dinh" required />
                    <p class="form-hint">Chủ Sở Hữu (User ID) phân quyền thiết bị. Trạng thái: {user_badge_text}</p>
                </div>

                <div class="form-group">
                    <label class="form-label">Mã Phần Cứng Cố Định (Hardware MAC):</label>
                    <input type="text" id="modalHardwareIdInput" class="form-input readonly" value="{device_id}" readonly />
                </div>

                <div class="dialog-footer">
                    <button type="button" class="btn-outline" onclick="closeModals()">Đóng</button>
                    <button type="submit" id="btnSaveSpeakerInfo" class="btn-primary">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg>
                        <span>Lưu Thay Đổi</span>
                    </button>
                </div>
            </form>

            <!-- DANGER ZONE -->
            <div class="danger-zone">
                <div class="danger-zone-text">
                    <span class="danger-title">Xóa Thiết Bị (Delete Device)</span>
                    <span class="danger-desc">Hủy ghép nối loa khỏi tài khoản và đưa về trạng thái chờ mã PIN.</span>
                </div>
                <button type="button" class="btn-outline danger sm" onclick="handleDeleteSpeaker()">
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/></svg>
                    <span>Xóa Thiết Bị (Delete Device)</span>
                </button>
            </div>
        </div>
    </dialog>

    <!-- DIALOG 3: QUÉT MÃ QR LIÊN KẾT SMART LIFE -->
    <dialog id="tuyaQrModal" aria-labelledby="tuyaQrModalTitle">
        <div class="dialog-content">
            <div class="dialog-header">
                <div class="dialog-header-left">
                    <div class="dialog-icon-badge emerald">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect width="5" height="5" x="3" y="3" rx="1"/><rect width="5" height="5" x="16" y="3" rx="1"/><rect width="5" height="5" x="3" y="16" rx="1"/><path d="M21 16h-3a2 2 0 0 0-2 2v3"/><path d="M21 21v.01"/><path d="M12 7v3a2 2 0 0 1-2 2H7"/></svg>
                    </div>
                    <div>
                        <h3 class="dialog-title" id="tuyaQrModalTitle">Liên Kết Smart Life (Quét QR 1-Chạm)</h3>
                        <p class="dialog-subtitle">Đồng bộ tự động tài khoản người dùng Tuya Smart Life vào Loa Sunhouse.</p>
                    </div>
                </div>
                <button type="button" class="btn-dialog-close" onclick="closeModals()" aria-label="Đóng dialog">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                </button>
            </div>

            <div class="qr-guide-box">
                <div class="guide-step"><span class="step-num">1</span> Mở ứng dụng <strong>Smart Life</strong> trên điện thoại.</div>
                <div class="guide-step"><span class="step-num">2</span> Chọn <strong>Tôi (Me)</strong> &rarr; <strong>Cài đặt (&gear;)</strong> &rarr; <strong>Tài khoản &amp; Bảo mật</strong> &rarr; Sao chép <strong>Mã người dùng (User Code)</strong>.</div>
                <div class="guide-step"><span class="step-num">3</span> Nhập mã vào ô dưới đây, bấm <strong>Tạo Mã QR</strong> và dùng app Smart Life quét xác nhận.</div>
            </div>

            <!-- BƯỚC 1: FORM NHẬP USER CODE -->
            <div id="qrStepInput" class="form-group">
                <label class="form-label" for="modalUserCodeInput">Mã User Code từ App Smart Life:</label>
                <div class="input-with-button">
                    <input type="text" id="modalUserCodeInput" class="form-input" placeholder="Ví dụ: AB12CD hoặc mã 8 ký tự..." />
                    <button type="button" class="btn-primary emerald" onclick="handleGenerateQr()">
                        <span>Tạo Mã QR</span>
                    </button>
                </div>
            </div>

            <!-- BƯỚC 2: HIỂN THỊ MÃ QR CODE & ĐẾM NGƯỢC -->
            <div id="qrStepDisplay" style="display:none;" class="qr-result-container">
                <div class="qr-frame">
                    <img id="qrDisplayImg" src="" alt="Mã QR Tuya Smart Life" />
                </div>
                <div class="qr-timer-badge">
                    <span>Hiệu lực trong: <strong id="qrTimerVal">05:00</strong></span>
                </div>
                <div id="qrStatusBadge" class="qr-status-pill">
                    <span class="dot-status"></span>
                    <span>Đang chờ bạn mở App Smart Life quét mã...</span>
                </div>
            </div>

            <div class="dialog-footer between">
                <button type="button" class="btn-outline" onclick="closeModals()">Đóng</button>
                <div class="dialog-footer-actions">
                    <button type="button" id="btnManualConfirmQr" class="btn-primary emerald sm" onclick="handleManualConfirmQr()" style="display:none;">
                        <span>Tôi Đã Quét Xong</span>
                    </button>
                    <button type="button" id="btnRegenQr" class="btn-outline sm" onclick="handleGenerateQr()" style="display:none;">
                        <span>Tạo Lại Mã</span>
                    </button>
                </div>
            </div>
        </div>
    </dialog>

    <script>
        let CURRENT_DEVICE = "{device_id}";
        let CURRENT_USER = "{user_id}";
        let CURRENT_SPEAKER_NAME = "{speaker_name}";

        let activeTicketId = null;
        let qrPollInterval = null;
        let qrTimerInterval = null;
        let qrRemainingSeconds = 300;

        // SAO CHÉP NHANH VÀO CLIPBOARD
        function copyToClipboard(text, el) {{
            if (!text) return;
            navigator.clipboard.writeText(text).then(() => {{
                showToast("Đã sao chép", text, "info", 2000);
            }}).catch(() => {{
                const ta = document.createElement("textarea");
                ta.value = text;
                document.body.appendChild(ta);
                ta.select();
                document.execCommand("copy");
                document.body.removeChild(ta);
                showToast("Đã sao chép", text, "info", 2000);
            }});
        }}

        // LỌC DANH SÁCH LOA & THIẾT BỊ
        function filterAgentsAndDevices() {{
            const query = (document.getElementById("agentSearchInput")?.value || "").toLowerCase().trim();
            document.querySelectorAll(".agent-card").forEach(card => {{
                const text = card.textContent.toLowerCase();
                card.style.display = text.includes(query) ? "" : "none";
            }});
            document.querySelectorAll("#devicesTable tbody tr").forEach(row => {{
                const text = row.textContent.toLowerCase();
                row.style.display = text.includes(query) ? "" : "none";
            }});
        }}

        // QUẢN LÝ CỤM OTP GRID VÀ TỰ ĐỘNG FOCUS
        function initOtpGrid() {{
            const digits = document.querySelectorAll(".otp-digit");
            const hiddenInput = document.getElementById("modalPinInput");
            if (!digits || digits.length === 0) return;

            digits.forEach((input, idx) => {{
                input.addEventListener("input", (e) => {{
                    const val = e.target.value.replace(/\\D/g, "");
                    if (val) {{
                        e.target.value = val[val.length - 1];
                        e.target.classList.add("filled");
                        e.target.classList.remove("shake");
                        if (idx < 5) {{
                            digits[idx + 1].focus();
                        }}
                    }} else {{
                        e.target.value = "";
                        e.target.classList.remove("filled");
                    }}
                    syncHiddenPin();
                }});

                input.addEventListener("keydown", (e) => {{
                    if (e.key === "Backspace") {{
                        if (!e.target.value && idx > 0) {{
                            digits[idx - 1].focus();
                            digits[idx - 1].value = "";
                            digits[idx - 1].classList.remove("filled");
                            e.preventDefault();
                        }} else {{
                            e.target.value = "";
                            e.target.classList.remove("filled");
                        }}
                        syncHiddenPin();
                    }} else if (e.key === "ArrowLeft" && idx > 0) {{
                        digits[idx - 1].focus();
                    }} else if (e.key === "ArrowRight" && idx < 5) {{
                        digits[idx + 1].focus();
                    }}
                }});

                input.addEventListener("paste", (e) => {{
                    e.preventDefault();
                    const clipData = (e.clipboardData || window.clipboardData).getData("text");
                    const clean = clipData.replace(/\\D/g, "");
                    if (!clean) return;

                    for (let i = 0; i < 6; i++) {{
                        if (i < clean.length) {{
                            digits[i].value = clean[i];
                            digits[i].classList.add("filled");
                            digits[i].classList.remove("shake");
                        }}
                    }}
                    const nextFocus = Math.min(clean.length, 5);
                    digits[nextFocus].focus();
                    syncHiddenPin();
                }});
            }});

            function syncHiddenPin() {{
                let full = "";
                digits.forEach(d => full += d.value);
                if (hiddenInput) hiddenInput.value = full;
            }}
        }}

        // TOAST NOTIFICATION HỆ THỐNG
        function showToast(title, message, type = "success", duration = 3500) {{
            const container = document.getElementById("toastContainer");
            if (!container) return;
            const icons = {{
                success: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#059669" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>',
                error: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#dc2626" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>',
                info: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#005baa" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>',
                warning: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#d97706" stroke-width="2"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>'
            }};
            const toast = document.createElement("div");
            toast.className = `toast-item ${{type}}`;
            toast.innerHTML = `
                <div class="toast-icon">${{icons[type] || icons.info}}</div>
                <div class="toast-content">
                    <div class="toast-title">${{title}}</div>
                    <div class="toast-desc">${{message}}</div>
                </div>
                <button class="toast-close" onclick="this.parentElement.remove()" aria-label="Đóng thông báo">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                </button>
            `;
            container.appendChild(toast);
            setTimeout(() => toast.classList.add("show"), 10);
            setTimeout(() => {{
                toast.classList.remove("show");
                setTimeout(() => toast.remove(), 300);
            }}, duration);
        }}

        // MODERN WEB GUIDANCE: DIALOG OPEN & CLOSE (SHOWMODAL / CLOSE)
        function closeModals() {{
            ['pinModal', 'userModal', 'tuyaQrModal'].forEach(id => {{
                const d = document.getElementById(id);
                if (d && d.open) d.close();
            }});
            stopQrPolling();
        }}

        function openPinModal() {{
            closeModals();
            const d = document.getElementById("pinModal");
            if (d) {{
                d.showModal();
                const digits = d.querySelectorAll(".otp-digit");
                digits.forEach(el => {{ el.value = ""; el.classList.remove("filled", "shake"); }});
                const hidden = document.getElementById("modalPinInput");
                if (hidden) hidden.value = "";
                if (digits[0]) setTimeout(() => digits[0].focus(), 100);
            }}
        }}

        function openUserModal() {{
            closeModals();
            const d = document.getElementById("userModal");
            if (d) {{
                d.showModal();
                const spkInput = document.getElementById("modalSpeakerNameInput");
                if (spkInput) setTimeout(() => {{ spkInput.focus(); spkInput.select(); }}, 100);
            }}
        }}

        function openQrModal() {{
            closeModals();
            const d = document.getElementById("tuyaQrModal");
            if (d) {{
                d.showModal();
                const input = document.getElementById("modalUserCodeInput");
                if (input) setTimeout(() => input.focus(), 100);
            }}
        }}

        // LIGHT-DISMISS CHO DIALOG: CLICK VÀO BACKDROP THÌ TỰ ĐÓNG
        document.querySelectorAll('dialog').forEach(dialog => {{
            dialog.addEventListener('click', (e) => {{
                const rect = dialog.getBoundingClientRect();
                if (
                    e.clientX < rect.left ||
                    e.clientX > rect.right ||
                    e.clientY < rect.top ||
                    e.clientY > rect.bottom
                ) {{
                    closeModals();
                }}
            }});
        }});

        function stopQrPolling() {{
            if (qrPollInterval) {{
                clearInterval(qrPollInterval);
                qrPollInterval = null;
            }}
            if (qrTimerInterval) {{
                clearInterval(qrTimerInterval);
                qrTimerInterval = null;
            }}
        }}

        async function handleGenerateQr() {{
            const userCode = document.getElementById("modalUserCodeInput").value.trim();
            stopQrPolling();

            try {{
                const res = await fetch("/api/v1/auth/tuya/qr-ticket", {{
                    method: "POST",
                    headers: {{ "Content-Type": "application/json" }},
                    body: JSON.stringify({{ user_id: CURRENT_USER, user_code: userCode }})
                }});
                const data = await res.json();
                if (!res.ok || data.status !== "success") {{
                    showToast("Lỗi tạo vé QR", data.message || "Không thể tạo mã QR", "error");
                    return;
                }}

                activeTicketId = data.ticket_id;
                const qrPayload = encodeURIComponent(data.qr_payload);
                const qrUrl = `https://api.qrserver.com/v1/create-qr-code/?size=220x220&data=${{qrPayload}}`;
                
                document.getElementById("qrDisplayImg").src = qrUrl;
                document.getElementById("qrStepDisplay").style.display = "block";
                document.getElementById("btnManualConfirmQr").style.display = "inline-flex";
                document.getElementById("btnRegenQr").style.display = "inline-flex";

                qrRemainingSeconds = data.expire_seconds || 300;
                updateQrTimerDisplay();
                qrTimerInterval = setInterval(() => {{
                    qrRemainingSeconds--;
                    updateQrTimerDisplay();
                    if (qrRemainingSeconds <= 0) {{
                        stopQrPolling();
                        document.getElementById("qrStatusBadge").innerHTML = "Mã QR đã hết hạn. Vui lòng bấm 'Tạo Lại Mã'.";
                        document.getElementById("qrStatusBadge").style.background = "var(--rose-subtle)";
                        document.getElementById("qrStatusBadge").style.color = "var(--rose)";
                        document.getElementById("qrStatusBadge").style.borderColor = "var(--rose-border)";
                    }}
                }}, 1000);

                qrPollInterval = setInterval(pollQrStatus, 2000);

            }} catch (err) {{
                showToast("Lỗi kết nối", "Không thể kết nối đến máy chủ: " + err, "error");
            }}
        }}

        function updateQrTimerDisplay() {{
            const m = Math.floor(qrRemainingSeconds / 60).toString().padStart(2, '0');
            const s = (qrRemainingSeconds % 60).toString().padStart(2, '0');
            document.getElementById("qrTimerVal").innerText = `${{m}}:${{s}}`;
        }}

        async function pollQrStatus() {{
            if (!activeTicketId) return;
            try {{
                const res = await fetch(`/api/v1/auth/tuya/qr-ticket/${{activeTicketId}}/status`);
                const data = await res.json();
                if (data.status === "confirmed") {{
                    stopQrPolling();
                    document.getElementById("qrStatusBadge").innerHTML = data.message || "Ủy quyền thành công! Đang tải lại...";
                    document.getElementById("qrStatusBadge").style.background = "var(--emerald-subtle)";
                    document.getElementById("qrStatusBadge").style.color = "var(--emerald)";
                    document.getElementById("qrStatusBadge").style.borderColor = "var(--emerald-border)";
                    showToast("Ủy quyền thành công", "Đang nạp lại trang...", "success", 2000);
                    setTimeout(() => {{
                        window.location.reload();
                    }}, 1200);
                }} else if (data.status === "expired") {{
                    stopQrPolling();
                    document.getElementById("qrStatusBadge").innerHTML = "Mã QR đã hết hạn.";
                }}
            }} catch (err) {{
                console.warn("Lỗi poll QR:", err);
            }}
        }}

        async function handleManualConfirmQr() {{
            if (!activeTicketId) return;
            try {{
                const res = await fetch(`/api/v1/auth/tuya/qr-ticket/${{activeTicketId}}/confirm`, {{
                    method: "POST"
                }});
                const data = await res.json();
                if (data.status === "success") {{
                    stopQrPolling();
                    showToast("Đồng bộ thành công", `Đã đồng bộ ${{data.synced_count}} thiết bị!`, "success", 3000);
                    setTimeout(() => window.location.reload(), 1000);
                }} else {{
                    showToast("Đang chờ quét", data.message || "Vui lòng quét và xác nhận trên app Smart Life", "info");
                }}
            }} catch (err) {{
                showToast("Lỗi kết nối", err.message || err, "error");
            }}
        }}

        async function handleUnlinkTuya() {{
            if (!confirm("Bạn có chắc chắn muốn HỦY LIÊN KẾT tài khoản Smart Life khỏi Loa không?\\n\\nSau khi hủy, Loa sẽ ngừng điều khiển các thiết bị thuộc tài khoản này cho đến khi quét mã QR mới.")) {{
                return;
            }}
            try {{
                const res = await fetch("/api/v1/auth/tuya/unlink", {{
                    method: "POST",
                    headers: {{ "Content-Type": "application/json" }},
                    body: JSON.stringify({{ user_id: CURRENT_USER }})
                }});
                const data = await res.json();
                if (res.ok && data.status === "success") {{
                    showToast("Đã hủy liên kết", data.message, "info", 3000);
                    setTimeout(() => window.location.reload(), 1000);
                }} else {{
                    showToast("Lỗi hủy liên kết", data.message || JSON.stringify(data), "error");
                }}
            }} catch (err) {{
                showToast("Lỗi kết nối", "Không thể kết nối đến máy chủ: " + err, "error");
            }}
        }}

        async function handleClaimPinModal(e) {{
            e.preventDefault();
            let pin = "";
            const digits = document.querySelectorAll(".otp-digit");
            digits.forEach(d => pin += d.value.trim());
            const customUser = document.getElementById("modalPinUserInput").value.trim();

            if (!pin || pin.length < 6) {{
                showToast("Chưa nhập đủ mã PIN", "Vui lòng nhập đầy đủ 6 chữ số hiển thị trên Loa!", "warning");
                digits.forEach(d => {{
                    if (!d.value) d.classList.add("shake");
                }});
                for (let d of digits) {{
                    if (!d.value) {{ d.focus(); break; }}
                }}
                return;
            }}

            const btn = document.getElementById("btnConfirmPin");
            const spinner = document.getElementById("btnPinSpinner");
            const btnText = document.getElementById("btnPinText");

            try {{
                if (btn) btn.disabled = true;
                if (spinner) spinner.style.display = "inline-block";
                if (btnText) btnText.textContent = "Đang xác thực...";

                const res = await fetch("/api/v1/pairing/claim-pin", {{
                    method: "POST",
                    headers: {{ "Content-Type": "application/json" }},
                    body: JSON.stringify({{ pairing_code: pin, user_id: customUser || CURRENT_USER }})
                }});
                const data = await res.json();
                if (res.ok && data.status === "success") {{
                    showToast("Ghép nối thành công!", `Đã liên kết Loa [${{data.speaker_mac || data.device_id}}]!`, "success", 4000);
                    closeModals();
                    setTimeout(() => {{
                        window.location.href = `/portal?user_id=${{encodeURIComponent(data.user_id)}}&device_id=${{encodeURIComponent(data.device_id || CURRENT_DEVICE)}}`;
                    }}, 1200);
                }} else {{
                    showToast("Xác thực thất bại", data.message || "Mã PIN không đúng hoặc đã hết hạn!", "error", 4500);
                    digits.forEach(d => d.classList.add("shake"));
                    if (digits[0]) digits[0].focus();
                }}
            }} catch (err) {{
                showToast("Lỗi kết nối", "Không thể kết nối đến máy chủ: " + err, "error");
            }} finally {{
                if (btn) btn.disabled = false;
                if (spinner) spinner.style.display = "none";
                if (btnText) btnText.textContent = "Xác Nhận Ghép Nối";
            }}
        }}

        async function handleDeleteSpeakerDirect(mac, name) {{
            if (!confirm(`CẢNH BÁO: Bạn có chắc chắn muốn HỦY LIÊN KẾT Loa '${{name}}' (${{mac}}) khỏi tài khoản không?\\n\\nLoa sẽ trở về trạng thái chưa kích hoạt và hiển thị lại mã PIN.`)) {{
                return;
            }}

            try {{
                const res = await fetch("/api/v1/pairing/delete-speaker", {{
                    method: "POST",
                    headers: {{ "Content-Type": "application/json" }},
                    body: JSON.stringify({{ speaker_mac: mac }})
                }});
                const data = await res.json();
                if (res.ok && data.status === "success") {{
                    showToast("Đã xóa thiết bị", `Đã hủy liên kết Loa [${{name}}] thành công.`, "info", 3000);
                    const card = document.getElementById(`speaker-card-${{mac.replace(/:/g, '')}}`);
                    if (card) card.remove();
                    setTimeout(() => {{
                        const u = new URL(window.location.href);
                        u.searchParams.delete('device_id');
                        window.location.href = u.pathname + (u.searchParams.toString() ? '?' + u.searchParams.toString() : '');
                    }}, 600);
                }} else {{
                    showToast("Thao tác thất bại", data.message || "Không thể xóa thiết bị.", "error");
                }}
            }} catch (err) {{
                showToast("Lỗi kết nối", "Không thể gửi yêu cầu: " + err, "error");
            }}
        }}

        function openUserModalForSpeaker(mac, name, userId) {{
            const spkInput = document.getElementById("modalSpeakerNameInput");
            const userInput = document.getElementById("modalNewUserInput");
            const hwInput = document.getElementById("modalHardwareIdInput");
            const titleEl = document.getElementById("modalUserTitle");

            if (spkInput) spkInput.value = name || "";
            if (userInput) userInput.value = userId || CURRENT_USER || "";
            if (hwInput) hwInput.value = mac || "";
            if (titleEl) titleEl.innerText = `Cài Đặt & Đổi Tên: ${{name || 'Loa Sunhouse'}}`;

            CURRENT_DEVICE = mac || "";
            CURRENT_SPEAKER_NAME = name || "";
            if (userId) CURRENT_USER = userId;

            openUserModal();
        }}

        async function handleUpdateUserModal(e) {{
            e.preventDefault();
            const spkInput = document.getElementById("modalSpeakerNameInput");
            const userInput = document.getElementById("modalNewUserInput");
            const hwInput = document.getElementById("modalHardwareIdInput");

            const newSpeakerName = spkInput ? spkInput.value.trim() : "";
            const newUserId = userInput ? userInput.value.trim() : "";
            const targetDevice = (hwInput ? hwInput.value.trim() : "") || CURRENT_DEVICE;

            if (!newUserId) {{
                showToast("Dữ liệu không hợp lệ", "Vui lòng nhập Tài khoản sở hữu (User ID)!", "warning");
                if (userInput) userInput.focus();
                return;
            }}
            if (!newSpeakerName) {{
                showToast("Dữ liệu không hợp lệ", "Vui lòng nhập Tên định danh cho Loa!", "warning");
                if (spkInput) spkInput.focus();
                return;
            }}

            const btnSave = document.getElementById("btnSaveSpeakerInfo");
            const origHtml = btnSave ? btnSave.innerHTML : "";
            if (btnSave) {{
                btnSave.disabled = true;
                btnSave.innerHTML = '<span class="spinner-sm"></span> Đang lưu...';
            }}

            try {{
                const res = await fetch("/api/v1/pairing/bind-user", {{
                    method: "POST",
                    headers: {{ "Content-Type": "application/json" }},
                    body: JSON.stringify({{
                        device_id: targetDevice,
                        speaker_mac: targetDevice,
                        user_id: newUserId,
                        device_name: newSpeakerName,
                    }})
                }});
                const data = await res.json();
                if (res.ok && data.status === "success") {{
                    showToast("Cập nhật thành công!", data.message || "Đã lưu tên Loa mới.", "success");
                    closeModals();
                    setTimeout(() => {{
                        window.location.href = `/portal?user_id=${{encodeURIComponent(newUserId)}}&device_id=${{encodeURIComponent(targetDevice)}}`;
                    }}, 800);
                }} else {{
                    showToast("Cập nhật thất bại", data.message || "Không thể cập nhật thông tin Loa", "error");
                }}
            }} catch (err) {{
                showToast("Lỗi kết nối", "Không thể gửi yêu cầu: " + err, "error");
            }} finally {{
                if (btnSave) {{
                    btnSave.disabled = false;
                    btnSave.innerHTML = origHtml;
                }}
            }}
        }}

        async function handleDeleteSpeaker() {{
            const targetMac = CURRENT_DEVICE;
            const targetName = CURRENT_SPEAKER_NAME || "Loa Sunhouse";
            if (!confirm(`CẢNH BÁO: Bạn có chắc chắn muốn XÓA thiết bị Loa '${{targetName}}' (${{targetMac}}) khỏi hệ thống không?\\n\\nToàn bộ phiên ghép nối của Loa sẽ bị xóa bỏ và loa sẽ trở về trạng thái chờ ghép nối lại.`)) {{
                return;
            }}

            try {{
                const res = await fetch("/api/v1/pairing/delete-speaker", {{
                    method: "POST",
                    headers: {{ "Content-Type": "application/json" }},
                    body: JSON.stringify({{ device_id: targetMac, speaker_mac: targetMac }})
                }});
                const data = await res.json();
                if (res.ok && data.status === "success") {{
                    showToast("Xóa thành công", data.message || "Đã xóa Loa khỏi hệ thống.", "success");
                    closeModals();
                    const card = document.getElementById(`speaker-card-${{targetMac.replace(/:/g, '')}}`);
                    if (card) card.remove();
                    setTimeout(() => {{
                        const u = new URL(window.location.href);
                        u.searchParams.delete('device_id');
                        window.location.href = u.pathname + (u.searchParams.toString() ? '?' + u.searchParams.toString() : '');
                    }}, 600);
                }} else {{
                    showToast("Thao tác thất bại", data.message || "Không thể xóa thiết bị.", "error");
                }}
            }} catch (err) {{
                showToast("Lỗi kết nối", "Không thể kết nối đến máy chủ: " + err, "error");
            }}
        }}

        async function syncDevices() {{
            try {{
                const res = await fetch(`/api/v1/devices/sync?user_id=${{encodeURIComponent(CURRENT_USER)}}`);
                const data = await res.json();
                if (data.status === "success") {{
                    showToast("Đồng bộ thành công", `Đã đồng bộ ${{data.synced_count}} thiết bị cho User [${{CURRENT_USER}}]!`, "success", 3000);
                    setTimeout(() => window.location.reload(), 1000);
                }} else {{
                    showToast("Lỗi đồng bộ", JSON.stringify(data), "error");
                }}
            }} catch (err) {{
                showToast("Lỗi kết nối", "Không thể kết nối: " + err, "error");
            }}
        }}

        document.addEventListener('DOMContentLoaded', initOtpGrid);
    </script>

    <!-- TOAST NOTIFICATION CONTAINER -->
    <div id="toastContainer" class="toast-container"></div>
</body>
</html>"""
        return web.Response(text=html, content_type="text/html", charset="utf-8")

    return {
        "portal_page": portal_page_handler,
    }
