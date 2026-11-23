# Tóm Tắt Chi Tiết Luồng Logic Hoạt Động — Server Backend XiaoZhi

---
## 📑 Mục Lục

- [I. TỔNG QUAN KIẾN TRÚC HỆ SINH THÁI BACKEND XIAOZHI](#i-tổng-quan-kiến-trúc-hệ-sinh-thái-backend-xiaozhi)
  - [1. Mục Đích & Bản Chất của Server Backend XiaoZhi](#1-mục-đích--bản-chất-của-server-backend-xiaozhi)
  - [2. Bản Đồ Hệ Sinh Thái: 5 Thành Phần Phối Hợp](#2-bản-đồ-hệ-sinh-thái-5-thành-phần-phối-hợp)
  - [3. Cấu Trúc Thư Mục & Module Toàn Dự Án (`xiaozhi-esp32-server`)](#3-cấu-trúc-thư-mục--module-toàn-dự-án-xiaozhi-esp32-server)
  - [4. Phân Tầng Trách Nhiệm Chi Tiết trong Lõi AI (`xiaozhi-server`)](#4-phân-tầng-trách-nhiệm-chi-tiết-trong-lõi-ai-xiaozhi-server)
  - [5. Quản Lý Vòng Đời Kết Nối & Máy Trạng Thái Phiên (Session Lifecycle)](#5-quản-lý-vòng-đời-kết-nối--máy-trạng-thái-phiên-session-lifecycle)
  - [6. Cơ Chế Xác Thực, Phân Quyền & Cấp Phát Cấu Hình Động](#6-cơ-chế-xác-thực-phân-quyền--cấp-phát-cấu-hình-động)
- [II. SƠ ĐỒ THUẬT TOÁN & CÁC LUỒNG HOẠT ĐỘNG CHÍNH (CORE PIPELINES)](#ii-sơ-đồ-thuật-toán--các-luồng-hoạt-động-chính-core-pipelines)
  - [1. Luồng Khởi Động Server & Quản Lý Đa Nhiệm Bất Đồng Bộ](#1-luồng-khởi-động-server--quản-lý-đa-nhiệm-bất-đồng-bộ)
  - [2. Luồng Kích Hoạt Thiết Bị & Cấp Phát Điểm Kết Nối (OTA & Provisioning)](#2-luồng-kích-hoạt-thiết-bị--cấp-phát-điểm-kết-nối-ota--provisioning)
  - [3. Luồng Bắt Tay WebSocket & Đàm Phán Năng Lực (Handshake & Capabilities)](#3-luồng-bắt-tay-websocket--đàm-phán-năng-lực-handshake--capabilities)
  - [4. Luồng Thu Nhận Âm Thanh, Lọc Vọng (AEC), VAD & Nhận Dạng (ASR)](#4-luồng-thu-nhận-âm-thanh-lọc-vọng-aec-vad--nhận-dạng-asr)
  - [5. Luồng Xử Lý Trí Tuệ Nhân Tạo & Stream LLM Đa Phương Thức](#5-luồng-xử-lý-trí-tuệ-nhân-tạo--stream-llm-đa-phương-thức)
    - [5.1. Bản Chất Stateless & Cấu Trúc Payload Mỗi Lượt Nói (Kể Cả Câu "Xin Chào")](#51-bản-chất-stateless--cấu-trúc-payload-mỗi-lượt-nói-kể-cả-câu-xin-chào)
    - [5.2. Khảo Sát Tính Năng Prompt Caching Trên Các Nhà Cung Cấp](#52-khảo-sát-tính-năng-prompt-caching-trên-các-nhà-cung-cấp)
    - [5.3. Nguyên Lý Prefix Matching & 5 Nguyên Tắc Vàng Tránh "Vỡ Cache"](#53-nguyên-lý-prefix-matching--5-nguyên-tắc-vàng-tránh-vỡ-cache)
    - [5.4. Giải Mã Cơ Chế: "Vỏ Bọc JSON API" vs "Cụm Token Thực Tế Trong Transformer"](#54-giải-mã-cơ-chế-vỏ-bọc-json-api-vs-cụm-token-thực-tế-trong-transformer)
    - [5.5. "Nghịch Lý Tối Ưu Hóa": Vì Sao KHÔNG Nên Viết Bộ Lọc Bật/Tắt Tools?](#55-nghịch-lý-tối-ưu-hóa-vì-sao-không-nên-viết-bộ-lọc-bậttắt-tools)
  - [6. Luồng Tổng Hợp Giọng Nói (TTS) & Bộ Điều Khiển Tốc Độ Phát (Rate Controller)](#6-luồng-tổng-hợp-giọng-nói-tts--bộ-điều-khiển-tốc-độ-phát-rate-controller)
  - [7. Luồng Thực Thi Công Cụ Cục Bộ & Đám Mây (MCP & Unified Tool Calling)](#7-luồng-thực-thi-công-cụ-cục-bộ--đám-mây-mcp--unified-tool-calling)
  - [8. Cơ Chế Ngắt Lời Thời Gian Thực (Full-Duplex Barge-In / Abort)](#8-cơ-chế-ngắt-lời-thời-gian-thực-full-duplex-barge-in--abort)
- [III. CẨM NANG DÀNH CHO LẬP TRÌNH VIÊN TỰ PHÁT TRIỂN SERVER](#iii-cẩm-nang-dành-cho-lập-trình-viên-tự-phát-triển-server)
  - [1. Các Điểm Nghẽn & Sai Lầm Kiến Trúc Cần Tránh Khi Tự Viết Lại Code](#1-các-điểm-nghẽn--sai-lầm-kiến-trúc-cần-tránh-khi-tự-viết-lại-code)
  - [2. Hướng Dẫn Thêm Một Server Plugin / Tool Mới](#2-hướng-dẫn-thêm-một-server-plugin--tool-mới)
  - [3. Hướng Dẫn Tích Hợp Provider ASR / LLM / TTS Tùy Chỉnh](#3-hướng-dẫn-tích-hợp-provider-asr--llm--tts-tùy-chỉnh)
  - [4. Mô Thức Triển Khai: Standalone Cục Bộ vs Hệ Thống Doanh Nghiệp Phân Tán](#4-mô-thức-triển-khai-standalone-cục-bộ-vs-hệ-thống-doanh-nghiệp-phân-tán)
  - [5. Bảng Tra Cứu Cổng Mạng, Giao Thức & Cấu Trúc Message Chuẩn](#5-bảng-tra-cứu-cổng-mạng-giao-thức--cấu-trúc-message-chuẩn)

---

## I. TỔNG QUAN KIẾN TRÚC HỆ SINH THÁI BACKEND XIAOZHI

### 1. Mục Đích & Bản Chất của Server Backend XiaoZhi

Nếu Firmware ESP32 đóng vai trò là **"tai, mắt, miệng và tay chân"** (thu âm I2S, hiển thị OLED/LCD, phát loa và kích hoạt chân GPIO), thì cụm Server Backend XiaoZhi chính là **"bộ não xử lý trung ương đặt trên Cloud/Edge"**.

Backend XiaoZhi đảm nhận các sứ mệnh sống còn:
1. **Duy trì phiên kết nối Full-Duplex (hai chiều đồng thời) siêu tốc**: Tiếp nhận luồng âm thanh nén Opus liên tục từ thiết bị qua WebSocket (hoặc MQTT/UDP Gateway) với độ trễ tính bằng mili-giây.
2. **Chuỗi cung ứng AI thông minh (AI Processing Pipeline)**: Giải mã âm thanh ➔ Khử tiếng vọng (AEC) ➔ Phát hiện giọng nói (VAD) ➔ Nhận dạng giọng nói (ASR) ➔ Quản lý trí nhớ & ngữ cảnh (Dialogue Memory RAG) ➔ Xử lý ngôn ngữ tự nhiên bằng LLM ➔ Tổng hợp giọng nói biểu cảm (TTS) ➔ Bắn ngược luồng Opus về thiết bị.
3. **Cầu nối giao thức Model Context Protocol (MCP)**: Cho phép mô hình LLM trên Cloud có thể "gọi ngược" lại phần cứng ESP32 để ra lệnh vật lý (bật quạt, bật đèn, quét Wi-Fi, đổi âm lượng, chụp ảnh camera) theo chuẩn JSON-RPC 2.0 mà không làm lộ kiến trúc phần cứng với mô hình.
4. **Quản lý thiết bị & Cấp phát dịch vụ động (Dynamic Provisioning & OTA)**: Phân phối URL kết nối, cấp phát Token bảo mật, kiểm tra và nâng cấp Firmware từ xa cho hàng ngàn vi điều khiển.

---

### 2. Bản Đồ Hệ Sinh Thái: 5 Thành Phần Phối Hợp

Hệ sinh thái mã nguồn mở `xiaozhi-esp32-server` được thiết kế theo mô hình **phân tán - đa ngôn ngữ (Polyglot Microservices)**, bao gồm 5 dự án độc lập nhưng liên kết chặt chẽ:

```	ext
====================================================================================================
                        BẢN ĐỒ HỆ SINH THÁI 5 THÀNH PHẦN XIAOZHI BACKEND
====================================================================================================

   ┌───────────────────────────────────────────────────────────┐
   │             [1. THIẾT BỊ ĐẦU CUỐI (CLIENTS)]              │
   │  • ESP32 / ESP32-S3 (Phần cứng vi điều khiển: Mic/Loa/LCD) │
   │  • Digital Human (Trình giả lập Web Avatar để test)       │
   └─────────────────────────────┬─────────────────────────────┘
                                 │
     ┌───────────────────────────┴───────────────────────────┐
     │ (1) HTTP GET /xiaozhi/ota/                            │ (2) WebSocket: ws://...:8000/xiaozhi/v1/
     │     Cấp phát động URL & Token                         │     Opus Audio 2 chiều & JSON Events
     ▼                                                       ▼
┌─────────────────────────────────┐   ┌────────────────────────────────────────────────────────┐
│  SimpleHttpServer (Port 8003)   │   │     [2. LÕI AI THỜI GIAN THỰC: xiaozhi-server]         │
│  - API OTA & cấp phát WebSocket │   │  • WebSocketServer: Nhận diện, bắt tay, giải mã Opus   │
│  - Tải firmware .bin cập nhật   │   │  • Audio Pipeline: Lọc vọng (AEC) + Silero VAD        │
│  - /mcp/vision/explain (Ảnh)   │   │  • AI Orchestrator: Quản lý ASR -> LLM -> TTS Stream  │
└─────────────────────────────────┘   │  • Unified Tool Manager: Điều khiển MCP & Plugins      │
                                      └───────────┬───────────────────────────────┬────────────┘
                                                  │                               │
                                      (Gọi Model) │                   (tools/call)│ [MCP Protocol]
                                                  ▼                               ▼
                      ┌───────────────────────────────────────┐       ┌────────────────────────┐
                      │ [4. DỊCH VỤ AI ĐÁM MÂY (CLOUD AI)]    │       │ Ra lệnh ngược về ESP32 │
                      │ • ASR: Aliyun, Doubao, Whisper, Vosk  │       │ Bật/Tắt GPIO, Đổi Vol, │
                      │ • LLM: OpenAI, Groq, DeepSeek, Gemini │       │ Đổi giao diện màn hình │
                      │ • TTS: Edge-TTS, FishSpeech, Piper    │       └────────────────────────┘
                      └───────────────────────────────────────┘

────────────────────────────────────────────────────────────────────────────────────────────────────
   [3. HẠ TẦNG QUẢN TRỊ DOANH NGHIỆP: manager-platform (TÙY CHỌN, KHI CHẠY MÔ HÌNH ENTERPRISE)]
────────────────────────────────────────────────────────────────────────────────────────────────────
   ┌──────────────────────────┐      ┌──────────────────────────┐
   │ manager-web (Vue.js 8001)│      │manager-mobile (Uni-App)  │
   │ Giao diện Web Admin      │      │App di động iOS / Android │
   └────────────┬─────────────┘      └────────────┬─────────────┘
                │                                 │
                └────────────────┬────────────────┘
                                 ▼ (RESTful API HTTP)
   ┌───────────────────────────────────────────────────────────────────────────────────────────┐
   │ manager-api (Java Spring Boot - Port 8002)                                                │
   │ • Quản lý tài khoản, thiết bị, mã kích hoạt (Binding Code), phân quyền                    │
   │ • Quản lý kho firmware OTA, cơ sở tri thức RAG                                            │
   │ • Kết nối cơ sở dữ liệu MySQL 8.0 & Cache Redis                                           │
   └─────────────────────────────┬─────────────────────────────────────────────────────────────┘
                                 │
                                 ▼ (xiaozhi-server kéo cấu hình động khi khởi động - Tùy chọn)
```

| Tên Module | Ngôn Ngữ / Nền Tảng | Cổng Mặc Định | Nhiệm Vụ Cốt Lõi |
| :--- | :--- | :--- | :--- |
| **`xiaozhi-server`** | Python 3.10+ (AsyncIO) | **8000** (WS), **8003** (HTTP) | **Trọng tâm tối thượng**: Xử lý luồng âm thanh Opus, VAD, ASR, LLM, TTS, điều khiển MCP Tool. Chạy độc lập hoàn toàn bằng file `config.yaml` mà không cần Java. |
| **`manager-api`** | Java 17+ (Spring Boot 3) | **8002** (HTTP REST) | Quản lý hệ thống: Xác thực tài khoản, kích hoạt thiết bị, kho tri thức RAG, cấu hình đại lý (Agent), quản lý firmware OTA vào MySQL/Redis. |
| **`manager-web`** | Node.js / Vue.js 3 | **8001** (Web UI) | Giao diện đồ họa (Dashboard) trên trình duyệt giúp người quản trị cấu hình AI, xem nhật ký đàm thoại, quản lý thiết bị trực quan. |
| **`manager-mobile`** | Uni-App / Vue 3 / Vite | App / Mini-Program | Ứng dụng di động (Android, iOS, WeChat Mini-app) giúp người dùng quản lý thiết bị XiaoZhi tiện lợi trên điện thoại. |
| **`digital-human`** | Python + HTML5 Web | Web Browser (Local) | Giả lập người ảo (Avatar) và thiết bị ảo trên trình duyệt, có tích hợp sẵn từ khóa đánh thức Sherpa-ONNX để dev và test không cần mạch ESP32. |

---

### 3. Cấu Trúc Thư Mục & Module Toàn Dự Án (xiaozhi-esp32-server)

Hệ sinh thái máy chủ XiaoZhi được thiết kế theo **Phương Án A (Chuẩn Kiến Trúc Microservices Phân Tầng Kỹ Sư Chuyên Nghiệp - Chia Để Trị)**, phân tách rạch ròi 3 cụm Server độc lập, tránh xung đột chéo và bảo toàn trọn vẹn luồng âm thanh thời gian thực. Trong đó, **xiaozhi-server/** là **linh hồn cốt lõi** đảm nhận toàn bộ DSP âm thanh và pipeline trí tuệ nhân tạo:

```text
xiaozhi-esp32-server/         📁 HỆ SINH THÁI BACKEND XIAOZHI (KIẾN TRÚC MICROSERVICES)
│
├── main/                     📁 CỤM SERVICE 1: CORE ENGINE & QUẢN TRỊ (PORT 8000 & 8003)
│   │
│   ├── xiaozhi-server/       📁 LÕI XỬ LÝ ÂM THANH & AI CHÍNH (PYTHON) - LINH HỒN DỰ ÁN
│   │   ├── app.py            → Điểm khởi chạy ứng dụng (Khởi tạo WS 8000 & HTTP 8003)
│   │   ├── config.yaml       → Cấu hình tổng (Voice, Model LLM, Prompt, VAD, Endpoint)
│   │   ├── requirements.txt  → Danh sách thư viện Python (websockets, aiohttp, opuslib)
│   │   │
│   │   ├── config/           📁 Module quản lý cấu hình tập trung và ghi log
│   │   │   ├── logger.py     → Loguru đa luồng, định dạng màu sắc theo tag module
│   │   │   ├── settings.py   → Nạp cấu hình động runtime từ YAML hoặc Java API
│   │   │   └── config_loader.py → Thứ tự ưu tiên: data/.config.yaml > config.yaml
│   │   │
│   │   ├── core/             📁 TRÁI TIM KIẾN TRÚC MÁY CHỦ (AI & CONNECTION ENGINE)
│   │   │   ├── connection.py → Class ConnectionHandler: Quản lý trọn vẹn 1 phiên đàm thoại
│   │   │   ├── websocket_server.py → Port 8000: Bắt tay WS, nhận diện header, whitelist
│   │   │   ├── http_server.py→ Port 8003: Cung cấp API cập nhật OTA và phân tích Vision
│   │   │   ├── auth.py       → Xác thực Token HMAC-SHA256 / JWT bảo vệ kết nối
│   │   │   │
│   │   │   ├── api/          📁 Xử lý các REST API chuyên dụng trên cổng HTTP 8003
│   │   │   │   ├── ota_handler.py    → Cấp phát WebSocket URL, kiểm tra file .bin OTA
│   │   │   │   └── vision_handler.py → Phân tích hình ảnh camera gửi lên từ ESP32-CAM
│   │   │   │
│   │   │   ├── handle/       📁 Các bộ điều phối thông điệp đàm thoại thời gian thực
│   │   │   │   ├── receiveAudioHandle.py → Đón nhận PCM, kích hoạt VAD, đẩy sang ASR
│   │   │   │   ├── sendAudioHandle.py    → Quản lý luồng gửi Opus, gửi JSON trạng thái
│   │   │   │   ├── helloHandle.py        → Bắt tay Loa, đàm phán Audio format, nạp MCP
│   │   │   │   ├── abortHandle.py        → Cơ chế ngắt lời tức thì (Full-Duplex Barge-in)
│   │   │   │   ├── intentHandler.py      → Phân tích nhanh ý định (Ngắt máy, điều hướng)
│   │   │   │   └── textHandler/          → Phân rã xử lý gói tin JSON ('hello', 'mcp'...)
│   │   │   │
│   │   │   ├── providers/    📁 Lớp trừu tượng và tích hợp các dịch vụ AI đám mây
│   │   │   │   ├── vad/      → Phát hiện giọng nói (Silero VAD cục bộ độ nhạy cao)
│   │   │   │   ├── asr/      → Nhận dạng tiếng nói (FunASR, Whisper, Aliyun, Doubao)
│   │   │   │   ├── llm/      → Mô hình ngôn ngữ (OpenAI, Groq, DeepSeek, Gemini, Dify)
│   │   │   │   ├── tts/      → Tổng hợp giọng nói (Edge-TTS, FishSpeech, CosyVoice)
│   │   │   │   ├── memory/   → Quản lý bộ nhớ ngắn hạn và ngữ cảnh hội thoại Loa
│   │   │   │   └── tools/    → Quản lý công cụ MCP UnifiedToolHandler & MCP Client
│   │   │   │
│   │   │   ├── extensions/   📁 Khung mở rộng độc lập cho bản Việt hóa & Production
│   │   │   │   ├── stream_guard/   → Màng lọc luồng, chặn rò rỉ ký tự JSON ra Loa
│   │   │   │   ├── schema_adapter/ → Chuẩn hóa Schema cho các model Groq/Ollama
│   │   │   │   └── intent_router/  → Bộ định tuyến ý định tiếng Việt tốc độ cao
│   │   │   │
│   │   │   └── utils/        📁 Tiện ích bổ trợ (Mã hóa Opus, xử lý âm thanh PCM, thời gian)
│   │   │
│   │   └── plugins_func/     📁 Kho công cụ ngoại vi (Server Plugins / Function Calling)
│   │       ├── register.py   → Decorator @register_function đăng ký Tool cho LLM gọi
│   │       └── functions/    → Các tool viết sẵn: Tra thời tiết, âm lịch, tin tức...
│   │
│   ├── manager-api/          → Quản trị thiết bị, mã kích hoạt (Java Spring Boot)
│   ├── manager-web/          → Bảng điều khiển Web Quản trị (Vue.js + Element Plus)
│   ├── manager-mobile/       → Ứng dụng di động quản trị (Uni-App cross-platform)
│   └── digital-human/        → Trình giả lập người ảo trên trình duyệt để kiểm thử
│
├── mcp_sunhouse_rag/         📁 CỤM SERVICE 2: SUNHOUSE RAG KNOWLEDGE MCP (PORT 8004)
│   ├── main.py               → Điểm tiếp nhận MCP JSON-RPC 2.0 & HTTP Healthcheck (8004)
│   ├── config.py             → Cấu hình Token bảo mật, kết nối CSDL và Search Engine
│   └── tools/                📁 Kho công cụ MCP tri thức nội bộ & cứu cánh khách hàng
│       ├── tim_kiem_truc_tuyen.py → Tool Live Web Search: Tìm kiếm tin tức, dữ liệu thực
│       ├── tra_cuu_ma_loi.py      → Tool chẩn đoán mã lỗi thiết bị gia dụng Sunhouse
│       └── tra_cuu_thong_tin.py   → Tool RAG tra cứu chính sách bảo hành, trạm kỹ thuật
│
├── mcp_smarthome_hub/        📁 CỤM SERVICE 3: IOT SMARTHOME & HA MCP HUB (PORT 8005)
│   ├── main.py               → Daemon MCP JSON-RPC 2.0, Ingress WSS, HTTP Healthcheck
│   ├── storage/              → Tầng Lưu trữ DAL: AES-256-GCM, ẩn danh UID, RedLock, CRUD
│   ├── clients/              → Tầng Kết nối Cloud: Tuya OpenAPI (SG), Pulsar Consumer
│   ├── adapters/             → Tầng Chuẩn hóa: Dynamic DP Normalizer, Sweeper 298 Pro
│   ├── ha_bridge/            → Cầu nối HA: Reverse WebSocket Ingress, Redis Session
│   ├── dispatcher/           → Bộ định tuyến O(1) 4 nguồn (AWS, Tuya OEM, HA) < 5ms
│   ├── tools/                → Công cụ MCP Unified: smarthome_control, sweeper_tool
│   ├── routers/              → Cụm REST API: Onboarding eSunhouse 0-chạm, OAuth2, PIN
│   ├── edge_lan/             → Giao thức Tuya LAN TCP 6668 cục bộ (< 50ms, BOM = 0 VNĐ)
│   └── tests/                → Bộ kiểm thử tự động CI/CD theo giai đoạn (Pass gates)
│
├── Tools_server/             📁 BỘ CÔNG CỤ QUẢN TRỊ & KHỞI ĐỘNG 1-CLICK (WINDOWS BATCH)
│   ├── 1_KHOI_DONG_XIAOZHI_SERVER.bat         → Khởi động riêng Core Server (8000/8003)
│   ├── 2_KHOI_DONG_MCP_SERVER.bat             → Khởi động riêng Sunhouse RAG (8004)
│   ├── 3_KHOI_DONG_SMARTHOME_MCP_SERVER.bat   → Khởi động riêng SmartHome Hub (8005)
│   ├── 4_KHOI_DONG_YOUTUBE_RELAY.bat          → Khởi động YouTube Stream & Ngrok (3001)
│   ├── KHOI_DONG_TAT_CA_SERVER.bat            → 1-Click khởi động toàn bộ cụm server
│   ├── DUNG_TAT_CA_SERVER.bat                 → 1-Click giải phóng toàn bộ port server
│   └── CAU_HINH_FIREWALL_TAT_CA_CONG.bat      → Mở cổng Windows Firewall cho mạng LAN
│
├── my_docs_server/           📁 KHO TÀI LIỆU THIẾT KẾ & BẢN ĐỒ KIẾN TRÚC TOÀN HỆ THỐNG
│   ├── KẾ HOẠCH TRIỂN KHAI MCP HOME ASISSTANT SERVER điều khiển thiết bị IoT hãng Tuya.md
│   └── TOM_TAT_CHI_TIET_LUONG_LOGIC_HOAT_DONG_SERVER_XIAOZHI.md
│
├── docs/                     📁 Kho tài liệu tích hợp chuyên sâu (RAG, MCP, HA, FishSpeech)
├── venv/                     📁 Môi trường ảo Python độc lập cho toàn bộ server
└── docker-compose_all.yml    📁 Kịch bản điều phối Container toàn diện (Microservices)
```

---

### 4. Phân Tầng Trách Nhiệm Chi Tiết trong Lõi AI (`xiaozhi-server`)

Khi bạn tự phát triển hoặc viết lại code cho Server, việc hiểu rõ kiến trúc 4 tầng phân lập (Clean Architecture) của `xiaozhi-server` là điều tối quan trọng:

```	ext
┌────────────────────────────────────────────────────────────────────────┐
│ TẦNG 1: HẠ TẦNG MẠNG & GIAO VẬN (TRANSPORT LAYER)                     │
│ • websocket_server.py : Quản lý Socket kết nối, Whitelist, Ping/Pong  │
│ • http_server.py      : Quản lý cổng REST HTTP, cấp phát URL cho OTA   │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ TẦNG 2: ĐIỀU PHỐI & QUẢN LÝ PHIÊN (SESSION ORCHESTRATOR)              │
│ • core/connection.py         : Vòng đời Client, ThreadPool, Queue đệm  │
│ • core/handle/textHandle.py  : Phân loại thông điệp JSON đến           │
│ • core/handle/receiveAudio...: Giải mã Opus & Queue PCM               │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ TẦNG 3: CUNG ỨNG TRÍ TUỆ AI (AI PROVIDER PIPELINE)                    │
│ • VAD    : Silero cắt lát giọng nói (Voice Activity Detection)         │
│ • ASR    : Chuyển đổi âm thanh thành văn bản (Aliyun / Whisper / Vosk) │
│ • Memory : Truy xuất ngữ cảnh & RAG (Dialogue History / RAGFlow)       │
│ • LLM    : Sinh câu phản hồi & phát hiện cảm xúc (OpenAI / DeepSeek)   │
│ • TTS    : Đọc văn bản thành luồng âm thanh Opus (Edge-TTS / Piper)    │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ ▲
                        (Tool Call) │ │ (Tool Result)
                                    ▼ │
┌────────────────────────────────────────────────────────────────────────┐
│ TẦNG 4: THỰC THI HÀNH ĐỘNG & CÔNG CỤ (ACTUATION & TOOLS LAYER)        │
│ • unified_tool_handler.py : Bộ điều phối công cụ tập trung            │
│ • device_mcp              : Điều khiển phần cứng ESP32 qua JSON-RPC    │
│ • plugins_func            : Gọi API thời tiết, Home Assistant, Web     │
└────────────────────────────────────────────────────────────────────────┘
```

1. **Tầng Giao Vận (Transport Layer)**: Chỉ quan tâm đến bytes và chuỗi text thuần túy. Kiểm tra tính hợp lệ của IP, Header (`device-id`, `client-id`, `authorization`).
2. **Tầng Quản Lý Phiên (Session Orchestrator)**: Mỗi kết nối mở ra được đóng gói vào một đối tượng `ConnectionHandler` riêng biệt. Tầng này nắm giữ trạng thái: thiết bị có đang nói không (`client_is_speaking`), đang ở chế độ nghe nào (`auto` hay `manual`), và dọn dẹp bộ nhớ khi ngắt kết nối.
3. **Tầng Cung Ứng AI (AI Pipeline Layer)**: Hoạt động theo mô hình đường ống bất đồng bộ (Async Pipeline). Dữ liệu chảy tuần tự hoặc stream song song: `Audio Chunk ➔ VAD ➔ ASR Text ➔ Context Assembly ➔ LLM Stream ➔ TTS Stream ➔ Rate Controller`.
4. **Tầng Thực Thi Công Cụ (Tool Calling Layer)**: Khi LLM muốn thực hiện hành động, tầng này phân loại công cụ đó thuộc về phần cứng thiết bị (Device MCP) hay thuộc về đám mây (Server Plugins) để định tuyến chính xác.

---

### 5. Quản Lý Vòng Đời Kết Nối & Máy Trạng Thái Phiên (Session Lifecycle)

Đối tượng [ConnectionHandler](file:///e:/Espressif/frameworks/esp-idf-v5.5.3/examples/xiaozhi-esp32-main/xiaozhi-esp32-server/main/xiaozhi-server/core/connection.py#L79-L202) trong `core/connection.py` sở hữu một máy trạng thái nội tại cực kỳ chặt chẽ:

```	ext
[*] (Khởi động)
 │
 ▼
[Disconnected] (Thiết bị chưa kết nối)
 │
 │ (1) Mở kết nối WebSocket: ws://...:8000/xiaozhi/v1/
 ▼
[Authenticating] (Kiểm tra Device ID & Token JWT)
 ├─ [Sai Token / Bị chặn Whitelist] ──► [Terminated] (Đóng kết nối)
 │
 └─ [Hợp lệ]
     │
     ▼
[Initializing] (Bắt tay đàm phán tính năng)
 │  ├─ Nhận {"type":"hello"} từ Client
 │  └─ Trả về Server Hello + audio_params
 │
 └─► [Ready: PHIÊN HOẠT ĐỘNG CHÍNH (ACTIVE SESSION)]
      │
      ├─► [Idle] (Chờ người dùng bắt đầu nói)
      │     │
      │     ▼ (VAD phát hiện giọng nói người dùng)
      ├─► [Listening] (Thu Opus, lọc AEC, tích lũy PCM)
      │     │
      │     ▼ (VAD phát hiện dừng nói / voice_stop)
      ├─► [Processing] (Chạy ASR nhận dạng văn bản)
      │     │
      │     ▼ (Đẩy văn bản vào LLM)
      ├─► [Thinking] (LLM suy luận, phát hiện cảm xúc, gọi Tool MCP)
      │     │
      │     ▼ (Tokens đầu tiên chảy sang TTS)
      ├─► [Speaking] (Stream gói Opus về Loa thiết bị)
      │     ├─ [Phát hết âm thanh] ──────────────────────────► Quay về [Idle]
      │     │
      │     └─ [Bị ngắt lời (Barge-in: có tiếng đè)] ────────► Quay lại [Listening]
      │
      └─► [SavingMemory & Closed] (Hết timeout 120s hoặc ngắt mạng: Lưu RAG & dọn RAM)
```

#### Các thông số trạng thái trọng yếu trong `ConnectionHandler`:
- `self.session_id`: Chuỗi UUID định danh duy nhất cho một phiên đàm thoại (được tạo mới mỗi khi thiết bị mở lại kết nối).
- `self.sentence_id`: Chuỗi UUID định danh cho **từng câu nói cụ thể của AI**. Mỗi khi người dùng hỏi một câu mới, `sentence_id` thay đổi để vô hiệu hóa mọi gói tin âm thanh rác còn sót lại của câu nói trước.
- `self.client_is_speaking`: Đánh dấu cờ True khi server đang bắn âm thanh về thiết bị. Nếu cờ này bật mà micro lại thu được tiếng người, hệ thống lập tức kích hoạt cơ chế **Cắt Lời (Abort/Barge-in)**.
- `self.client_listen_mode`: 
  - `"auto"`: Chế độ đàm thoại tự do (mặc định), hệ thống tự nghe và tự ngắt bằng VAD.
  - `"manual"`: Chế độ bộ đàm (Push-to-talk), chỉ nghe khi người dùng giữ nút bấm, không cho phép ngắt lời tự động.
- `self.client_abort`: Cờ ngắt khẩn cấp. Khi bật True, toàn bộ vòng lặp sinh token của LLM và hàng đợi âm thanh TTS đang phát dở lập tức bị hủy bỏ (drop).

---

### 6. Cơ Chế Xác Thực, Phân Quyền & Cấp Phát Cấu Hình Động

Server XiaoZhi hỗ trợ hai hình thức hoạt động: **Độc lập (Standalone)** và **Liên kết Doanh nghiệp (Enterprise Mode với `manager-api`)**:

1. **Chế độ Độc lập (Standalone Mode - Mặc định cho lập trình viên)**:
   - Server đọc trực tiếp file cấu hình cục bộ `config.yaml` (hoặc `data/.config.yaml`).
   - Nếu `server.auth.enabled = false`: Server chấp nhận mọi thiết bị kết nối lên mà không yêu cầu Token.
   - Nếu `server.auth.enabled = true`: Thiết bị phải cung cấp mã Token trong Header `Authorization: Bearer <token>` hoặc nằm trong danh sách trắng `allowed_devices: ["MAC_ADDRESS"]`.
   - Token được ký bằng khóa bí mật `server.auth_key` qua thuật toán HMAC-SHA256 (triển khai trong `core/auth.py`).

2. **Chế độ Cấp cấu hình Động (Enterprise Dynamic Provisioning)**:
   - Khi thiết bị ESP32 khởi động, nó chưa biết địa chỉ IP của máy chủ WebSocket đàm thoại. Nó gửi một request HTTP GET lên cổng **8003** (`/xiaozhi/ota/`).
   - Server kiểm tra MAC Address của thiết bị. Nếu hợp lệ, Server sẽ tự động ký một Token mới và trả về JSON:
     ```json
     {
       "server_time": {"timestamp": 1727850000000, "timezone_offset": 480},
       "websocket": {
         "url": "ws://192.168.1.100:8000/xiaozhi/v1/",
         "token": "eyJhbGciOiJIUzI1NiIsIn..."
       },
       "firmware": {"version": "1.0.0", "url": ""}
     }
     ```
   - Nhờ cơ chế này, bạn có thể thay đổi cổng hoặc IP của cụm AI Server trên Cloud mà **không cần phải nạp lại code cho vi điều khiển ESP32**!

---

## II. SƠ ĐỒ THUẬT TOÁN & CÁC LUỒNG HOẠT ĐỘNG CHÍNH (CORE PIPELINES)

---

### 1. Luồng Khởi Động Server & Quản Lý Đa Nhiệm Bất Đồng Bộ

Điểm nhập cuộc của server nằm tại file [app.py](file:///e:/Espressif/frameworks/esp-idf-v5.5.3/examples/xiaozhi-esp32-main/xiaozhi-esp32-server/main/xiaozhi-server/app.py). Server sử dụng mô hình kết hợp **AsyncIO Event Loop + ThreadPoolExecutor** để đảm bảo tác vụ mạng I/O không bao giờ bị nghẽn bởi các thuật toán AI tính toán nặng.

```	ext
               [🚀 KHỞI ĐỘNG PYTHON SERVER: app.py]
                               │
               (1) check_ffmpeg_installed() (Bắt buộc để giải mã âm thanh)
               (2) load_config() (Ưu tiên nạp: data/.config.yaml > config.yaml)
               (3) Thiết lập Auth Key (JWT Secret bảo mật)
                               │
                               ▼
        ┌──────────────────────┴──────────────────────┐
        │                                             │
        ▼                                             ▼
 [Task 1: WebSocketServer]                   [Task 2: SimpleHttpServer]
 (Port 8000: ws://.../xiaozhi/v1/)           (Port 8003: http://.../xiaozhi/ota/)
   ├─ Lắng nghe luồng âm thanh thời gian thực  ├─ /xiaozhi/ota/ (Cấp phát URL & Token)
   ├─ Bắt tay đàm phán năng lực (Features)     ├─ /xiaozhi/ota/download/ (Tải firmware .bin)
   └─ Xử lý đàm thoại & công cụ MCP           └─ /mcp/vision/explain (Phân tích ảnh)
        │                                             │
        └──────────────────────┬──────────────────────┘
                               ▼
        [Task 3: Background Garbage Collector (gc_manager)]
             (Chạy định kỳ 300s/lần thu hồi bộ nhớ RAM rác)
                               │
                               ▼
                    [wait_for_exit() Loop]
             (Lắng nghe SIGINT / SIGTERM để tắt server an toàn)
```

---

### 2. Luồng Kích Hoạt Thiết Bị & Cấp Phát Điểm Kết Nối (OTA & Provisioning)

Đây là mắt xích đầu tiên khi phần cứng cắm điện khởi động, đảm bảo tính mềm dẻo trong triển khai thực tế.

```	ext
[ESP32 Vi Điều Khiển]         [SimpleHttpServer (Port 8003)]       [Auth & data/bin/]
         │                                   │                              │
         │ (1) Khởi động & Wi-Fi thành công  │                              │
         ├──────────────────────────────────►│                              │
         │     HTTP GET /xiaozhi/ota/        │                              │
         │     Headers: device-id, model...  │                              │
         │                                   ├─────────────────────────────►│
         │                                   │ (2) Kiểm tra ID, sinh Token  │
         │                                   │     Quét firmware .bin mới   │
         │                                   │◄─────────────────────────────┤
         │                                   │                              │
         │ (3) Trả về JSON cấp phát động     │                              │
         │◄──────────────────────────────────┤                              │
         │     {                             │                              │
         │       "websocket": {              │                              │
         │         "url": "ws://...:8000",   │                              │
         │         "token": "..."            │                              │
         │       },                          │                              │
         │       "firmware": {...}           │                              │
         │     }                             │                              │
         │                                   │                              │
         ▼                                   │                              │
[ESP32 nạp URL & Token vào RAM]              │                              │
[Sẵn sàng mở kênh đàm thoại WebSocket!]      │                              │
```

---

### 3. Luồng Bắt Tay WebSocket & Đàm Phán Năng Lực (Handshake & Capabilities)

Sau khi có URL từ bước OTA, ESP32 sẽ mở kết nối WebSocket đến `ws://<ip>:8000/xiaozhi/v1/`.

```	ext
[ESP32 Vi Điều Khiển]            [WebSocketServer (8000)]           [Session (core/connection.py)]
         │                                   │                                    │
         │ (1) Mở kết nối WebSocket          │                                    │
         ├──────────────────────────────────►│                                    │
         │     Upgrade: websocket            │ (2) Xác thực Token/Whitelist       │
         │     Header: authorization, dev-id ├───────────────────────────────────►│
         │                                   │     Tạo ConnectionHandler (UUID)   │
         │ (3) 101 Switching Protocols       │◄───────────────────────────────────┤
         │◄──────────────────────────────────┤                                    │
         │                                   │                                    │
         │ (4) Gửi Hello JSON                │                                    │
         ├──────────────────────────────────►│                                    │
         │     type: "hello",                │ (5) Cấu hình audio_params          │
         │     audio_params: {opus, 24kHz},  ├───────────────────────────────────►│
         │     features: {mcp: true}         │     Lưu cờ hỗ trợ MCP & AEC        │
         │                                   │                                    │
         │ (6) Nhận Server Hello JSON        │ (6) Phản hồi Server Hello JSON     │
         │◄──────────────────────────────────┴────────────────────────────────────┤
         │     type: "hello", transport: "websocket", session_id: "..."           │
         │                                                                        │
         │ (7) [Nếu bật MCP] Gửi JSON-RPC Khởi tạo & Lấy danh sách công cụ        │
         │◄───────────────────────────────────────────────────────────────────────┤
         │     Server: {"jsonrpc": "2.0", "method": "tools/list"}                 │
         │     ESP32 : {"result": {"tools": [{"name": "turn_on_light"}]}}        │
         │                                                                        │
         ▼                                                                        ▼
[BẮT ĐẦU ĐÀM THOẠI 2 CHIỀU THỜI GIAN THỰC (FULL-DUPLEX REAL-TIME AUDIO SESSION)]
```

---

### 4. Luồng Thu Nhận Âm Thanh, Lọc Vọng (AEC), VAD & Nhận Dạng (ASR)

Đây là luồng xử lý dữ liệu nhị phân (Binary Pipeline) có cường độ cao nhất trong toàn bộ hệ thống.

```	ext
[🎤 MICROPHONE ESP32] (Thu âm I2S 16kHz)
        │
        ├─ [Nén Opus Encoder trên chip] (Gói 60ms)
        │
        ▼ (Gửi gói nhị phân qua WebSocket liên tục)
[core/websocket_server.py]
        │
        ▼ (Nhận bytes)
[core/connection.py: _route_message()]
        │
        ├─ (1) Giải mã Opus sang PCM 16-bit: _decode_opus_packet()
        │
        ├─ (2) Lọc tiếng vọng (Server AEC nếu bật): _apply_aec()
        │        └─ Thuật toán kết hợp: Khớp tương quan trễ + Bộ lọc Wiener + Trừ phổ
        │
        ▼ (Đẩy PCM vào asr_audio_queue)
[core/handle/receiveAudioHandle.py: handleAudioMessage()]
        │
        ├─ (3) Chạy Silero VAD (Voice Activity Detection): conn.vad.is_vad()
        │        ├─ Nếu KHÔNG có tiếng: Đếm thời gian im lặng (Timeout 120s ngắt kết nối)
        │        └─ Nếu CÓ tiếng người: Đánh dấu conn.client_have_voice = True
        │                 └─ (Nếu loa đang phát dở -> Lập tức gọi handleAbortMessage để ngắt loa!)
        │
        ▼ (Tích lũy các frame PCM có tiếng người)
[core/providers/asr/ (Module Nhận Dạng Giọng Nói)]
        ├─ CHẾ ĐỘ 1: STREAM ASR (Aliyun Stream, Doubao Stream)
        │     └─ Stream PCM thời gian thực qua WebSocket của nhà cung cấp Cloud
        │
        └─ CHẾ ĐỘ 2: CHUNK / REST ASR (OpenAI Whisper, FunASR, Vosk)
              └─ Khi VAD phát hiện người dùng dừng nói (voice_stop)
              └─ Gom toàn bộ mảng PCM -> Đóng gói file WAV RAM -> Bắn API ASR
                    │
                    ▼
            [VĂN BẢN KẾT QUẢ (Transcribed Text)]
                    │
                    ▼
    [startToChat(conn, text) - Bắt đầu giai đoạn Trí Tuệ Nhân Tạo]
```

---

### 5. Luồng Xử Lý Trí Tuệ Nhân Tạo & Stream LLM Đa Phương Thức

Khi văn bản người dùng nói được ASR giải mã, hàm [startToChat](file:///e:/Espressif/frameworks/esp-idf-v5.5.3/examples/xiaozhi-esp32-main/xiaozhi-esp32-server/main/xiaozhi-server/core/handle/receiveAudioHandle.py#L43) và [chat](file:///e:/Espressif/frameworks/esp-idf-v5.5.3/examples/xiaozhi-esp32-main/xiaozhi-esp32-server/main/xiaozhi-server/core/connection.py#L1055) sẽ kích hoạt chuỗi suy luận:

```	ext
[Văn bản từ ASR / Chat Text]
         │
         ▼
[core/handle/receiveAudioHandle.py: startToChat()]
         │
         ├─ (1) Gửi gói JSON báo cho ESP32 hiển thị trạng thái:
         │        {"type": "llm", "state": "start"}
         │        {"type": "stt", "text": "Người dùng vừa nói gì..."}
         │
         ▼
[core/connection.py: chat()]
         │
         ├─ (2) Lắp ráp Prompt & Ngữ cảnh:
         │        ├─ System Prompt (Tính cách AI, persona, ngày giờ)
         │        ├─ Memory Context (Lịch sử đàm thoại gần nhất + RAG tri thức)
         │        └─ Tool Declarations (Khai báo JSON Schema: MCP phần cứng + Plugins)
         │
         ▼ (Gọi Async Generator Stream)
[core/providers/llm/ (OpenAI / DeepSeek / Claude / Gemini / Qwen)]
         │
         ▼ (Nhận từng Token văn bản trả về qua Generator)
[Vòng lặp đọc Stream Tokens: async for token in response]
         │
         ├─ (3) Tách & phát hiện Thẻ Cảm Xúc (Emotion Extraction):
         │        Ví dụ: "[happy] Chào bạn" -> Gửi JSON cảm xúc:
         │        {"type": "llm", "emotion": "happy"} -> ESP32 đổi biểu cảm khuôn mặt
         │
         ├─ (4) Kiểm tra Tool Calling:
         │        Nếu LLM yêu cầu gọi hàm (tool_calls) -> Chuyển sang Section 7 (MCP)
         │
         └─ (5) Bắn Tokens văn bản vào Hàng đợi TTS:
                  tts_text_buff.append(token)
                  -> Kích hoạt Bộ chia câu thông minh (Sentence Slicer)
```

> [!IMPORTANT]
> **CHUYÊN ĐỀ KỸ THUẬT: CƠ CHẾ ĐÓNG GÓI PAYLOAD LLM & TỐI ƯU HÓA PROMPT CACHING TỰ ĐỘNG**
> Trong một hệ thống Voice-to-Voice như XiaoZhi, chi phí vận hành (Token Cost) và độ trễ phản hồi (First Token Latency) phụ thuộc phần lớn vào việc **Prompt Caching** có hoạt động hiệu quả hay không. Nếu backend đóng gói payload sai quy chuẩn, toàn bộ bộ nhớ đệm KV Cache trên Cloud sẽ bị vỡ (Cache Miss), khiến hệ thống tiêu hao token gấp 5–10 lần và độ trễ tăng vọt.

---

#### 5.1. Bản Chất Stateless & Cấu Trúc Payload Mỗi Lượt Nói (Kể Cả Câu "Xin Chào")

**Hỏi:** *Mỗi khi phát sinh câu nói (kể cả câu cực ngắn như "xin chào", "ừ"), toàn bộ System Prompt, Lịch sử hội thoại và khai báo MCP Tools đều bị gửi lại cho LLM hay sao?*

**Trả lời: ĐÚNG VẬY.**
- Các API LLM (OpenAI, DeepSeek, Claude, Gemini, Qwen...) hoạt động theo mô hình **Stateless (Vô trạng thái)**. Cloud không duy trì bộ nhớ RAM lưu phiên làm việc sau khi ngắt request.
- Nếu Backend không gửi lại **System Prompt** ➔ AI lập tức quên danh tính (tên XiaoZhi, xưng hô, tính cách).
- Nếu Backend không gửi lại **Tools Declaration** ➔ AI không biết nó có "chân tay" (bật/tắt GPIO quạt, đèn, camera ESP32) để điều khiển khi cần.
- Nếu Backend không gửi lại **Lịch sử (History Context)** ➔ AI bị mất trí nhớ, không hiểu các câu hỏi nối tiếp.

**Minh họa JSON Payload thực tế bắn qua API LLM:**
```json
{
  "model": "deepseek-chat",
  "messages": [
    {
      "role": "system",
      "content": "Bạn là trợ lý ảo XiaoZhi thông minh, phản hồi ngắn gọn dưới 30 từ... <memory>Chủ nhân tên Nam, ở Hà Nội</memory>"
    },
    {
      "role": "user",
      "content": "Bật cho tôi bài nhạc nhẹ"
    },
    {
      "role": "assistant",
      "content": "Dạ, tôi đã mở danh sách nhạc thư giãn cho bạn rồi nhé!"
    },
    {
      "role": "user",
      "content": "xin chào"
    }
  ],
  "tools": [
    { "type": "function", "function": { "name": "turn_on_light", "description": "Bật đèn ESP32..." } },
    { "type": "function", "function": { "name": "get_weather", "description": "Lấy thời tiết..." } },
    { "type": "function", "function": { "name": "direct_answer", "description": "Trả lời trực tiếp không gọi tool" } }
  ],
  "stream": true
}
```

*Ngoại lệ lọc cục bộ:* Tại [core/handle/intentHandler.py](file:///e:/Espressif/frameworks/esp-idf-v5.5.3/examples/xiaozhi-esp32-main/xiaozhi-esp32-server/main/xiaozhi-server/core/handle/intentHandler.py#L31-L64), server chặn lại ngay trên máy chủ **mà không gọi LLM** nếu người dùng phát lệnh thoát nhanh (`check_direct_exit`: *"tạm biệt"*, *"ngủ đi"*, *"cút"*) hoặc từ khóa đánh thức mặc định (`checkWakeupWords`), giúp tiết kiệm 100% token cho các trường hợp này.

---

#### 5.2. Khảo Sát Tính Năng Prompt Caching Trên Các Nhà Cung Cấp

Không phải 100% các API LLM đều hỗ trợ hoặc tự động kích hoạt Prompt Caching:

| Nhà Cung Cấp / Mô Hình | Khả Năng Prompt Caching | Cơ Chế & Ngưỡng Kích Hoạt | Chi Phí Khi Cache Hit |
| :--- | :--- | :--- | :--- |
| **DeepSeek (V3 / R1)** | ✅ **Tự động 100%** | Tự động lưu trên cụm NVMe/RAM khi tiền tố $\ge 64$ tokens. | Giảm **90%** (0.014$/1M tokens). |
| **OpenAI (GPT-4o, 4o-mini)** | ⚠️ **Tự động có điều kiện** | Tự động kích hoạt **CHỈ KHI** tiền tố trùng khớp $\ge 1.024$ tokens. | Giảm **50%** giá Input Tokens. |
| **Anthropic Claude (3.5 Sonnet)** | ⚠️ **Bán tự động (Explicit)** | Không tự động; bắt buộc backend phải chèn cờ `"cache_control": {"type": "ephemeral"}`. | Giảm **90%** giá Input Tokens. |
| **Google Gemini (1.5 Flash/Pro)** | ⚠️ **Cần Context Caching API** | Cần tạo Cache Object riêng nếu ngữ cảnh $\ge 32.768$ tokens. | Giảm **75%** giá Input Tokens. |
| **Ollama / vLLM (Self-hosted)** | ❌ / ⚠️ **Cần cờ khởi động** | Ollama mặc định tắt; vLLM bắt buộc truyền tham số `--enable-prefix-caching`. | Tiết kiệm 100% GPU compute time. |
| **Các API Giá Rẻ / Model Cũ** | ❌ **Không hỗ trợ** | Luôn tính phí 100% full input tokens mỗi lượt gọi. | Không giảm giá. |

---

#### 5.3. Nguyên Lý Prefix Matching & 5 Nguyên Tắc Vàng Tránh "Vỡ Cache"

Mô hình AI chỉ cache được khi **TIỀN TỐ (PREFIX) TRÙNG KHỚP 100% TỪ TOKEN ĐẦU TIÊN**. Chỉ cần sai lệch **1 ký tự duy nhất** ở phía trước, toàn bộ khối dữ liệu phía sau sẽ bị **Cache Miss (Vỡ cache)** và phải tính toán lại từ đầu.

```	ext
CẤU TRÚC ĐÓNG GÓI PAYLOAD CHUẨN ĐỂ ĐẠT CACHE HIT 90%+:

┌────────────────────────────────────────────────────────────────────────┐
│ [VÙNG 1: BẤT BIẾN TUYỆT ĐỐI - KHÓA CACHE CỐ ĐỊNH Ở ĐẦU PAYLOAD]        │
│  • System Prompt tĩnh (Tính cách, phong cách trả lời ngắn gọn)         │
│  • Tool Declarations (Khai báo MCP Tools + Plugins đã SORT tên)        │
│  • Few-shot Examples (Các mẫu câu hỏi - đáp chuẩn mực)                │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ (Trùng khớp 100% -> Cache Hit liên tục)
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ [VÙNG 2: LỊCH SỬ TÍCH LŨY DẦN - CHỈ NỐI THÊM VÀO ĐUÔI]                │
│  • Lịch sử đối thoại: (User 1 -> Bot 1) -> (User 2 -> Bot 2)...        │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ (Phần cũ vẫn trúng Cache, chỉ tính phí phần nối thêm)
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ [VÙNG 3: BIẾN ĐỘNG THỜI GIAN & TRUY VẤN MỚI - ĐẶT TẠI CUỐI CÙNG]      │
│  • Ngữ cảnh thời gian thực (Giờ hiện tại {{current_time}})             │
│  • Câu nói mới nhất của User (Query hiện tại)                          │
└────────────────────────────────────────────────────────────────────────┘
```

**Năm "Bẫy Tử Thần" cần kiểm soát khi tự dev Server:**

1. **Bẫy 1: Chèn thời gian thực `{{current_time}}` vào đầu System Prompt (Sai lầm phổ biến nhất)**
   - *Nguy cơ:* Nếu viết *"Bây giờ là {{current_time}}, bạn là trợ lý..."*, thì lúc 15:53 token là `15:53`, sang 15:54 biến thành `15:54`. Cứ mỗi phút trôi qua, **toàn bộ System Prompt và toàn bộ Tools Schema phía sau bị vỡ sạch cache**, khiến server đốt token liên tục.
   - *Cách khắc phục:* Giữ System Prompt hoàn toàn tĩnh. Nếu cần truyền giờ, hãy chèn giờ vào **cuối tin nhắn của User** (ví dụ: `{"role": "user", "content": "[15:54] xin chào"}`).
2. **Bẫy 2: Thứ tự mảng Tools Schema bị xáo trộn**
   - *Nguy cơ:* Lấy danh sách tool từ `dict.values()` hoặc `set()` trong Python khiến vị trí các tool bị đảo ngẫu nhiên (`[turn_on_fan, get_weather]` ➔ `[get_weather, turn_on_fan]`). Khác chuỗi băm ➔ Vỡ cache.
   - *Cách khắc phục:* Luôn sắp xếp cố định theo tên (`sorted(tools, key=lambda x: x['function']['name'])`).
3. **Bẫy 3: Không vượt qua ngưỡng Token tối thiểu của Provider**
   - *Nguy cơ:* OpenAI yêu cầu tiền tố tối thiểu **1.024 tokens**. Nếu System Prompt + Tools chỉ dài 400 tokens, OpenAI **từ chối kích hoạt cache**, bạn vẫn phải trả 100% tiền input.
   - *Cách khắc phục:* Bổ sung các chỉ dẫn hành vi chi tiết, quy tắc xưng hô và few-shot examples để tổng tiền tố đạt trên 1.024 tokens.
4. **Bẫy 4: Xóa lẻ tẻ 1 tin nhắn cũ trong lịch sử hội thoại**
   - *Nguy cơ:* Khi trượt cửa sổ hội thoại (Sliding Window), nếu xóa đơn lẻ 1 tin nhắn `User`, tin nhắn đầu tiên sau Tools sẽ đổi thành `Assistant` ➔ Làm lệch toàn bộ tiền tố của các lượt nói sau.
   - *Cách khắc phục:* Luôn cắt tỉa lịch sử theo **từng cặp nguyên vẹn (1 User + 1 Assistant)**.
5. **Bẫy 5: Cách kiểm tra chính xác Cache Hit qua Code**
   - Kiểm tra trực tiếp trường `usage` trong phản hồi API tại [core/providers/llm/openai/openai.py](file:///e:/Espressif/frameworks/esp-idf-v5.5.3/examples/xiaozhi-esp32-main/xiaozhi-esp32-server/main/xiaozhi-server/core/providers/llm/openai/openai.py#L162-L175):
   ```python
   # Đọc metrics sau khi stream kết thúc
   usage = stream_response.usage
   if usage:
       # OpenAI:
       cached = getattr(usage.prompt_tokens_details, "cached_tokens", 0)
       print(f"Tổng Input: {usage.prompt_tokens} | Đã Cache Hit: {cached}")

       # DeepSeek:
       hit = getattr(usage, "prompt_cache_hit_tokens", 0)
       miss = getattr(usage, "prompt_cache_miss_tokens", 0)
       print(f"DeepSeek Cache Hit: {hit} tokens | Miss: {miss} tokens")
   ```
   Nếu `cached > 0` hoặc `hit > 0` và chiếm 70%–90% tổng input, hệ thống đã đạt trạng thái tối ưu chuẩn mực.

---

#### 5.4. Giải Mã Cơ Chế: "Vỏ Bọc JSON API" vs "Cụm Token Thực Tế Trong Transformer"

**Hỏi:** *Tại sao trong gói tin JSON gửi lên API thì `messages` và `tools` nằm ở 2 trường tách biệt, nhưng thực tế cả System Prompt và Tools MCP lại được fix cứng và gộp thành 1 cụm ở đầu gói tin để LLM nhận diện Prompt Caching?*

**Trả lời:** Có sự phân biệt rõ ràng giữa **Tầng Lập Trình Viên (API JSON Schema)** và **Tầng Mô Hình Nơ-ron (Transformer Tokenizer)**:

1. **Ở Tầng Lập Trình Viên (API JSON Format):**
   - Theo chuẩn OpenAI / DeepSeek API, lập trình viên bắt buộc phải tách thành 2 tham số riêng biệt:
     - `messages`: Danh sách các lượt hội thoại văn bản (`system`, `user`, `assistant`, `tool`).
     - `tools`: Danh sách khai báo cấu trúc hàm (JSON Schema) gồm tên tool, mô tả và kiểu tham số.
   - Nếu nhét thủ công cả JSON Schema vào trong `messages`, Cloud API sẽ không hiểu đó là công cụ để sinh ra đối tượng `tool_calls` tự động.

2. **Ở Tầng Mô Hình Nơ-ron (LLM Engine & KV Cache):**
   - Mạng nơ-ron Transformer **không hề đọc dữ liệu dạng JSON**. Khi Cloud nhận được gói tin, bộ **Tokenizer / Chat Template** của máy chủ Cloud sẽ **TỰ ĐỘNG NHÚNG TOÀN BỘ TOOLS VÀO KHỐI SYSTEM PROMPT Ở NGAY ĐẦU CHUỖI TOKENS**!
   - Chuỗi ký tự nơ-ron thực tế được cấp cho Transformer tính toán attention như sau:

```	ext
DÒNG TOKENS THỰC TẾ NẠP VÀO MẠNG NƠ-RON TRANSFORMER (TỪ TOKEN SỐ 0 TRỞ ĐI):

┌────────────────────────────────────────────────────────────────────────┐
│ <|im_start|>system                                                     │
│ Bạn là trợ lý ảo XiaoZhi thông minh, xưng hô thân mật...               │
│                                                                        │
│ # THÔNG TIN CÔNG CỤ (TOOLS SCHEMA ĐƯỢC CLOUD NHÚNG THẲNG VÀO ĐÂY):     │
│ You have access to the following tools:                                │
│ - turn_on_fan(speed: int): Bật quạt phòng khách trên phần cứng ESP32   │
│ - get_weather(location: str): Lấy thông tin thời tiết từ Cloud         │
│ - direct_answer(): Công cụ ảo trả lời đối thoại thông thường           │
│                                                                        │
│ When you need to call a tool, respond with <tool_call>...              │
│ <|im_end|>                                                             │
├────────────────────────────────────────────────────────────────────────┤
│ <|im_start|>user                                                       │
│ [Các câu ví dụ Few-shot mẫu - nếu có]                                  │
│ <|im_end|>                                                             │
├────────────────────────────────────────────────────────────────────────┤
│ <|im_start|>user                                                       │
│ [Lịch sử đàm thoại cũ...]                                              │
│ <|im_end|>                                                             │
│ <|im_start|>user                                                       │
│ xin chào                                                               │
│ <|im_end|>                                                             │
│ <|im_start|>assistant                                                  │
└────────────────────────────────────────────────────────────────────────┘
  ▲                                                                      ▲
Token 0 (Bắt đầu Prefix Cache)                                     Token Cuối
```

3. **Mối liên hệ quyết định đến Prompt Caching:**
   - Khối `<|im_start|>system ... <|im_end|>` chứa **cả System Prompt LẪN toàn bộ danh sách Tools**.
   - Vì cả hai thành phần này **đều được fix cứng 100% không đổi một chữ** giữa các lần gọi:
     ➔ Chúng tạo thành một khối Token bất biến nằm từ **Token số 0 đến Token thứ $N$**.
     ➔ Cloud LLM (DeepSeek, OpenAI) kiểm tra bảng băm và thấy đoạn từ Token 0 đến Token $N$ giống hệt request trước đó ➔ **Kích hoạt Prompt Caching tự động (Cache Hit 90%+)!**

4. **Bằng chứng trong mã nguồn XiaoZhi:**
   - Tại [core/providers/llm/system_prompt.py](file:///e:/Espressif/frameworks/esp-idf-v5.5.3/examples/xiaozhi-esp32-main/xiaozhi-esp32-server/main/xiaozhi-server/core/providers/llm/system_prompt.py#L69), với các mô hình mã nguồn mở cũ không có tham số `tools` riêng ở tầng API, chính code XiaoZhi cũng tự động nhúng `{functions}` trực tiếp vào bên trong `SYSTEM_PROMPT`.

---

#### 5.5. "Nghịch Lý Tối Ưu Hóa": Vì Sao KHÔNG Nên Viết Bộ Lọc Bật/Tắt Tools?

**Hỏi:** *Nếu backend viết thêm 1 bộ lọc để phân biệt: lúc người dùng chat thường thì KHÔNG gửi `tools`, lúc có ý định điều khiển mới gửi `tools` thì có tối ưu hơn không?*

**Trả lời: KHÔNG. ĐÂY LÀ SAI LẦM KHIẾN HỆ THỐNG ĐỐT TOKEN VÀ CHẬM HƠN GẤP NHIỀU LẦN!**

- **Hiệu ứng bóng bàn (Cache Thrashing):**
  - Lượt 1 (Chat thường): Không có tools ➔ Cloud băm tiền tố Hash_A.
  - Lượt 2 (Ra lệnh): Có tools ➔ Tiền tố lệch so với Hash_A ➔ **Cache Miss 100%**, phải tính lại attention từ đầu.
  - Lượt 3 (Chat tiếp): Lại bỏ tools ➔ Lệch so với Lượt 2 ➔ **Tiếp tục Cache Miss 100%**.
- **Bài toán kinh tế thực tế (Ví dụ trên DeepSeek V3):**
  - Giá Cache Miss (Full Input): **0.14$ / 1M tokens**.
  - Giá Cache Hit: **0.014$ / 1M tokens** *(Rẻ hơn gấp 10 lần!)*.
  - Gửi kèm 500 tokens của mảng Tools nhưng đạt Cache Hit chỉ tiêu tốn **0.000007$** (7 phần triệu USD).
  - Ngược lại, cắt bỏ 500 tokens nhưng làm vỡ Cache khiến toàn bộ System Prompt (1000 tokens) + Lịch sử cũ (2000 tokens) bị tính theo giá Full Input đắt gấp 10 lần, đồng thời độ trễ TTFT tăng từ 150ms lên 700ms!
- **Giải pháp chuẩn của XiaoZhi:**
  - Luôn luôn gửi toàn bộ danh sách Tools cố định trong mọi lượt chat.
  - Bổ sung công cụ ảo `DIRECT_ANSWER_TOOL` ([core/connection.py:1107](file:///e:/Espressif/frameworks/esp-idf-v5.5.3/examples/xiaozhi-esp32-main/xiaozhi-esp32-server/main/xiaozhi-server/core/connection.py#L1107)) để AI không bị ảo giác gọi nhầm tool khi người dùng chỉ chào hỏi xã giao.

---

#### 5.6. Cơ Chế Xử Lý Đa Mô Hình (Qwen, DeepSeek, GPT, Doubao, Xiaozhi Lite...) Trong Backend

Trên giao diện Web của XiaoZhi, người dùng có thể chọn hàng loạt mô hình AI khác nhau. Backend xử lý phân nhánh như thế nào?

**A. 80% Mô Hình Được Quy Về Chuẩn "OpenAI-Compatible" (`type: openai`):**
- Toàn bộ các model như **DeepSeek** (`deepseek-v4-flash`), **Qwen** (`AliLLM`), **Doubao** (`DoubaoLLM`), **ChatGLM** (`ChatGLMLLM`), **Xiaozhi Lite** (`LMStudioLLM`), và **OpenAI** (GPT-4o) đều chạy qua **DUY NHẤT** một Adapter: [core/providers/llm/openai/openai.py](file:///e:/Espressif/frameworks/esp-idf-v5.5.3/examples/xiaozhi-esp32-main/xiaozhi-esp32-server/main/xiaozhi-server/core/providers/llm/openai/openai.py).
- Điểm khác biệt duy nhất được lưu trong cấu hình/database là: `base_url`, `model_name`, `api_key`.

**B. Can Thiệp Ngầm Đặc Thù: Tắt Chế Độ Suy Nghĩ (Thinking Mode Suppression):**
- Các mô hình suy luận (DeepSeek-R1, Qwen-Thinking) thường sinh ra thẻ `<think>...</think>` dài hàng ngàn từ khiến phản hồi âm thanh bị trễ từ 5–15 giây.
- Tại [core/providers/llm/openai/openai.py](file:///e:/Espressif/frameworks/esp-idf-v5.5.3/examples/xiaozhi-esp32-main/xiaozhi-esp32-server/main/xiaozhi-server/core/providers/llm/openai/openai.py#L13-L19), backend tự động soi tên miền (`base_url`) để bơm tham số tắt thinking riêng cho từng nhà cung cấp:
  - `aliyuncs.com` ➔ `{"enable_thinking": False}`
  - `deepseek.com` / `bigmodel.cn` / `volces.com` ➔ `{"thinking": {"type": "disabled"}}`
- Đồng thời, bộ lọc Stream tại dòng 127–133 chủ động cắt bỏ mọi nội dung bên trong thẻ `<think>` nếu model vẫn xuất ra, đảm bảo chỉ có câu trả lời cuối cùng được gửi sang TTS để phát ra loa ngay lập tức.

**C. Các Adapter Chuyên Biệt Cho Các Nền Tảng Ngoại Lệ (`core/providers/llm/`):**
- **`gemini/`**: Dùng thư viện `google.generativeai` riêng và tự động cấu hình HTTP/HTTPS Proxy.
- **`AliBL/`**: Dùng SDK DashScope Native của Alibaba, kết nối kho trí nhớ dài hạn qua `ali_memory_id`.
- **`dify/` & `fastgpt/`**: Không gửi tin nhắn đàm thoại thông thường mà gọi REST API của nền tảng Workflow/RAG để Dify tự quản lý toàn bộ Prompt và Agent bên ngoài.
- **`ollama/` & `xinference/`**: Chuyên dụng kết nối các cụm máy chủ AI chạy offline nội bộ.

---

### 6. Luồng Tổng Hợp Giọng Nói (TTS) & Bộ Điều Khiển Tốc Độ Phát (Rate Controller)

Điểm tinh hoa giúp XiaoZhi phản hồi nhanh như người thật chính là **mô hình xử lý đường ống 2 tầng (Two-Stage Pipeline)** bên trong [core/providers/tts/base.py](file:///e:/Espressif/frameworks/esp-idf-v5.5.3/examples/xiaozhi-esp32-main/xiaozhi-esp32-server/main/xiaozhi-server/core/providers/tts/base.py) và bộ điều tốc [AudioRateController](file:///e:/Espressif/frameworks/esp-idf-v5.5.3/examples/xiaozhi-esp32-main/xiaozhi-esp32-server/main/xiaozhi-server/core/handle/sendAudioHandle.py#L12):

```	ext
[LLM Streaming Tokens]
         │ (Đẩy từng token vào)
         ▼
┌────────────────────────────────────────────────────────────────────────┐
│ TẦNG 1: BỘ CHIA CÂU THÔNG MINH (Sentence Slicer Thread)                │
│                                                                        │
│ - Gom các token lại trong `tts_text_buff`                              │
│ - Câu ĐẦU TIÊN: Cắt ngay khi gặp dấu ngắt nhẹ (",", "~", "...")        │
│   ==> Mục đích: Gửi đi siêu tốc để loa phát tiếng sau 300-500ms!        │
│ - Các câu SAU: Cắt theo dấu chấm câu chuẩn (".", "!", "?", ";")        │
│                                                                        │
│ [Câu hoàn chỉnh] ──> Gọi Engine TTS (Edge-TTS / FishSpeech / Piper)     │
│                       └─ Sinh mảng âm thanh PCM                         │
│                       └─ Nén sang Opus Frame (chuẩn 60ms/frame)        │
│                       └─ Đẩy gói Opus vào `tts_audio_queue`            │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ TẦNG 2: BỘ ĐIỀU TỐC MẠNG CHỐNG NGHẼN (AudioRateController Thread)      │
│                                                                        │
│ (1) Gửi gói tin báo hiệu JSON:                                         │
│     {"type": "tts", "state": "sentence_start", "text": "Dạ vâng..."}   │
│                                                                        │
│ (2) Chiến lược phát âm thanh qua WebSocket:                            │
│     - 5 GÓI ĐẦU TIÊN (Pre-buffer): Bắn ngay lập tức không chờ         │
│       ==> Đổ đầy bộ đệm DMA trên chip ESP32, chống vấp tiếng (Underrun)│
│     - CÁC GÓI TIẾP THEO: Phát đều đặn theo nhịp chính xác 60ms/gói     │
│       ==> Ngăn tràn bộ nhớ RAM (Overflow) trên vi điều khiển ESP32     │
│                                                                        │
│ (3) Khi hết bài phát:                                                  │
│     {"type": "tts", "state": "stop"}                                   │
│     -> ESP32 phát xong toàn bộ DMA thì quay về trạng thái kDeviceStateIdle │
└────────────────────────────────────────────────────────────────────────┘
```

---


### 7. Luồng Thực Thi Công Cụ Cục Bộ & Đám Mây (MCP & Unified Tool Calling)

Khi người dùng ra lệnh: *"Bật quạt phòng khách và kiểm tra thời cơ mai thế nào"*, mô hình LLM sẽ sinh ra các `tool_calls`. Bộ quản lý [UnifiedToolHandler](file:///e:/Espressif/frameworks/esp-idf-v5.5.3/examples/xiaozhi-esp32-main/xiaozhi-esp32-server/main/xiaozhi-server/core/providers/tools/unified_tool_handler.py) sẽ phân loại và thực thi đồng thời:

```	ext
[LLM (Cloud)]          [UnifiedToolHandler]         [ESP32 (Phần cứng)]      [Cloud Plugin]
     │                          │                            │                      │
     │ "Bật quạt số 2 và xem thời tiết Hà Nội"               │                      │
     ├─────────────────────────►│                            │                      │
     │ Trả về 2 Tool Calls:     │                            │                      │
     │ 1. turn_on_fan(speed=2)  │                            │                      │
     │ 2. get_weather("Hanoi")  │                            │                      │
     │                          ├─ [Nhánh 1: Thiết bị MCP] ─►│                      │
     │                          │  {"method":"tools/call",   │                      │
     │                          │   "params":{"name":"fan"}} │ (Kích hoạt GPIO)    │
     │                          │                            ├─ Bật quạt số 2       │
     │                          │◄───────────────────────────┤                      │
     │                          │  {"result":"Quạt đã bật"}  │                      │
     │                          │                            │                      │
     │                          ├─ [Nhánh 2: Cloud Plugin] ────────────────────────►│
     │                          │  Chạy get_weather("Hanoi") │                      │ (Gọi API thời tiết)
     │                          │◄──────────────────────────────────────────────────┤
     │                          │  "Hà Nội 26°C, nhiều mây"  │                      │
     │                          │                            │                      │
     │ (Tổng hợp kết quả tools) │                            │                      │
     │◄─────────────────────────┤                            │                      │
     │                          │                            │                      │
     │ Sinh câu trả lời mượt mà:│                            │                      │
     │ "Đã bật quạt số 2. Thời tiết Hà Nội nhiều mây 26°C"   │                      │
     ├─────────────────────────►│                            │                      │
     │                          ├─ (Stream TTS sang Opus) ──►│                      │
     │                          │                            ▼ (Loa ESP32 phát âm)  │
```

#### Giải thích cơ chế Direct Answer (`DIRECT_ANSWER_TOOL`):
Trong `core/connection.py`, server khai báo một công cụ ảo tên là `direct_answer`. Khi người dùng chỉ hỏi chuyện thông thường ("Bạn tên là gì?", "Thủ đô của Pháp là đâu?"), một số mô hình ngôn ngữ nhỏ (như Llama-3-8B hoặc Qwen) rất hay bị "ngứa tay" gọi bừa vào các tool vật lý. Kỹ thuật `direct_answer` biến bài toán nhị phân *"Nên gọi tool hay nói chuyện?"* thành bài toán trắc nghiệm *"Chọn tool quạt, tool thời tiết hay tool direct_answer?"*. Nếu chọn `direct_answer`, server trích xuất câu trả lời trực tiếp mà không tốn công gọi hàm.

---

### 8. Cơ Chế Ngắt Lời Thời Gian Thực (Full-Duplex Barge-In / Abort)

Một trong những tính năng cao cấp nhất của XiaoZhi là khả năng **cướp lời / ngắt họng AI** khi AI đang nói dài dòng.

```	ext
                 [🔊 LOA ESP32 ĐANG PHÁT GIỌNG AI (Speaking)]
                                      │
        [Người dùng bất ngờ nói: "Dừng lại, tắt đi!"] ──> [Micro thu âm]
                                      │
                 ┌────────────────────┴────────────────────┐
                 │                                         │
        [Cơ Chế 1: Ngắt Tại ESP32]                [Cơ Chế 2: Ngắt Tại Server]
      (Firmware AEC phát hiện có giọng)         (Server AEC & Silero VAD phát hiện có giọng)
                 │                                         │
        ESP32 gửi gói tin JSON:                            │
        {"type": "abort"}                                  │
                 │                                         │
                 └────────────────────┬────────────────────┘
                                      ▼
                        [core/handle/abortHandle.py]
                                      │
            ├─ (1) Bật cờ ngắt: conn.client_abort = True
            ├─ (2) Ngắt luồng Generator của LLM (Dừng sinh thêm token)
            ├─ (3) Dọn sạch hàng đợi chữ: conn.tts.tts_text_queue.clear()
            ├─ (4) Dọn sạch hàng đợi âm thanh: conn.tts.tts_audio_queue.clear()
            ├─ (5) Xóa bộ đệm phát mạng: conn.audio_rate_controller.clear()
            └─ (6) Tạo sentence_id mới để loại bỏ các gói âm thanh trôi nổi
                                      │
                                      ▼
             [Gửi JSON {"type": "tts", "state": "stop"} về ESP32]
                   ==> Loa ESP32 nín bặt ngay lập tức!
                   ==> Hệ thống sẵn sàng nhận lệnh mới!
```

---

## III. CẨM NANG DÀNH CHO LẬP TRÌNH VIÊN TỰ PHÁT TRIỂN SERVER

Nếu mục tiêu của bạn là **dựa trên mã nguồn gốc này để tự code lại hoặc tùy biến một hệ thống server riêng đạt chuẩn thương mại**, dưới đây là những hướng dẫn thực chiến được đúc kết từ quá trình kiểm toán mã nguồn.

---

### 1. Các Điểm Nghẽn & Sai Lầm Kiến Trúc Cần Tránh Khi Tự Viết Lại Code

Khi nghiên cứu các phiên bản vá lỗi tạm thời, có 5 "ổ gà kiến trúc" mà bạn tuyệt đối **KHÔNG ĐƯỢC LẶP LẠI**:

1. **Không dùng "Rừng" Regex để bắt câu nói (`fast_router.py`)**:
   - *Sai lầm:* Viết hàng trăm dòng regex tiếng Việt để đoán xem câu nói có phải là lệnh hay không.
   - *Hậu quả:* Người dùng nói biến thể một chữ là trượt regex ➔ AI bị "điếc" không gọi được tool.
   - *Cách làm chuẩn:* Hãy giao toàn bộ schema của tool cho LLM tự quyết định thông qua cơ chế Function Calling chuẩn mực.
2. **Không được cắt xén Tool Schema (`desc[:160]`)**:
   - *Sai lầm:* Sợ tốn token nên cắt ngắn mô tả của tool còn 160 ký tự.
   - *Hậu quả:* Cắt mất câu hướng dẫn kích hoạt tool khiến AI không hiểu tham số và từ chối gọi tool.
3. **Phải có Màng Lọc Phòng Thủ (Defensive Stream Guard)**:
   - Các mô hình OSS khi bối rối thường sinh thẳng cú pháp `{"name": "turn_on"}` ra luồng text. Nếu bạn đưa thẳng token text này vào hàng đợi TTS, loa sẽ đọc to từng dấu ngoặc nhọn, nháy kép ra loa gây trải nghiệm rất tệ.
   - Luôn phải có bộ đệm (Stream Buffer ~15 ký tự) để kiểm tra xem đoạn text sắp gửi có phải là mở đầu của JSON hay không trước khi đẩy sang TTS.
4. **Không Hardcode nghiệp vụ phần cứng vào lõi Server**:
   - Tuyệt đối không viết `if tool_name == "quat_sunhouse": ...` bên trong `core/connection.py`.
   - Mọi thiết bị phải được trừu tượng hóa thành các MCP Tool độc lập hoặc nạp động từ file JSON cấu hình.
5. **Không dùng các file nhị phân `.exe` trên Windows khi muốn deploy Cloud**:
   - Loại bỏ việc gọi `ffmpeg.exe`, `opus.dll` trôi nổi trong thư mục code. Hãy đóng gói dependencies chuẩn qua Docker trên hệ điều hành Linux.

---

### 2. Hướng Dẫn Thêm Một Server Plugin / Tool Mới

Để thêm một công cụ AI mới chạy trên Server (ví dụ: Tra cứu giá vàng, điều khiển máy bơm, đọc tin tức RSS), bạn chỉ cần tạo 1 file Python duy nhất trong thư mục `plugins_func/functions/`:

**Ví dụ: Tạo file `plugins_func/functions/get_gold_price.py`:**

```python
from datetime import datetime
from plugins_func.register import register_function, ToolType, ActionResponse, Action

# 1. Định nghĩa Schema chuẩn OpenAI/JSON-Schema
gold_price_desc = {
    "type": "function",
    "function": {
        "name": "get_gold_price",
        "description": "Tra cứu giá vàng SJC, 9999 mới nhất tại Việt Nam theo từng ngày.",
        "parameters": {
            "type": "object",
            "properties": {
                "gold_type": {
                    "type": "string",
                    "description": "Loại vàng cần tra, ví dụ: 'SJC', '9999', 'nhẫn trơn'",
                }
            },
            "required": ["gold_type"],
        },
    },
}

# 2. Sử dụng Decorator để hệ thống tự động quét và nạp tool
@register_function("get_gold_price", gold_price_desc, ToolType.WAIT)
def get_gold_price(gold_type="SJC"):
    """Hàm xử lý logic nghiệp vụ thực tế"""
    try:
        # Gọi API bên ngoài hoặc truy vấn Database
        gia_mua = "82.500.000"
        gia_ban = "84.500.000"
        ket_qua = f"Giá vàng {gold_type} hôm nay: Mua vào {gia_mua} đ/lượng, Bán ra {gia_ban} đ/lượng."
        
        # Trả về Action.REQLLM để LLM dùng thông tin này trả lời tự nhiên cho người dùng
        return ActionResponse(action=Action.REQLLM, result=ket_qua)
    except Exception as e:
        return ActionResponse(action=Action.ERROR, result=f"Lỗi tra cứu giá vàng: {str(e)}")
```

> **Cơ chế hoạt động:** Hệ thống có hàm `auto_import_modules("plugins_func.functions")` trong `core/connection.py`. Ngay khi server khởi động, file mới của bạn sẽ tự động được quét, kiểm tra cú pháp và tích hợp thẳng vào danh sách tool của LLM mà **không cần sửa một dòng code lõi nào**!

---

### 3. Hướng Dẫn Tích Hợp Provider ASR / LLM / TTS Tùy Chỉnh

Mọi dịch vụ AI trong XiaoZhi đều kế thừa từ lớp cơ sở trừu tượng (Abstract Base Class). Khi muốn thêm một dịch vụ mới (ví dụ: PiperTTS tiếng Việt, Gemini Flash 2.0, DeepSeek R1), bạn chỉ cần kế thừa lớp tương ứng:

#### 1. Thêm LLM mới: Kế thừa [LLMProviderBase](file:///e:/Espressif/frameworks/esp-idf-v5.5.3/examples/xiaozhi-esp32-main/xiaozhi-esp32-server/main/xiaozhi-server/core/providers/llm/base.py)
- Triển khai phương thức sinh stream: `response(session_id, dialogue)`
- Triển khai phương thức có công cụ: `response_with_functions(session_id, dialogue, functions)`
- Trả về generator sinh từng chunk text hoặc tuple `(content, tool_calls)`.

#### 2. Thêm TTS mới: Kế thừa [TTSProviderBase](file:///e:/Espressif/frameworks/esp-idf-v5.5.3/examples/xiaozhi-esp32-main/xiaozhi-esp32-server/main/xiaozhi-server/core/providers/tts/base.py)
- Triển khai phương thức: `to_tts(text) -> bytes` (Trả về âm thanh PCM hoặc WAV).
- Hệ thống lớp cha `TTSProviderBase` sẽ tự động xử lý chia câu, lọc markdown, mã hóa Opus và đẩy vào hàng đợi truyền dẫn mạng.

---

### 4. Mô Thức Triển Khai: Standalone Cục Bộ vs Hệ Thống Doanh Nghiệp Phân Tán

Khi phát triển sản phẩm thực tế, bạn có thể lựa chọn 1 trong 2 mô hình kiến trúc:

```	ext
MÔ HÌNH 1: STANDALONE (Tối Giản Cho Developer & Dự Án Vừa / Nhỏ)
┌────────────────────────────────────────────────────────┐
│                   MÁY CHỦ PYTHON                       │
│  - Chạy duy nhất: python app.py                        │
│  - Cấu hình toàn bộ trong: config.yaml                │
│  - Không cần cài đặt Java, không cần MySQL, Redis      │
│  - Lưu file âm thanh và log cục bộ trong tmp/ và data/ │
└────────────────────────────────────────────────────────┘
                          ▲
                          │ WebSocket (8000) & HTTP OTA (8003)
                          ▼
                   [Thiết Bị ESP32]

MÔ HÌNH 2: ENTERPRISE (Doanh Nghiệp / Sản Phẩm Thương Mại Hàng Loạt)
┌───────────────────────┐         ┌───────────────────────┐
│ manager-web (Vue.js)  │         │ manager-mobile (App)  │
└──────────┬────────────┘         └──────────┬────────────┘
           │                                 │
           └────────────────┬────────────────┘
                            ▼ (REST API)
┌─────────────────────────────────────────────────────────┐
│        manager-api (Java Spring Boot Microservice)       │
│  - Quản lý tài khoản, mã kích hoạt (Binding Code)       │
│  - Quản lý kho firmware OTA đa chi nhánh                │
│  - Lưu trữ lịch sử đàm thoại, phân tích dữ liệu         │
└───────────────────────────┬─────────────────────────────┘
                            │ (MySQL 8.0 & Redis Cluster)
           ┌────────────────┴────────────────┐
           ▼                                 ▼
┌───────────────────────┐       ┌───────────────────────┐
│ xiaozhi-server Node 1 │  ...  │ xiaozhi-server Node N │ (Cụm xử lý Audio AI)
└──────────┬────────────┘       └──────────┬────────────┘
           │                               │
           └────────────────┬──────────────┘
                            ▼ (WebSocket Load Balancer)
               [Hàng Vạn Thiết Bị ESP32 Khắp Nơi]
```

---

### 5. Bảng Tra Cứu Cổng Mạng, Giao Thức & Cấu Trúc Message Chuẩn

Dưới đây là từ điển giao tiếp chuẩn giữa Vi Điều Khiển ESP32 và Server Backend:

#### Bảng Cổng Mạng (Port Map):
| Cổng | Giao Thức | Chiều Dữ Liệu | Chức Năng Chi Tiết |
| :---: | :---: | :---: | :--- |
| **8000** | WebSocket (`ws://`) | ESP32 ⇄ Server | Kênh đàm thoại chính: Stream Opus 2 chiều, gửi nhận JSON trạng thái, gọi tool MCP. |
| **8003** | HTTP REST (`http://`) | ESP32 ➔ Server | Cung cấp API OTA (`/xiaozhi/ota/`), tải firmware (`/download/`) và API camera (`/mcp/vision/explain`). |
| **8001** | HTTP Web | Admin ➔ Server | Giao diện Web quản trị Dashboard (Frontend Vue.js). |
| **8002** | HTTP REST | Web ⇄ Java | API dịch vụ nền tảng quản trị (Java Spring Boot). |

#### Bảng Định Dạng Message JSON Trao Đổi Qua WebSocket (Port 8000):

| Loại Gói Tin (`type`) | Bên Gửi | Cấu Trúc Payload Mẫu | Ý Nghĩa Nghiệp Vụ |
| :--- | :---: | :--- | :--- |
| `hello` | ESP32 | `{"type":"hello", "version":1, "transport":"websocket", "audio_params":{"format":"opus", "sample_rate":24000}, "features":{"mcp":true, "aec":true}}` | Thiết bị bắt tay, khai báo định dạng âm thanh và năng lực phần cứng. |
| `hello` | Server | `{"type":"hello", "version":1, "transport":"websocket", "session_id":"...", "audio_params":{"sample_rate":24000}}` | Server đồng ý bắt tay, cấp phát Session ID. |
| `listen` | ESP32 | `{"type":"listen", "state":"start"}` hoặc `{"state":"stop"}` hoặc `{"state":"detect", "text":"Xin chào"}` | ESP32 thông báo trạng thái thu âm (Bắt đầu nói, ngừng nói, hoặc phát hiện từ khóa đánh thức). |
| `stt` | Server | `{"type":"stt", "text":"Bật quạt lên giúp tôi", "session_id":"..."}` | Server trả về văn bản đã nhận dạng từ giọng nói để ESP32 in lên màn hình. |
| `llm` | Server | `{"type":"llm", "emotion":"happy", "session_id":"..."}` | Server gửi mã cảm xúc để ESP32 đổi ảnh động khuôn mặt trên OLED/LCD. |
| `tts` | Server | `{"type":"tts", "state":"start"}`<br/>`{"type":"tts", "state":"sentence_start", "text":"Dạ vâng..."}`<br/>`{"type":"tts", "state":"stop"}` | Server đồng bộ hóa trạng thái phát âm thanh. Khi nhận `start`, ESP32 đổi sang trạng thái `Speaking`. Khi nhận `stop`, đổi về `Idle`. |
| `abort` | ESP32 | `{"type":"abort", "reason":"wake_word_detected"}` | ESP32 yêu cầu Server lập tức ngừng phát âm thanh và hủy luồng suy luận của LLM. |
| `mcp` | Server | `{"type":"mcp", "payload":{"jsonrpc":"2.0", "id":10, "method":"tools/call", "params":{"name":"set_volume", "arguments":{"volume":80}}}}` | Server ra lệnh phần cứng cho ESP32 thay đổi âm lượng, bật đèn, quay motor. |
| `mcp` | ESP32 | `{"type":"mcp", "payload":{"jsonrpc":"2.0", "id":10, "result":{"content":[{"type":"text", "text":"success"}]}}}` | ESP32 phản hồi kết quả thực thi lệnh phần cứng về cho Server. |

---

> [!TIP]
> **Khuyến Nghị Cho Kế Hoạch Tự Dev Server Của Bạn:**
> - Nếu bạn muốn viết một server tối ưu riêng bằng **Python** hoặc **Node.js/Go**: Bạn chỉ cần cài đặt đúng **Giao thức WebSocket cổng 8000** và **API Cấp phát cổng 8003** theo đúng cấu trúc bảng trên.
> - Firmware ESP32 hoàn toàn không quan tâm bên dưới Server viết bằng ngôn ngữ gì, miễn là gói tin JSON và nhị phân Opus được gửi/nhận đúng thứ tự thời gian.
> - Hãy khai thác cấu trúc thư mục mở rộng độc lập `core/extensions/` để tích hợp các tính năng tối ưu tiếng Việt mà không làm xáo trộn tính ổn định của mã nguồn gốc!
