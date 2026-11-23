# BỘ CÔNG CỤ ĐIỀU KHIỂN SERVER XIAOZHI (TOOLS_SERVER)

Thư mục này tập trung toàn bộ các script điều khiển khởi động, tắt và cấu hình Firewall cho toàn bộ hệ sinh thái Server XiaoZhi trên Windows.

---

## 🚀 Danh Sách File Khởi Động (Start)

| Tên File | Chức Năng | Cổng / Giao Thức |
| :--- | :--- | :--- |
| **`KHOI_DONG_TAT_CA_SERVER.bat`** | **Khởi động 1-Click các dịch vụ chính** (XiaoZhi Core + Sunhouse RAG MCP + SmartHome MCP Hub + YouTube Relay). Nhạc đã kết nối sẵn qua Vercel Cloud nên không mở thêm cửa sổ dư thừa. | 8000, 8003, 8004, 8005, 3001 |
| [**`1_KHOI_DONG_XIAOZHI_SERVER.bat`**](./1_KHOI_DONG_XIAOZHI_SERVER.bat) | Khởi động riêng XiaoZhi Voice Core Server (Nhận diện giọng nói, Opus, VAD, ASR, LLM, TTS) | `ws://0.0.0.0:8000/xiaozhi/v1/`<br>`http://0.0.0.0:8003/xiaozhi/ota/` |
| [**`2_KHOI_DONG_MCP_SERVER.bat`**](./2_KHOI_DONG_MCP_SERVER.bat) | Khởi động riêng Sunhouse RAG MCP Endpoint Server (Tra cứu bảo hành, tài liệu tri thức, mã lỗi Sunhouse) | `ws://127.0.0.1:8004/mcp_endpoint/mcp/`<br>`http://127.0.0.1:8004/health` |
| [**`3_KHOI_DONG_SMARTHOME_MCP_SERVER.bat`**](./3_KHOI_DONG_SMARTHOME_MCP_SERVER.bat) | Khởi động riêng SmartHome IoT & Home Assistant MCP Hub Server (Tuya Cloud, Pulsar, HA Tunnel, Robot 298 Pro) | `ws://127.0.0.1:8005/mcp_endpoint/mcp/`<br>`http://127.0.0.1:8005/health` |
| [**`3_KHOI_DONG_MUSIC_GATEWAY.bat`**](./3_KHOI_DONG_MUSIC_GATEWAY.bat) | Khởi động Music Resolver Gateway Local *(Dùng làm cổng dự phòng offline khi mất Internet, bình thường hệ thống dùng Vercel)* | `http://localhost:3000` |
| [**`4_KHOI_DONG_YOUTUBE_RELAY.bat`**](./4_KHOI_DONG_YOUTUBE_RELAY.bat) | Khởi động dịch vụ Audio Stream Relay & tạo Ngrok Tunnel cho phát nhạc YouTube | `http://localhost:3001`<br>Ngrok Domain |

---

## 🛑 Danh Sách File Dừng Server (Stop)

| Tên File | Chức Năng | Cổng Bị Tắt |
| :--- | :--- | :--- |
| **`DUNG_TAT_CA_SERVER.bat`** | **Dừng toàn bộ mọi dịch vụ** và tắt tiến trình ngrok.exe | Giải phóng 8000, 8003, 8004, 8005, 3000, 3001, ngrok |
| [**`DUNG_XIAOZHI_SERVER.bat`**](./DUNG_XIAOZHI_SERVER.bat) | Dừng XiaoZhi Voice Core Server | 8000, 8003 |
| [**`DUNG_MCP_SERVER.bat`**](./DUNG_MCP_SERVER.bat) | Dừng Sunhouse RAG MCP Endpoint Server | 8004 |
| [**`DUNG_SMARTHOME_MCP_SERVER.bat`**](./DUNG_SMARTHOME_MCP_SERVER.bat) | Dừng SmartHome IoT & HA MCP Hub Server | 8005 |
| [**`DUNG_MUSIC_GATEWAY.bat`**](./DUNG_MUSIC_GATEWAY.bat) | Dừng Music Resolver Gateway | 3000 |
| [**`DUNG_YOUTUBE_RELAY.bat`**](./DUNG_YOUTUBE_RELAY.bat) | Dừng Audio Stream Relay và tắt ngrok.exe | 3001, ngrok.exe |

---

## 🛠️ Công Cụ Cấu Hình & Tiện Ích

| Tên File | Chức Năng |
| :--- | :--- |
| **`CAU_HINH_FIREWALL_TAT_CA_CONG.bat`** | Mở toàn bộ cổng Inbound trên Windows Firewall cho LAN |
| **`KET_NOI_MCP_XIAOZHI_CLOUD.bat`** | Cấu hình nhanh kết nối MCP Cloud cho XiaoZhi |
| **`TIEN_ICH_DEPLOY_VERCEL.bat`** | Deploy dịch vụ Resolver lên hạ tầng Vercel Serverless |
