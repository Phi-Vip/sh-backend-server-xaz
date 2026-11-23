import re
import httpx
from config.logger import setup_logging
from plugins_func.register import register_function, ToolType, ActionResponse, Action
from core.utils.util import get_ip_info
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from core.connection import ConnectionHandler

TAG = __name__
logger = setup_logging()

GET_WEATHER_FUNCTION_DESC = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": (
            "Tra cứu dự báo thời tiết hiện tại và các ngày tới cho một địa điểm cụ thể (thành phố, tỉnh thành, quận huyện tại Việt Nam hoặc quốc tế). "
            "Ví dụ: Hà Nội, Sài Gòn, TP.HCM, Đà Nẵng, Hải Phòng, Cần Thơ, Tokyo, Paris, v.v. "
            "Nếu người dùng hỏi chung chung như 'thời tiết hôm nay thế nào', 'trời có mưa không' mà không nói địa điểm thì để trống tham số location."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "Tên địa điểm, thành phố hoặc tỉnh thành cần tra cứu. Ví dụ: 'Hà Nội', 'Sài Gòn', 'Đà Nẵng'. Để trống nếu muốn tra cứu thời tiết tại vị trí hiện tại.",
                },
            },
            "required": [],
        },
    },
}

# Bảng chuẩn hóa tên gọi các thành phố / tỉnh thành phổ biến tại Việt Nam
CITY_ALIASES = {
    "sài gòn": "Thành phố Hồ Chí Minh",
    "sai gon": "Thành phố Hồ Chí Minh",
    "saigon": "Thành phố Hồ Chí Minh",
    "tphcm": "Thành phố Hồ Chí Minh",
    "tp hcm": "Thành phố Hồ Chí Minh",
    "tp.hcm": "Thành phố Hồ Chí Minh",
    "tp. hcm": "Thành phố Hồ Chí Minh",
    "hcm": "Thành phố Hồ Chí Minh",
    "hồ chí minh": "Thành phố Hồ Chí Minh",
    "ho chi minh": "Thành phố Hồ Chí Minh",
    "hn": "Hà Nội",
    "hà nội": "Hà Nội",
    "ha noi": "Hà Nội",
    "hanoi": "Hà Nội",
    "đà nẵng": "Đà Nẵng",
    "da nang": "Đà Nẵng",
    "danang": "Đà Nẵng",
    "hải phòng": "Hải Phòng",
    "hai phong": "Hải Phòng",
    "cần thơ": "Cần Thơ",
    "can tho": "Cần Thơ",
    "nha trang": "Nha Trang",
    "đà lạt": "Đà Lạt",
    "da lat": "Đà Lạt",
    "huế": "Huế",
    "hue": "Huế",
    "thừa thiên huế": "Huế",
    "vũng tàu": "Vũng Tàu",
    "vung tau": "Vũng Tàu",
    "bà rịa vũng tàu": "Vũng Tàu",
    "quy nhơn": "Quy Nhơn",
    "quy nhon": "Quy Nhơn",
    "buôn ma thuột": "Buôn Ma Thuột",
    "buon ma thuot": "Buôn Ma Thuột",
    "bmt": "Buôn Ma Thuột",
    "bình dương": "Bình Dương",
    "binh duong": "Bình Dương",
    "đồng nai": "Đồng Nai",
    "dong nai": "Đồng Nai",
    "quảng ninh": "Quảng Ninh",
    "hạ long": "Hạ Long",
    "ha long": "Hạ Long",
    "thanh hóa": "Thanh Hóa",
    "thanh hoa": "Thanh Hóa",
    "nghệ an": "Nghệ An",
    "vinh": "Vinh",
}

# Mã diễn giải thời tiết WMO chuẩn quốc tế sang tiếng Việt tự nhiên
WMO_WEATHER_MAP = {
    0: "Trời quang đãng, nắng đẹp",
    1: "Trời hầu như quang đãng",
    2: "Trời có mây rải rác",
    3: "Trời nhiều mây, u ám",
    45: "Có sương mù",
    48: "Sương mù lạnh",
    51: "Mưa phùn nhẹ rải rác",
    53: "Mưa phùn vừa",
    55: "Mưa phùn dày hạt",
    56: "Mưa phùn buốt giá nhẹ",
    57: "Mưa phùn buốt giá dày",
    61: "Mưa rào nhẹ",
    63: "Mưa vừa",
    65: "Mưa to, mưa lớn",
    66: "Mưa lạnh đóng băng nhẹ",
    67: "Mưa lạnh đóng băng nặng hạt",
    71: "Tuyết rơi nhẹ",
    73: "Tuyết rơi vừa",
    75: "Tuyết rơi dày",
    77: "Hạt tuyết rơi",
    80: "Mưa rào thoáng qua",
    81: "Mưa rào rải rác",
    82: "Mưa rào rất to",
    85: "Mưa tuyết rào nhẹ",
    86: "Mưa tuyết rào to",
    95: "Có dông sét",
    96: "Dông sét kèm mưa đá nhẹ",
    99: "Dông bão mạnh kèm mưa đá",
}

