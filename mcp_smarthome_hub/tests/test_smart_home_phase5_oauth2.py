# -*- coding: utf-8 -*-
"""KIỂM THỬ TẬP TRUNG TASK 2: LUỒNG OAUTH 2.0 AUTHORIZATION CODE & DEVELOPER WEB PORTAL
Kiểm thử chuyên sâu cho Task 2 của Giai đoạn 5 (SmartHome MCP Hub - Port 8005):
1. Tự động định tuyến Data Center Singapore (auth-sg.tuya.com) cho thiết bị / tài khoản Việt Nam.
2. Trả về HTML thân thiện cho trình duyệt khi Tuya redirect về GET /api/v1/auth/tuya/callback.
3. Hỗ trợ POST /api/v1/auth/tuya/oauth-callback trả JSON cho kiểm thử và API client.
4. Giao diện Developer Web Portal (/portal) hiển thị trực quan thông số, mã PIN và nút kích hoạt 1-chạm.
5. MultiSourceDispatcher ưu tiên sử dụng User Token (grant_type=2) khi điều khiển thiết bị TUYA_EXTERNAL_SMARTLIFE.
"""

from datetime import datetime, timedelta
import time
import os
import sys
import json
import pytest
from unittest.mock import AsyncMock, MagicMock
from contextlib import asynccontextmanager
from aiohttp import web, ClientSession

# Đường dẫn thư mục
SERVER_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HUB_ROOT = os.path.join(SERVER_ROOT, "mcp_smarthome_hub")
if SERVER_ROOT not in sys.path:
    sys.path.insert(0, SERVER_ROOT)
if HUB_ROOT not in sys.path:
    sys.path.insert(0, HUB_ROOT)

from storage.db import SmartHomeDAL
from storage.models import PlatformType
from storage.token_manager import TuyaTokenManager
from routers.pairing_router import create_pairing_router
from routers.tuya_auth_router import create_tuya_auth_router
from routers.portal_router import create_portal_router
from dispatcher.multisource_dispatcher import MultiSourceDispatcher
from dispatcher.context_injector import ContextInjector


@pytest.fixture
def test_dal():
    """Tạo DAL in-memory độc lập cho mỗi test case."""
    return SmartHomeDAL("sqlite:///:memory:")


@pytest.fixture
def mock_tuya_client():
    """Tạo mock TuyaCloudClient mô phỏng phản hồi từ Tuya OpenAPI Singapore."""
    client = MagicMock()
    client.client_id = "tuya_sg_client_id_live_test"
    client.client_secret = "tuya_sg_client_secret_live_test"
    client.base_url = "https://openapi.tuyasg.com"
    client.get_token = AsyncMock(
        return_value={
            "access_token": "tuya_user_token_live_sg_access_999",
            "refresh_token": "tuya_user_token_live_sg_refresh_888",
            "expire_time": 7200,
            "uid": "bay_sg_user_test_phi",
        }
    )
    client.get_user_devices = AsyncMock(return_value=[])
    client.get_associated_user_devices = AsyncMock(return_value=[])
    client.request = AsyncMock(
        return_value={
            "success": True,
            "result": {
                "devices": [
                    {
                        "id": "bf_light_sg_01",
                        "name": "Đèn trần Phòng Khách",
                        "category": "dj",
                        "online": True,
                        "status": [{"code": "switch_led", "value": True}],
                    }
                ]
            },
        }
    )
    return client


@pytest.fixture
def token_mgr():
    """Tạo instance TuyaTokenManager độc lập."""
    return TuyaTokenManager()


@pytest.fixture
def make_ephemeral_server():
    """Khởi tạo aiohttp test server trên cổng ngẫu nhiên."""
    @asynccontextmanager
    async def _make(app):
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        try:
            yield f"http://127.0.0.1:{port}"
        finally:
            await runner.cleanup()

    return _make


