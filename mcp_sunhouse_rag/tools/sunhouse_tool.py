"""
Công cụ chuyên sâu tra cứu sự cố và mã lỗi thiết bị gia dụng Sunhouse.
Hỗ trợ: Bếp từ, Quạt điều hòa, Nồi cơm điện, Máy lọc nước RO, Nồi chiên không dầu.
"""

import json
import os
from . import register_tool

# Đường dẫn tương đối tới file dữ liệu
DATA_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "sunhouse_knowledge.json")

def load_knowledge_base():
    if os.path.exists(DATA_PATH):
        try:
            with open(DATA_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[LỖI] Không thể đọc file sunhouse_knowledge.json: {e}")
    return {}

@register_tool(
    name="tra_cuu_ma_loi_sunhouse",
    description=(
        "Tra cứu nguyên nhân kỹ thuật và giải pháp khắc phục mã lỗi thiết bị gia dụng Sunhouse từ sổ tay dịch vụ chính hãng. "
        "BẮT BUỘC sử dụng công cụ này khi khách hàng hỏi về các mã lỗi kỹ thuật (như E0, E1, E2, E3, E4, E5, E6...) "
        "hoặc tiếng kêu bíp cảnh báo, đèn nhấp nháy trên các thiết bị Sunhouse (Bếp từ, Quạt điều hòa, Nồi cơm điện, Nồi chiên không dầu, Máy lọc nước RO)."
    ),
    parameters={
        "type": "object",
        "properties": {
            "loai_thiet_bi": {
                "type": "string",
                "description": "Tên loại thiết bị (ví dụ: 'bep_tu', 'quat_dieu_hoa', 'noi_com', 'may_loc_nuoc', 'noi_chien', 'bếp từ', 'quạt hơi nước', 'nồi cơm điện')."
            },
            "ma_loi": {
                "type": "string",
                "description": "Ký tự mã lỗi hiển thị trên màn hình hoặc mã cảnh báo (ví dụ: 'E0', 'E1', 'E2', 'E3', 'E4')."
            },
            "device_id": {
                "type": "string",
                "description": "Mã định danh của thiết bị gọi loa (hệ thống tự động điền nếu có)."
            }
        },
        "required": ["loai_thiet_bi", "ma_loi"]
    }
)
async def tra_cuu_ma_loi_sunhouse(loai_thiet_bi: str, ma_loi: str, device_id: str = None) -> str:
    db = load_knowledge_base()
    if not db:
        return "Hiện tại hệ thống cơ sở tri thức Sunhouse đang được bảo trì, bạn vui lòng liên hệ hotline 1800.6680 để được hỗ trợ nhé."

    # 1. Bảng chuẩn hóa từ đồng nghĩa dân dã sang khóa dữ liệu chuẩn
    synonyms = {
        # Bếp từ
        "bếp từ": "bep_tu", "bep tu": "bep_tu", "bếp điện": "bep_tu", "bep dien": "bep_tu",
        "bếp hồng ngoại": "bep_tu", "bep hong ngoai": "bep_tu", "bếp đôi": "bep_tu",
        # Quạt điều hòa
        "quạt điều hòa": "quat_dieu_hoa", "quat dieu hoa": "quat_dieu_hoa",
        "quạt hơi nước": "quat_dieu_hoa", "quat hoi nuoc": "quat_dieu_hoa",
        "máy làm mát": "quat_dieu_hoa", "may lam mat": "quat_dieu_hoa",
        # Nồi cơm điện
        "nồi cơm": "noi_com", "noi com": "noi_com",
        "nồi cơm điện": "noi_com", "noi com dien": "noi_com",
        "nồi cơm điện tử": "noi_com",
        # Máy lọc nước
        "máy lọc nước": "may_loc_nuoc", "may loc nuoc": "may_loc_nuoc",
        "máy lọc": "may_loc_nuoc", "cây nước": "may_loc_nuoc",
        # Nồi chiên không dầu
        "nồi chiên": "noi_chien", "noi chien": "noi_chien",
        "nồi chiên không dầu": "noi_chien", "noi chien khong dau": "noi_chien"
    }

    raw_dev = str(loai_thiet_bi).lower().strip()
    dev_key = synonyms.get(raw_dev, raw_dev)
    err_key = str(ma_loi).upper().strip()

    device_data = db.get(dev_key)
    if not device_data:
        supported = "Bếp từ, Quạt điều hòa, Nồi cơm điện, Máy lọc nước RO và Nồi chiên không dầu"
        return f"Hiện tại hệ thống sổ tay dịch vụ Sunhouse chỉ hỗ trợ các thiết bị gồm {supported}. Chưa có thông tin cho thiết bị '{loai_thiet_bi}'."

    err_data = device_data.get(err_key)
    dev_name = device_data.get("_name", "Thiết bị Sunhouse")
    if not err_data:
        return f"Không tìm thấy mã lỗi '{ma_loi}' trong sổ tay kỹ thuật của {dev_name}. Bạn vui lòng kiểm tra lại ký tự hiển thị trên màn hình nhé."

    # 2. Xây dựng thông điệp kỹ thuật chuẩn xác
    lines = [
        f"KẾT QUẢ TỪ SỔ TAY KỸ THUẬT SUNHOUSE:",
        f"Thiết bị: {dev_name}",
        f"Mã lỗi: {err_key}",
        f"Hiện tượng: {err_data['symptom']}",
        f"Nguyên nhân cốt lõi: {err_data['root_cause']}",
        f"Cách xử lý an toàn tại nhà: {err_data['solution_diy']}"
    ]

    if err_data.get("need_technician", False):
        lines.append(
            "CẢNH BÁO NGUY HIỂM: Lỗi này xuất phát từ linh kiện bo mạch điện tử bên trong. "
            "Khách hàng tuyệt đối không tự ý tháo mở thiết bị để tránh chập điện. "
            "Vui lòng ngắt nguồn và gọi ngay tổng đài bảo hành miễn phí Sunhouse 1800.6680."
        )

    return "\n".join(lines)
