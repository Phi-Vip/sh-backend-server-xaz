"""
Công cụ MCP tra cứu thông tin trực tuyến thời gian thực (Real-time Live Web Search & Scraping)
Tích hợp bộ phân giải tiền tố thông minh và phục hồi lỗi phát âm ASR cho mọi dòng sản phẩm Sunhouse:
1. Bảng ánh xạ tiền tố chính thức theo danh mục:
   - SHD : Bếp từ đơn (SHD6xxx), Nồi chiên (SHD4xxx), Quạt điều hòa (SHD7xxx), Nồi cơm (SHD8xxx), Máy xay/ép (SHD5xxx), Ấm siêu tốc (SHD1xxx)
   - SHB / MMB : Bếp từ đôi / hồng ngoại đôi (SHBxxxx, MMBxxxx), Máy hút mùi (SHB6xxx, SHB7xxx, MMB6xxx)
   - SHA / SHR : Máy lọc nước RO gia đình, UltraX (SHA76xxx, SHA88xxx), Cây nước nóng lạnh (SHRxxxx)
   - SHG / ST / SBD : Chảo chống dính Ultra Titanium Plasma (ST), Nano Diamond Ceramic (SHG), Bộ nồi Inox (SHG, SH)
   - HTD / APB : Nhãn HappyTime (HTD) và Apex (APB) thuộc Tập đoàn Sunhouse
2. Chuẩn hóa ngữ âm tiếng Việt từ ASR (ví dụ: 'ét hát đê' -> 'SHD', 'ét hát bê' -> 'SHB', 'máy lọc nước 76688' -> 'SHA76688SH'...)
3. Dự đoán và tự động sửa sai tiền tố khi người dùng nói nhầm hoặc chỉ nói số model.
"""

import re
import time
import urllib.parse
from collections import OrderedDict
from typing import Dict, Any, Optional, List
import aiohttp
from bs4 import BeautifulSoup

try:
    from . import register_tool
except ImportError:
    # Cho phép import độc lập khi chạy test
    def register_tool(name: str, description: str, parameters: Optional[Dict[str, Any]] = None):
        def decorator(func):
            return func
        return decorator

# Cấu hình bộ nhớ đệm LRU đa cấp chuẩn thương mại
MAX_CACHE_SIZE = 1000
CACHE_TTL_QUERY = 600.0        # 10 phút: câu truy vấn thô người dùng
CACHE_TTL_MODEL = 86400.0      # 24 giờ: thông số kỹ thuật model chính hãng (ít thay đổi)
CACHE_TTL_NEGATIVE = 10.0      # 10 giây: chỉ chặn spam ngắn hạn, không được block lâu khi người dùng thử lại
CACHE_TTL_NEWS = 1800.0        # 30 phút: tin tức sự kiện mới nhất
CACHE_TTL_FEATURED = 3600.0    # 1 giờ: danh sách sản phẩm nổi bật

# Bộ nhớ đệm LRU (Least Recently Used) lưu trữ dạng: key -> (value, expire_at)
_CACHE: OrderedDict[str, tuple[str, float]] = OrderedDict()

# Bảng phân loại tiền tố chính thức theo từng danh mục thiết bị của Sunhouse
CATEGORY_PREFIX_MAP = {
    # Bếp từ đôi / Bếp đôi điện từ hồng ngoại
    'bếp từ đôi': ['SHB', 'MMB'],
    'bếp đôi': ['SHB', 'MMB'],
    'bếp điện đôi': ['SHB', 'MMB'],
    'bếp đôi điện từ': ['SHB', 'MMB'],
    'bếp điện': ['SHB', 'SHD', 'MMB'],
    'bếp hồng ngoại đôi': ['SHB', 'MMB'],
    # Máy hút mùi
    'hút mùi': ['SHB', 'MMB'],
    'máy hút mùi': ['SHB', 'MMB'],
    # Máy lọc nước RO
    'máy lọc nước': ['SHA', 'SHR'],
    'lọc nước': ['SHA', 'SHR'],
    'cây nước': ['SHA', 'SHR'],
    # Bếp từ đơn
    'bếp từ đơn': ['SHD'],
    'bếp từ': ['SHD', 'SHB'],
    # Nồi chiên không dầu
    'nồi chiên không dầu': ['SHD', 'HTD'],
    'nồi chiên': ['SHD', 'HTD'],
    # Quạt điều hòa / Máy làm mát
    'quạt điều hòa': ['SHD'],
    'máy làm mát': ['SHD'],
    'quạt hơi nước': ['SHD'],
    'quạt': ['SHD'],
    # Nồi cơm điện
    'nồi cơm điện': ['SHD', 'HTD'],
    'nồi cơm': ['SHD', 'HTD'],
    # Ấm siêu tốc
    'ấm siêu tốc': ['SHD'],
    'bình đun': ['SHD'],
    # Máy xay & ép
    'máy xay sinh tố': ['SHD'],
    'máy xay': ['SHD'],
    'máy ép trái cây': ['SHD'],
    'máy ép chậm': ['SHD'],
    'máy ép': ['SHD'],
    # Chảo chống dính & Bộ nồi
    'chảo chống dính': ['SHG', 'ST', 'SBD'],
    'chảo': ['SHG', 'ST', 'SBD'],
    'bộ nồi inox': ['SHG', 'SH'],
    'bộ nồi': ['SHG', 'SH'],
}