def build_app(dal, mock_tuya, token_mgr):
    """Khởi dựng App tích hợp đầy đủ các Router cho Task 2."""
    app = web.Application()

    pairing_router = create_pairing_router(dal=dal)
    app.router.add_post("/api/v1/pairing/generate-pin", pairing_router["generate_pin"])
    app.router.add_post("/api/v1/pairing/claim-pin", pairing_router["claim_pin"])
    app.router.add_post("/api/v1/pairing/bind-user", pairing_router["bind_user"])
    app.router.add_post("/api/v1/pairing/delete-speaker", pairing_router["delete_speaker"])
    app.router.add_delete("/api/v1/pairing/speakers/{speaker_id}", pairing_router["delete_speaker"])

    tuya_auth_router = create_tuya_auth_router(dal=dal, tuya_client=mock_tuya)
    app.router.add_get("/api/v1/auth/tuya/authorize-url", tuya_auth_router["get_authorize_url"])
    app.router.add_post("/api/v1/auth/tuya/oauth-callback", tuya_auth_router["oauth_callback"])
    app.router.add_get("/api/v1/auth/tuya/callback", tuya_auth_router["oauth_callback"])
    app.router.add_post("/api/v1/auth/tuya/link-account", tuya_auth_router["link_account"])
    app.router.add_post("/api/v1/auth/tuya/unlink", tuya_auth_router["unlink_account"])
    app.router.add_post("/api/v1/admin/clean-database", tuya_auth_router["clean_database"])

    portal_router = create_portal_router(dal=dal, tuya_client=mock_tuya, token_mgr=token_mgr)
    app.router.add_get("/portal", portal_router["portal_page"])
    app.router.add_get("/", portal_router["portal_page"])

    return app


@pytest.mark.asyncio
async def test_oauth2_authorize_url_auto_singapore(make_ephemeral_server, test_dal, mock_tuya_client, token_mgr):
    """1. Kiểm tra URL Ủy quyền Tuya tự động trỏ sang Data Center Singapore (auth-sg.tuya.com)."""
    app = build_app(test_dal, mock_tuya_client, token_mgr)

    async with make_ephemeral_server(app) as base_url:
        async with ClientSession() as client:
            user_id = "user_real_phi"
            async with client.get(
                f"{base_url}/api/v1/auth/tuya/authorize-url",
                params={"user_id": user_id},
            ) as resp:
                assert resp.status == 200
                data = await resp.json()
                assert data["status"] == "success"
                auth_url = data["authorize_url"]

                # Kiểm tra định tuyến Singapore
                assert "auth-sg.tuya.com/authorize" in auth_url
                assert f"client_id={mock_tuya_client.client_id}" in auth_url
                assert "response_type=code" in auth_url
                assert f"state={user_id}_" in auth_url
                assert "redirect_uri=" in auth_url


@pytest.mark.asyncio
async def test_oauth2_callback_get_html_browser_redirect(make_ephemeral_server, test_dal, mock_tuya_client, token_mgr):
    """2. Kiểm tra Browser Redirect GET /api/v1/auth/tuya/callback trả về giao diện HTML thẻ thành công."""
    app = build_app(test_dal, mock_tuya_client, token_mgr)

    async with make_ephemeral_server(app) as base_url:
        async with ClientSession() as client:
            user_id = "user_real_phi"
            code = "mock_tuya_auth_code_from_smartlife_browser"
            state = f"{user_id}_abcdef12"

            # Trình duyệt chuyển hướng về sau khi người dùng quét mã / đăng nhập trên Tuya Auth
            async with client.get(
                f"{base_url}/api/v1/auth/tuya/callback",
                params={"code": code, "state": state},
            ) as resp:
                assert resp.status == 200
                assert resp.content_type == "text/html"
                html_text = await resp.text()

                # Xác minh giao diện người dùng
                assert "ỦY QUYỀN THÀNH CÔNG" in html_text
                assert "bay_sg_user_test_phi" in html_text
                assert "AES-256-GCM" in html_text

            # Xác minh dữ liệu Token đã được mã hóa an toàn và lưu vào CSDL
            cred = test_dal.get_user_credential(user_id)
            assert cred is not None
            assert cred["user_id"] == user_id
            assert cred["access_token"] == "tuya_user_token_live_sg_access_999"
            assert cred["refresh_token"] == "tuya_user_token_live_sg_refresh_888"
            assert cred["external_tuya_uid"] == "bay_sg_user_test_phi"


