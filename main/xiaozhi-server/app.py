import os
import sys
import uuid
import signal
import asyncio
from aioconsole import ainput
from config.settings import load_config
from config.logger import setup_logging
from core.utils.util import get_local_ip, validate_mcp_endpoint
from core.http_server import SimpleHttpServer
from core.websocket_server import WebSocketServer
from core.utils.util import check_ffmpeg_installed
from core.utils.gc_manager import get_gc_manager

TAG = __name__
logger = setup_logging()


async def wait_for_exit() -> None:
    """
    阻塞直到收到 Ctrl‑C / SIGTERM。
    - Unix: 使用 add_signal_handler
    - Windows: 依赖 KeyboardInterrupt
    """
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    if sys.platform != "win32":  # Unix / macOS
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop_event.set)
        await stop_event.wait()
    else:
        # Windows：await一个永远pending的fut，
        # 让 KeyboardInterrupt 冒泡到 asyncio.run，以此消除遗留普通线程导致进程退出阻塞的问题
        try:
            await asyncio.Future()
        except KeyboardInterrupt:  # Ctrl‑C
            pass


async def monitor_stdin():
    """监控标准输入，消费回车键"""
    while True:
        await ainput()  # 异步等待输入，消费回车


async def main():
    check_ffmpeg_installed()
    config = await load_config()

    # Tải biến môi trường từ .env
    try:
        import os
        from dotenv import load_dotenv
        project_root_env = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
        if os.path.exists(project_root_env):
            load_dotenv(project_root_env)
        else:
            load_dotenv()
    except Exception:
        pass

    # auth_key ưu tiên: Biến môi trường SERVER_AUTH_KEY > file cấu hình server.auth_key > manager-api.secret
    env_auth_key = os.getenv("SERVER_AUTH_KEY", "").strip()
    config_auth_key = config.get("server", {}).get("auth_key", "").strip()
    manager_secret = config.get("manager-api", {}).get("secret", "").strip()

    if env_auth_key:
        auth_key = env_auth_key
    elif config_auth_key and "你" not in config_auth_key:
        auth_key = config_auth_key
    elif manager_secret and "你" not in manager_secret:
        auth_key = manager_secret
    else:
        # Cố định fallback key chuẩn (>= 32 bytes) thay vì sinh uuid.uuid4().hex ngẫu nhiên làm rớt token của thiết bị (Issue #3456)
        auth_key = "8f14e45fceea167a5a36dedd4bea254395cfb613a9607b0c39f1e16c90d63428"
        logger.warning(
            "CẢNH BÁO: Không tìm thấy SERVER_AUTH_KEY hợp lệ trong .env hoặc file cấu hình. "
            "Sử dụng khóa cố định fallback an toàn để tránh làm rớt token của thiết bị ESP32 (Vá Issue #3456)."
        )
    
    config["server"]["auth_key"] = auth_key
    env_server_secret = os.getenv("SERVER_SECRET", "").strip()
    config["server"]["secret"] = env_server_secret or config.get("server", {}).get("secret") or auth_key

    # 添加 stdin 监控任务
    stdin_task = asyncio.create_task(monitor_stdin())

    # 启动全局GC管理器（5分钟清理一次）
    gc_manager = get_gc_manager(interval_seconds=300)
    await gc_manager.start()

    # Hỗ trợ cấu hình cổng linh hoạt cho Cụm Multi-Worker (Giai đoạn 4)
    env_ws_port = os.getenv("PORT") or os.getenv("WS_PORT")
    if env_ws_port:
        config["server"]["port"] = int(env_ws_port)
    env_http_port = os.getenv("HTTP_PORT")
    if env_http_port:
        config["server"]["http_port"] = int(env_http_port)
    worker_id = os.getenv("WORKER_ID", f"worker_{config['server'].get('port', 8000)}")
    logger.bind(tag=TAG).info(
        f"🚀 Khởi động Voice Worker [{worker_id}] - WebSocket Port: {config['server'].get('port', 8000)}, HTTP Port: {config['server'].get('http_port', 8003)}"
    )

    # 启动 WebSocket 服务器
    ws_server = WebSocketServer(config)
    ws_task = asyncio.create_task(ws_server.start())
    # 启动 Simple http 服务器 (kết nối ws_server để phục vụ Real-time Kick API)
    ota_server = SimpleHttpServer(config, ws_server=ws_server)
    ota_task = asyncio.create_task(ota_server.start())

    read_config_from_api = config.get("read_config_from_api", False)
    port = int(config["server"].get("http_port", 8003))
    if not read_config_from_api:
        logger.bind(tag=TAG).info(
            "OTA接口是\t\thttp://{}:{}/xiaozhi/ota/",
            get_local_ip(),
            port,
        )
    logger.bind(tag=TAG).info(
        "视觉分析接口是\thttp://{}:{}/mcp/vision/explain",
        get_local_ip(),
        port,
    )
    mcp_endpoint = config.get("mcp_endpoint", None)
    if mcp_endpoint is not None:
        if isinstance(mcp_endpoint, list):
            valid_endpoints = []
            for ep in mcp_endpoint:
                if isinstance(ep, str) and "你" not in ep:
                    if validate_mcp_endpoint(ep):
                        ep_call = ep.replace("/mcp/", "/call/")
                        valid_endpoints.append(ep_call)
                        logger.bind(tag=TAG).info("mcp接入点是\t{}", ep_call)
                    else:
                        valid_endpoints.append(ep)
                        logger.bind(tag=TAG).info("mcp接入点是\t{}", ep)
            if valid_endpoints:
                config["mcp_endpoint"] = valid_endpoints
            else:
                logger.bind(tag=TAG).error("mcp接入点不符合规范")
                config["mcp_endpoint"] = "你的接入点 websocket地址"
        elif isinstance(mcp_endpoint, str) and "你" not in mcp_endpoint:
            if validate_mcp_endpoint(mcp_endpoint):
                logger.bind(tag=TAG).info("mcp接入点是\t{}", mcp_endpoint)
                mcp_endpoint = mcp_endpoint.replace("/mcp/", "/call/")
                config["mcp_endpoint"] = mcp_endpoint
            else:
                logger.bind(tag=TAG).error("mcp接入点不符合规范")
                config["mcp_endpoint"] = "你的接入点 websocket地址"

    # 获取WebSocket配置，使用安全的默认值
    websocket_port = 8000
    server_config = config.get("server", {})
    if isinstance(server_config, dict):
        websocket_port = int(server_config.get("port", 8000))

    logger.bind(tag=TAG).info(
        "Websocket地址是\tws://{}:{}/xiaozhi/v1/",
        get_local_ip(),
        websocket_port,
    )

    logger.bind(tag=TAG).info(
        "=======上面的地址是websocket协议地址，请勿用浏览器访问======="
    )
    logger.bind(tag=TAG).info(
        "如想测试websocket请启动digital-human模块，打开浏览器交互测试"
    )
    logger.bind(tag=TAG).info(
        "=============================================================\n"
    )

    try:
        await wait_for_exit()  # 阻塞直到收到退出信号
    except asyncio.CancelledError:
        print("任务被取消，清理资源中...")
    finally:
        # 停止TTS Keep-Warm Daemon
        if hasattr(ws_server, "_tts") and ws_server._tts and hasattr(ws_server._tts, "stop_keep_warm"):
            try:
                await ws_server._tts.stop_keep_warm()
            except Exception:
                pass

        # 停止全局GC管理器
        await gc_manager.stop()

        # 取消所有任务（关键修复点）
        stdin_task.cancel()
        ws_task.cancel()
        if ota_task:
            ota_task.cancel()

        # 等待任务终止（必须加超时）
        await asyncio.wait(
            [stdin_task, ws_task, ota_task] if ota_task else [stdin_task, ws_task],
            timeout=3.0,
            return_when=asyncio.ALL_COMPLETED,
        )
        print("服务器已关闭，程序退出。")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("手动中断，程序终止。")
