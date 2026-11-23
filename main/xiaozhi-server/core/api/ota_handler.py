import json
import time
import base64
import hashlib
import hmac
import os
import re
import glob
from typing import Dict, List, Tuple, Optional
from aiohttp import web

from core.auth import AuthManager
from core.utils.auth import AuthToken
from core.utils.util import get_local_ip, get_vision_url
from core.api.base_handler import BaseHandler

TAG = __name__

# Cửa sổ Rate limit OTA { (client_ip, clean_mac): (count, window_start_ts) }
_ota_rate_limit: Dict[Tuple[str, str], Tuple[int, float]] = {}


def _safe_basename(filename: str) -> str:
    # Prevent directory traversal
    return os.path.basename(filename)


def _parse_version(ver: str) -> Tuple[int, ...]:
    # conservative parser: split by non-digit, keep numeric parts
    parts = re.findall(r"\d+", ver)
    return tuple(int(p) for p in parts) if parts else (0,)


def _is_higher_version(a: str, b: str) -> bool:
    """Return True if version string a > b (semver-like numeric compare)."""
    ta = _parse_version(a)
    tb = _parse_version(b)
    # compare tuple lexicographically, but allow different lengths
    maxlen = max(len(ta), len(tb))
    for i in range(maxlen):
        ai = ta[i] if i < len(ta) else 0
        bi = tb[i] if i < len(tb) else 0
        if ai > bi:
            return True
        if ai < bi:
            return False
    return False