def _get_cache(key: str) -> Optional[str]:
    """Lấy dữ liệu từ Cache nếu còn hạn; tự động làm mới vị trí trong LRU."""
    now = time.time()
    if key in _CACHE:
        val, expire_at = _CACHE[key]
        if now < expire_at:
            _CACHE.move_to_end(key)  # Đưa lên đầu danh sách vừa dùng (LRU refresh)
            return val
        del _CACHE[key]  # Đã hết hạn TTL
    return None

def _set_cache(key: str, val: str, ttl: float = CACHE_TTL_QUERY):
    """Ghi dữ liệu vào Cache với TTL xác định và thực hiện LRU Eviction khi vượt MAX_CACHE_SIZE."""
    now = time.time()
    if key in _CACHE:
        _CACHE.move_to_end(key)
    _CACHE[key] = (val, now + ttl)
    if len(_CACHE) > MAX_CACHE_SIZE:
        _CACHE.popitem(last=False)  # Xóa phần tử cũ nhất (LRU Eviction)

def get_cache_stats() -> Dict[str, Any]:
    """Trả về thống kê hiện tại của Cache phục vụ giám sát và kiểm thử."""
    return {
        "size": len(_CACHE),
        "max_size": MAX_CACHE_SIZE,
    }

def clear_cache():
    """Xóa trắng bộ nhớ đệm (dành cho kiểm thử hoặc làm mới nóng)."""
    _CACHE.clear()

def normalize_asr_phonetics(text: str) -> str:
    """Chuẩn hóa cách phát âm ngữ âm tiếng Việt do ASR dịch ra sang chữ cái viết tắt chuẩn"""
    text_lower = text.lower()
    replacements = [
        # Tiền tố SHD (Điện gia dụng)
        (r'ét\s*hát\s*đê|ét\s*hắt\s*đê|sờ\s*hắt\s*đê|sờ\s*hát\s*đê|sắc\s*đê|s\s*đê|ét\s*đê|ép\s*đê', 'shd'),
        # Tiền tố SHB (Bếp đôi, hút mùi)
        (r'ét\s*hát\s*bê|ét\s*hắt\s*bê|sờ\s*hắt\s*bê|sờ\s*hát\s*bê|s\s*bê|ét\s*bê|sờ\s*bê', 'shb'),
        # Tiền tố SHA (Máy lọc nước, điện lạnh)
        (r'ét\s*hát\s*a|ét\s*hắt\s*a|sờ\s*hắt\s*a|sờ\s*hát\s*a|s\s*a|ét\s*a', 'sha'),
        # Tiền tố SHG (Đồ gia dụng, nồi chảo)
        (r'ét\s*hát\s*gờ|sờ\s*hắt\s*gờ|s\s*gờ', 'shg'),
        # Tiền tố MMB (Sunhouse Mama)
        (r'em\s*em\s*bê|mờ\s*mờ\s*bê|ma\s*ma', 'mmb'),
        # Chữ cái rời rạc
        (r'\bs\s+h\s+d\b', 'shd'),
        (r'\bs\s+h\s+b\b', 'shb'),
        (r'\bs\s+h\s+a\b', 'sha'),
        (r'\bs\s+h\s+g\b', 'shg'),
        (r'\bm\s+m\s+b\b', 'mmb'),
    ]
    for pattern, rep in replacements:
        text_lower = re.sub(pattern, rep, text_lower)
    return text_lower

