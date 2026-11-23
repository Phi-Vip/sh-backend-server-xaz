"""
Công cụ MCP tra cứu thông tin chính thức về Tập đoàn SUNHOUSE từ trang chủ https://sunhouse.com.vn/
Bao gồm: Giới thiệu tập đoàn, Chủ tịch Shark Phú, Lịch sử hình thành, Cụm nhà máy sản xuất,
Hệ sinh thái sản phẩm, Tổng đài bảo hành & Thông tin liên hệ.
"""

import json
import os
import re
from typing import Dict, Any, Optional
from . import register_tool

DATA_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "sunhouse_corporate_info.json")

def load_corporate_data() -> Dict[str, Any]:
    if os.path.exists(DATA_PATH):
        try:
            with open(DATA_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[LỖI] Không thể đọc file sunhouse_corporate_info.json: {e}")
    return {}

@register_tool(
    name="tra_cuu_thong_tin_sunhouse",
    description=(
        "Tra cứu thông tin chính thức và chi tiết về Tập đoàn SUNHOUSE từ trang chủ sunhouse.com.vn. "
        "Sử dụng công cụ này khi người dùng hỏi về: "
        "1. Giới thiệu tổng quan về Tập đoàn Sunhouse, triết lý kinh doanh. "
        "2. Chủ tịch Hội đồng Quản trị Nguyễn Xuân Phú (Shark Phú) và ban lãnh đạo. "
        "3. Lịch sử hình thành, năm thành lập, các mốc phát triển từ năm 2000 đến nay. "
        "4. Quy mô sản xuất, cụm nhà máy 100.000m2 tại Quốc Oai Hà Nội. "
        "5. Hệ sinh thái sản phẩm (đồ gia dụng, điện gia dụng, điện tử điện lạnh, thiết bị nhà bếp, thiết bị điện...). "
        "6. Tổng đài chăm sóc khách hàng, hotline bảo hành miễn cước 1800.6680, địa chỉ trụ sở và thông tin liên hệ."
    ),
    parameters={
        "type": "object",
        "properties": {
            "chu_de": {
                "type": "string",
                "description": (
                    "Chủ đề tra cứu: 'gioi_thieu_chung', 'chu_tich_lanh_dao', 'lich_su_hinh_thanh', "
                    "'quy_mo_nha_may', 'he_sinh_thai_san_pham', 'tong_dai_bao_hanh_lien_he', hoặc 'all'."
                )
            },
            "tu_khoa_chi_tiet": {
                "type": "string",
                "description": "Câu hỏi hoặc từ khóa cụ thể của người dùng (ví dụ: 'Shark Phú', 'năm thành lập', 'nhà máy ở đâu', 'tổng đài', 'bảo hành', 'địa chỉ trụ sở')."
            }
        },
        "required": ["chu_de"]
    }
)
async def tra_cuu_thong_tin_sunhouse(chu_de: str, tu_khoa_chi_tiet: Optional[str] = None) -> str:
    db = load_corporate_data()
    if not db:
        return (
            "Hiện tại hệ thống dữ liệu giới thiệu Sunhouse đang được cập nhật. "
            "Bạn vui lòng truy cập trực tiếp website chính thức https://sunhouse.com.vn/ hoặc gọi hotline miễn cước 1800.6680 để được hỗ trợ nhé."
        )

    # 1. Phân loại ý đồ tự động nếu từ khóa chi tiết được cung cấp
    query_text = f"{chu_de} {tu_khoa_chi_tiet or ''}".lower()

    target_topic = chu_de.lower().strip()

    if any(k in query_text for k in ["shark phú", "shark phu", "chủ tịch", "chu tich", "nguyễn xuân phú", "nguyen xuan phu", "lãnh đạo", "sáng lập", "người đứng đầu", "ai là sếp"]):
        target_topic = "chu_tich_lanh_dao"
    elif any(k in query_text for k in ["lịch sử", "lich su", "thành lập", "thanh lap", "năm nào", "nam nao", "cột mốc", "tiền thân", "phú thắng", "phu thang", "2000", "2004", "2005", "2010"]):
        target_topic = "lich_su_hinh_thanh"
    elif any(k in query_text for k in ["nhà máy", "nha may", "quy mô", "quy mo", "ngọc liệp", "ngoc liep", "quốc oai", "quoc oai", "diện tích", "sản xuất ở đâu"]):
        target_topic = "quy_mo_nha_may"
    elif any(k in query_text for k in ["sản phẩm", "san pham", "bán gì", "kinh doanh gì", "ngành hàng", "đồ gia dụng", "danh mục"]):
        target_topic = "he_sinh_thai_san_pham"
    elif any(k in query_text for k in ["tổng đài", "tong dai", "hotline", "số điện thoại", "sđt", "bảo hành", "bao hanh", "địa chỉ", "dia chi", "trụ sở", "tru so", "liên hệ", "lien he", "richy tower"]):
        target_topic = "tong_dai_bao_hanh_lien_he"
    elif any(k in query_text for k in ["giới thiệu", "gioi thieu", "là ai", "la ai", "là gì", "la gi", "tập đoàn", "tap doan", "thương hiệu"]):
        target_topic = "gioi_thieu_chung"

    # 2. Xử lý xuất kết quả theo chủ đề
    if target_topic == "chu_tich_lanh_dao":
        d = db.get("chu_tich_lanh_dao", {})
        return (
            f"THÔNG TIN LÃNH ĐẠO TẬP ĐOÀN SUNHOUSE:\n"
            f"- Chủ tịch Hội đồng Quản trị: Doanh nhân {d.get('name', 'Nguyễn Xuân Phú')} ({d.get('nickname', 'Shark Phú')}).\n"
            f"- Vai trò: {d.get('role', 'Nhà sáng lập, Chủ tịch HĐQT')}.\n"
            f"- Giới thiệu: {d.get('bio', '')}\n"
            f"- Triết lý lãnh đạo: {d.get('thong_diep', '')}\n"
            f"Nguồn chính thức: https://sunhouse.com.vn/gioi-thieu"
        )

    elif target_topic == "lich_su_hinh_thanh":
        d = db.get("lich_su_hinh_thanh", {})
        milestones = d.get("milestones", [])
        m_lines = [f"+ Năm {m.get('nam')}: {m.get('su_kien')}" for m in milestones]
        return (
            f"LỊCH SỬ HÌNH THÀNH VÀ PHÁT TRIỂN TẬP ĐOÀN SUNHOUSE:\n"
            + "\n".join(m_lines)
            + "\nNguồn tra cứu: https://sunhouse.com.vn/gioi-thieu"
        )

    elif target_topic == "quy_mo_nha_may":
        d = db.get("quy_mo_nha_may", {})
        factories = d.get("cac_nha_may", [])
        f_lines = [f"- {fac}" for fac in factories]
        return (
            f"QUY MÔ CỤM NHÀ MÁY SẢN XUẤT SUNHOUSE:\n"
            f"- Vị trí: {d.get('vi_tri', 'Khu công nghiệp Ngọc Liệp, Quốc Oai, Hà Nội')}.\n"
            f"- Tổng diện tích: {d.get('dien_tich', 'Hơn 100.000 m2')}.\n"
            f"- Hệ thống 8 nhà máy chuyên biệt bao gồm:\n"
            + "\n".join(f_lines)
            + f"\n- Năng lực công nghệ: {d.get('nang_luc', '')}\n"
            f"Chi tiết hình ảnh và quy trình tại: https://sunhouse.com.vn/"
        )

    elif target_topic == "he_sinh_thai_san_pham":
        d = db.get("he_sinh_thai_san_pham", {})
        cats = d.get("categories", {})
        c_lines = [
            f"1. Đồ gia dụng: {cats.get('do_gia_dung', '')}",
            f"2. Điện gia dụng: {cats.get('dien_gia_dung', '')}",
            f"3. Điện tử - Điện lạnh: {cats.get('dien_tu_dien_lanh', '')}",
            f"4. Thiết bị nhà bếp cao cấp: {cats.get('thiet_bi_nha_bep', '')}",
            f"5. Thiết bị điện và chiếu sáng: {cats.get('thiet_bi_dien_chieu_sang', '')}"
        ]
        return (
            f"HỆ SINH THÁI SẢN PHẨM SUNHOUSE:\n"
            + "\n".join(c_lines)
            + "\nDanh mục chi tiết và mua sắm trực tuyến: https://sunhouse.com.vn/"
        )

    elif target_topic == "tong_dai_bao_hanh_lien_he":
        d = db.get("tong_dai_bao_hanh_lien_he", {})
        return (
            f"THÔNG TIN LIÊN HỆ VÀ TRUNG TÂM BẢO HÀNH SUNHOUSE:\n"
            f"- Tổng đài Chăm sóc khách hàng & Bảo hành: {d.get('hotline_cskh_bao_hanh', '1800 6680')}.\n"
            f"- Đường dây hỗ trợ kỹ thuật: {d.get('ho_tro_ky_thuat', '0243 551 1212')}.\n"
            f"- Trụ sở chính: {d.get('tru_so_chinh', '')}.\n"
            f"- Chi nhánh miền Nam: {d.get('chi_nhanh_mien_nam', '')}.\n"
            f"- Tra cứu kích hoạt bảo hành điện tử e-warranty: {d.get('trang_bao_hanh_dien_tu', 'https://sunhouse.com.vn/bao-hanh')}\n"
            f"- Website chính thức: {d.get('website_chinh_thuc', 'https://sunhouse.com.vn/')}"
        )

    else: # gioi_thieu_chung hoặc all
        d = db.get("gioi_thieu_chung", {})
        contact = db.get("tong_dai_bao_hanh_lien_he", {})
        return (
            f"TẬP ĐOÀN SUNHOUSE (SUNHOUSE GROUP):\n"
            f"- Tổng quan: {d.get('summary', '')}\n"
            f"- Triết lý kinh doanh: {d.get('triet_ly_kinh_doanh', '')}\n"
            f"- Chủ tịch HĐQT: Shark Phú (Doanh nhân Nguyễn Xuân Phú).\n"
            f"- Tổng đài chăm sóc khách hàng & bảo hành miễn cước: {contact.get('hotline_cskh_bao_hanh', '1800 6680')}.\n"
            f"- Trụ sở chính: {contact.get('tru_so_chinh', 'Tầng 12, Tòa nhà Richy Tower, 35 Mạc Thái Tổ, Yên Hòa, Cầu Giấy, Hà Nội')}.\n"
            f"- Cổng thông tin chính thức: https://sunhouse.com.vn/"
        )