@pytest.mark.asyncio
async def test_oauth2_callback_post_json_api(make_ephemeral_server, test_dal, mock_tuya_client, token_mgr):
    """3. Kiểm tra POST /api/v1/auth/tuya/oauth-callback trả JSON chuẩn API cho automation scripts."""
    app = build_app(test_dal, mock_tuya_client, token_mgr)

    async with make_ephemeral_server(app) as base_url:
        async with ClientSession() as client:
            user_id = "user_dev_engineer"
            code = "tuya_auth_code_direct_post"

            async with client.post(
                f"{base_url}/api/v1/auth/tuya/oauth-callback",
                json={"code": code, "user_id": user_id},
            ) as resp:
                assert resp.status == 200
                data = await resp.json()
                assert data["status"] == "success"
                assert data["user_id"] == user_id
                assert data["external_tuya_uid"] == "bay_sg_user_test_phi"

            # Xác minh lưu vào DAL
            cred = test_dal.get_user_credential(user_id)
            assert cred is not None
            assert cred["access_token"] == "tuya_user_token_live_sg_access_999"


@pytest.mark.asyncio
async def test_developer_web_portal_rendering(make_ephemeral_server, test_dal, mock_tuya_client, token_mgr):
    """4. Kiểm tra trang Developer Web Portal (/portal) hiển thị trực quan các thẻ chức năng."""
    user_id = "user_real_phi"
    # Chuẩn bị trước 1 thiết bị trong cache
    test_dal.upsert_device(
        device_id="bf_fan_sg_02",
        user_id=user_id,
        device_name="Quạt Cây Phòng Khách",
        category="fs",
        platform_type=PlatformType.TUYA_EXTERNAL_SMARTLIFE,
        is_online=True,
    )

    app = build_app(test_dal, mock_tuya_client, token_mgr)

    async with make_ephemeral_server(app) as base_url:
        async with ClientSession() as client:
            # 1. Truy cập /portal khi chưa có token
            async with client.get(f"{base_url}/portal?user_id={user_id}") as resp:
                assert resp.status == 200
                assert resp.content_type == "text/html"
                html_body = await resp.text()

                assert "Sunhouse SmartHome MCP Hub" in html_body
                assert "Sunhouse Console" in html_body
                assert "Ghép Nối Loa ESP32" in html_body
                assert "TASK 2: Luồng Tuya OAuth 2.0" in html_body
                assert "Danh Sách Thiết Bị Nhà Thông Minh Trong CSDL" in html_body
                assert "Quạt Cây Phòng Khách" in html_body
                assert "CHƯA KẾT NỐI TÀI KHOẢN SMART LIFE NGOÀI" in html_body

            # 2. Giả lập người dùng đã OAuth2
            test_dal.save_user_credential(
                user_id=user_id,
                external_tuya_uid="tuya_sg_uid_123",
                access_token="test_access_token_tokenvault",
                refresh_token="test_refresh_token_tokenvault",
                expire_at=datetime.utcnow() + timedelta(seconds=7200),
            )

            # 3. Truy cập lại /portal -> Kiểm tra badge ĐÃ KẾT NỐI OAUTH2
            async with client.get(f"{base_url}/portal?user_id={user_id}") as resp:
                assert resp.status == 200
                html_updated = await resp.text()
                assert "ĐÃ KẾT NỐI OAUTH2" in html_updated
                assert "tuya_sg_uid_123" in html_updated
                assert "AES-256-GCM" in html_updated
                # Các nút thừa và tính năng không khả dụng đã được loại bỏ
                assert "Mở Cổng Ủy Quyền Tuya" not in html_updated
                assert "startOAuthFlow" not in html_updated

            # 4. Kiểm tra khi liên kết qua Tuya Sharing Gateway (QR flow)
            user_qr = "user_qr_test"
            test_dal.save_sharing_session(
                user_id=user_qr,
                user_code="TEST_CODE",
                terminal_id="term_123",
                endpoint="https://apigw-sg.iotbing.com",
                tuya_uid="tuya_sharing_uid_999",
                session_data={"username": "test@smartlife.com"},
            )
            async with client.get(f"{base_url}/portal?user_id={user_qr}") as resp:
                assert resp.status == 200
                html_qr = await resp.text()
                assert "ĐÃ KẾT NỐI OAUTH2" in html_qr
                assert "tuya_sharing_uid_999" in html_qr
                assert "test@smartlife.com" in html_qr


