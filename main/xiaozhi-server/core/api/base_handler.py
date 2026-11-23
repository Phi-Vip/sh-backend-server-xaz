from aiohttp import web
from config.logger import setup_logging
from urllib.parse import urlparse


class BaseHandler:
    def __init__(self, config: dict):
        self.config = config
        self.logger = setup_logging()
        # Whitelist domain CORS chuẩn (Task 2.3)
        server_cfg = config.get("server", {})
        self.allowed_origins = set(
            server_cfg.get(
                "cors_allowed_origins",
                [
                    "http://localhost",
                    "http://127.0.0.1",
                    "https://localhost",
                    "http://localhost:3000",
                    "http://localhost:8000",
                    "http://localhost:8080",
                ],
            )
        )

    def _add_cors_headers(self, response, request=None):
        """Thêm CORS headers an toàn: Không dùng đồng thời Origin:* và Credentials:true; kèm Vary:Origin (Task 2.3)"""
        response.headers["Access-Control-Allow-Headers"] = (
            "client-id, content-type, device-id, authorization, accept"
        )
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Vary"] = "Origin"

        req_origin = None
        if request and hasattr(request, "headers"):
            req_origin = request.headers.get("Origin")

        if req_origin:
            parsed = urlparse(req_origin)
            domain = parsed.hostname or ""
            is_allowed = (
                req_origin in self.allowed_origins
                or domain in ("localhost", "127.0.0.1")
                or domain.endswith(".sunhouse.com.vn")
                or domain == "sunhouse.com.vn"
            )
            if is_allowed:
                response.headers["Access-Control-Allow-Origin"] = req_origin
                response.headers["Access-Control-Allow-Credentials"] = "true"
            else:
                response.headers["Access-Control-Allow-Origin"] = "null"
        else:
            response.headers["Access-Control-Allow-Origin"] = "*"

    async def handle_options(self, request):
        """Xử lý OPTIONS preflight request"""
        response = web.Response(body=b"", content_type="text/plain")
        self._add_cors_headers(response, request)
        return response