def generate_model_candidates(query: str) -> List[str]:
    """
    Sinh danh sách các mã model ứng viên dựa trên:
    1. Mã model chính xác trích xuất từ câu
    2. Tiền tố tương ứng với danh mục thiết bị (ví dụ: 'bếp từ đôi' + số -> 'SHB...', 'quạt' + số -> 'SHD...')
    3. Các tiền tố phổ biến khác của Sunhouse (SHD, SHB, SHA, MMB, SHG)
    4. Số hiệu đơn thuần
    """
    q_norm = normalize_asr_phonetics(query)
    digit_match = re.search(r'\d{3,6}', q_norm)
    digits = digit_match.group(0) if digit_match else None

    candidates: List[str] = []

    # 1. Trích xuất mã có dạng tiền tố + số trực tiếp từ câu (ví dụ: SHD6805, SHA76688...)
    known_prefixes = r'(?:SHD|SHB|SHA|SHR|SHG|MMB|HTD|APB|ST|SBD|SBDS|SWP|SHE|SH)'
    exact = re.search(rf'\b({known_prefixes}\s*[-_]?\s*\d{{2,6}}[A-Za-z0-9]*)\b', q_norm, re.IGNORECASE)
    if exact:
        code = exact.group(1).replace(' ', '').replace('-', '').replace('_', '').upper()
        candidates.append(code)

    if digits:
        # 2. Ưu tiên tiền tố theo danh mục người dùng nhắc đến (ví dụ: 'bếp đôi' -> SHB82082)
        for cat_kw, prefixes in CATEGORY_PREFIX_MAP.items():
            if cat_kw in q_norm:
                for p in prefixes:
                    c = f"{p}{digits}"
                    if c not in candidates:
                        candidates.append(c)

        # 3. Ưu tiên số hiệu thuần túy ngay sau tiền tố danh mục (vì web Sunhouse tìm theo số cực nhạy)
        if digits not in candidates:
            candidates.append(digits)

        # 4. Thử các tiền tố thông dụng khác của Sunhouse
        for p in ['SHD', 'SHB', 'SHA', 'MMB', 'SHG']:
            c = f"{p}{digits}"
            if c not in candidates:
                candidates.append(c)

    # 5. Xử lý trường hợp chảo hoặc sản phẩm có ký tự kích thước (ví dụ: 26DM, ST26P)
    dim_match = re.search(r'\b(\d{2}[A-Za-z]+)\b', q_norm)
    if dim_match:
        dim_code = dim_match.group(1).upper()
        for p in ['SHG', 'ST', 'SBD']:
            c = f"{p}{dim_code}"
            if c not in candidates:
                candidates.append(c)
        if dim_code not in candidates:
            candidates.append(dim_code)

    return candidates

def extract_canonical_model(query: str) -> Optional[str]:
    """
    Trích xuất mã model chuẩn duy nhất (Canonical Model Code) từ câu truy vấn.
    Phục vụ Two-Key Indexing để đồng nhất mọi biến thể câu hỏi về cùng 1 mã thiết bị:
    - 'thông số bếp từ đơn SHD6805' -> 'SHD6805'
    - 'bếp từ 6805' -> 'SHD6805' (nhận diện danh mục 'bếp từ' và số '6805')
    - 'bếp SHD 6805' -> 'SHD6805'
    - 'SHD6805' -> 'SHD6805'
    - 'quạt 7737' -> 'SHD7737'
    - 'bếp từ đôi 9101' -> 'SHB9101'
    - 'máy lọc nước 76688' -> 'SHA76688'
    """
    if not query:
        return None

    q_norm = normalize_asr_phonetics(query)
    known_prefixes = r'(?:SHD|SHB|SHA|SHR|SHG|MMB|HTD|APB|ST|SBD|SBDS|SWP|SHE|SH)'

    # 1. Khớp chính xác tiền tố + số trực tiếp từ câu (ví dụ: SHD6805, SHA76688...)
    exact = re.search(rf'\b({known_prefixes}\s*[-_]?\s*\d{{2,6}}[A-Za-z0-9]*)\b', q_norm, re.IGNORECASE)
    if exact:
        return exact.group(1).replace(' ', '').replace('-', '').replace('_', '').upper()

    # 2. Suy luận từ danh mục + số (ưu tiên candidate đầu tiên khớp tiền tố chuẩn)
    candidates = generate_model_candidates(query)
    for cand in candidates:
        if re.match(rf'^{known_prefixes}\d{{2,6}}', cand):
            return cand.upper()

    # 3. Ký tự kích thước (ví dụ ST26P, SHG26DM)
    for cand in candidates:
        if re.match(rf'^{known_prefixes}\d{{2}}[A-Za-z]+', cand):
            return cand.upper()

    return None