@pytest.mark.asyncio
async def test_multisource_dispatcher_user_token_dispatch(test_dal, mock_tuya_client, token_mgr):
    """5. Kiểm tra MultiSourceDispatcher ưu tiên sử dụng User Token khi điều khiển thiết bị TUYA_EXTERNAL_SMARTLIFE."""
    user_id = "user_real_phi"
    device_id = "tuya_smartlife_switch_01"

    # Đăng ký thông tin thiết bị loại TUYA_EXTERNAL_SMARTLIFE
    test_dal.upsert_device(
        device_id=device_id,
        user_id=user_id,
        device_name="Công tắc Ban Công",
        category="kg",
        platform_type=PlatformType.TUYA_EXTERNAL_SMARTLIFE,
        raw_schema={"functions": [{"code": "switch_1", "type": "Boolean"}]},
        is_online=True,
    )

    # Lưu token người dùng vào CSDL
    test_dal.save_user_credential(
        user_id=user_id,
        external_tuya_uid="uid_tuya_sg_phi",
        access_token="user_oauth2_valid_access_token_abc",
        refresh_token="user_oauth2_valid_refresh_token_xyz",
        expire_at=datetime.utcnow() + timedelta(seconds=7200),
    )

    # Mock Tuya API client gửi lệnh điều khiển thiết bị
    mock_tuya_client.send_device_commands = AsyncMock(return_value=True)

    context_injector = ContextInjector(dal_instance=test_dal)
    dispatcher = MultiSourceDispatcher(
        dal_instance=test_dal,
        tuya_client=mock_tuya_client,
        token_mgr=token_mgr,
        context_injector=context_injector,
    )

    # Kỹ sư/AI phát lệnh bật công tắc
    cmd_result = await dispatcher.dispatch_command(
        user_id=user_id,
        device_query=device_id,
        action="turn_on",
    )

    assert cmd_result["success"] is True
    assert cmd_result["device_id"] == device_id
    assert cmd_result["platform"] == "tuya_ext"

    # Xác minh mock_tuya_client.send_device_commands được gọi với token là User Token
    mock_tuya_client.send_device_commands.assert_called_once()
    call_args, call_kwargs = mock_tuya_client.send_device_commands.call_args
    assert call_kwargs["token"] == "user_oauth2_valid_access_token_abc"


@pytest.mark.asyncio
async def test_default_user_id_matches_device_id_and_rename_flow(make_ephemeral_server, test_dal, mock_tuya_client, token_mgr):
    """6. Kiểm tra User ID mặc định đặt trùng với Device ID và cho phép đổi tên User ID linh hoạt."""
    app = build_app(test_dal, mock_tuya_client, token_mgr)
    from routers import create_pairing_router
    pairing_router = create_pairing_router(dal=test_dal)
    app.router.add_post("/api/v1/pairing/bind-user", pairing_router["bind_user"])

    test_device_id = "00:11:22:33:44:55"

    async with make_ephemeral_server(app) as base_url:
        async with ClientSession() as client:
            # A. Khi truy cập portal với Device ID, User ID mặc định trùng với Device ID
            async with client.get(f"{base_url}/portal?device_id={test_device_id}") as resp:
                assert resp.status == 200
                html = await resp.text()
                assert test_device_id in html
                assert "Mặc định (= Device ID)" in html
                assert "🔒 Bất biến" in html

            # B. Kỹ sư thực hiện đổi tên User ID thành số điện thoại / định danh riêng
            custom_user_id = "0988123456_phi"
            async with client.post(
                f"{base_url}/api/v1/pairing/bind-user",
                json={"device_id": test_device_id, "user_id": custom_user_id},
            ) as bind_resp:
                assert bind_resp.status == 200
                bind_data = await bind_resp.json()
                assert bind_data["status"] == "success"
                assert bind_data["device_id"] == test_device_id
                assert bind_data["user_id"] == custom_user_id

            # C. Truy cập lại portal -> Hiển thị Loa đã liên kết với User ID mới
            async with client.get(f"{base_url}/portal?device_id={test_device_id}") as resp2:
                assert resp2.status == 200
                html2 = await resp2.text()
                assert custom_user_id in html2
                assert "Tài khoản tùy chỉnh" in html2


