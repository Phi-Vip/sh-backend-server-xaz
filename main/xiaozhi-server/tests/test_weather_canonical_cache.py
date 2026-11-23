# -*- coding: utf-8 -*-
"""
Bộ kiểm thử tự động cho Giai đoạn 1: Chuẩn hóa Weather Cache & Bảo toàn Prompt Cache LLM
"""

import sys
import os
import asyncio
from unittest.mock import patch, MagicMock

# Thêm đường dẫn mã nguồn xiaozhi-server vào sys.path
SERVER_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_ROOT not in sys.path:
    sys.path.insert(0, SERVER_ROOT)

from plugins_func.functions.get_weather import (
    normalize_location,
    get_weather_cache_key,
    get_weather,
)
from core.utils.cache.manager import cache_manager, CacheType
from core.utils.cache.config import CacheConfig


def test_location_normalization_aliases():
    """Kiểm tra bảng chuẩn hóa địa danh tiếng Việt (CITY_ALIASES)"""
    assert normalize_location("hn") == "Hà Nội"
    assert normalize_location("HN") == "Hà Nội"
    assert normalize_location("ha noi") == "Hà Nội"
    assert normalize_location("hanoi") == "Hà Nội"
    assert normalize_location("hà nội") == "Hà Nội"
    assert normalize_location("Hà Nội") == "Hà Nội"

    assert normalize_location("sài gòn") == "Thành phố Hồ Chí Minh"
    assert normalize_location("sai gon") == "Thành phố Hồ Chí Minh"
    assert normalize_location("tphcm") == "Thành phố Hồ Chí Minh"
    assert normalize_location("tp hcm") == "Thành phố Hồ Chí Minh"
    assert normalize_location("hồ chí minh") == "Thành phố Hồ Chí Minh"

    assert normalize_location("đà nẵng") == "Đà Nẵng"
    assert normalize_location("da nang") == "Đà Nẵng"
    assert normalize_location("hải phòng") == "Hải Phòng"
    assert normalize_location("cần thơ") == "Cần Thơ"


def test_canonical_cache_key_generation():
    """Kiểm tra các biến thể câu chữ của cùng một thành phố đều sinh ra duy nhất một Canonical Cache Key"""
    hn_key = get_weather_cache_key("Hà Nội")
    assert hn_key == "weather:hà_nội"
    assert get_weather_cache_key("hn") == hn_key
    assert get_weather_cache_key("HN") == hn_key
    assert get_weather_cache_key("ha noi") == hn_key
    assert get_weather_cache_key("hanoi") == hn_key
    assert get_weather_cache_key("  hà nội  ") == hn_key

    sg_key = get_weather_cache_key("Thành phố Hồ Chí Minh")
    assert sg_key == "weather:thành_phố_hồ_chí_minh"
    assert get_weather_cache_key("sài gòn") == sg_key
    assert get_weather_cache_key("sai gon") == sg_key
    assert get_weather_cache_key("tphcm") == sg_key
    assert get_weather_cache_key("tp.hcm") == sg_key
    assert get_weather_cache_key("hcm") == sg_key


def test_cache_config_weather_ttl():
    """Kiểm tra cấu hình mặc định TTL của Weather Cache đã được chuẩn hóa về 1800 giây (30 phút)"""
    cfg = CacheConfig.for_type(CacheType.WEATHER)
    assert cfg.ttl == 1800, f"TTL phải là 1800s nhưng nhận được {cfg.ttl}"
    assert cfg.max_size == 500


def test_agent_base_prompt_static_context():
    """Kiểm tra agent-base-prompt.txt đã tách weather_info ra khỏi System Prompt tĩnh"""
    prompt_file = os.path.join(SERVER_ROOT, "agent-base-prompt.txt")
    with open(prompt_file, "r", encoding="utf-8") as f:
        content = f.read()

    assert "{{weather_info}}" not in content, "weather_info không được xuất hiện trong System Prompt để tránh làm vỡ KV-Cache!"
    assert "check weather → get_weather" in content, "Chỉ thị gọi tool get_weather phải rõ ràng"


