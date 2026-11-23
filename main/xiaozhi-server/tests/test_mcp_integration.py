"""
Test tích hợp trực tiếp từ phía Backend XiaoZhi kết nối tới MCP Endpoint Server
Sử dụng 100% mã nguồn thực tế của XiaoZhi:
- config.settings.load_config
- core.providers.tools.mcp_endpoint.connect_mcp_endpoint
- core.providers.tools.mcp_endpoint.call_mcp_endpoint_tool
"""

import os
import sys
import asyncio
import json

# Chuyển CWD về thư mục xiaozhi-server
SERVER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(SERVER_DIR)
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from config.settings import load_config
from core.providers.tools.mcp_endpoint import connect_mcp_endpoint, call_mcp_endpoint_tool


async def main():
    print("==================================================================")
    print("🔍 KIỂM THỬ TÍCH HỢP XIAOZHI BACKEND ⇄ MCP ENDPOINT SERVER")
    print("==================================================================")
    
    # 1. Nạp config thực tế của XiaoZhi
    config = await load_config()
    mcp_url = config.get("mcp_endpoint")
    print(f"👉 1. MCP Endpoint URL từ config: {mcp_url}")
    assert mcp_url is not None, "mcp_endpoint chưa được cấu hình trong config!"
    
    # Mô phỏng tiền xử lý URL như trong app.py
    if "/mcp/" in mcp_url:
        mcp_url = mcp_url.replace("/mcp/", "/call/")
    print(f"👉 2. URL kết nối thực tế sau khi app.py xử lý: {mcp_url}")
    
    # 2. Kết nối tới MCP Server qua handler của XiaoZhi
    print("👉 3. Đang thực hiện connect_mcp_endpoint()...")
    client = await connect_mcp_endpoint(mcp_url)
    assert client is not None, "Không thể kết nối tới MCP Endpoint Server!"
    print("✅ Kết nối thành công!")
    
    # Chờ 1 giây để client nhận tools/list qua background listener
    await asyncio.sleep(1.0)
    
    # 3. Kiểm tra danh sách Tools đã nạp vào client
    print(f"👉 4. Danh sách Tools XiaoZhi đã lấy về: {list(client.tools.keys())}")
    assert "tra_cuu_ma_loi_sunhouse" in client.tools, "Tool 'tra_cuu_ma_loi_sunhouse' chưa được load vào XiaoZhi client!"
    assert "tra_cuu_thong_tin_sunhouse" in client.tools, "Tool 'tra_cuu_thong_tin_sunhouse' chưa được load vào XiaoZhi client!"
    assert "tim_kiem_truc_tuyen_sunhouse" in client.tools, "Tool 'tim_kiem_truc_tuyen_sunhouse' chưa được load vào XiaoZhi client!"
    print("✅ Đã xác nhận XiaoZhi nhận diện đầy đủ cả 3 Tools Sunhouse!")
    
    # 4. Kiểm tra gọi Tool 1: tra_cuu_ma_loi_sunhouse
    print("👉 5. Mô phỏng LLM gọi Tool 1 qua call_mcp_endpoint_tool()...")
    args1 = json.dumps({"loai_thiet_bi": "bếp từ", "ma_loi": "E1"}, ensure_ascii=False)
    result1 = await call_mcp_endpoint_tool(client, "tra_cuu_ma_loi_sunhouse", args1)
    
    print("\n------------------- KẾT QUẢ TOOL 1 (MÃ LỖI) -------------------")
    print(result1)
    print("----------------------------------------------------------------\n")
    assert "Điện áp cấp cho bếp quá thấp" in result1, "Nội dung trả về không đúng với dữ liệu Sunhouse!"

    # 5. Kiểm tra gọi Tool 2: tra_cuu_thong_tin_sunhouse
    print("👉 6. Mô phỏng LLM gọi Tool 2 qua call_mcp_endpoint_tool()...")
    args2 = json.dumps({"chu_de": "chu_tich_lanh_dao", "tu_khoa_chi_tiet": "Shark Phú"}, ensure_ascii=False)
    result2 = await call_mcp_endpoint_tool(client, "tra_cuu_thong_tin_sunhouse", args2)
    
    print("\n------------------- KẾT QUẢ TOOL 2 (THÔNG TIN TẬP ĐOÀN) -------------------")
    print(result2)
    print("----------------------------------------------------------------------------\n")
    assert "Nguyễn Xuân Phú" in result2, "Nội dung trả về không có tên Chủ tịch Shark Phú!"
    assert "1800 6680" in (await call_mcp_endpoint_tool(client, "tra_cuu_thong_tin_sunhouse", json.dumps({"chu_de": "tong_dai_bao_hanh_lien_he"}))), "Nội dung không có tổng đài 1800 6680!"

    # 6. Kiểm tra gọi Tool 3: tim_kiem_truc_tuyen_sunhouse (Tra cứu model bếp từ SHD6805 trực tuyến)
    print("👉 7. Mô phỏng LLM gọi Tool 3 qua call_mcp_endpoint_tool()...")
    args3 = json.dumps({"tu_khoa": "bếp từ đơn sunhouse SHD6805", "loai_tim_kiem": "thong_so_model"}, ensure_ascii=False)
    result3 = await call_mcp_endpoint_tool(client, "tim_kiem_truc_tuyen_sunhouse", args3)

    print("\n------------------- KẾT QUẢ TOOL 3 (TRA CỨU MODEL TRỰC TUYẾN) -------------------")
    print(result3)
    print("----------------------------------------------------------------------------------\n")
    assert "SHD6805" in result3, "Nội dung trả về không có thông tin model SHD6805!"
    assert "2000" in result3 or "Công suất" in result3, "Nội dung không có thông số công suất của SHD6805!"
    
    await client.close()
    print("🎉 TẤT CẢ CÁC BÀI TEST TÍCH HỢP ĐÃ XÁC NHẬN CHẠY HOÀN HẢO 100%!")

if __name__ == "__main__":
    asyncio.run(main())