@pytest.mark.asyncio
async def test_claim_pin_without_user_id_auto_binds_to_device_id(make_ephemeral_server, test_dal, mock_tuya_client, token_mgr):
    """7. Kiểm tra ghép nối mã PIN khi không truyền user_id sẽ tự động lấy User ID = Device ID."""
    app = build_app(test_dal, mock_tuya_client, token_mgr)
    test_device_id = "00:11:22:33:44:55"

    async with make_ephemeral_server(app) as base_url:
        async with ClientSession() as client:
            # 1. Sinh mã PIN cho Loa
            async with client.post(
                f"{base_url}/api/v1/pairing/generate-pin",
                json={"device_id": test_device_id},
            ) as gen_resp:
                assert gen_resp.status == 200
                gen_data = await gen_resp.json()
                pin_code = gen_data["pairing_code"]

            # 2. Xác nhận PIN nhưng không truyền user_id
            async with client.post(
                f"{base_url}/api/v1/pairing/claim-pin",
                json={"pairing_code": pin_code},
            ) as claim_resp:
                assert claim_resp.status == 200
                claim_data = await claim_resp.json()
                assert claim_data["status"] == "success"
                # User ID tự động gán trùng với Device ID
                assert claim_data["user_id"] == test_device_id
                assert claim_data["device_id"] == test_device_id


@pytest.mark.asyncio
async def test_feature_flag_project_token_disabled_blocks_fallback(test_dal, mock_tuya_client, token_mgr, monkeypatch):
    """8. Kiểm tra TUYA_FEATURE_PROJECT_TOKEN=false nghiêm cấm fallback sang Project Token cho thiết bị ngoài."""
    monkeypatch.setenv("TUYA_FEATURE_PROJECT_TOKEN", "false")
    monkeypatch.setenv("TUYA_FEATURE_OAUTH2_CODE", "true")

    user_id = "user_unauthorized_phi"
    device_id = "external_smartlife_bulb_99"

    test_dal.upsert_device(
        device_id=device_id,
        user_id=user_id,
        device_name="Bóng đèn Smart Life",
        category="dj",
        platform_type=PlatformType.TUYA_EXTERNAL_SMARTLIFE,
        is_online=True,
    )

    context_injector = ContextInjector(dal_instance=test_dal)
    dispatcher = MultiSourceDispatcher(
        dal_instance=test_dal,
        tuya_client=mock_tuya_client,
        token_mgr=token_mgr,
        context_injector=context_injector,
    )

    # Chưa có User OAuth Token -> Phải trả về thất bại và từ chối fallback Project Token
    cmd_res = await dispatcher.dispatch_command(
        user_id=user_id,
        device_query=device_id,
        action="turn_on",
    )
    assert cmd_res["success"] is False
    assert "TUYA_FEATURE_PROJECT_TOKEN=false" in cmd_res["message"]
    assert "chưa được cấp quyền OAuth2 User Token" in cmd_res["message"]