class OTAHandler(BaseHandler):
    def __init__(self, config: dict):
        super().__init__(config)
        auth_config = config["server"].get("auth", {})
        self.auth_enable = auth_config.get("enabled", False)
        # 设备白名单
        self.allowed_devices = set(auth_config.get("allowed_devices", []))
        self.secret_key = str(config["server"]["auth_key"])
        expire_seconds = auth_config.get("expire_seconds")
        self.auth = AuthManager(secret_key=self.secret_key, expire_seconds=expire_seconds)
        self.auth_token_generator = AuthToken(secret_key=self.secret_key)

        # firmware storage
        self.bin_dir = os.path.join(os.getcwd(), "data", "bin")
        # cache structure: { 'updated_at': timestamp, 'ttl': seconds, 'files_by_model': { model: [(version, filename), ...] } }
        self._bin_cache: Dict = {
            "updated_at": 0,
            "ttl": config.get("firmware_cache_ttl", 30),
            "files_by_model": {},
        }

    def _check_rate_limit(self, client_ip: str, device_id: str) -> Tuple[bool, int]:
        """Rate limit: Tối đa 1 req/5s, burst 2 (Task 2.5). Trả về (is_allowed, retry_after)"""
        clean_mac = device_id.replace("-", ":").lower().strip()
        key = (client_ip, clean_mac)
        now = time.time()
        count, start = _ota_rate_limit.get(key, (0, now))

        if now - start > 5.0:
            _ota_rate_limit[key] = (1, now)
            return True, 0
        else:
            if count >= 2:
                retry_after = max(1, int(5.0 - (now - start)))
                return False, retry_after
            else:
                _ota_rate_limit[key] = (count + 1, start)
                return True, 0

    def _check_device_activation(self, device_id: str) -> Tuple[bool, Optional[str]]:
        """Kiểm tra quyền sở hữu thiết bị trong CSDL (Task 2.1). Trả về (is_active, user_id)."""
        if not device_id:
            return False, None
        clean_mac = device_id.replace("-", ":").lower().strip()

        # 1. Tra nhanh Redis
        try:
            import os, redis
            redis_url = os.getenv("REDIS_URL")
            if redis_url:
                r = redis.Redis.from_url(redis_url, decode_responses=True, socket_connect_timeout=0.2, socket_timeout=0.2)
                val = r.get(f"xiaozhi:device:status:{clean_mac}")
                if val == "0":
                    return False, None
        except Exception:
            pass

        # 2. Tra cứu database
        core_dir = os.path.dirname(os.path.abspath(__file__))
        candidates = [
            os.getenv("SMART_HOME_DB_PATH", ""),
            os.path.abspath(os.path.join(core_dir, "..", "..", "..", "..", "..", "data", "smarthome.db")),
            os.path.abspath(os.path.join(core_dir, "..", "..", "..", "..", "data", "smarthome.db")),
            os.path.abspath(os.path.join(core_dir, "..", "..", "..", "data", "smarthome.db")),
            os.path.abspath(os.path.join(core_dir, "..", "..", "data", "smarthome.db")),
            os.path.abspath(os.path.join(core_dir, "..", "data", "smarthome.db")),
        ]
        for db_path in candidates:
            if db_path and os.path.exists(db_path) and os.path.getsize(db_path) > 0:
                try:
                    import sqlite3
                    conn = sqlite3.connect(db_path, timeout=1.0)
                    cur = conn.cursor()
                    cur.execute(
                        "SELECT is_active, user_id FROM speakers WHERE LOWER(speaker_mac) = ? OR LOWER(device_id) = ? LIMIT 1",
                        (clean_mac, clean_mac),
                    )
                    row = cur.fetchone()
                    conn.close()
                    if row is not None:
                        return bool(row[0]), row[1]
                except Exception as e:
                    self.logger.bind(tag=TAG).debug(f"Lỗi truy vấn smarthome.db: {e}")
        return False, None

    def _generate_bind_code(self, device_id: str) -> str:
        """Tạo mã kích hoạt 6 số kèm TTL 5 phút (Phương án 2C)."""
        import random
        clean_mac = device_id.replace("-", ":").lower().strip()
        pin = f"{random.randint(100000, 999999)}"
        try:
            import os, redis
            redis_url = os.getenv("REDIS_URL")
            if redis_url:
                r = redis.Redis.from_url(redis_url, decode_responses=True, socket_connect_timeout=0.2, socket_timeout=0.2)
                r.set(f"xiaozhi:bind_code:{clean_mac}", pin, ex=300)
        except Exception:
            pass
        return pin

    def _refresh_bin_cache_if_needed(self):
        now = int(time.time())
        ttl = int(self._bin_cache.get("ttl", 30))
        if now - int(
            self._bin_cache.get("updated_at", 0)
        ) < ttl and self._bin_cache.get("files_by_model"):
            return

        files_by_model: Dict[str, List[Tuple[str, str]]] = {}
        try:
            if not os.path.isdir(self.bin_dir):
                os.makedirs(self.bin_dir, exist_ok=True)

            # match files like model_1.2.3.bin (allow dots, dashes, underscores in model and version)
            pattern = os.path.join(self.bin_dir, "*.bin")
            for path in glob.glob(pattern):
                fname = os.path.basename(path)
                # filename format: {model}_{version}.bin
                m = re.match(r"^(.+?)_([0-9][A-Za-z0-9\.\-_]*)\.bin$", fname)
                if not m:
                    # skip files not conforming to naming rule
                    continue
                model = m.group(1)
                version = m.group(2)
                files_by_model.setdefault(model, []).append((version, fname))

            # sort versions for each model descending
            for model, items in files_by_model.items():
                items.sort(key=lambda it: _parse_version(it[0]), reverse=True)

            self._bin_cache["files_by_model"] = files_by_model
            self._bin_cache["updated_at"] = now
            self.logger.bind(tag=TAG).info(
                f"Firmware cache refreshed: {len(files_by_model)} models"
            )
        except Exception as e:
            self.logger.bind(tag=TAG).error(f"刷新固件缓存失败: {e}")
            # keep previous cache if any

    def generate_password_signature(self, content: str, secret_key: str) -> str:
        """生成MQTT密码签名

        Args:
            content: 签名内容 (clientId + '|' + username)
            secret_key: 密钥

        Returns:
            str: Base64编码的HMAC-SHA256签名
        """
        try:
            hmac_obj = hmac.new(
                secret_key.encode("utf-8"), content.encode("utf-8"), hashlib.sha256
            )
            signature = hmac_obj.digest()
            return base64.b64encode(signature).decode("utf-8")
        except Exception as e:
            self.logger.bind(tag=TAG).error(f"生成MQTT密码签名失败: {e}")
            return ""

    def _get_websocket_url(self, local_ip: str, port: int) -> str:
        """获取websocket地址

        Args:
            local_ip: 本地IP地址
            port: 端口号

        Returns:
            str: websocket地址
        """
        server_config = self.config["server"]
        websocket_config = server_config.get("websocket", "")

        if "你的" not in websocket_config:
            return websocket_config
        else:
            return f"ws://{local_ip}:{port}/xiaozhi/v1/"

    async def handle_post(self, request):
        """Xử lý OTA POST: Kiểm tra MAC chuẩn, Rate-limit (Task 2.5), Chặn cấp token ẩn danh (Task 2.1) & Signed URL (Task 2.3)."""
        response = None
        try:
            data = await request.text()
            # Mask thông tin nhạy cảm trước khi log
            sanitized_headers = dict(request.headers)
            for k in ("authorization", "Authorization", "api_key", "secret", "cookie", "Cookie"):
                if k in sanitized_headers:
                    val = str(sanitized_headers[k])
                    sanitized_headers[k] = "Bearer ***" if val.lower().startswith("bearer ") else "***"

            self.logger.bind(tag=TAG).debug(f"OTA请求方法: {request.method}")
            self.logger.bind(tag=TAG).debug(f"OTA请求头: {sanitized_headers}")
            self.logger.bind(tag=TAG).debug(f"OTA请求数据: {data}")

            device_id = request.headers.get("device-id", "").strip()
            if not device_id:
                response = web.Response(
                    text=json.dumps({"success": False, "message": "Missing device-id header"}),
                    content_type="application/json",
                    status=400,
                )
                return response

            # 1. Kiểm tra định dạng MAC chuẩn (Task 2.1)
            mac_regex = re.compile(r"^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$")
            if not mac_regex.match(device_id):
                self.logger.bind(tag=TAG).warning(f"OTA từ chối device_id sai định dạng MAC: {device_id}")
                response = web.Response(
                    text=json.dumps({"success": False, "message": "Invalid MAC address format in Device-Id"}),
                    content_type="application/json",
                    status=400,
                )
                return response

            # 2. Rate-limit chống spam OTA (Task 2.5 - Phương án 2C)
            client_ip = request.remote or "unknown"
            allowed, retry_after = self._check_rate_limit(client_ip, device_id)
            if not allowed:
                self.logger.bind(tag=TAG).warning(f"Rate-limit chặn OTA spam từ {client_ip} / {device_id} (Retry-After: {retry_after}s)")
                response = web.Response(
                    text=json.dumps({"error": "Too Many Requests", "retry_after": retry_after}),
                    content_type="application/json",
                    status=429,
                    headers={"Retry-After": str(retry_after)},
                )
                return response

            client_id = request.headers.get("client-id", "").strip()
            if not client_id:
                client_id = "default_client"

            data_json = {}
            try:
                data_json = json.loads(data) if data else {}
            except Exception:
                data_json = {}

            server_config = self.config["server"]
            websocket_port = int(server_config.get("port", 8000))
            http_port = int(server_config.get("http_port", 8003))
            local_ip = get_local_ip()

            # Xác định device_model
            device_model = ""
            for h in ("device-model", "device_model", "model"):
                if h in request.headers:
                    device_model = request.headers.get(h, "").strip()
                    break
            if not device_model:
                try:
                    if "board" in data_json and isinstance(data_json["board"], dict):
                        device_model = data_json["board"].get("type", "")
                    elif "model" in data_json:
                        device_model = data_json.get("model", "")
                except Exception:
                    device_model = ""
            if not device_model:
                device_model = "default"

            # Xác định device_version
            device_version = ""
            for h in (
                "device-version",
                "device_version",
                "firmware-version",
                "app-version",
                "application-version",
            ):
                if h in request.headers:
                    device_version = request.headers.get(h, "").strip()
                    break
            if not device_version:
                try:
                    device_version = data_json.get("application", {}).get("version", "")
                except Exception:
                    device_version = ""
            if not device_version:
                device_version = "0.0.0"

            return_json = {
                "server_time": {
                    "timestamp": int(round(time.time() * 1000)),
                    "timezone_offset": server_config.get("timezone_offset", 7) * 60,
                },
                "firmware": {
                    "version": device_version,
                    "url": "",
                },
            }

            # 3. Kiểm tra trạng thái kích hoạt thiết bị (Task 2.1 & Phương án 2C)
            is_active, user_id = self._check_device_activation(device_id)

            mqtt_gateway_endpoint = server_config.get("mqtt_gateway")
            if mqtt_gateway_endpoint and is_active:
                try:
                    group_id = f"GID_{device_model}".replace(":", "_").replace(" ", "_")
                except Exception:
                    group_id = "GID_default"

                mac_address_safe = device_id.replace(":", "_")
                mqtt_client_id = f"{group_id}@@@{mac_address_safe}@@@{mac_address_safe}"
                user_data = {"ip": "unknown"}
                username = base64.b64encode(json.dumps(user_data).encode("utf-8")).decode("utf-8")
                password = ""
                sig_key = server_config.get("mqtt_signature_key", "")
                if sig_key:
                    password = self.generate_password_signature(f"{mqtt_client_id}|{username}", sig_key) or ""

                return_json["mqtt"] = {
                    "endpoint": mqtt_gateway_endpoint,
                    "client_id": mqtt_client_id,
                    "username": username,
                    "password": password,
                    "publish_topic": "device-server",
                    "subscribe_topic": f"devices/p2p/{mac_address_safe}",
                }
                self.logger.bind(tag=TAG).info(f"Cấp MQTT cho thiết bị active {device_id}")

            else:
                # Xử lý WebSocket
                if not is_active:
                    # Thiết bị CHƯA KÍCH HOẠT (Unbound): Tuyệt đối KHÔNG cấp token (Task 2.1 & 2.5)
                    bind_code = self._generate_bind_code(device_id)
                    return_json["bind_code"] = bind_code
                    return_json["activation_code"] = bind_code
                    return_json["websocket"] = {
                        "url": "",
                        "token": "",
                    }
                    self.logger.bind(tag=TAG).info(
                        f"🔒 [UNBOUND 2C] Thiết bị {device_id} chưa kích hoạt: Cấp PIN 6 số [{bind_code}], KHÔNG cấp token WebSocket."
                    )
                else:
                    # Thiết bị ĐÃ KÍCH HOẠT: Cấp 1 chuẩn AuthToken AES-GCM duy nhất (Task 2.2)
                    token = ""
                    if self.auth_enable:
                        token = self.auth_token_generator.generate_token(
                            device_id=device_id,
                            user_id=user_id or "user_default",
                            client_id=client_id,
                            expire_hours=720,  # 30 ngày (Task 2.1)
                            scope="voice,vision",
                        )
                    return_json["websocket"] = {
                        "url": self._get_websocket_url(local_ip, websocket_port),
                        "token": token,
                    }
                    self.logger.bind(tag=TAG).info(f"Cấp WebSocket + AuthToken AES-GCM cho thiết bị active {device_id}")

            # 4. Kiểm tra cập nhật Firmware & Ký URL Signed (Task 2.3)
            try:
                self._refresh_bin_cache_if_needed()
                files_by_model = self._bin_cache.get("files_by_model", {})
                candidates = files_by_model.get(device_model, [])

                chosen_url = ""
                chosen_version = device_version

                for ver, fname in candidates:
                    if _is_higher_version(ver, device_version):
                        chosen_version = ver
                        vision_url = get_vision_url(self.config)
                        base_dl_url = vision_url.replace("/mcp/vision/explain", f"/xiaozhi/ota/download/{fname}")

                        # Ký URL ngắn hạn TTL 10 phút (Task 2.3)
                        exp_ts = int(time.time()) + 600
                        sign_payload = f"{fname}:{exp_ts}"
                        sig = hmac.new(
                            self.secret_key.encode("utf-8"),
                            sign_payload.encode("utf-8"),
                            hashlib.sha256,
                        ).hexdigest()[:32]
                        chosen_url = f"{base_dl_url}?sign={sig}&exp={exp_ts}"
                        break

                if chosen_url:
                    return_json["firmware"]["version"] = chosen_version
                    return_json["firmware"]["url"] = chosen_url
                    self.logger.bind(tag=TAG).info(f"Hạ tải Signed URL firmware {chosen_version} cho {device_id}")

            except Exception as e:
                self.logger.bind(tag=TAG).error(f"Lỗi kiểm tra firmware: {e}")

            response = web.Response(
                text=json.dumps(return_json, separators=(",", ":")),
                content_type="application/json",
            )
        except Exception as e:
            self.logger.bind(tag=TAG).error(f"OTA POST xử lý ngoại lệ: {e}")
            return_json = {"success": False, "message": "request error."}
            response = web.Response(
                text=json.dumps(return_json, separators=(",", ":")),
                content_type="application/json",
            )
        finally:
            if response:
                self._add_cors_headers(response, request)
            return response

    async def handle_get(self, request):
        """Xử lý OTA GET kiểm tra trạng thái"""
        try:
            server_config = self.config["server"]
            local_ip = get_local_ip()
            websocket_port = int(server_config.get("port", 8000))
            websocket_url = self._get_websocket_url(local_ip, websocket_port)
            message = f"OTA接口运行正常，向设备发送的websocket地址是：{websocket_url}"
            response = web.Response(text=message, content_type="text/plain")
        except Exception as e:
            self.logger.bind(tag=TAG).error(f"OTA GET request error: {e}")
            response = web.Response(text="OTA接口异常", content_type="text/plain")
        finally:
            self._add_cors_headers(response, request)
            return response

    async def handle_download(self, request):
        """
        Tải firmware: Yêu cầu Signed URL ngắn hạn (TTL 10m) hoặc Bearer Token (Task 2.3).
        URL: /xiaozhi/ota/download/{filename}?sign=...&exp=...
        """
        try:
            fname = request.match_info.get("filename", "")
            if not fname:
                raise web.HTTPBadRequest(text="filename required")

            fname = _safe_basename(fname)
            if not re.match(r"^[A-Za-z0-9\.\-_]+\.bin$", fname):
                raise web.HTTPBadRequest(text="invalid filename format")

            # 1. Xác thực Signed URL hoặc Bearer Token (Task 2.3)
            sign = request.query.get("sign", "").strip()
            exp_str = request.query.get("exp", "").strip()

            if not sign or not exp_str:
                auth_hdr = request.headers.get("Authorization", "")
                if auth_hdr.startswith("Bearer "):
                    token = auth_hdr[7:].strip()
                    valid, _ = self.auth_token_generator.verify_token(token)
                    if not valid:
                        raise web.HTTPUnauthorized(text="Unauthorized: Invalid Bearer token")
                else:
                    raise web.HTTPUnauthorized(text="Unauthorized: Missing signed URL parameters (sign, exp)")
            else:
                try:
                    exp_val = int(exp_str)
                    if time.time() > exp_val:
                        raise web.HTTPForbidden(text="Forbidden: Signed download URL has expired")
                    sign_payload = f"{fname}:{exp_val}"
                    expected_sig = hmac.new(
                        self.secret_key.encode("utf-8"),
                        sign_payload.encode("utf-8"),
                        hashlib.sha256,
                    ).hexdigest()[:32]
                    if not hmac.compare_digest(sign, expected_sig):
                        raise web.HTTPForbidden(text="Forbidden: Invalid download signature")
                except ValueError:
                    raise web.HTTPBadRequest(text="Bad Request: Invalid exp timestamp")

            # 2. Truy xuất file nhị phân
            file_path = os.path.join(self.bin_dir, fname)
            file_real = os.path.realpath(file_path)
            bin_dir_real = os.path.realpath(self.bin_dir)
            if not file_real.startswith(bin_dir_real + os.sep) and file_real != bin_dir_real:
                raise web.HTTPForbidden(text="forbidden path traversal")

            if not os.path.isfile(file_real):
                raise web.HTTPNotFound(text="file not found")

            resp = web.FileResponse(path=file_real)
        except web.HTTPError as e:
            resp = e
        except Exception as e:
            self.logger.bind(tag=TAG).error(f"Lỗi tải firmware: {e}")
            resp = web.Response(text="download error", status=500)
        finally:
            try:
                self._add_cors_headers(resp, request)
            except Exception:
                pass
            return resp
