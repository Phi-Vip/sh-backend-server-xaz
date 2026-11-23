import asyncio
import time
import os
from aiohttp import web
from config.logger import setup_logging
from core.api.ota_handler import OTAHandler
from core.api.vision_handler import VisionHandler

TAG = __name__


class SimpleHttpServer:
    def __init__(self, config: dict, ws_server=None):
        self.config = config
        self.ws_server = ws_server
        self.logger = setup_logging()
        self.ota_handler = OTAHandler(config)
        self.vision_handler = VisionHandler(config)
        self._start_time = time.time()

    async def healthz_handler(self, request: web.Request) -> web.Response:
        """Endpoint kiểm tra sức khỏe cụm Worker (Health Check cho Nginx Load Balancer / Supervisor - Task 4.1)."""
        worker_pid = os.getpid()
        active_cnt = len(self.ws_server.active_connections) if self.ws_server else 0
        worker_id = os.getenv("WORKER_ID", f"worker_{self.config.get('server', {}).get('port', worker_pid)}")
        uptime = round(time.time() - getattr(self, "_start_time", time.time()), 2)
        return web.json_response({
            "status": "ok",
            "worker_id": worker_id,
            "pid": worker_pid,
            "active_connections": active_cnt,
            "uptime_seconds": uptime,
        })

    async def kick_device_handler(self, request: web.Request) -> web.Response:
        """API nhận yêu cầu ngắt kết nối WebSocket của thiết bị (phục vụ Unbind / Xóa Loa tức thì)."""
        try:
            data = await request.json()
            device_id = data.get("device_id") or data.get("mac") or ""
            reason = data.get("reason", "Device Unlinked from Portal")
            if not device_id:
                return web.json_response({"status": "error", "message": "Missing device_id"}, status=400)

            kicked = False
            if self.ws_server:
                kicked = await self.ws_server.kick_device(device_id, reason=reason)
                # Phát sóng liên cụm qua Redis Pub/Sub (Task 4.3)
                if hasattr(self.ws_server, "broadcast_cluster_kick"):
                    asyncio.create_task(self.ws_server.broadcast_cluster_kick(device_id, reason=reason))

            return web.json_response({
                "status": "success",
                "device_id": device_id,
                "kicked": kicked,
                "message": f"Thiết bị {device_id} {'đã bị ngắt kết nối WebSocket' if kicked else 'hiện không có phiên kết nối trực tuyến'}"
            })
        except Exception as e:
            self.logger.bind(tag=TAG).error(f"Lỗi khi xử lý kick_device_handler: {e}")
            return web.json_response({"status": "error", "message": str(e)}, status=500)

    def _get_websocket_url(self, local_ip: str, port: int) -> str:
        """获取websocket地址

        Args:
            local_ip: 本地IP地址
            port: 端口号

        Returns:
            str: websocket地址
        """
        server_config = self.config["server"]
        websocket_config = server_config.get("websocket")

        if websocket_config and "你" not in websocket_config:
            return websocket_config
        else:
            return f"ws://{local_ip}:{port}/xiaozhi/v1/"

    async def start(self):
        try:
            server_config = self.config["server"]
            read_config_from_api = self.config.get("read_config_from_api", False)
            host = server_config.get("ip", "0.0.0.0")
            port = int(server_config.get("http_port", 8003))

            if port:
                app = web.Application()

                if not read_config_from_api:
                    # 如果没有开启智控台，只是单模块运行，就需要再添加简单OTA接口，用于下发websocket接口
                    app.add_routes(
                        [
                            web.get("/xiaozhi/ota/", self.ota_handler.handle_get),
                            web.post("/xiaozhi/ota/", self.ota_handler.handle_post),
                            web.options(
                                "/xiaozhi/ota/", self.ota_handler.handle_options
                            ),
                            # 下载接口，仅提供 data/bin/*.bin 下载
                            web.get(
                                "/xiaozhi/ota/download/{filename}",
                                self.ota_handler.handle_download,
                            ),
                            web.options(
                                "/xiaozhi/ota/download/{filename}",
                                self.ota_handler.handle_options,
                            ),
                        ]
                    )
                # 添加路由
                app.add_routes(
                    [
                        web.get("/mcp/vision/explain", self.vision_handler.handle_get),
                        web.post(
                            "/mcp/vision/explain", self.vision_handler.handle_post
                        ),
                        web.options(
                            "/mcp/vision/explain", self.vision_handler.handle_options
                        ),
                        # Realtime Kick API cho Giai đoạn 4
                        web.post("/api/device/kick", self.kick_device_handler),
                        web.post("/device/kick", self.kick_device_handler),
                        # Health Check cho Nginx Load Balancer và Supervisor (Task 4.1)
                        web.get("/healthz", self.healthz_handler),
                        web.get("/health", self.healthz_handler),
                    ]
                )

                # 运行服务
                runner = web.AppRunner(app)
                await runner.setup()
                site = web.TCPSite(runner, host, port)
                await site.start()

                # 保持服务运行
                while True:
                    await asyncio.sleep(3600)  # 每隔 1 小时检查一次
        except Exception as e:
            self.logger.bind(tag=TAG).error(f"HTTP服务器启动失败: {e}")
            import traceback

            self.logger.bind(tag=TAG).error(f"错误堆栈: {traceback.format_exc()}")
            raise