@pytest.mark.asyncio
async def test_tuya_link_account_and_clean_database_endpoints(make_ephemeral_server, test_dal, mock_tuya_client, token_mgr):
    """9. Kiểm tra API liên kết tài khoản Smart Life (link-account) và làm sạch CSDL (clean-database)."""
    app = build_app(test_dal, mock_tuya_client, token_mgr)
    user_id = "user_phi_link_test"

    async with make_ephemeral_server(app) as base_url:
        async with ClientSession() as client:
            # 1. Gọi liên kết tài khoản Smart Life
            async with client.post(
                f"{base_url}/api/v1/auth/tuya/link-account",
                json={"user_id": user_id, "tuya_uid": "sg1794473334329NFeph"},
            ) as link_resp:
                assert link_resp.status == 200
                link_data = await link_resp.json()
                assert link_data["status"] == "success"
                assert link_data["external_tuya_uid"] == "sg1794473334329NFeph"
                assert link_data["auth_source"] == "oauth2"

            # Xác minh đã lưu vào DAL
            cred = test_dal.get_user_credential(user_id)
            assert cred is not None
            assert cred["external_tuya_uid"] == "sg1794473334329NFeph"

            # 2. Gọi dọn dẹp sạch CSDL
            async with client.post(f"{base_url}/api/v1/admin/clean-database") as clean_resp:
                assert clean_resp.status == 200
                clean_data = await clean_resp.json()
                assert clean_data["status"] == "success"
                assert "deleted_user_creds" in clean_data["details"]

            # Xác minh credential đã được làm sạch
            cred_after = test_dal.get_user_credential(user_id)
            assert cred_after is None


@pytest.mark.asyncio
async def test_portal_dynamic_speaker_name_and_delete_speaker(make_ephemeral_server, test_dal, mock_tuya_client, token_mgr):
    """10. Kiểm tra thông tin Loa động (không fix cứng Phi-SHT), vai trò User ID và tính năng Delete Device."""
    app = build_app(test_dal, mock_tuya_client, token_mgr)

    # 1. Đăng ký Loa thông minh tùy chỉnh
    test_spk = test_dal.upsert_speaker(
        speaker_mac="11:22:33:44:55:66",
        user_id="user_gia_dinh_01",
        device_name="Loa Thông Minh Phòng Khách",
    )
    assert test_spk.device_name == "Loa Thông Minh Phòng Khách"

    async with make_ephemeral_server(app) as base_url:
        async with ClientSession() as client:
            # 2. Truy cập /portal -> Kiểm tra tên Loa hiển thị động và trường Chủ sở hữu (User ID)
            async with client.get(f"{base_url}/portal?device_id=11:22:33:44:55:66") as resp:
                assert resp.status == 200
                html = await resp.text()

                # Không còn fix cứng "Phi-SHT agent"
                assert "Phi-SHT agent" not in html
                # Hiển thị đúng tên loa động từ CSDL
                assert "Loa Thông Minh Phòng Khách" in html
                # Có nhãn rõ ràng vai trò Chủ Sở Hữu (User ID)
                assert "Chủ Sở Hữu (User ID)" in html
                assert "user_gia_dinh_01" in html
                # Có tính năng Xóa thiết bị (Delete Device)
                assert "Xóa Thiết Bị (Delete Device)" in html
                assert "handleDeleteSpeaker" in html

            # 3. Đổi tên Loa và đổi User ID qua API bind-user
            async with client.post(
                f"{base_url}/api/v1/pairing/bind-user",
                json={
                    "device_id": "11:22:33:44:55:66",
                    "device_name": "Loa Sunhouse S1 VIP",
                    "user_id": "user_phi_moi",
                },
            ) as update_resp:
                assert update_resp.status == 200
                up_data = await update_resp.json()
                assert up_data["status"] == "success"
                assert up_data["device_name"] == "Loa Sunhouse S1 VIP"

            # 4. Kiểm tra CSDL đã cập nhật
            spk_updated = test_dal.get_speaker("11:22:33:44:55:66")
            assert spk_updated.device_name == "Loa Sunhouse S1 VIP"
            assert spk_updated.user_id == "user_phi_moi"

            # 5. Xóa thiết bị Loa (Delete Device)
            async with client.post(
                f"{base_url}/api/v1/pairing/delete-speaker",
                json={"device_id": "11:22:33:44:55:66"},
            ) as del_resp:
                assert del_resp.status == 200
                del_data = await del_resp.json()
                assert del_data["status"] == "success"

            # 6. Kiểm tra Loa đã bị xóa khỏi CSDL
            assert test_dal.get_speaker("11:22:33:44:55:66") is None


