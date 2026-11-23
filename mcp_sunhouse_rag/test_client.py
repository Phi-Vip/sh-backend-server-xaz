"""
Script kiểm thử độc lập dành cho MCP Endpoint Server (Port 8004)
Mô phỏng 100% các hành vi bắt tay và gọi Tool của XiaoZhi Server.
"""

import asyncio
import json
import websockets

MCP_URL = "ws://127.0.0.1:8004/mcp_endpoint/mcp/?token=sunhouse_secret_token"

async def run_tests():
    print(f"Connecting to MCP Endpoint Server at: {MCP_URL}")
    try:
        async with websockets.connect(MCP_URL) as ws:
            print("✅ 1. Kết nối WebSocket thành công!\n")

            # 1. Gửi initialize
            init_req = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "clientInfo": {"name": "XiaoZhi-Test-Runner", "version": "1.0.0"}
                }
            }
            await ws.send(json.dumps(init_req))
            res = await ws.recv()
            init_data = json.loads(res)
            print("✅ 2. Phản hồi Initialize:")
            print(f"   Server Name: {init_data['result']['serverInfo']['name']}")
            print(f"   Version: {init_data['result']['serverInfo']['version']}\n")

            # 2. Gửi notification initialized
            noti_req = {
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
                "params": {}
            }
            await ws.send(json.dumps(noti_req))
            print("✅ 3. Đã gửi notifications/initialized thành công!\n")

            # 3. Yêu cầu tools/list
            list_req = {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/list",
                "params": {}
            }
            await ws.send(json.dumps(list_req))
            res = await ws.recv()
            list_data = json.loads(res)
            tools = list_data['result']['tools']
            print(f"✅ 4. Phản hồi Tools List ({len(tools)} tools):")
            for t in tools:
                print(f"   - Tool: {t['name']}")
                print(f"     Mô tả: {t['description'][:80]}...")
            print()

            # 4. Test gọi tool: Quạt điều hòa báo lỗi E1
            print("👉 5. Test 1: Khách hỏi 'Quạt điều hòa báo lỗi E1'")
            call_req_1 = {
                "jsonrpc": "2.0",
                "id": 10,
                "method": "tools/call",
                "params": {
                    "name": "tra_cuu_ma_loi_sunhouse",
                    "arguments": {
                        "loai_thiet_bi": "quat_dieu_hoa",
                        "ma_loi": "E1"
                    }
                }
            }
            await ws.send(json.dumps(call_req_1))
            res1 = json.loads(await ws.recv())
            print(f"   Kết quả trả về:\n{res1['result']['content'][0]['text']}\n")

            # 5. Test gọi tool: Dùng từ đồng nghĩa dân dã 'quạt hơi nước'
            print("👉 6. Test 2: Khách dùng từ ngữ dân dã 'quạt hơi nước báo lỗi E1'")
            call_req_2 = {
                "jsonrpc": "2.0",
                "id": 11,
                "method": "tools/call",
                "params": {
                    "name": "tra_cuu_ma_loi_sunhouse",
                    "arguments": {
                        "loai_thiet_bi": "quạt hơi nước",
                        "ma_loi": "E1"
                    }
                }
            }
            await ws.send(json.dumps(call_req_2))
            res2 = json.loads(await ws.recv())
            print(f"   Kết quả trả về:\n{res2['result']['content'][0]['text']}\n")

            # 6. Test gọi tool: Bếp từ lỗi phần cứng E4 (Cần thợ)
            print("👉 7. Test 3: Khách hỏi 'Bếp từ báo lỗi E4'")
            call_req_3 = {
                "jsonrpc": "2.0",
                "id": 12,
                "method": "tools/call",
                "params": {
                    "name": "tra_cuu_ma_loi_sunhouse",
                    "arguments": {
                        "loai_thiet_bi": "bếp từ",
                        "ma_loi": "E4"
                    }
                }
            }
            await ws.send(json.dumps(call_req_3))
            res3 = json.loads(await ws.recv())
            print(f"   Kết quả trả về:\n{res3['result']['content'][0]['text']}\n")

            # 7. Test gọi tool ngoại lệ: Bếp từ báo mã lỗi không tồn tại E88
            print("👉 8. Test 4: Mã lỗi lạ không có trong sổ tay 'E88'")
            call_req_4 = {
                "jsonrpc": "2.0",
                "id": 13,
                "method": "tools/call",
                "params": {
                    "name": "tra_cuu_ma_loi_sunhouse",
                    "arguments": {
                        "loai_thiet_bi": "bếp từ",
                        "ma_loi": "E88"
                    }
                }
            }
            await ws.send(json.dumps(call_req_4))
            res4 = json.loads(await ws.recv())
            print(f"   Kết quả trả về:\n{res4['result']['content'][0]['text']}\n")

            # 8. Test tra cứu thông tin tập đoàn: Chủ tịch Shark Phú
            print("👉 9. Test 5: Khách hỏi 'Chủ tịch của Sunhouse là ai?'")
            call_req_5 = {
                "jsonrpc": "2.0",
                "id": 14,
                "method": "tools/call",
                "params": {
                    "name": "tra_cuu_thong_tin_sunhouse",
                    "arguments": {
                        "chu_de": "chu_tich_lanh_dao",
                        "tu_khoa_chi_tiet": "Shark Phú"
                    }
                }
            }
            await ws.send(json.dumps(call_req_5))
            res5 = json.loads(await ws.recv())
            print(f"   Kết quả trả về:\n{res5['result']['content'][0]['text']}\n")

            # 9. Test tra cứu thông tin tập đoàn: Tổng đài bảo hành
            print("👉 10. Test 6: Khách hỏi 'Tổng đài bảo hành và địa chỉ trụ sở Sunhouse'")
            call_req_6 = {
                "jsonrpc": "2.0",
                "id": 15,
                "method": "tools/call",
                "params": {
                    "name": "tra_cuu_thong_tin_sunhouse",
                    "arguments": {
                        "chu_de": "tong_dai_bao_hanh_lien_he"
                    }
                }
            }
            await ws.send(json.dumps(call_req_6))
            res6 = json.loads(await ws.recv())
            print(f"   Kết quả trả về:\n{res6['result']['content'][0]['text']}\n")

            # 10. Test tra cứu trực tuyến: Bếp từ đơn Sunhouse model SHD6805
            print("👉 11. Test 7: Tra cứu trực tuyến model cụ thể 'Bếp từ đơn SHD6805'")
            call_req_7 = {
                "jsonrpc": "2.0",
                "id": 16,
                "method": "tools/call",
                "params": {
                    "name": "tim_kiem_truc_tuyen_sunhouse",
                    "arguments": {
                        "tu_khoa": "bếp từ đơn sunhouse model SHD6805",
                        "loai_tim_kiem": "thong_so_model"
                    }
                }
            }
            await ws.send(json.dumps(call_req_7))
            res7 = json.loads(await ws.recv())
            print(f"   Kết quả trả về:\n{res7['result']['content'][0]['text']}\n")

            # 11. Test tra cứu trực tuyến: Bản tin mới cập nhật hàng ngày
            print("👉 12. Test 8: Tra cứu trực tuyến 'Bản tin mới cập nhật hàng ngày về Sunhouse'")
            call_req_8 = {
                "jsonrpc": "2.0",
                "id": 17,
                "method": "tools/call",
                "params": {
                    "name": "tim_kiem_truc_tuyen_sunhouse",
                    "arguments": {
                        "tu_khoa": "tin tức mới cập nhật hàng ngày",
                        "loai_tim_kiem": "tin_tuc_moi"
                    }
                }
            }
            await ws.send(json.dumps(call_req_8))
            res8 = json.loads(await ws.recv())
            print(f"   Kết quả trả về:\n{res8['result']['content'][0]['text']}\n")

            # 12. Test tra cứu trực tuyến: Sản phẩm mới / Model quạt điều hòa SHD7737
            print("👉 13. Test 9: Tra cứu trực tuyến model 'Quạt điều hòa SHD7737'")
            call_req_9 = {
                "jsonrpc": "2.0",
                "id": 18,
                "method": "tools/call",
                "params": {
                    "name": "tim_kiem_truc_tuyen_sunhouse",
                    "arguments": {
                        "tu_khoa": "quạt điều hòa SHD7737"
                    }
                }
            }
            await ws.send(json.dumps(call_req_9))
            res9 = json.loads(await ws.recv())
            print(f"   Kết quả trả về:\n{res9['result']['content'][0]['text']}\n")

            print("🎉 TẤT CẢ CÁC BÀI TEST MCP SERVER ĐÃ THÀNH CÔNG 100%!")

    except Exception as e:
        print(f"❌ Lỗi trong quá trình kiểm thử: {e}")

if __name__ == "__main__":
    asyncio.run(run_tests())
