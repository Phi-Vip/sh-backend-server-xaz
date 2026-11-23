"""
Unit test suite for Phase 2: Sunhouse Live Search MCP Tool Canonical Caching & LRU Eviction
Covers:
1. Canonical Model Extraction (ASR phonetics, prefix mapping, exact matches)
2. Two-Key Indexing (Query key + Canonical Model key) cross-query cache hit
3. Negative Caching (empty_model, empty_query to prevent scraping storms)
4. LRU Eviction & bounded memory (OrderedDict MAX_CACHE_SIZE = 1000)
5. Clean TTS Text (removing markdown, bullets, and weird characters)
6. TTL Expiration logic
"""

import sys
import os
import time
import asyncio
from unittest.mock import patch

# Add mcp_sunhouse_rag path to sys.path so tool can be imported
server_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
mcp_server_dir = os.path.join(server_root, "mcp_sunhouse_rag")
if mcp_server_dir not in sys.path:
    sys.path.insert(0, mcp_server_dir)

from tools.sunhouse_live_search_tool import (
    extract_canonical_model,
    normalize_asr_phonetics,
    generate_model_candidates,
    _clean_tts_text,
    _get_cache,
    _set_cache,
    clear_cache,
    get_cache_stats,
    _scrape_sunhouse_model_spec,
    _fallback_web_search,
    MAX_CACHE_SIZE,
    CACHE_TTL_MODEL,
    CACHE_TTL_QUERY,
    CACHE_TTL_NEGATIVE,
)


def setup_function():
    """Ensure clean cache before every test."""
    clear_cache()


def teardown_function():
    """Ensure clean cache after every test."""
    clear_cache()


def test_canonical_model_extraction():
    """Test Case: Extracting canonical model from varied queries."""
    # 1. Exact model code
    assert extract_canonical_model("SHD6805") == "SHD6805"
    assert extract_canonical_model("thông số bếp từ đơn SHD6805") == "SHD6805"

    # 2. Model code with spacing and punctuation
    assert extract_canonical_model("bếp SHD 6805") == "SHD6805"
    assert extract_canonical_model("bếp SHD-6805") == "SHD6805"

    # 3. ASR phonetic normalization (ét hát đê -> SHD)
    assert extract_canonical_model("thông số ét hát đê 6805") == "SHD6805"
    assert extract_canonical_model("sờ hát đê 7737") == "SHD7737"

    # 4. Category + digits inference
    assert extract_canonical_model("bếp từ 6805") == "SHD6805"
    assert extract_canonical_model("quạt 7737") == "SHD7737"
    assert extract_canonical_model("quạt điều hòa 7737") == "SHD7737"
    assert extract_canonical_model("bếp từ đôi 9101") == "SHB9101"
    assert extract_canonical_model("máy lọc nước 76688") == "SHA76688"

    # 5. Non-model query
    assert extract_canonical_model("tin tức sunhouse") is None
    assert extract_canonical_model("") is None


def test_clean_tts_text():
    """Test Case 2.2: Ensure TTS text is completely stripped of markdown and weird symbols."""
    raw_markdown = "## Thông số kỹ thuật cho **Bếp từ SHD6805**:\n- Công suất: 2000W\n• Mặt kính: Ceramic\n[Xem thêm](http://sunhouse.com.vn)"
    cleaned = _clean_tts_text(raw_markdown)

    assert "**" not in cleaned
    assert "##" not in cleaned
    assert "•" not in cleaned
    assert "[" not in cleaned
    assert "]" not in cleaned
    assert "\n" not in cleaned
    assert "Thông số kỹ thuật cho Bếp từ SHD6805 : - Công suất: 2000W Mặt kính: Ceramic Xem thêm http://sunhouse.com.vn" == cleaned


async def async_two_key_indexing_test():
    """Test Case 2.1: Lần 1 hỏi 'Thông số bếp từ 6805', Lần 2 hỏi 'Bếp SHD 6805 giá bao nhiêu', Lần 3 hỏi 'SHD6805'."""
    call_count = 0

    class MockResponse:
        def __init__(self, status, text):
            self.status = status
            self._text = text

        async def text(self):
            return self._text

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    search_html = """
    <html>
        <div class="item-infos">
            <a class="item-title" href="https://sunhouse.com.vn/bep-dien-tu/sunhouse-shd6805">Bếp điện từ SUNHOUSE SHD6805</a>
        </div>
    </html>
    """

    detail_html = """
    <html>
        <h1>Bếp điện từ SUNHOUSE SHD6805</h1>
        <ul>
            <li><div>Mã sản phẩm</div><div>SHD6805</div></li>
            <li><div>Công suất</div><div>2000 W</div></li>
            <li><div>Điện áp</div><div>220V/50Hz</div></li>
            <li><div>Mặt kính</div><div>Ceramic</div></li>
        </ul>
    </html>
    """

    def mock_get(url, **kwargs):
        nonlocal call_count
        call_count += 1
        if "search" in url:
            return MockResponse(200, search_html)
        else:
            return MockResponse(200, detail_html)

    with patch("aiohttp.ClientSession.get", side_effect=mock_get):
        # Query 1: "Thông số bếp từ 6805"
        t0 = time.perf_counter()
        res1 = await _scrape_sunhouse_model_spec("Thông số bếp từ 6805")
        dur1 = (time.perf_counter() - t0) * 1000
        assert res1 is not None
        assert "SHD6805" in res1
        assert "2000 W" in res1
        assert call_count > 0  # Network scraping executed on first miss
        initial_calls = call_count

        # Verify Two-Key indexing in Cache:
        # Both model:shd6805 and query:thông số bếp từ 6805 are cached
        assert _get_cache("model:shd6805") is not None
        assert _get_cache("query:thông số bếp từ 6805") is not None

        # Query 2: "Bếp SHD 6805 giá bao nhiêu" -> Different query wording!
        t0 = time.perf_counter()
        res2 = await _scrape_sunhouse_model_spec("Bếp SHD 6805 giá bao nhiêu")
        dur2 = (time.perf_counter() - t0) * 1000
        assert dur2 < 10.0  # Instant Cache Hit < 10ms (typically < 1ms)
        assert res2 == res1
        assert call_count == initial_calls  # Zero extra network calls!

        # Query 3: "SHD6805" -> Just model code
        t0 = time.perf_counter()
        res3 = await _scrape_sunhouse_model_spec("SHD6805")
        dur3 = (time.perf_counter() - t0) * 1000
        assert dur3 < 10.0  # Instant Cache Hit
        assert res3 == res1
        assert call_count == initial_calls  # Zero extra network calls!