def _clean_tts_text(text: str) -> str:
    """Loại bỏ ký tự markdown, bullets và định dạng lạ để giọng đọc TTS phát âm chuẩn xác nhất"""
    if not text:
        return ""
    text = re.sub(r'[*#_~`\[\]\(\)\{\}<>•▪▫|]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

async def _scrape_sunhouse_model_spec(query: str) -> Optional[str]:
    """Tìm kiếm trực tiếp trên trang chủ Sunhouse và bóc tách thông số kỹ thuật chi tiết của model"""
    clean_query = query.lower().strip()
    query_key = f"query:{clean_query}"

    # 1. Kiểm tra cache theo Query thô (nếu cùng 1 câu hỏi)
    cached = _get_cache(query_key)
    if cached:
        return cached

    # 2. Trích xuất mã model chuẩn duy nhất (Canonical Model Code)
    canonical_model = extract_canonical_model(query)
    if canonical_model:
        model_key = f"model:{canonical_model.lower()}"
        cached = _get_cache(model_key)
        if cached:
            # Lưu lại vào query_key để lần sau hỏi đúng câu này hit ngay
            _set_cache(query_key, cached, ttl=CACHE_TTL_QUERY)
            return cached

        # Kiểm tra Negative Cache theo Model
        if _get_cache(f"empty_model:{canonical_model.lower()}") is not None:
            return None

    # 3. Sinh các mã ứng viên và kiểm tra xem có ứng viên nào đã được lưu cache model chưa
    candidates = generate_model_candidates(query)
    if not candidates:
        candidates = [query.strip()]

    for cand in candidates:
        cand_model_key = f"model:{cand.lower()}"
        cached = _get_cache(cand_model_key)
        if cached:
            _set_cache(query_key, cached, ttl=CACHE_TTL_QUERY)
            if canonical_model:
                _set_cache(f"model:{canonical_model.lower()}", cached, ttl=CACHE_TTL_MODEL)
            return cached

    # 4. Kiểm tra Negative Cache theo Query
    if _get_cache(f"empty_query:{clean_query}") is not None:
        return None

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

    digit_match = re.search(r'\d{3,6}', query)
    digits = digit_match.group(0) if digit_match else ""

    async with aiohttp.ClientSession(headers=headers) as session:
        for candidate in candidates[:5]:
            search_url = f"https://sunhouse.com.vn/search/{urllib.parse.quote(candidate)}"
            try:
                async with session.get(search_url, timeout=aiohttp.ClientTimeout(total=8.0)) as resp:
                    if resp.status != 200:
                        continue
                    html = await resp.text()

                soup = BeautifulSoup(html, 'html.parser')
                items = soup.find_all(class_='item-infos')
                if not items:
                    continue

                # Chọn liên kết chi tiết sản phẩm phù hợp nhất
                prod_link = None
                for it in items:
                    a = it.find('a', class_='item-title') or it.find('a')
                    if a and a.get('href'):
                        title_text = a.get_text(strip=True)
                        # Nếu có số hiệu, bắt buộc tiêu đề phải khớp số hiệu để tránh nhầm
                        if digits == "" or digits in title_text or digits in a['href']:
                            prod_link = a['href']
                            break

                if not prod_link and items:
                    a = items[0].find('a', class_='item-title') or items[0].find('a')
                    if a and a.get('href'):
                        prod_link = a['href']

                if not prod_link:
                    continue

                # Tải trang chi tiết sản phẩm
                async with session.get(prod_link, timeout=aiohttp.ClientTimeout(total=8.0)) as resp2:
                    if resp2.status != 200:
                        continue
                    html2 = await resp2.text()

                soup2 = BeautifulSoup(html2, 'html.parser')
                h1 = soup2.find('h1')
                prod_name = h1.get_text(strip=True) if h1 else f"Sản phẩm {candidate}"

                # Trích xuất toàn bộ thông số trong danh sách đặc tính kỹ thuật
                specs = {}
                for li in soup2.find_all('li'):
                    divs = li.find_all('div')
                    if len(divs) >= 2:
                        k = divs[0].get_text(strip=True)
                        v = divs[1].get_text(strip=True)
                        if 2 < len(k) < 35 and 1 < len(v) < 120 and 'danh mục' not in k.lower():
                            specs[k] = v

                if specs:
                    priority_keys = [
                        'mã sản phẩm', 'model', 'công suất', 'điện áp', 'vùng nấu',
                        'kích thước', 'dung tích', 'trọng lượng', 'khối lượng', 'bảng điều khiển',
                        'chế độ', 'mặt kính', 'chất liệu', 'loại nồi', 'hẹn giờ',
                        'khóa trẻ em', 'quá tải', 'diện tích', 'xuất xứ', 'bảo hành'
                    ]

                    selected_specs = []
                    used_keys = set()
                    for pk in priority_keys:
                        for k, v in specs.items():
                            if pk in k.lower() and k not in used_keys and 'danh mục' not in k.lower():
                                selected_specs.append(f"{k}: {v}")
                                used_keys.add(k)
                                break

                    for k, v in specs.items():
                        if k not in used_keys and len(selected_specs) < 8 and 'danh mục' not in k.lower():
                            selected_specs.append(f"{k}: {v}")
                            used_keys.add(k)

                    res_text = (
                        f"Thông số kỹ thuật chính thức từ Sunhouse cho {prod_name}: "
                        + ". ".join(selected_specs)
                        + ". Bạn có thể tham khảo thêm tại website sunhouse.com.vn hoặc gọi tổng đài 1800.6680 để được hỗ trợ chi tiết."
                    )
                    res_clean = _clean_tts_text(res_text)

                    # Lưu cache hai lớp (Two-Key Indexing):
                    # 1. Lưu theo mã model ứng viên tìm thấy (TTL 24 giờ)
                    _set_cache(f"model:{candidate.lower()}", res_clean, ttl=CACHE_TTL_MODEL)
                    if canonical_model:
                        _set_cache(f"model:{canonical_model.lower()}", res_clean, ttl=CACHE_TTL_MODEL)

                    # Bóc tách mã model từ bảng specs nếu có
                    for mk in ['mã sản phẩm', 'model']:
                        for k, v in specs.items():
                            if mk in k.lower():
                                clean_spec_code = re.sub(r'[^a-zA-Z0-9]', '', v).lower()
                                if clean_spec_code:
                                    _set_cache(f"model:{clean_spec_code}", res_clean, ttl=CACHE_TTL_MODEL)

                    # 2. Lưu theo câu query người dùng (TTL 10 phút)
                    _set_cache(query_key, res_clean, ttl=CACHE_TTL_QUERY)
                    return res_clean

                # Nếu không có danh sách li, lấy mô tả meta
                desc_tag = soup2.find('meta', {'name': 'description'})
                if desc_tag and desc_tag.get('content'):
                    desc = desc_tag.get('content').strip()
                    res_text = f"Thông tin về {prod_name}: {desc}. Chi tiết xem tại sunhouse.com.vn."
                    res_clean = _clean_tts_text(res_text)
                    _set_cache(f"model:{candidate.lower()}", res_clean, ttl=CACHE_TTL_MODEL)
                    if canonical_model:
                        _set_cache(f"model:{canonical_model.lower()}", res_clean, ttl=CACHE_TTL_MODEL)
                    _set_cache(query_key, res_clean, ttl=CACHE_TTL_QUERY)
                    return res_clean

            except Exception:
                continue

    # NẾU CÀO THẤT BẠI TOÀN BỘ ỨNG VIÊN -> LƯU NEGATIVE CACHE (TTL 5 phút)
    _set_cache(f"empty_query:{clean_query}", "", ttl=CACHE_TTL_NEGATIVE)
    if canonical_model:
        _set_cache(f"empty_model:{canonical_model.lower()}", "", ttl=CACHE_TTL_NEGATIVE)
    elif candidates:
        _set_cache(f"empty_model:{candidates[0].lower()}", "", ttl=CACHE_TTL_NEGATIVE)

    return None

async def _scrape_sunhouse_latest_news() -> Optional[str]:
    """Cào các bản tin và sự kiện hoạt động mới nhất hàng ngày từ https://sunhouse.com.vn/tin-hoat-dong"""
    cache_key = "news:latest"
    cached = _get_cache(cache_key)
    if cached:
        return cached

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    url = "https://sunhouse.com.vn/tin-hoat-dong"

    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=4)) as resp:
                if resp.status != 200:
                    return None
                html = await resp.text()

        soup = BeautifulSoup(html, 'html.parser')
        items = []
        for a in soup.find_all('a', href=True):
            href = a['href']
            if '/tin-hoat-dong/' in href and href.endswith('.html'):
                title = a.get_text(strip=True)
                if title and len(title) > 20 and not any(it['link'] == href for it in items):
                    parent = a.find_parent(['div', 'article', 'li'])
                    desc = ''
                    if parent:
                        p_desc = parent.find(['p', 'div'], class_=lambda c: c and any(w in c.lower() for w in ['desc', 'summary', 'sapo', 'intro']))
                        if p_desc:
                            desc = p_desc.get_text(strip=True)
                        else:
                            p = parent.find('p')
                            if p and p.get_text(strip=True) != title:
                                desc = p.get_text(strip=True)
                    items.append({'title': title, 'link': href, 'desc': desc})
                    if len(items) >= 3:
                        break

        if items:
            parts = ["Các bản tin và sự kiện hoạt động mới nhất từ Tập đoàn Sunhouse:"]
            for i, it in enumerate(items, 1):
                t = it['title']
                d = it['desc']
                if d:
                    parts.append(f"Tin số {i}: {t}. Tóm tắt: {d}")
                else:
                    parts.append(f"Tin số {i}: {t}.")

            parts.append("Bạn có thể theo dõi chi tiết các bài viết tại chuyên mục Tin hoạt động trên website sunhouse.com.vn.")
            res_text = " ".join(parts)
            res_clean = _clean_tts_text(res_text)
            _set_cache(cache_key, res_clean, ttl=CACHE_TTL_NEWS)
            return res_clean

    except Exception:
        pass
    return None

