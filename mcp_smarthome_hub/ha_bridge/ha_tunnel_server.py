# -*- coding: utf-8 -*-
"""CỔNG TIẾP NHẬN ĐƯỜNG HẦM WEBSOCKET NGƯỢC HOME ASSISTANT (HA TUNNEL SERVER - PHASE 3).

Đặc tả kỹ thuật (Chuẩn Mass Production / B2B Prosumer):
1. Ingress Endpoint: GET /xiaozhi/v1/ha/tunnel (WebSocket Secure).
2. Bảo mật tuyệt đối: Bắt buộc xác thực qua HTTP Upgrade Header `Authorization: Bearer <token>`.
   Chặn 100% mọi request truyền token qua URL query parameter (ngăn rò rỉ token qua log proxy/CDN).
3. Thu hồi quyền tức thì (Instant Revocation < 500ms): Đóng kết nối ngay với WebSocket Close Code 1008 (Policy Violation).
4. Duy trì nhịp tim Ping/Pong RFC 6455 mỗi 25s đảm bảo xuyên thủng NAT/Firewall gia đình.
5. Định tuyến phản hồi JSON-RPC 2.0 nội bộ và liên node qua RedisSessionManager.
"""

import asyncio
import json
import logging
import time
from typing import Any, Dict, Optional
from aiohttp import web, WSMsgType, WSCloseCode

try:
    from mcp_smarthome_hub.storage.db import SmartHomeDAL, dal as default_dal
except ImportError:
    try:
        from storage.db import SmartHomeDAL, dal as default_dal
    except ImportError:
        from ..storage.db import SmartHomeDAL, dal as default_dal
from .redis_session_mgr import RedisSessionManager

logger = logging.getLogger("HATunnelServer")