@pytest.mark.asyncio
async def test_tuya_token_auto_refresh_and_unlink_flow(make_ephemeral_server, test_dal, mock_tuya_client, token_mgr):
    """11. Kiểm tra cơ chế tự động gia hạn Token, cảnh báo phiên hết hạn và API Hủy liên kết chuẩn thương mại."""
    user_id = "user_test_token_flow"

    # 1. Tạo phiên đăng nhập với token còn hiệu lực
    now_ms = int(time.time() * 1000)
    test_dal.save_sharing_session(
        user_id=user_id,
        user_code="USER_CODE_ACTIVE",
        terminal_id="term_12345",
        endpoint="https://apigw-sg.iotbing.com",
        tuya_uid="tuya_uid_active_99",
        session_data={
            "t": now_ms,
            "expire_time": 7200,
            "access_token": "valid_token_123",
            "refresh_token": "valid_refresh_456",
            "username": "user_active@sunhouse.vn",
        },
    )

    test_dal.upsert_device(
        device_id="dev_fan_test",
        user_id=user_id,
        device_name="Quạt Trần Phòng Ăn",
        category="fs",
        platform_type=PlatformType.TUYA_EXTERNAL_SMARTLIFE,
    )

    app = build_app(test_dal, mock_tuya_client, token_mgr)

    async with make_ephemeral_server(app) as base_url:
        async with ClientSession() as client:
            # A. Kiểm tra khi token còn hạn -> Hiển thị ĐÃ KẾT NỐI OAUTH2
            async with client.get(f"{base_url}/portal?user_id={user_id}") as resp:
                assert resp.status == 200
                html = await resp.text()
                assert "ĐÃ KẾT NỐI OAUTH2" in html
                assert "tuya_uid_active_99" in html
                assert "user_active@sunhouse.vn" in html
                assert "🔌 Hủy Liên Kết Smart Life" in html

            # B. Giả lập Token đã hết hạn (tạo từ 3 tiếng trước, hạn 2 tiếng)
            test_dal.save_sharing_session(
                user_id=user_id,
                user_code="USER_CODE_EXPIRED",
                terminal_id="term_12345",
                endpoint="https://apigw-sg.iotbing.com",
                tuya_uid="tuya_uid_expired_99",
                session_data={
                    "t": now_ms - (3 * 3600 * 1000),  # 3 tiếng trước
                    "expire_time": 7200,             # hạn 2 tiếng -> đã hết hạn
                    "access_token": "expired_token_123",
                    "refresh_token": "expired_refresh_456",
                },
            )

            # C. Truy cập Portal khi token hết hạn -> Hiển thị cảnh báo PHIÊN KẾT NỐI HẾT HẠN
            async with client.get(f"{base_url}/portal?user_id={user_id}") as resp:
                assert resp.status == 200
                html_expired = await resp.text()
                assert "PHIÊN KẾT NỐI HẾT HẠN" in html_expired
                assert "Cần quét lại mã QR" in html_expired

            # D. Gọi API Hủy liên kết tài khoản chuẩn thương mại: POST /api/v1/auth/tuya/unlink
            async with client.post(
                f"{base_url}/api/v1/auth/tuya/unlink",
                json={"user_id": user_id},
            ) as unlink_resp:
                assert unlink_resp.status == 200
                unlink_data = await unlink_resp.json()
                assert unlink_data["status"] == "success"
                assert unlink_data["details"]["deleted_sharing_sessions"] >= 1
                assert unlink_data["details"]["deleted_devices"] >= 1

            # E. Kiểm tra sau khi Hủy liên kết: Portal chuyển ngay về CHƯA KẾT NỐI TÀI KHOẢN SMART LIFE
            async with client.get(f"{base_url}/portal?user_id={user_id}") as resp:
                assert resp.status == 200
                html_unlinked = await resp.text()
                assert "CHƯA KẾT NỐI TÀI KHOẢN SMART LIFE NGOÀI" in html_unlinked
                assert "PHIÊN KẾT NỐI HẾT HẠN" not in html_unlinked