DEFAULT_TIMEOUT = httpx.Timeout(6.0, connect=3.0)


def normalize_location(location: Optional[str]) -> str:
    """Chuẩn hóa tên địa điểm theo tiếng Việt"""
    if not location:
        return ""
    cleaned = location.strip().strip("'\"").strip()
    lower = cleaned.lower()
    return CITY_ALIASES.get(lower, cleaned)


def get_weather_cache_key(location: Optional[str]) -> str:
    """Tạo khóa định danh chuẩn (Canonical Key) cho bộ nhớ đệm thời tiết"""
    normalized = normalize_location(location)
    clean = re.sub(r"\s+", "_", normalized.lower().strip())
    return f"weather:{clean}"


async def fetch_open_meteo_weather(location: str) -> Optional[str]:
    """Lấy dữ liệu thời tiết thời gian thực và dự báo từ Open-Meteo API"""
    search_query = normalize_location(location)
    if not search_query:
        return None

    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            # 1. Geocoding API: Tìm tọa độ kinh/vĩ độ
            geo_url = "https://geocoding-api.open-meteo.com/v1/search"
            geo_params = {
                "name": search_query,
                "count": 5,
                "language": "vi",
                "format": "json",
            }
            geo_resp = await client.get(geo_url, params=geo_params)
            if geo_resp.status_code != 200:
                logger.bind(tag=TAG).warning(f"Geocoding error HTTP {geo_resp.status_code}")
                return None

            geo_data = geo_resp.json()
            results = geo_data.get("results", [])
            if not results:
                return None

            # Ưu tiên tìm địa điểm tại Việt Nam nếu có
            chosen = results[0]
            for r in results:
                if r.get("country_code") == "VN" or r.get("country") == "Việt Nam":
                    chosen = r
                    break

            city_name = chosen.get("name", search_query)
            admin1 = chosen.get("admin1", "")
            country = chosen.get("country", "")
            lat = chosen.get("latitude")
            lon = chosen.get("longitude")

            # 2. Forecast API: Dự báo thời tiết hiện tại và 7 ngày tới
            fc_url = "https://api.open-meteo.com/v1/forecast"
            fc_params = {
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m",
                "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                "timezone": "Asia/Bangkok",
            }
            fc_resp = await client.get(fc_url, params=fc_params)
            if fc_resp.status_code != 200:
                logger.bind(tag=TAG).warning(f"Forecast error HTTP {fc_resp.status_code}")
                return None

            fc_data = fc_resp.json()
            current = fc_data.get("current", {})
            daily = fc_data.get("daily", {})

            c_temp = current.get("temperature_2m", 0)
            c_app = current.get("apparent_temperature", c_temp)
            c_hum = current.get("relative_humidity_2m", 0)
            c_wind = current.get("wind_speed_10m", 0)
            c_precip = current.get("precipitation", 0)
            c_code = current.get("weather_code", 0)
            c_desc = WMO_WEATHER_MAP.get(c_code, "Thời tiết bình thường")

            full_loc_name = f"{city_name}"
            if admin1 and admin1 != city_name:
                full_loc_name += f", {admin1}"
            if country:
                full_loc_name += f", {country}"

            report_lines = [
                f"Thông tin thời tiết tại {full_loc_name}:",
                f"- Hiện tại: {c_desc}. Nhiệt độ: {round(c_temp)}°C (cảm nhận như {round(c_app)}°C). Độ ẩm: {c_hum}%. Tốc độ gió: {round(c_wind)} km/h. Lượng mưa hiện tại: {c_precip} mm.",
            ]

            # Thêm dự báo các ngày tới
            dates = daily.get("time", [])
            codes = daily.get("weather_code", [])
            max_temps = daily.get("temperature_2m_max", [])
            min_temps = daily.get("temperature_2m_min", [])
            rain_probs = daily.get("precipitation_probability_max", [])

            if dates:
                report_lines.append("- Dự báo các ngày tới:")
                for i in range(min(4, len(dates))):
                    d_date = dates[i]
                    d_desc = WMO_WEATHER_MAP.get(codes[i] if i < len(codes) else 0, "Thời tiết ổn định")
                    d_max = round(max_temps[i]) if i < len(max_temps) else 0
                    d_min = round(min_temps[i]) if i < len(min_temps) else 0
                    d_rain = rain_probs[i] if i < len(rain_probs) else 0

                    label = "Hôm nay" if i == 0 else ("Ngày mai" if i == 1 else f"Ngày {d_date}")
                    report_lines.append(
                        f"  + {label} ({d_date}): {d_desc}, nhiệt độ {d_min}°C - {d_max}°C, khả năng mưa {d_rain}%."
                    )

            return "\n".join(report_lines)

    except Exception as e:
        logger.bind(tag=TAG).error(f"Lỗi khi gọi Open-Meteo cho {location}: {e}")
        return None