async def async_test_weather_cache_hit_flow():
    """Kiểm tra thực tế luồng Cache Hit: Gọi 'hn' rồi gọi 'Hà Nội' phải đạt Cache Hit 100% không gọi lại API"""
    mock_conn = MagicMock()
    mock_conn.config = {"plugins": {"get_weather": {"default_location": "Hà Nội"}}}
    mock_conn.client_ip = "127.0.0.1"

    mock_report = "Thông tin thời tiết tại Hà Nội: 28°C, trời nắng đẹp."

    # Xóa sạch cache test trước khi chạy
    canonical_key = get_weather_cache_key("hn")
    cache_manager.delete(CacheType.WEATHER, canonical_key)
    cache_manager.delete(CacheType.WEATHER, "Hà Nội")

    with patch("plugins_func.functions.get_weather.fetch_open_meteo_weather") as mock_fetch:
        mock_fetch.return_value = mock_report

        # LƯỢT 1: Người dùng hỏi 'hn' -> Cache Miss -> Phải gọi mock_fetch 1 lần
        resp1 = await get_weather(mock_conn, location="hn")
        assert resp1.result == mock_report
        assert mock_fetch.call_count == 1, "Lượt 1 phải gọi API do Cache Miss"

        # Kiểm tra canonical key đã được lưu vào cache
        cached_val = cache_manager.get(CacheType.WEATHER, canonical_key)
        assert cached_val == mock_report, "Canonical key phải được lưu trong cache"

        # LƯỢT 2: Người dùng khác hỏi 'Hà Nội' -> Phải CACHE HIT 100%!
        resp2 = await get_weather(mock_conn, location="Hà Nội")
        assert resp2.result == mock_report
        assert mock_fetch.call_count == 1, "Lượt 2 phải lấy từ cache, KHÔNG ĐƯỢC gọi API lần thứ 2!"

        # LƯỢT 3: Người dùng khác hỏi 'ha noi' -> Phải CACHE HIT 100%!
        resp3 = await get_weather(mock_conn, location="ha noi")
        assert resp3.result == mock_report
        assert mock_fetch.call_count == 1, "Lượt 3 phải lấy từ cache, KHÔNG ĐƯỢC gọi API!"

        # LƯỢT 4: Người dùng khác hỏi 'hanoi' -> Phải CACHE HIT 100%!
        resp4 = await get_weather(mock_conn, location="hanoi")
        assert resp4.result == mock_report
        assert mock_fetch.call_count == 1, "Lượt 4 phải lấy từ cache, KHÔNG ĐƯỢC gọi API!"


def test_weather_cache_hit_flow_runner():
    asyncio.run(async_test_weather_cache_hit_flow())


if __name__ == "__main__":
    print("=== ĐANG CHẠY BỘ TEST GIAI ĐOẠN 1 ===")
    test_location_normalization_aliases()
    print("✓ [PASS] Chuẩn hóa địa danh (CITY_ALIASES)")
    test_canonical_cache_key_generation()
    print("✓ [PASS] Sinh Canonical Cache Key đồng nhất (get_weather_cache_key)")
    test_cache_config_weather_ttl()
    print("✓ [PASS] Cấu hình TTL 1800s cho Weather Cache")
    test_agent_base_prompt_static_context()
    print("✓ [PASS] Bảo toàn System Prompt tĩnh (Không chứa weather_info)")
    test_weather_cache_hit_flow_runner()
    print("✓ [PASS] Luồng Cache Hit 100% giữa 'hn', 'Hà Nội', 'ha noi', 'hanoi'")
    print("=== TẤT CẢ 5/5 TEST CASE GIAI ĐOẠN 1 ĐÃ PASS HOÀN TOÀN! ===")