async def _scrape_sunhouse_featured_products() -> Optional[str]:
    """Cào các sản phẩm nổi bật và mới ra mắt trên trang chủ Sunhouse"""
    cache_key = "products:featured"
    cached = _get_cache(cache_key)
    if cached:
        return cached

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    url = "https://sunhouse.com.vn/"

    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=4)) as resp:
                if resp.status != 200:
                    return None
                html = await resp.text()

        soup = BeautifulSoup(html, 'html.parser')
        title_home = soup.find('div', class_='titleHome')
        prods = []
        if title_home and title_home.parent:
            for a in title_home.parent.find_all('a', href=True):
                t = a.get_text(strip=True)
                if len(t) > 5 and not any(k in t.lower() for k in ['xem tất cả', 'chi tiết']):
                    if t not in prods:
                        prods.append(t)
                        if len(prods) >= 5:
                            break

        if prods:
            parts = ["Các dòng sản phẩm nổi bật và mới nhất hiện nay của Sunhouse bao gồm:"]
            for i, p in enumerate(prods, 1):
                parts.append(f"{i} là {p}.")
            parts.append("Bạn có thể hỏi cụ thể tên hoặc mã model của bất kỳ sản phẩm nào để mình tra cứu thông số kỹ thuật chi tiết nhé.")
            res_text = " ".join(parts)
            res_clean = _clean_tts_text(res_text)
            _set_cache(cache_key, res_clean, ttl=CACHE_TTL_FEATURED)
            return res_clean

    except Exception:
        pass
    return None