async def fetch_wttr_in_fallback(location: str) -> Optional[str]:
    """Dự phòng qua wttr.in nếu Open-Meteo gặp sự cố mạng"""
    search_query = normalize_location(location)
    if not search_query:
        return None

    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            url = f"https://wttr.in/{search_query}?format=j1"
            resp = await client.get(url)
            if resp.status_code != 200:
                return None
            data = resp.json()
            curr = data.get("current_condition", [{}])[0]
            temp = curr.get("temp_C", "N/A")
            feels = curr.get("FeelsLikeC", temp)
            humidity = curr.get("humidity", "N/A")
            desc = curr.get("weatherDesc", [{}])[0].get("value", "Bình thường")
            return (
                f"Thông tin thời tiết tại {search_query}:\n"
                f"- Hiện tại: {desc}. Nhiệt độ: {temp}°C (cảm nhận như {feels}°C). Độ ẩm: {humidity}%."
            )
    except Exception as e:
        logger.bind(tag=TAG).warning(f"wttr.in fallback failed: {e}")
        return None


@register_function("get_weather", GET_WEATHER_FUNCTION_DESC, ToolType.SYSTEM_CTL)
async def get_weather(conn: "ConnectionHandler", location: str = None, **kwargs):
    """Lấy dự báo thời tiết cho thiết bị và LLM"""
    from core.utils.cache.manager import cache_manager, CacheType

    weather_config = conn.config.get("plugins", {}).get("get_weather", {})
    default_location = weather_config.get("default_location", "Hà Nội")
    client_ip = getattr(conn, "client_ip", None)

    # 1. Xác định địa điểm cần truy vấn
    target_location = location
    if not target_location or str(target_location).strip().lower() in [
        "none",
        "null",
        "vị trí hiện tại",
        "địa phương",
        "nơi này",
        "未知位置",
        "未知",
        "unknown",
    ]:
        target_location = None

    if not target_location:
        # Nếu không có tham số, thử lấy từ IP thiết bị
        if client_ip:
            cached_ip_info = cache_manager.get(CacheType.IP_INFO, client_ip)
            if cached_ip_info and isinstance(cached_ip_info, dict):
                target_location = cached_ip_info.get("city")
            else:
                ip_info = get_ip_info(client_ip, logger)
                if ip_info and isinstance(ip_info, dict):
                    cache_manager.set(CacheType.IP_INFO, client_ip, ip_info)
                    target_location = ip_info.get("city")

        if not target_location or target_location in ["未知位置", "未知", "unknown"]:
            target_location = default_location

    target_location = str(target_location).strip()
    normalized_loc = normalize_location(target_location)
    canonical_key = get_weather_cache_key(target_location)

    # 2. Kiểm tra bộ nhớ đệm (Cache) theo Canonical Key trước
    cached_report = cache_manager.get(CacheType.WEATHER, canonical_key)
    if not cached_report:
        # Fallback kiểm tra các key cũ (backward compatibility)
        cached_report = (
            cache_manager.get(CacheType.WEATHER, f"weather_{target_location.lower()}")
            or cache_manager.get(CacheType.WEATHER, target_location)
            or cache_manager.get(CacheType.WEATHER, normalized_loc)
        )

    if cached_report:
        logger.bind(tag=TAG).info(
            f"Đã lấy thời tiết từ cache cho '{target_location}' -> '{normalized_loc}' (key={canonical_key})"
        )
        return ActionResponse(Action.REQLLM, cached_report, None)

    # 3. Gọi Open-Meteo API
    logger.bind(tag=TAG).info(f"Đang tra cứu thời tiết thời gian thực cho: {normalized_loc}")
    weather_report = await fetch_open_meteo_weather(normalized_loc)

    # 4. Nếu Open-Meteo lỗi mạng, kích hoạt wttr.in làm phương án dự phòng
    if not weather_report:
        weather_report = await fetch_wttr_in_fallback(normalized_loc)

    # 5. Nếu cả 2 đều không tìm thấy địa điểm
    if not weather_report:
        msg = f"Rất tiếc, hiện tại không tìm thấy thông tin thời tiết cho địa điểm '{target_location}'. Vui lòng thử lại với tên thành phố cụ thể."
        return ActionResponse(Action.REQLLM, msg, None)

    # 6. Lưu vào cache trong 30 phút (1800 giây)
    cache_manager.set(CacheType.WEATHER, canonical_key, weather_report, ttl=1800)
    # Lưu thêm alias để tương thích ngược 100%
    cache_manager.set(CacheType.WEATHER, normalized_loc, weather_report, ttl=1800)
    cache_manager.set(CacheType.WEATHER, f"weather_{target_location.lower()}", weather_report, ttl=1800)

    return ActionResponse(Action.REQLLM, weather_report, None)
