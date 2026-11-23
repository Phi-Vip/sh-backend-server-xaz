import asyncio
import logging

import websockets
from config.logger import setup_logging


class SuppressInvalidHandshakeFilter(logging.Filter):
    """过滤掉无效握手错误日志（如HTTPS访问WS端口）"""

    def filter(self, record):
        msg = record.getMessage()
        suppress_keywords = [
            "opening handshake failed",
            "did not receive a valid HTTP request",
            "connection closed while reading HTTP request",
            "line without CRLF",
        ]
        return not any(keyword in msg for keyword in suppress_keywords)


def _setup_websockets_logger():
    """配置 websockets 相关的所有 logger，过滤无效握手错误"""
    filter_instance = SuppressInvalidHandshakeFilter()
    for logger_name in ["websockets", "websockets.server", "websockets.client"]:
        logger = logging.getLogger(logger_name)
        logger.addFilter(filter_instance)


_setup_websockets_logger()


from core.connection import ConnectionHandler
from config.config_loader import get_config_from_api_async
from core.auth import AuthManager, AuthenticationError
from core.utils.modules_initialize import initialize_modules
from core.utils.util import check_vad_update, check_asr_update

TAG = __name__


class WebSocketServer:
    def __init__(self, config: dict):
        self.config = config
        self.logger = setup_logging(config)
        self.config_lock = asyncio.Lock()
        selected_mod = self.config.get("selected_module", {})
        modules = initialize_modules(
            self.logger,
            self.config,
            "VAD" in selected_mod,
            "ASR" in selected_mod,
            "LLM" in selected_mod,
            "TTS" in selected_mod,
            "Memory" in selected_mod,
            "Intent" in selected_mod,
        )
        self._vad = modules["vad"] if "vad" in modules else None
        self._asr = modules["asr"] if "asr" in modules else None
        self._llm = modules["llm"] if "llm" in modules else None
        self._intent = modules["intent"] if "intent" in modules else None
        self._memory = modules["memory"] if "memory" in modules else None
        self._tts = modules["tts"] if "tts" in modules else None

        auth_config = self.config["server"].get("auth", {})
        self.auth_enable = auth_config.get("enabled", False)
        # 设备白名单
        self.allowed_devices = set(auth_config.get("allowed_devices", []))
        secret_key = self.config["server"]["auth_key"]
        expire_seconds = auth_config.get("expire_seconds", None)
        self.auth = AuthManager(secret_key=secret_key, expire_seconds=expire_seconds)

        # Quản lý danh bạ các phiên kết nối WebSocket đang hoạt động (Phục vụ Real-time Kick)
        self.active_connections: dict = {}

    @staticmethod
    def normalize_mac(mac: str) -> str:
        """Chuẩn hóa MAC dạng lowercase cách nhau bởi dấu hai chấm."""
        if not mac:
            return ""
        return mac.replace("-", ":").lower().strip()

    @staticmethod
    async def broadcast_cluster_kick(device_id: str, reason: str = "Cluster Revocation") -> bool:
        """Phát sóng lệnh thu hồi / ngắt kết nối thiết bị lên toàn cụm Worker qua Redis Pub/Sub (Task 4.3)."""
        import os, json
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        try:
            import redis.asyncio as aioredis
            r = aioredis.from_url(redis_url, encoding="utf-8", decode_responses=True, socket_connect_timeout=0.5)
            norm_mac = (device_id or "").replace("-", ":").lower().strip()
            payload = json.dumps({"device_id": norm_mac, "reason": reason})
            await r.publish("xiaozhi:control:revoke", payload)
            await r.publish("xiaozhi:cluster:kick_device", payload)
            await r.aclose()
            return True
        except Exception:
            return False

    async def kick_device(self, device_id: str, reason: str = "Device Unlinked") -> bool:
        """Đá ngay lập tức kết nối WebSocket của thiết bị theo MAC / Device-Id."""
        norm_mac = self.normalize_mac(device_id)
        handler = self.active_connections.get(norm_mac)
        if handler:
            self.logger.bind(tag=TAG).info(
                f"⚡ [REALTIME KICK] Ngắt kết nối WebSocket của Loa {norm_mac} (Lý do: {reason})"
            )
            try:
                # Gửi lệnh system unlink trước khi đóng kết nối để firmware hiển thị màn hình Unlinked và phát âm báo
                target_ws = getattr(handler, "websocket", None)
                if target_ws and hasattr(target_ws, "send"):
                    import json
                    unlink_msg = json.dumps({
                        "type": "system",
                        "command": "unlink",
                        "message": "Thiết bị đã bị hủy liên kết khỏi máy chủ"
                    })
                    try:
                        res = target_ws.send(unlink_msg)
                        if asyncio.iscoroutine(res):
                            await res
                        await asyncio.sleep(0.15)
                    except Exception as send_err:
                        self.logger.bind(tag=TAG).warning(f"Không thể gửi gói unlink: {send_err}")
                await handler.close(code=4001, reason=reason)
            except Exception as e:
                self.logger.bind(tag=TAG).error(f"Lỗi khi đá kết nối thiết bị {norm_mac}: {e}")
            return True
        else:
            self.logger.bind(tag=TAG).info(
                f"ℹ️ [REALTIME KICK] Thiết bị {norm_mac} hiện không có phiên kết nối WebSocket trực tuyến."
            )
            return False

    async def start(self):
        # Khởi động Keep-Warm Daemon nếu TTS hỗ trợ
        if hasattr(self, "_tts") and self._tts and hasattr(self._tts, "start_keep_warm"):
            try:
                self._tts.start_keep_warm()
            except Exception as e:
                self.logger.bind(tag=TAG).warning(f"Không thể khởi động TTS Keep-Warm: {e}")

        # Khởi động listener Pub/Sub lắng nghe lệnh thu hồi token tức thì (Task 2.4)
        asyncio.create_task(self._listen_revocation_channel())

        server_config = self.config["server"]
        host = server_config.get("ip", "0.0.0.0")
        port = int(server_config.get("port", 8000))

        async with websockets.serve(
            self._handle_connection,
            host,
            port,
            process_request=self._http_response,
            ping_interval=None,
        ):
            await asyncio.Future()

    async def _listen_revocation_channel(self):
        """Lắng nghe kênh Redis Pub/Sub 'xiaozhi:control:revoke' và 'xiaozhi:cluster:kick_device' để ngắt kết nối tức thì <= 500ms (Task 2.4 & 4.3)."""
        import os
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        while True:
            try:
                import redis.asyncio as aioredis
                import json
                r = aioredis.from_url(redis_url, encoding="utf-8", decode_responses=True, socket_connect_timeout=0.5)
                pubsub = r.pubsub()
                await pubsub.subscribe("xiaozhi:control:revoke", "xiaozhi:cluster:kick_device")
                self.logger.bind(tag=TAG).info("📡 [REVOCATION PUBSUB] Đã đăng ký lắng nghe kênh 'xiaozhi:control:revoke' & 'xiaozhi:cluster:kick_device'")
                async for msg in pubsub.listen():
                    if msg.get("type") == "message":
                        try:
                            raw_data = msg.get("data", "{}")
                            payload = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
                            dev_id = payload.get("device_id") or payload.get("mac")
                            reason = payload.get("reason", "Device revoked/unlinked by user")
                            if dev_id:
                                await self.kick_device(dev_id, reason=reason)
                        except Exception as parse_err:
                            self.logger.bind(tag=TAG).warning(f"Lỗi phân tích gói revoke: {parse_err}")
            except asyncio.CancelledError:
                break
            except Exception as e:
                # Tránh in log quá dày nếu Redis chưa được bật ở chế độ standalone
                await asyncio.sleep(5)

    async def _handle_connection(self, websocket: websockets.ServerConnection):
        headers = dict(websocket.request.headers)
        if headers.get("device-id", None) is None:
            # Hỗ trợ lấy device-id / client-id từ query params cho môi trường dev nhưng TUYỆT ĐỐI KHÔNG nhận authorization
            from urllib.parse import parse_qs, urlparse

            request_path = websocket.request.path
            if not request_path:
                self.logger.bind(tag=TAG).error("无法获取请求路径")
                await websocket.close()
                return
            parsed_url = urlparse(request_path)
            query_params = parse_qs(parsed_url.query)
            if "device-id" in query_params:
                websocket.request.headers["device-id"] = query_params["device-id"][0]
            if "client-id" in query_params:
                websocket.request.headers["client-id"] = query_params["client-id"][0]
            # Chặn tuyệt đối token qua URL query string (Task 2.3)

        """处理新连接，每次创建独立的ConnectionHandler"""
        # 先认证，后建立连接
        try:
            await self._handle_auth(websocket)
        except AuthenticationError as auth_err:
            self.logger.bind(tag=TAG).warning(f"Xác thực thất bại: {auth_err}")
            await websocket.send(f"认证失败: {auth_err}")
            await websocket.close(code=4001, reason=str(auth_err))
            return
        # 创建ConnectionHandler时传入当前server实例
        handler = ConnectionHandler(
            self.config,
            self._vad,
            self._asr,
            self._llm,
            self._memory,
            self._intent,
            self,  # 传入server实例
        )
        handler.user_id = getattr(websocket, "authenticated_user_id", None)
        norm_mac = self.normalize_mac(websocket.request.headers.get("device-id", ""))
        if norm_mac:
            self.active_connections[norm_mac] = handler
            self.logger.bind(tag=TAG).info(f"🔗 [FLEET REGISTRY] Đã đăng ký kết nối hoạt động cho Loa: {norm_mac}")

        try:
            await handler.handle_connection(websocket)
        except Exception as e:
            self.logger.bind(tag=TAG).error(f"处理连接时出错: {e}")
        finally:
            if norm_mac:
                self.active_connections.pop(norm_mac, None)
                self.logger.bind(tag=TAG).info(f"🔌 [FLEET REGISTRY] Đã giải phóng kết nối cho Loa: {norm_mac}")
            # 强制关闭连接（如果还没有关闭的话）
            try:
                # 安全地检查WebSocket状态并关闭
                if hasattr(websocket, "closed") and not websocket.closed:
                    await websocket.close()
                elif hasattr(websocket, "state") and websocket.state.name != "CLOSED":
                    await websocket.close()
                else:
                    # 如果没有closed属性，直接尝试关闭
                    await websocket.close()
            except Exception as close_error:
                self.logger.bind(tag=TAG).error(
                    f"服务器端强制关闭连接时出错: {close_error}"
                )

    async def _http_response(self, websocket, request_headers):
        # 检查是否为 WebSocket 升级请求
        if request_headers.headers.get("connection", "").lower() == "upgrade":
            # 如果是 WebSocket 请求，返回 None 允许握手继续
            return None
        else:
            # 如果是普通 HTTP 请求，返回 "server is running"
            return websocket.respond(200, "Server is running\n")

    async def update_config(self) -> bool:
        """更新服务器配置并重新初始化组件

        Returns:
            bool: 更新是否成功
        """
        try:
            async with self.config_lock:
                # 重新获取配置（使用异步版本）
                new_config = await get_config_from_api_async(self.config)
                if new_config is None:
                    self.logger.bind(tag=TAG).error("获取新配置失败")
                    return False
                self.logger.bind(tag=TAG).info(f"获取新配置成功")
                # 检查 VAD 和 ASR 类型是否需要更新
                update_vad = check_vad_update(self.config, new_config)
                update_asr = check_asr_update(self.config, new_config)
                self.logger.bind(tag=TAG).info(
                    f"检查VAD和ASR类型是否需要更新: {update_vad} {update_asr}"
                )
                # 更新配置
                self.config = new_config
                # 重新初始化组件
                selected_mod = new_config.get("selected_module", {})
                modules = initialize_modules(
                    self.logger,
                    new_config,
                    update_vad,
                    update_asr,
                    "LLM" in selected_mod,
                    "TTS" in selected_mod,
                    "Memory" in selected_mod,
                    "Intent" in selected_mod,
                )

                # 更新组件实例
                if "vad" in modules:
                    self._vad = modules["vad"]
                if "asr" in modules:
                    self._asr = modules["asr"]
                if "llm" in modules:
                    self._llm = modules["llm"]
                if "intent" in modules:
                    self._intent = modules["intent"]
                if "memory" in modules:
                    self._memory = modules["memory"]
                if "tts" in modules:
                    self._tts = modules["tts"]
                    if hasattr(self._tts, "start_keep_warm"):
                        try:
                            self._tts.start_keep_warm()
                        except Exception as e:
                            self.logger.bind(tag=TAG).warning(f"Không thể khởi động lại TTS Keep-Warm: {e}")
                self.logger.bind(tag=TAG).info(f"更新配置任务执行完毕")
                return True
        except Exception as e:
            self.logger.bind(tag=TAG).error(f"更新服务器配置失败: {str(e)}")
            return False

    async def _handle_auth(self, websocket: websockets.ServerConnection):
        """Xác thực bắt tay WebSocket: Kiểm tra MAC chuẩn, cấm query token, xác thực AuthToken AES-GCM (Task 2.1-2.4)."""
        req_path = websocket.request.path or ""
        if "authorization=" in req_path.lower():
            raise AuthenticationError("Forbidden: Passing token via URL query string is not permitted")

        headers = dict(websocket.request.headers)
        device_id = headers.get("device-id") or headers.get("Device-Id")
        client_id = headers.get("client-id") or headers.get("Client-Id")

        import re
        mac_regex = re.compile(r"^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$")
        if not device_id or not mac_regex.match(device_id.strip()):
            raise AuthenticationError("Missing or invalid MAC address format in Device-Id header")

        if self.auth_enable:
            token = headers.get("authorization", "")
            # Hỗ trợ lấy token từ Sec-WebSocket-Protocol cho client test trình duyệt
            if not token and "sec-websocket-protocol" in headers:
                subprotocols = [p.strip() for p in headers["sec-websocket-protocol"].split(",")]
                for p in subprotocols:
                    if p.lower().startswith("bearer."):
                        token = "Bearer " + p[7:]
                        break

            if not token.startswith("Bearer "):
                raise AuthenticationError("Missing or invalid Authorization header")

            token = token[7:].strip()
            # Xác thực token (thống nhất chuẩn 1A AuthToken AES-GCM, xóa bỏ hoàn toàn allowed_devices bypass Issue #3448)
            auth_success = self.auth.verify_token(
                token, client_id=client_id, username=device_id
            )
            if not auth_success:
                raise AuthenticationError("Invalid token or token has been revoked")

            # Trích xuất user_id từ AuthToken AES-GCM (Task 3.3)
            token_payload = self.auth.get_token_payload(token)
            if token_payload:
                websocket.authenticated_user_id = token_payload.get("user_id")