class HATunnelServer:
    """Máy chủ quản lý đường hầm WebSocket ngược dành cho Home Assistant."""

    def __init__(
        self,
        session_mgr: Optional[RedisSessionManager] = None,
        dal_instance: Optional[SmartHomeDAL] = None,
    ):
        """Khởi tạo Gateway đường hầm Home Assistant."""
        self.session_mgr = session_mgr or RedisSessionManager()
        self.dal = dal_instance or default_dal

        # Bản đồ lưu các kết nối WebSocket đang hoạt động trên node cục bộ: user_id -> web.WebSocketResponse
        self.local_connections: Dict[str, web.WebSocketResponse] = {}

        # Quản lý các lệnh đang chờ HA Client phản hồi trên node cục bộ: request_id -> asyncio.Future
        self._local_pending_requests: Dict[str, asyncio.Future] = {}

        # Đăng ký lắng nghe sự kiện thu hồi quyền từ Redis
        self.session_mgr.on_revocation(self._handle_remote_revocation)

        # Đăng ký lắng nghe lệnh chuyển tiếp liên node từ Redis
        self.session_mgr.on_command(self._handle_remote_command)

    # =========================================================================
    # WebSocket Ingress Handler (Điểm Tiếp Nhận Kết Nối)
    # =========================================================================

    async def handle_tunnel_connection(self, request: web.Request) -> web.StreamResponse:
        """Xử lý bắt tay WebSocket Ingress từ Home Assistant Client (wss://.../ha/tunnel)."""
        client_ip = request.remote or "Unknown"

        # ---------------------------------------------------------------------
        # 1. KIỂM TRA BẢO MẬT: CHẶN 100% TOKEN TRÊN URL QUERY PARAM
        # ---------------------------------------------------------------------
        if "token" in request.query or "access_token" in request.query or "bearer" in request.query:
            logger.warning(
                f"🚨 [CẢNH BÁO BẢO MẬT] Từ chối kết nối từ {client_ip}: "
                f"Phát hiện truyền token qua URL Query Parameter (Vi phạm chính sách an ninh)!"
            )
            return web.Response(
                status=401,
                text="Chính sách bảo mật: Tuyệt đối không truyền token trên URL query param. Sử dụng header 'Authorization: Bearer <token>'!",
                content_type="text/plain", charset="utf-8",
            )

        # ---------------------------------------------------------------------
        # 2. XÁC THỰC HTTP UPGRADE HEADER (Authorization: Bearer <token>)
        # ---------------------------------------------------------------------
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.strip():
            logger.warning(f"Từ chối kết nối từ {client_ip}: Thiếu Header Authorization!")
            return web.Response(
                status=401,
                text="Lỗi xác thực: Thiếu Header 'Authorization: Bearer <token>'!",
                content_type="text/plain", charset="utf-8",
            )

        parts = auth_header.strip().split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            logger.warning(f"Từ chối kết nối từ {client_ip}: Định dạng Header Authorization không phải Bearer!")
            return web.Response(
                status=401,
                text="Lỗi xác thực: Header Authorization phải có định dạng 'Bearer <token>'!",
                content_type="text/plain", charset="utf-8",
            )

        bearer_token = parts[1]

        # Thẩm định token qua CSDL (giải mã AES-256-GCM từ bảng ha_credentials)
        user_id = self.dal.verify_ha_bearer_token(bearer_token)
        if not user_id:
            logger.warning(f"Từ chối kết nối từ {client_ip}: Bearer Token không hợp lệ hoặc đã bị thu hồi!")
            return web.Response(
                status=401,
                text="Lỗi xác thực: Bearer Token không hợp lệ hoặc đã bị thu hồi!",
                content_type="text/plain", charset="utf-8",
            )

        # ---------------------------------------------------------------------
        # 3. NÂNG CẤP KẾT NỐI WEBSOCKET (RFC 6455) & NHỊP TIM 25S XUYÊN NAT
        # ---------------------------------------------------------------------
        ws = web.WebSocketResponse(
            heartbeat=25.0,  # Ping frame định kỳ 25s đảm bảo xuyên thủng NAT gia đình
            autoping=True,
            max_msg_size=4 * 1024 * 1024,  # Hỗ trợ payload lớn tối đa 4MB (bản đồ, danh sách entities)
        )
        await ws.prepare(request)

        logger.info(
            f"✅ [KẾT NỐI THÀNH CÔNG]: Đường hầm HA của User [{user_id}] đã mở tại Node [{self.session_mgr.node_id}]"
        )

        # Nếu user đã có kết nối cũ trên node này, đóng kết nối cũ
        if user_id in self.local_connections:
            old_ws = self.local_connections[user_id]
            if not old_ws.closed:
                await old_ws.close(code=WSCloseCode.POLICY_VIOLATION, message=b"Replaced by new connection")

        # Lưu kết nối cục bộ và đồng bộ lên Redis
        self.local_connections[user_id] = ws
        await self.session_mgr.register_session(user_id, self.session_mgr.node_id)

        # ---------------------------------------------------------------------
        # 4. VÒNG LẶP TIẾP NHẬN BẢN TIN TỪ HOME ASSISTANT CLIENT
        # ---------------------------------------------------------------------
        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    await self._process_incoming_message(user_id, msg.data)
                elif msg.type == WSMsgType.BINARY:
                    # Hỗ trợ gói tin nhị phân nếu có
                    pass
                elif msg.type in (WSMsgType.CLOSE, WSMsgType.CLOSING, WSMsgType.CLOSED):
                    logger.info(f"Đường hầm HA của User [{user_id}] nhận tín hiệu đóng.")
                    break
                elif msg.type == WSMsgType.ERROR:
                    logger.error(f"Lỗi kết nối socket của User [{user_id}]: {ws.exception()}")
                    break
        finally:
            # -----------------------------------------------------------------
            # 5. DỌN DẸP KHI NGẮT KẾT NỐI
            # -----------------------------------------------------------------
            if self.local_connections.get(user_id) is ws:
                self.local_connections.pop(user_id, None)
                await self.session_mgr.unregister_session(user_id)
            logger.info(f"Đã giải phóng đường hầm HA của User [{user_id}].")

        return ws

    # =========================================================================
    # Xử Lý Bản Tin Đến & Phản Hồi JSON-RPC 2.0
    # =========================================================================

    async def _process_incoming_message(self, user_id: str, raw_text: str):
        """Xử lý bản tin JSON-RPC 2.0 nhận từ Home Assistant Client."""
        try:
            data = json.loads(raw_text)
        except Exception as e:
            logger.warning(f"Nhận bản tin không hợp lệ từ User [{user_id}]: {e}")
            return

        req_id = data.get("id")
        if req_id is not None:
            req_id_str = str(req_id)

            # 1. Kiểm tra nếu request này xuất phát từ node cục bộ
            if req_id_str in self._local_pending_requests:
                fut = self._local_pending_requests.pop(req_id_str)
                if not fut.done():
                    fut.set_result(data)
                return

            # 2. Ngược lại, publish kết quả về Redis để Node gọi lệnh nhận kết quả
            await self.session_mgr.publish_response(req_id_str, data)

    # =========================================================================
    # Gửi Lệnh Trực Tiếp Xuống HA Client Trên Node Cục Bộ
    # =========================================================================

    def is_user_local(self, user_id: str) -> bool:
        """Kiểm tra xem User có đang giữ kết nối WebSocket trực tiếp trên node này không."""
        ws = self.local_connections.get(user_id)
        return ws is not None and not ws.closed

    async def send_to_local_user(
        self,
        user_id: str,
        payload: Dict[str, Any],
        timeout: float = 3.0,
    ) -> Dict[str, Any]:
        """Gửi lệnh JSON-RPC xuống HA client đang kết nối với node này và chờ kết quả."""
        ws = self.local_connections.get(user_id)
        if not ws or ws.closed:
            raise ConnectionError(f"User [{user_id}] không có kết nối WebSocket trực tuyến trên node này!")

        req_id = str(payload.get("id", ""))
        if not req_id:
            import uuid
            req_id = f"ha_req_{uuid.uuid4().hex[:8]}"
            payload["id"] = req_id

        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        self._local_pending_requests[req_id] = fut

        # Gửi gói tin qua WebSocket
        await ws.send_str(json.dumps(payload, ensure_ascii=False))

        try:
            result = await asyncio.wait_for(fut, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            self._local_pending_requests.pop(req_id, None)
            raise TimeoutError(f"Quá thời gian ({timeout}s) chờ phản hồi từ Home Assistant của User [{user_id}]")

    # =========================================================================
    # Xử Lý Lệnh Chuyển Tiếp Liên Node (Remote Command Dispatched via Redis)
    # =========================================================================

    async def _handle_remote_command(self, cmd_envelope: Dict[str, Any]):
        """Xử lý lệnh từ Node khác chuyển tiếp qua Redis để gửi xuống HA Client cục bộ."""
        user_id = cmd_envelope.get("user_id")
        req_id = cmd_envelope.get("req_id")
        payload = cmd_envelope.get("payload")

        if not user_id or not payload:
            return

        ws = self.local_connections.get(user_id)
        if not ws or ws.closed:
            # Gửi phản hồi lỗi về Redis
            error_res = {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32001, "message": f"Client HA của User [{user_id}] vừa mất kết nối!"},
            }
            await self.session_mgr.publish_response(str(req_id), error_res)
            return

        try:
            # Chuyển tiếp xuống client
            await ws.send_str(json.dumps(payload, ensure_ascii=False))
        except Exception as e:
            error_res = {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32000, "message": f"Lỗi gửi xuống WebSocket: {e}"},
            }
            await self.session_mgr.publish_response(str(req_id), error_res)

    # =========================================================================
    # Xử Lý Thu Hồi Quyền Tức Thì (Instant Revocation < 500ms)
    # =========================================================================

    async def close_user_tunnel(
        self,
        user_id: str,
        code: int = WSCloseCode.POLICY_VIOLATION,  # 1008
        reason: str = "Chính sách bảo mật: Token đã bị thu hồi",
    ) -> bool:
        """Đóng ngay lập tức đường hầm của user với Close Frame 1008 (Policy Violation)."""
        ws = self.local_connections.pop(user_id, None)
        if ws and not ws.closed:
            try:
                await ws.close(code=code, message=reason.encode("utf-8"))
                logger.warning(f"⚡ [ĐÃ NGẮT KẾT NỐI]: Thu hồi thành công đường hầm User [{user_id}] với mã {code}!")
                return True
            except Exception as e:
                logger.error(f"Lỗi khi đóng WebSocket của User [{user_id}]: {e}")
                return False
        return False

    async def _handle_remote_revocation(self, user_id: str, reason: str):
        """Xử lý sự kiện thu hồi phát sóng từ Redis: Đóng ngay socket nếu node này đang nắm giữ."""
        if user_id in self.local_connections:
            await self.close_user_tunnel(
                user_id=user_id,
                code=WSCloseCode.POLICY_VIOLATION,  # 1008
                reason=f"Thu hồi tức thì: {reason}",
            )
