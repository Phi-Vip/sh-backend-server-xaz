import os
import json
import asyncio
import yaml
from collections.abc import Mapping
try:
    from dotenv import load_dotenv
    # Nạp file .env từ thư mục gốc dự án
    _server_root_env = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "..", ".env"))
    if os.path.exists(_server_root_env):
        load_dotenv(_server_root_env)
    else:
        load_dotenv()
except ImportError:
    pass
from config.manage_api_client import (
    init_service,
    get_server_config,
    get_agent_models,
    get_correct_words,
    DeviceNotFoundException,
    DeviceBindException,
)


def get_project_dir():
    """获取项目根目录"""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + "/"


def read_config(config_path):
    with open(config_path, "r", encoding="utf-8") as file:
        config = yaml.safe_load(file)
    return config


async def load_config():
    """加载配置文件"""
    from core.utils.cache.manager import cache_manager, CacheType

    # 检查缓存
    cached_config = cache_manager.get(CacheType.CONFIG, "main_config")
    if cached_config is not None:
        return cached_config

    default_config_path = get_project_dir() + "config.yaml"
    custom_config_path = get_project_dir() + "data/.config.yaml"

    # 加载默认配置
    default_config = read_config(default_config_path)
    custom_config = read_config(custom_config_path)

    # Hợp nhất cấu hình nền tảng giữa default_config và custom_config (data/.config.yaml)
    base_config = merge_configs(default_config, custom_config)

    if custom_config.get("manager-api", {}).get("url"):
        try:
            api_config = await get_config_from_api_async(custom_config)
            # Hợp nhất cấu hình API lên trên base_config (giữ nguyên selected_module, AI providers từ local)
            config = merge_configs(base_config, api_config)
        except Exception as e:
            print(f"Không thể lấy cấu hình từ manager-api ({e}), tự động fallback cấu hình cục bộ.")
            config = base_config
    else:
        # Hợp nhất cấu hình
        config = base_config
    # Đảm bảo server.auth_key và server.secret lấy từ biến môi trường nếu có
    env_auth_key = os.getenv("SERVER_AUTH_KEY", "").strip()
    if env_auth_key:
        config.setdefault("server", {})["auth_key"] = env_auth_key
    env_server_secret = os.getenv("SERVER_SECRET", "").strip()
    if env_server_secret:
        config.setdefault("server", {})["secret"] = env_server_secret

    # 初始化目录
    ensure_directories(config)

    # 缓存配置
    cache_manager.set(CacheType.CONFIG, "main_config", config)
    return config


async def get_config_from_api_async(config):
    """从Java API获取配置（异步版本）"""
    # 初始化API客户端
    init_service(config)

    # 获取服务器配置
    config_data = await get_server_config()
    if config_data is None:
        raise Exception("Failed to fetch server config from API")

    config_data["read_config_from_api"] = True
    config_data["manager-api"] = {
        "url": config["manager-api"].get("url", ""),
        "secret": config["manager-api"].get("secret", ""),
    }
    auth_enabled = config_data.get("server", {}).get("auth", {}).get("enabled", False)
    # server的配置以本地为准, deep-merge nhánh server.auth để không mất expire_seconds, issued_after
    local_server = config.get("server", {})
    if local_server:
        config_data.setdefault("server", {})
        for k, v in local_server.items():
            if k == "auth" and isinstance(v, dict):
                config_data["server"].setdefault("auth", {})
                config_data["server"]["auth"].update(v)
            else:
                config_data["server"][k] = v
    if "auth" not in config_data.get("server", {}):
        config_data.setdefault("server", {})["auth"] = {"enabled": auth_enabled}
    else:
        config_data["server"]["auth"].setdefault("enabled", auth_enabled)
    # Nếu API không trả về log, kế thừa từ cấu hình cục bộ
    if "log" not in config_data:
        config_data["log"] = config.get("log", {})
    # 如果服务器没有prompt_template，则从本地配置读取
    if not config_data.get("prompt_template"):
        config_data["prompt_template"] = config.get("prompt_template")
    return config_data


# Client Redis kết nối cache cấu hình Agent (Task 3.2 - Giai đoạn 3)
_redis_agent_cache_client = None


def get_redis_agent_cache_client():
    global _redis_agent_cache_client
    if _redis_agent_cache_client is None:
        try:
            import redis.asyncio as aioredis
            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
            _redis_agent_cache_client = aioredis.from_url(
                redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=0.2,
                socket_timeout=0.2,
            )
        except Exception:
            _redis_agent_cache_client = None
    return _redis_agent_cache_client