async def _fallback_web_search(query: str) -> str:
    """Tìm kiếm web trực tiếp qua công cụ tìm kiếm Bing khi không có trên website Sunhouse"""
    clean_q = query.lower().strip()
    cache_key = f"fallback:{clean_q}"
    cached = _get_cache(cache_key)
    if cached:
        return cached

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    url = f"https://www.bing.com/search?q={urllib.parse.quote('sunhouse ' + query)}"

    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=4)) as resp:
                if resp.status == 200:
                    html = await resp.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    results = []
                    for li in soup.find_all('li', class_='b_algo')[:3]:
                        h2 = li.find('h2')
                        cap = li.find('div', class_='b_caption')
                        if h2:
                            title = h2.get_text(strip=True)
                            snippet = cap.get_text(strip=True) if cap else ''
                            results.append(f"{title}: {snippet}")

                    if results:
                        res_text = f"Kết quả tra cứu trực tuyến về {query}: " + ". ".join(results)
                        res_clean = _clean_tts_text(res_text)
                        _set_cache(cache_key, res_clean, ttl=CACHE_TTL_QUERY)
                        return res_clean

    except Exception:
        pass

    fallback_msg = (
        f"Hiện tại mình chưa tìm thấy thông tin cụ thể cho từ khóa {query} trên hệ thống trực tuyến. "
        "Bạn vui lòng kiểm tra lại mã model hoặc liên hệ hotline chăm sóc khách hàng 1800.6680 để được hỗ trợ nhé."
    )
    _set_cache(cache_key, fallback_msg, ttl=CACHE_TTL_NEGATIVE)
    return fallback_msg