def test_two_key_indexing_and_cross_query_cache_hit():
    clear_cache()
    asyncio.run(async_two_key_indexing_test())


async def async_negative_caching_test():
    """Test Case: Negative caching prevents repeated HTTP requests when model does not exist."""
    call_count = 0

    class Mock404Response:
        def __init__(self):
            self.status = 200
            self._text = "<html><body>No products found</body></html>"

        async def text(self):
            return self._text

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    def mock_get(url, **kwargs):
        nonlocal call_count
        call_count += 1
        return Mock404Response()

    with patch("aiohttp.ClientSession.get", side_effect=mock_get):
        # Query 1: Nonexistent model
        res1 = await _scrape_sunhouse_model_spec("bếp từ 999999")
        assert res1 is None
        assert call_count > 0
        calls_after_miss = call_count

        # Check negative cache entries
        assert _get_cache("empty_model:shd999999") is not None
        assert _get_cache("empty_query:bếp từ 999999") is not None

        # Query 2: Same query -> Hit empty_query negative cache
        res2 = await _scrape_sunhouse_model_spec("bếp từ 999999")
        assert res2 is None
        assert call_count == calls_after_miss  # Zero network requests!

        # Query 3: SHD999999 -> Hit empty_model negative cache
        res3 = await _scrape_sunhouse_model_spec("SHD999999")
        assert res3 is None
        assert call_count == calls_after_miss  # Zero network requests!


def test_negative_caching_prevents_scraping_storms():
    clear_cache()
    asyncio.run(async_negative_caching_test())


def test_lru_eviction_bounded_memory():
    """Test Case 2.3: Cache must never exceed MAX_CACHE_SIZE and evict oldest entries."""
    clear_cache()
    stats_init = get_cache_stats()
    assert stats_init["size"] == 0
    assert stats_init["max_size"] == MAX_CACHE_SIZE

    # Populate 1,100 items (100 over MAX_CACHE_SIZE)
    for i in range(1100):
        _set_cache(f"item:{i}", f"data_{i}")

    stats_after = get_cache_stats()
    assert stats_after["size"] == MAX_CACHE_SIZE  # strictly capped at 1000!

    # The oldest 100 items (0 to 99) should have been evicted
    for i in range(100):
        assert _get_cache(f"item:{i}") is None

    # The newer items (100 to 1099) should still exist
    for i in range(100, 1100):
        assert _get_cache(f"item:{i}") == f"data_{i}"


def test_cache_ttl_expiration():
    """Test Case: Cache entries expire after TTL."""
    # Set with a short TTL (0.05 seconds)
    _set_cache("temp_key", "temporary_value", ttl=0.05)
    assert _get_cache("temp_key") == "temporary_value"

    time.sleep(0.08)
    assert _get_cache("temp_key") is None


if __name__ == "__main__":
    print("=== ĐANG CHẠY BỘ TEST GIAI ĐOẠN 2: SUNHOUSE LIVE SEARCH CACHE ===")
    test_canonical_model_extraction()
    print("✓ [PASS] Trích xuất mã Canonical Model từ đa dạng câu hỏi")
    test_clean_tts_text()
    print("✓ [PASS] Xử lý chuỗi văn bản sạch cho giọng đọc TTS")
    test_two_key_indexing_and_cross_query_cache_hit()
    print("✓ [PASS] Bộ đệm hai lớp Two-Key Indexing & Cache Hit chéo giữa các câu hỏi")
    test_negative_caching_prevents_scraping_storms()
    print("✓ [PASS] Negative Caching ngăn chặn hoàn toàn bão cào web khi model không tồn tại")
    test_lru_eviction_bounded_memory()
    print("✓ [PASS] Giới hạn bộ nhớ đệm LRU Eviction tối đa 1.000 phần tử")
    test_cache_ttl_expiration()
    print("✓ [PASS] Cơ chế tự động giải phóng mục hết hạn TTL")
    print("=== TẤT CẢ 6/6 TEST CASE GIAI ĐOẠN 2 ĐÃ PASS HOÀN TOÀN! ===")