async def invalidate_agent_config_cache(device_id: str) -> int:
    """Xóa bỏ cache Redis cấu hình Agent khi người dùng đổi tên/giọng đọc trên Web Portal/App (Task 3.2)."""
    if not device_id:
        return 0
    clean_id = device_id.replace("-", ":").lower().strip()
    keys_to_del = {
        f"xiaozhi:agent_cfg:{clean_id}",
        f"xiaozhi:agent_cfg:{device_id.strip()}",
    }
    client = get_redis_agent_cache_client()
    if client:
        try:
            deleted = await client.delete(*keys_to_del)
            return deleted
        except Exception:
            pass
    return 0


async def get_private_config_from_api(config, device_id, client_id):
    """Lấy cấu hình Agent động riêng biệt theo thiết bị từ Manager API kèm Lớp Cache Redis 120s (Task 3.2).
    
    Chống hiện tượng bão request (thundering herd) khi 1.000 loa kết nối lại cùng một lúc.
    """
    clean_id = (device_id or "").replace("-", ":").lower().strip()
    cache_key = f"xiaozhi:agent_cfg:{clean_id}"
    redis_client = get_redis_agent_cache_client()

    # 1. Kiểm tra Lớp Cache Redis (TTL 120s): Nếu trúng cache, trả về ngay lập tức (< 2ms)
    if redis_client and clean_id:
        try:
            cached_val = await redis_client.get(cache_key)
            if cached_val:
                cached_data = json.loads(cached_val)
                return cached_data
        except Exception:
            pass

    # 2. Cache miss: Gọi API lấy cấu hình động từ Manager API
    results = await asyncio.gather(
        get_agent_models(device_id, client_id, config["selected_module"]),
        get_correct_words(device_id),
        return_exceptions=True,
    )
    agent_result = results[0]
    correct_words = results[1] if not isinstance(results[1], Exception) else None

    # 抛出业务异常
    if isinstance(agent_result, DeviceNotFoundException):
        raise agent_result
    if isinstance(agent_result, DeviceBindException):
        raise agent_result

    private_config = agent_result if not isinstance(agent_result, Exception) else {}
    if correct_words:
        private_config["correct_words"] = correct_words

    # 3. Ghi vào Cache Redis với TTL 120 giây
    if redis_client and clean_id and private_config:
        try:
            await redis_client.set(cache_key, json.dumps(private_config, ensure_ascii=False), ex=120)
        except Exception:
            pass

    return private_config


def ensure_directories(config):
    """确保所有配置路径存在"""
    dirs_to_create = set()
    project_dir = get_project_dir()  # 获取项目根目录
    # 日志文件目录
    log_dir = config.get("log", {}).get("log_dir", "tmp")
    dirs_to_create.add(os.path.join(project_dir, log_dir))

    # ASR/TTS模块输出目录
    for module in ["ASR", "TTS"]:
        if config.get(module) is None:
            continue
        for provider in config.get(module, {}).values():
            output_dir = provider.get("output_dir", "")
            if output_dir:
                dirs_to_create.add(output_dir)

    # 根据selected_module创建模型目录
    selected_modules = config.get("selected_module", {})
    for module_type in ["ASR", "LLM", "TTS"]:
        selected_provider = selected_modules.get(module_type)
        if not selected_provider:
            continue
        if config.get(module_type) is None:
            continue
        if config.get(selected_provider) is None:
            continue
        provider_config = config.get(module_type, {}).get(selected_provider, {})
        output_dir = provider_config.get("output_dir")
        if output_dir:
            full_model_dir = os.path.join(project_dir, output_dir)
            dirs_to_create.add(full_model_dir)

    # 统一创建目录（保留原data目录创建）
    for dir_path in dirs_to_create:
        try:
            os.makedirs(dir_path, exist_ok=True)
        except PermissionError:
            print(f"警告：无法创建目录 {dir_path}，请检查写入权限")


def merge_configs(default_config, custom_config):
    """
    递归合并配置，custom_config优先级更高

    Args:
        default_config: 默认配置
        custom_config: 用户自定义配置

    Returns:
        合并后的配置
    """
    if not isinstance(default_config, Mapping) or not isinstance(
        custom_config, Mapping
    ):
        return custom_config

    merged = dict(default_config)

    for key, value in custom_config.items():
        if (
            key in merged
            and isinstance(merged[key], Mapping)
            and isinstance(value, Mapping)
        ):
            merged[key] = merge_configs(merged[key], value)
        else:
            merged[key] = value

    return merged