@register_tool(
    name="tim_kiem_truc_tuyen_sunhouse",
    description=(
        "Tìm kiếm và tra cứu thông tin trực tuyến thời gian thực từ trang web chính thức của Tập đoàn SUNHOUSE (sunhouse.com.vn). "
        "Hỗ trợ bộ phân giải model thông minh tự động khắc phục lỗi phát âm ASR (ví dụ: 'quạt 7737' tự hiểu là SHD7737, 'bếp đôi 9101' tự hiểu là SHB9101, 'bếp từ SHB6805' tự sửa thành SHD6805). "
        "BẮT BUỘC sử dụng công cụ này khi: "
        "1. Người dùng hỏi về các thông tin hoặc tin tức mới cập nhật hàng ngày, các sự kiện, hoạt động mới nhất của Sunhouse. "
        "2. Người dùng hỏi về các dòng sản phẩm mới ra mắt hoặc tìm kiếm sản phẩm theo từ khóa. "
        "3. Người dùng tra cứu thông số kỹ thuật, cấu hình, công suất, kích thước, dung tích, tính năng của một thiết bị cụ thể có tên model "
        "(ví dụ: bếp từ đơn SHD6805, quạt điều hòa SHD7737, máy lọc nước SHA76688SH, nồi chiên SHD4018, nồi cơm điện SHD8903...)."
    ),
    parameters={
        "type": "object",
        "properties": {
            "tu_khoa": {
                "type": "string",
                "description": "Từ khóa tìm kiếm hoặc tên model thiết bị (ví dụ: 'SHD6805', 'bếp từ 6805', 'quạt 7737', 'bếp từ đôi 9101', 'máy lọc nước 76688', 'tin tức mới', 'nồi chiên không dầu')."
            },
            "loai_tim_kiem": {
                "type": "string",
                "description": (
                    "Loại tra cứu: "
                    "'thong_so_model' (tra cứu thông số kỹ thuật của 1 model cụ thể), "
                    "'tin_tuc_moi' (tin tức sự kiện cập nhật hàng ngày), "
                    "hoặc 'san_pham_moi' (dòng sản phẩm mới hoặc tìm kiếm sản phẩm theo danh mục)."
                )
            }
        },
        "required": ["tu_khoa"]
    }
)
async def tim_kiem_truc_tuyen_sunhouse(tu_khoa: str, loai_tim_kiem: Optional[str] = None) -> str:
    """
    Hàm thực thi chính của tool tra cứu trực tuyến Sunhouse
    """
    tu_khoa_lower = tu_khoa.lower().strip()

    # 1. Nếu người dùng hỏi tin tức mới cập nhật hàng ngày
    news_keywords = ['tin tức', 'tin mới', 'bản tin', 'hàng ngày', 'sự kiện', 'hoạt động', 'news']
    if loai_tim_kiem == "tin_tuc_moi" or any(kw in tu_khoa_lower for kw in news_keywords):
        result = await _scrape_sunhouse_latest_news()
        if result:
            return result
        return await _fallback_web_search(f"tin tức sự kiện {tu_khoa}")

    # 2. Nếu người dùng hỏi sản phẩm mới ra mắt
    new_prod_keywords = ['sản phẩm mới', 'mới ra mắt', 'dòng mới', 'mới nhất', 'nổi bật', 'bán chạy']
    if loai_tim_kiem == "san_pham_moi" or any(kw in tu_khoa_lower for kw in new_prod_keywords):
        result = await _scrape_sunhouse_featured_products()
        if result:
            return result

    # 3. Tra cứu model thông minh (tự động phân giải danh mục, tiền tố và sửa lỗi phát âm ASR)
    result = await _scrape_sunhouse_model_spec(tu_khoa)
    if result:
        return result

    # 4. Fallback tra cứu web trực tiếp
    return await _fallback_web_search(tu_khoa)
