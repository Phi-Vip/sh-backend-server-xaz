# KẾ HOẠCH XÂY BACKEND MCP ENDPOINT SERVER
### (Trạm Trung Chuyển Công Cụ, Cào Dữ Liệu Thời Gian Thực & Cổng Nạp Tri Thức Chuyên Sâu Sunhouse Cho Trợ Lý Ảo XiaoZhi)

> **Tài liệu kỹ thuật nội bộ hệ thống XiaoZhi Voice Assistant & Sunhouse Smart Home / Technical Support Ecosystem**  
> **Kiến trúc mục tiêu:** Modular Plugin & Broker Microservices Architecture (XiaoZhi Voice Backend Port 8000/8003 ⇄ MCP Endpoint Server Port 8004 ⇄ Tri Thức Nội Bộ & Web Scraper Sunhouse.com.vn).  
> **Môi trường vận hành:**  
> - **Local Development (Windows):** Chạy trực tiếp qua **Modular Python MCP Server (Python 3.10 trong venv)** tại Port `8004`, siêu nhẹ (~30MB RAM), không phụ thuộc Docker Desktop, tự động nạp công cụ từ thư mục `tools/`.  
> - **Cloud Production (Oracle OCI / VPS Linux):** Đóng gói Docker Compose chuẩn hóa cho môi trường Linux.  
> **Giao thức chuẩn hóa:** **Model Context Protocol (MCP)** do Anthropic khởi xướng, chạy trên nền **JSON-RPC 2.0 qua WebSocket Tunnel**.  
> **Bộ ba công cụ chuyên trách hoàn thiện:**  
> 1. `tra_cuu_ma_loi_sunhouse`: Sổ tay kỹ thuật xử lý mã lỗi (E0–E9, bo mạch, an toàn điện, hotline 1800.6680).  
> 2. `tra_cuu_thong_tin_sunhouse`: Thông tin tập đoàn chính thống (Shark Phú, nhà máy, lịch sử, chính sách bảo hành e-warranty).  
> 3. `tim_kiem_truc_tuyen_sunhouse`: Cào thông số kỹ thuật model trực tiếp từ web Sunhouse, tin tức hoạt động mới, tích hợp bộ tự phục hồi lỗi nhận diện ASR và dự đoán tiền tố model (`SHD`, `SHB`, `SHA`, `MMB`...).  
> **Thời gian cập nhật:** Tháng 10/2026 | **Phiên bản:** v2.0 (Full Production & Hardware-Verified).

---

## 📑 MỤC LỤC CHI TIẾT

- [I. BẢN CHẤT KIẾN TRÚC, NGUYÊN LÝ LOGIC & PHÂN TẦNG NHIỆM VỤ](#i-bản-chất-kiến-trúc-nguyên-lý-logic--phân-tầng-nhiệm-vụ)
  - [1.1. Bản chất chuẩn xác của MCP Endpoint Server trong Hệ sinh thái XiaoZhi](#11-bản-chất-chuẩn-xác-của-mcp-endpoint-server-trong-hệ-sinh-thái-xiaozhi)
  - [1.2. Phân định ranh giới & Phân tầng nhiệm vụ giữa các khối](#12-phân-định-ranh-giới--phân-tầng-nhiệm-vụ-giữa-các-khối)
  - [1.3. Cơ chế Khám phá Đa Công cụ (Multi-Server Merging & Smart Routing)](#13-cơ-chế-khám-phá-đa-công-cụ-multi-server-merging--smart-routing)
  - [1.4. So sánh Tri thức tĩnh nội bộ (Database) và Cào Web trực tuyến (Live Scraping)](#14-so-sánh-tri-thức-tĩnh-nội-bộ-database-và-cào-web-trực-tuyến-live-scraping)
  - [1.5. Sơ đồ tương tác toàn trình End-to-End (E2E Sequence Flow)](#15-sơ-đồ-tương-tác-toàn-trình-end-to-end-e2e-sequence-flow)
- [II. THIẾT KẾ BỘ BA CÔNG CỤ MCP SUNHOUSE CHUYÊN BIỆT](#ii-thiết-kế-bộ-ba-công-cụ-mcp-sunhouse-chuyên-biệt)
  - [2.1. Tool 1: Sổ tay kỹ thuật tra cứu mã lỗi (`tra_cuu_ma_loi_sunhouse`)](#21-tool-1-sổ-tay-kỹ-thuật-tra-cứu-mã-lỗi-tra_cuu_ma_loi_sunhouse)
  - [2.2. Tool 2: Tra cứu thông tin doanh nghiệp & Lãnh đạo (`tra_cuu_thong_tin_sunhouse`)](#22-tool-2-tra-cứu-thông-tin-doanh-nghiệp--lãnh-đạo-tra_cuu_thong_tin_sunhouse)
  - [2.3. Tool 3: Tìm kiếm trực tuyến & Cào Web thời gian thực (`tim_kiem_truc_tuyen_sunhouse`)](#23-tool-3-tìm-kiếm-trực-tuyến--cào-web-thời-gian-thực-tim_kiem_truc_tuyen_sunhouse)
  - [2.4. Bảng ánh xạ tiền tố model chính thức của Tập đoàn Sunhouse](#24-bảng-ánh-xạ-tiền-tố-model-chính-thức-của-tập-đoàn-sunhouse)
  - [2.5. Thuật toán bù trừ ngữ âm tiếng Việt & Dự đoán Model từ ASR](#25-thuật-toán-bù-trừ-ngữ-âm-tiếng-việt--dự-đoán-model-từ-asr)
- [III. GIẢI QUYẾT TRIỆT ĐỂ LỖI ASR FILTER KHI ĐỌC MÃ MODEL](#iii-giải-quyết-triệt-để-lỗi-asr-filter-khi-đọc-mã-model)
  - [3.1. Hiện tượng thực tế trên phần cứng ESP32 & Nguyên nhân gốc rễ](#31-hiện-tượng-thực-tế-trên-phần-cứng-esp32--nguyên-nhân-gốc-rễ)
  - [3.2. Cải tiến giải thuật trong `core/utils/asr_filter.py`](#32-cải-tiến-giải-thuật-trong-coreutilsasr_filterpy)
  - [3.3. Kết quả kiểm chứng thực nghiệm](#33-kết-quả-kiểm-chứng-thực-nghiệm)
- [IV. CHUẨN HÓA KIẾN TRÚC PROMPT 3 TẦNG (LOẠI BỎ TRÙNG LẶP)](#iv-chuẩn-hóa-kiến-trúc-prompt-3-tầng-loại-bỏ-trùng-lặp)
  - [4.1. Vấn đề dư thừa Token khi định nghĩa Tool lặp lại 3 lần](#41-vấn-đề-dư-thừa-token-khi-định-nghĩa-tool-lặp-lại-3-lần)
  - [4.2. Phân tầng chuẩn xác giữa MCP Schema, Base Prompt và System Prompt](#42-phân-tầng-chuẩn-xác-giữa-mcp-schema-base-prompt-và-system-prompt)
  - [4.3. Nội dung cấu hình thực tế trong `agent-base-prompt.txt` và `.config.yaml`](#43-nội-dung-cấu-hình-thực-tế-trong-agent-base-prompttxt-và-configyaml)
- [V. CẤU TRÚC MÃ NGUỒN & QUY TRÌNH VẬN HÀNH](#v-cấu-trúc-mã-nguồn--quy-trình-vận-hành)
  - [5.1. Cây thư mục hoàn chỉnh của MCP Server](#51-cây-thư-mục-hoàn-chỉnh-của-mcp-server)
  - [5.2. Hệ thống Script vận hành tiện ích trong `Tools_server/`](#52-hệ-thống-script-vận-hành-tiện-ích-trong-tools_server)
  - [5.3. Bộ công cụ kiểm thử tự động (Unit Test & Integration Test)](#53-bộ-công-cụ-kiểm-thử-tự-động-unit-test--integration-test)
- [VI. BẢNG RỦI RO TIỀM TÀNG & KẾ HOẠCH PHÒNG VỆ MỞ RỘNG](#vi-bảng-rủi-ro-tiềm-tàng--kế-hoạch-phòng-vệ-mở-rộng)
- [VII. TIÊU CHÍ NGHIỆM THU ĐẠT CHUẨN THƯƠNG MẠI (DEFINITION OF DONE - DoD)](#vii-tiêu-chí-nghiệm-thu-đạt-chuẩn-thương-mại-definition-of-done---dod)

---

## I. BẢN CHẤT KIẾN TRÚC, NGUYÊN LÝ LOGIC & PHÂN TẦNG NHIỆM VỤ

### 1.1. Bản chất chuẩn xác của MCP Endpoint Server trong Hệ sinh thái XiaoZhi

Theo thiết kế mã nguồn mở chính thức của hệ sinh thái XiaoZhi (xem kho [xinnan-tech/mcp-endpoint-server](https://github.com/xinnan-tech/mcp-endpoint-server)), **MCP Endpoint Server** là một **MCP Message Broker & Registry Hub (Trạm Đăng Ký & Điều Phối Thông Điệp Tập Trung)** chạy trên cổng `8004`.

Nó giải quyết triệt để bài toán:
- **XiaoZhi Voice Server chỉ cần duy nhất 1 kết nối WebSocket** tới MCP Endpoint Server:
  `ws://<IP>:8004/mcp_endpoint/mcp/?token=<TOKEN>`
- **Nhiều công cụ mở rộng (Tools)** khác nhau (Sổ tay mã lỗi, Thông tin doanh nghiệp, Live Scraper Sunhouse, Nhà thông minh Home Assistant, Tra cứu phạt nguội...) được quản lý tập trung và tự động nạp.
- MCP Server tự động **gộp (merge)** tất cả danh sách Tool và **định tuyến thông minh (smart routing)** cuộc gọi `tools/call` đến đúng Tool phụ trách.

```text
┌────────────────────────────────────────────────────────────────────────────────────────┐
│               SƠ ĐỒ BẢN CHẤT KIẾN TRÚC MCP ENDPOINT SERVER (PORT 8004)                 │
├────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                        │
│   [XiaoZhi Server] (Voice Backend - Port 8000/8003)                                    │
│          ▲                                                                             │
│          │ (WebSocket: ws://127.0.0.1:8004/mcp_endpoint/mcp/?token=abc)               │
│          ▼                                                                             │
│   ┌──────────────────────────────────────────────────────────────────────────────┐     │
│   │                 MCP ENDPOINT SERVER (Python Port 8004)                       │     │
│   │   - Quản lý Token & Xác thực an ninh.                                        │     │
│   │   - Endpoint kiểm tra sức khỏe: http://127.0.0.1:8004/mcp_endpoint/health    │     │
│   │   - Bộ tự động khám phá Tool (Auto-discovery từ thư mục tools/).             │     │
│   │   - Xử lý JSON-RPC 2.0 (initialize, tools/list, tools/call).                 │     │
│   └──────────────────────▲───────────────────────▲───────────────────────────────┘     │
│                          │                       │                                     │
│     (Hệ sinh thái Sunhouse)                      │ (Plugin tương lai: Home Assistant)  │
│                          │                       │                                     │
│   ┌──────────────────────┴───────────────────────────────────────┐                     │
│   │ HỆ THỐNG CÔNG CỤ CHUYÊN TRÁCH SUNHOUSE                       │                     │
│   │ • Tool 1: tra_cuu_ma_loi_sunhouse (Database mã lỗi E0–E9)    │                     │
│   │ • Tool 2: tra_cuu_thong_tin_sunhouse (Shark Phú, nhà máy...) │                     │
│   │ • Tool 3: tim_kiem_truc_tuyen_sunhouse (Live Web Scraper)    │                     │
│   │   └─ Trích xuất HTML sunhouse.com.vn + Tự sửa sai ASR        │                     │
│   └──────────────────────────────────────────────────────────────┘                     │
│                                                                                        │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

### 1.2. Phân định ranh giới & Phân tầng nhiệm vụ giữa các khối

| Thành phần | Công nghệ / Port | Nhiệm vụ chuyên trách | Khả năng chịu lỗi (Fault Tolerance) |
| :--- | :--- | :--- | :--- |
| **XiaoZhi Voice Backend** | Python AsyncIO<br>Port `8000` (WS Audio)<br>Port `8003` (HTTP Vision/OTA) | Xử lý âm thanh thời gian thực: Nhận luồng Opus 24kHz từ ESP32, VAD, FunASR, lọc ảo giác ASR Filter, gửi LLM, tạo giọng nói VieNeu-TTS. | Cốt lõi, bắt buộc phải online 24/7 để phục vụ đàm thoại. |
| **MCP Endpoint Server** | Python AsyncIO / Websockets<br>Port `8004` (WS & HTTP Health) | Trạm trung chuyển, phân luồng gói tin JSON-RPC 2.0 giữa XiaoZhi Server và các Tool. Cung cấp API giám sát `/mcp_endpoint/health`. | Độc lập hoàn toàn. Nếu rớt mạng, XiaoZhi tự thử kết nối lại sau mỗi 5s. |
| **Tool 1: Mã lỗi Sunhouse** | `tools/sunhouse_tool.py` | Tra cứu cơ sở tri thức mã lỗi kỹ thuật chuẩn từ file `sunhouse_knowledge.json`. Trả về nguyên nhân cốt lõi và hướng xử lý an toàn. | Tốc độ < 2ms, độc lập dữ liệu nội bộ. |
| **Tool 2: Thông tin tập đoàn** | `tools/sunhouse_tool.py` | Cung cấp thông tin chính thống về Shark Phú, cụm nhà máy, chính sách bảo hành 1800.6680. | Tốc độ < 2ms, triệt tiêu 100% ảo giác thông tin doanh nghiệp. |
| **Tool 3: Cào Web trực tuyến** | `tools/sunhouse_live_search_tool.py` | Cào trực tiếp thông số kỹ thuật model, tin tức từ trang chủ `https://sunhouse.com.vn/`. Tự động sửa lỗi ngọng ASR và fallback Bing. | Có Cache TTL 10 phút, fallback an toàn nếu mạng chập chờn. |

---

### 1.3. Cơ chế Khám phá Đa Công cụ (Multi-Server Merging & Smart Routing)

Trong file mã nguồn `core/providers/tools/mcp_endpoint/mcp_endpoint_handler.py` của XiaoZhi:
1. Khi XiaoZhi kết nối tới Broker, nó gửi:
   ```json
   {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
   ```
2. MCP Server tổng hợp 3 tool từ thư mục `tools/` (`tra_cuu_ma_loi_sunhouse`, `tra_cuu_thong_tin_sunhouse`, `tim_kiem_truc_tuyen_sunhouse`) và trả về cho XiaoZhi trong một danh sách duy nhất.
3. Khi LLM quyết định gọi tool:
   XiaoZhi gửi:
   ```json
   {
     "jsonrpc": "2.0",
     "id": 10,
     "method": "tools/call",
     "params": {
       "name": "tim_kiem_truc_tuyen_sunhouse",
       "arguments": {"tu_khoa": "bếp từ đơn SHD6805", "loai_tim_kiem": "thong_so_model"}
     }
   }
   ```
4. Server đọc trường `name`, gọi đúng hàm Python tương ứng, lấy kết quả và đóng gói phản hồi chuẩn:
   ```json
   {"jsonrpc": "2.0", "id": 10, "result": {"content": [{"type": "text", "text": "..."}]}}
   ```

---

### 1.4. So sánh Tri thức tĩnh nội bộ (Database) và Cào Web trực tuyến (Live Scraping)

| Tiêu chí | Dữ liệu nội bộ Backend (Tool 1 & 2) | Cào Web trực tuyến (Tool 3) |
| :--- | :--- | :--- |
| **Bản chất** | File JSON/Database lưu sẵn trong server backend. | Backend đóng vai trò Web Scraper chủ động gửi HTTP Request lên website hãng. |
| **Loại thông tin** | Sổ tay mã lỗi kỹ thuật, lãnh đạo doanh nghiệp, hotline, nhà máy. | Model sản phẩm chi tiết (công suất, kích thước), tin tức sự kiện mới ra, sản phẩm mới. |
| **Tốc độ truy xuất** | Siêu nhanh (< 2ms). | ~1.5 - 2.5s (phụ thuộc tốc độ mạng và độ phản hồi của trang web). |
| **Tính cập nhật** | Cố định, cần sửa file khi có thay đổi. | Thời gian thực 100%, web có gì mới là lấy được ngay. |
| **Khả năng chịu tải** | Cực cao, không phụ thuộc bên ngoài. | Tối ưu bằng In-memory Cache TTL 10 phút để tránh spam request. |

---

### 1.5. Sơ đồ tương tác toàn trình End-to-End (E2E Sequence Flow)

```text
  [ KHÁCH HÀNG ]
        │  Nói: "Bếp từ đơn sáu tám không năm công suất bao nhiêu em?"
        ▼
 ┌──────────────┐   (1) Stream Opus 24kHz    ┌───────────────────────────────────────────────┐
 │  LOA ESP32   │ ─────────────────────────► │         XIAOZHI VOICE SERVER (PORT 8000)      │
 │  (Phần cứng) │ ◄───────────────────────── │ • VAD cắt câu -> FunASR nhận văn bản: '6805'  │
 └──────────────┘   (8) Stream âm thanh TTS  │ • ASR Filter: Cho phép token số '6805' qua    │
                                             │ • LLM ghép tiền tố 'SHD6805' -> Quyết định    │
                                             │   gọi tool: 'tim_kiem_truc_tuyen_sunhouse'    │
                                             └───────────────────────┬───────────────────────┘
                                                                     │ (2) JSON-RPC: tools/call
                                                                     │     tu_khoa: SHD6805
                                                                     │     loai_tim_kiem: thong_so_model
                                                                     ▼
                                             ┌───────────────────────────────────────────────┐
                                             │     MCP ENDPOINT SERVER (PORT 8004)           │
                                             │ • Smart Routing gọi sunhouse_live_search_tool │
                                             └───────────────────────┬───────────────────────┘
                                                                     │ (3) HTTP GET /search/SHD6805
                                                                     ▼
                                             ┌───────────────────────────────────────────────┐
                                             │        TRANG CHỦ SUNHOUSE (SUNHOUSE.COM.VN)   │
                                             │ • Trả về HTML chi tiết sản phẩm               │
                                             │ • Bóc tách: Công suất 2000W, kính ceramic...  │
                                             └───────────────────────┬───────────────────────┘
                                                                     │ (4) Trích xuất thông số chuẩn
                                                                     ▼
                                             ┌───────────────────────────────────────────────┐
                                             │        TRẢ VỀ KẾT QUẢ CHO TIẾN TRÌNH TTS       │
                                             │ (5) MCP Server -> (6) XiaoZhi Voice Server    │
                                             │ • LLM tóm lược thành câu thoại tự nhiên       │
                                             │ • VieNeu-TTS phát giọng ấm áp qua Loa ESP32   │
                                             └───────────────────────────────────────────────┘
```

---

## II. THIẾT KẾ BỘ BA CÔNG CỤ MCP SUNHOUSE CHUYÊN BIỆT

### 2.1. Tool 1: Sổ tay kỹ thuật tra cứu mã lỗi (`tra_cuu_ma_loi_sunhouse`)

* **Mục đích:** Cung cấp giải pháp chuẩn xác khi thiết bị gặp lỗi, bảo vệ an toàn điện và tránh ảo giác.
* **Đặc tính kỹ thuật:**
  * Hỗ trợ 5 nhóm thiết bị: Bếp từ, Quạt điều hòa/hơi nước, Nồi cơm điện tử, Nồi chiên không dầu, Máy lọc nước RO.
  * Tự động chuẩn hóa từ vựng dân gian ("bếp điện" ➔ "bep_tu", "quạt hơi nước" ➔ "quat_dieu_hoa").
  * Tự động thêm cảnh báo an toàn điện và cung cấp hotline 1800.6680 khi gặp lỗi bo mạch phần cứng (`need_technician = true`).

```python
@register_tool(
    name="tra_cuu_ma_loi_sunhouse",
    description="Tra cứu nguyên nhân kỹ thuật và giải pháp xử lý mã lỗi thiết bị gia dụng Sunhouse...",
    parameters={
        "type": "object",
        "properties": {
            "loai_thiet_bi": {"type": "string", "description": "Tên loại thiết bị (bếp từ, quạt điều hòa...)"},
            "ma_loi": {"type": "string", "description": "Ký tự mã lỗi hiển thị (E0, E1, E2, E4...)"}
        },
        "required": ["loai_thiet_bi", "ma_loi"]
    }
)
```

---

### 2.2. Tool 2: Tra cứu thông tin doanh nghiệp & Lãnh đạo (`tra_cuu_thong_tin_sunhouse`)

* **Mục đích:** Đảm bảo câu trả lời về uy tín thương hiệu, nhà sáng lập, chính sách bảo hành luôn đạt chuẩn mực truyền thông doanh nghiệp.
* **Các chủ đề hỗ trợ:**
  * `chu_tich_lanh_dao`: Doanh nhân Nguyễn Xuân Phú (Shark Phú), vai trò sáng lập, triết lý kinh doanh.
  * `tong_dai_bao_hanh_lien_he`: Tổng đài miễn cước 1800 6680, địa chỉ trụ sở Richy Tower Cầu Giấy (Hà Nội) và Chi nhánh Sonatus (TP.HCM), website e-warranty.
  * `nha_may_san_xuat`: Cụm 8 cụm nhà máy tại Quốc Oai (Hà Nội) và Hà Nam (nhà máy vi mạch điện tử Sunhouse).
  * `lich_su_gioi_thieu`: Thành lập năm 2000 (tiền thân Công ty TNHH Phú Thắng), liên doanh Hàn Quốc, Thương hiệu Quốc gia.

---

### 2.3. Tool 3: Tìm kiếm trực tuyến & Cào Web thời gian thực (`tim_kiem_truc_tuyen_sunhouse`)

* **Mục đích:** Giải quyết các câu hỏi động về thông số kỹ thuật model cụ thể, các bản tin thời sự mới nhất hoặc các sản phẩm Sunhouse mới ra mắt.
* **Cơ chế bóc tách thông minh (HTML Spec Scraper):**
  * Tự động crawl trang tìm kiếm: `https://sunhouse.com.vn/search/<candidate>`.
  * Trích xuất thông số kỹ thuật cốt lõi theo thứ tự ưu tiên: Mã sản phẩm, Công suất, Điện áp, Vùng nấu, Kích thước, Dung tích, Mặt kính, Bảng điều khiển, Chế độ nấu, Hẹn giờ, Khóa trẻ em, Xuất xứ, Bảo hành.
  * Tích hợp bộ nhớ đệm `_CACHE` với TTL 10 phút, tránh lặp request.
  * Tích hợp cơ chế Fallback sang Bing Search khi website bảo trì hoặc sản phẩm thuộc catalog cũ.

---

### 2.4. Bảng ánh xạ tiền tố model chính thức của Tập đoàn Sunhouse

Để giúp hệ thống tự động suy luận model khi khách chỉ nói số hoặc nói thiếu tiền tố:

| Tiền tố | Dòng sản phẩm tương ứng | Ví dụ model thực tế | Quy tắc suy luận tự động |
| :--- | :--- | :--- | :--- |
| **SHD** | **Điện gia dụng phổ biến:**<br>• Bếp từ đơn (`SHD6xxx`)<br>• Quạt điều hòa, máy làm mát (`SHD7xxx`)<br>• Nồi cơm điện (`SHD8xxx`)<br>• Nồi chiên không dầu (`SHD4xxx`)<br>• Máy xay sinh tố, ép chậm (`SHD5xxx`)<br>• Ấm siêu tốc, bình thủy (`SHD1xxx`) | • `SHD6805` (Bếp từ đơn 2000W)<br>• `SHD7737` (Máy làm mát 220W)<br>• `SHD8903` (Nồi cơm điện tử)<br>• `SHD4018` (Nồi chiên 4L) | Khi khách nói thiết bị gia dụng đơn kèm số (ví dụ: *"quạt 7737"*, *"bếp từ 6805"*), tự động ghép tiền tố `SHD`. |
| **SHB** / **MMB** | **Thiết bị nhà bếp cao cấp:**<br>• Bếp từ đôi, bếp đôi hồng ngoại<br>• Bếp ba điện từ hồng ngoại<br>• Máy hút mùi kính cong, kính vát | • `SHB82082-VMD` (Bếp đôi 2200W Booster)<br>• `SHB9101` (Bếp từ đôi)<br>• `MMB8888` (Sunhouse Mama) | Khi khách nói "bếp đôi", "bếp từ đôi" kèm số, ưu tiên ghép `SHB` hoặc `MMB`. |
| **SHA** / **SHR** | **Máy lọc nước & Điện lạnh:**<br>• Máy lọc nước RO UltraX, nóng lạnh<br>• Cây nước nóng lạnh, máy lọc nước để bàn | • `SHA76688SH` (UltraX 11 lõi)<br>• `SHA76210KL`<br>• `SHR76210CK` | Khi khách nói "máy lọc nước" kèm số, ưu tiên ghép `SHA` hoặc `SHR`. |
| **SHG** / **ST** / **SBD** | **Nồi chảo & Gia dụng nhà bếp:**<br>• Chảo Ultra Titanium Plasma (`ST`)<br>• Chảo Nano Diamond Ceramic (`SHG`)<br>• Bộ nồi Inox Anod (`SHG`, `SH`) | • `ST28B` (Chảo Titanium 28cm)<br>• `SHG1120-24`<br>• `SBD24` | Khi khách nói "chảo", "nồi inox" kèm số hoặc kích thước. |
| **HTD** / **APB** | **Thương hiệu con thuộc Sunhouse:**<br>• HappyTime (`HTD`)<br>• Apex (`APB`) | • `HTD4018` (Nồi chiên HappyTime)<br>• `APB9988` | Dự phòng khi model không khớp với các dải chính. |

---

### 2.5. Thuật toán bù trừ ngữ âm tiếng Việt & Dự đoán Model từ ASR

Hàm `normalize_asr_phonetics()` và `generate_model_candidates()` trong `sunhouse_live_search_tool.py`:

```python
def normalize_asr_phonetics(text: str) -> str:
    """Chuẩn hóa cách phát âm ngữ âm tiếng Việt do ASR dịch ra sang chữ cái viết tắt chuẩn"""
    text_lower = text.lower()
    replacements = [
        # Tiền tố SHD
        (r'ét\s*hát\s*đê|ét\s*hắt\s*đê|sờ\s*hắt\s*đê|sờ\s*hát\s*đê|sắc\s*đê|s\s*đê|ét\s*đê|ép\s*đê', 'shd'),
        # Tiền tố SHB
        (r'ét\s*hát\s*bê|ét\s*hắt\s*bê|sờ\s*hắt\s*bê|sờ\s*hát\s*bê|s\s*bê|ét\s*bê|sờ\s*bê', 'shb'),
        # Tiền tố SHA
        (r'ét\s*hát\s*a|ét\s*hắt\s*a|sờ\s*hắt\s*a|sờ\s*hát\s*a|s\s*a|ét\s*a', 'sha'),
        # Tiền tố MMB (Sunhouse Mama)
        (r'em\s*em\s*bê|mờ\s*mờ\s*bê|ma\s*ma', 'mmb'),
    ]
    for pattern, rep in replacements:
        text_lower = re.sub(pattern, rep, text_lower)
    return text_lower
```

**Chiến lược sinh ứng viên:**
1. Trích xuất mã có sẵn tiền tố chuẩn: `SHD6805`, `SHB82082`.
2. Trích xuất cụm số 3–6 chữ số (ví dụ: `82082`, `6805`).
3. Ưu tiên ghép tiền tố theo từ khóa ngữ cảnh (ví dụ thấy chữ "bếp đôi" ➔ sinh `SHB82082`, `MMB82082`).
4. Thử xoay vòng các tiền tố chủ lực: `SHD`, `SHB`, `SHA`, `MMB`, `SHG`.
5. Đưa chính cụm số vào danh sách tìm kiếm (ví dụ `/search/82082` vẫn tìm thấy Bếp đôi `SHB82082-VMD`).

---

## III. GIẢI QUYẾT TRIỆT ĐỂ LỖI ASR FILTER KHI ĐỌC MÃ MODEL

### 3.1. Hiện tượng thực tế trên phần cứng ESP32 & Nguyên nhân gốc rễ

Khi kiểm thử thực tế với bo mạch ESP32:
* Người dùng đọc mã model ngắn: *"HB82082"* hoặc *"82082"*.
* Hoặc ASR FunASR/Whisper nghe ngọng thành: `" nhmhp82082"`.
* **Hiện tượng:** Chatbot hoàn toàn im lặng, không trả lời và không gọi bất kỳ công cụ nào.
* **Nguyên nhân phân tích từ Log hệ thống:**
  ```text
  [core.providers.asr.base]-INFO-识别文本:  HB82082
  [core.providers.asr.base]-WARNING-[ASR FILTER] 🗑️ Bỏ qua văn bản không hợp lệ: ' HB82082' 
  (Lý do: Từ đơn ngoài Whitelist: 'hb82082' (nghi vấn tiếng tặc lưỡi/click mic/ảo giác)), không gửi LLM
  ```
  Bộ lọc [asr_filter.py](file:///e:/Espressif/frameworks/esp-idf-v5.5.3/examples/xiaozhi-esp32-main/xiaozhi-esp32-server/main/xiaozhi-server/core/utils/asr_filter.py) kiểm tra thấy `len(words) == 1`. Vì chuỗi này không nằm trong `VALID_SINGLE_WORDS`, hệ thống đã **đánh đồng mã model là tiếng tặc lưỡi của Whisper và vứt bỏ**, không hề gửi tới LLM.

---

### 3.2. Cải tiến giải thuật trong `core/utils/asr_filter.py`

Áp dụng 2 cải tiến mang tính bản lề:

1. **Quy tắc chữ số bất khả xâm phạm:**
   Mọi từ đơn có chứa chữ số (`re.search(r'\d', single_word)`) như:
   * Mã model: `HB82082`, `nhmhp82082`, `SHD6805`, `MMB82082`...
   * Số hiệu: `82082`, `6805`, `7737`, `100`...
   * Mã lỗi: `E1`, `E4`, `E01`, `E88`...  
   👉 **BẮT BUỘC coi là hợp lệ 100%**, vì tiếng tặc lưỡi, chép miệng của con người không bao giờ chứa chữ số.

2. **Mở rộng Whitelist từ đơn:**
   Bổ sung các danh từ thiết bị (`bếp`, `quạt`, `đèn`, `nồi`, `ấm`, `lọc`...), thương hiệu (`sunhouse`, `xiaozhi`), tiền tố model (`shd`, `shb`, `sha`, `mmb`...) để người dùng nói câu cộc lốc vẫn được phục vụ chu đáo.

---

### 3.3. Kết quả kiểm chứng thực nghiệm

* Unit Test [tests/test_asr_filter.py](file:///e:/Espressif/frameworks/esp-idf-v5.5.3/examples/xiaozhi-esp32-main/xiaozhi-esp32-server/main/xiaozhi-server/tests/test_asr_filter.py): Vượt qua 6/6 bài test (`OK`).
* Kiểm thử cào web với 2 chuỗi thực tế từ log:
  * `HB82082` ➔ Trích xuất số `82082` ➔ Cào thành công **BẾP ĐÔI ĐIỆN TỪ SUNHOUSE SHB82082-VMD** (Công suất 2200W Booster, mặt kính Ultra Vitro Ceramic, kích thước 730x430x85mm, bảo hành 36 tháng).
  * `nhmhp82082` (ASR nghe dính chữ) ➔ Vẫn bắt được số `82082` và trả về chính xác model `SHB82082-VMD`.

---

## IV. CHUẨN HÓA KIẾN TRÚC PROMPT 3 TẦNG (LOẠI BỎ TRÙNG LẶP)

### 4.1. Vấn đề dư thừa Token khi định nghĩa Tool lặp lại 3 lần

Trước khi tối ưu, phần mô tả các Tool Sunhouse bị khai báo trùng lặp tại 3 nơi:
1. `description` và `parameters` trong mã nguồn Python MCP Tool.
2. Thẻ `<tool_and_knowledge>` trong [agent-base-prompt.txt](file:///e:/Espressif/frameworks/esp-idf-v5.5.3/examples/xiaozhi-esp32-main/xiaozhi-esp32-server/main/xiaozhi-server/agent-base-prompt.txt).
3. Mục 10, 11, 12 trong [data/.config.yaml](file:///e:/Espressif/frameworks/esp-idf-v5.5.3/examples/xiaozhi-esp32-main/xiaozhi-esp32-server/main/xiaozhi-server/data/.config.yaml).

Điều này gây lãng phí từ 400 - 600 Token cho mỗi lượt chat (turn), làm tăng độ trễ suy luận của LLM và gây phân tâm chỉ dẫn (instruction dilution).

---

### 4.2. Phân tầng chuẩn xác giữa MCP Schema, Base Prompt và System Prompt

Áp dụng mô hình kiến trúc phân tầng chuẩn quốc tế:

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│ TẦNG 1: MCP TOOL SCHEMA (Giao thức JSON-RPC tools/list)                     │
│ • Định nghĩa: Tên hàm, kiểu tham số, ví dụ, docstring chi tiết.            │
│ • Nhiệm vụ: Cung cấp API Contract kỹ thuật để LLM Function Calling hiểu.   │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ TẦNG 2: BASE PROMPT (agent-base-prompt.txt)                                 │
│ • Định nghĩa: Chỉ dẫn định tuyến cốt lõi (Routing Policy ngắn gọn 4 dòng).  │
│ • Nhiệm vụ: Hướng dẫn phân luồng câu hỏi nào thì gọi công cụ nào.           │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ TẦNG 3: SYSTEM PROMPT NGHIỆP VỤ (data/.config.yaml - Mục 10)               │
│ • Định nghĩa: Kỷ luật cấm bịa số liệu + Bảng quy đổi tiền tố bù trừ ASR.    │
│ • Nhiệm vụ: Kiểm soát hành vi nghiệp vụ và xử lý tình huống đặc thù hãng.  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### 4.3. Nội dung cấu hình thực tế trong `agent-base-prompt.txt` và `.config.yaml`

**1. Trong [agent-base-prompt.txt](file:///e:/Espressif/frameworks/esp-idf-v5.5.3/examples/xiaozhi-esp32-main/xiaozhi-esp32-server/main/xiaozhi-server/agent-base-prompt.txt):**
```text
<tool_and_knowledge>
You have tools available. Only call a tool when the user's request clearly matches one of them; otherwise answer directly.
- Core routing: play music → play_music | control devices → IoT/hass tools | check weather → get_weather | farewell → handle_exit_intent.
- Sunhouse routing: error codes/malfunctions → tra_cuu_ma_loi_sunhouse | corporate info/leadership/history/hotline → tra_cuu_thong_tin_sunhouse | model specs/online search/daily news/new products → tim_kiem_truc_tuyen_sunhouse.
- No forced matching: If no tool fits, answer directly. Never force-call an unrelated tool.
</tool_and_knowledge>
```

**2. Trong [data/.config.yaml](file:///e:/Espressif/frameworks/esp-idf-v5.5.3/examples/xiaozhi-esp32-main/xiaozhi-esp32-server/main/xiaozhi-server/data/.config.yaml) (Gộp thành Mục 10 duy nhất):**
```yaml
  10. QUY TẮC KỶ LUẬT NGHIỆP VỤ & SỬ DỤNG CÔNG CỤ SUNHOUSE:
     - KỶ LUẬT TUYỆT ĐỐI: CẤM TỰ BỊA ĐẶT thông số kỹ thuật (công suất, kích thước), mã lỗi thiết bị hoặc tin tức doanh nghiệp. Bắt buộc gọi đúng công cụ MCP tương ứng:
       + Lỗi kỹ thuật / tiếng bíp / đèn cảnh báo: gọi 'tra_cuu_ma_loi_sunhouse'. Tóm tắt [Nguyên nhân] -> [Cách xử lý an toàn tại nhà]. Lỗi bo mạch cảnh báo nguy hiểm và nhắc gọi hotline miễn cước 1800.6680.
       + Thông tin doanh nghiệp / Shark Phú / nhà máy / bảo hành: gọi 'tra_cuu_thong_tin_sunhouse'.
       + Tra cứu model thiết bị / thông số kỹ thuật / tin tức hàng ngày / sản phẩm mới: gọi 'tim_kiem_truc_tuyen_sunhouse'.
     - BẢNG TIỀN TỐ MODEL BÙ TRỪ LỖI ASR (khi khách nói thiếu tiền tố hoặc nói ngọng):
       + Bếp từ đơn, nồi chiên, quạt điều hòa, nồi cơm, ấm siêu tốc, máy xay/ép: ghép tiền tố 'SHD' (ví dụ: 'bếp từ 6805' -> SHD6805, 'quạt 7737' -> SHD7737, 'nồi chiên 4018' -> SHD4018, 'nồi cơm 8903' -> SHD8903).
       + Bếp từ đôi, bếp đôi hồng ngoại, máy hút mùi: ghép tiền tố 'SHB' hoặc 'MMB' (ví dụ: 'bếp từ đôi 9101' -> SHB9101, 'bếp đôi 82082' -> SHB82082).
       + Máy lọc nước RO, bình nóng lạnh: ghép tiền tố 'SHA' hoặc 'SHR' (ví dụ: 'máy lọc nước 76688' -> SHA76688SH, 'lọc nước 76210' -> SHA76210KL).
       + Nồi chảo, chảo chống dính: ghép tiền tố 'SHG', 'ST', 'SBD'.
       + Âm vần rời rạc từ ASR: 'ét hát đê/sắc đê/s đê' -> SHD, 'ét hát bê/s bê' -> SHB, 'ét hát a/s a' -> SHA.
```

---

## V. CẤU TRÚC MÃ NGUỒN & QUY TRÌNH VẬN HÀNH

### 5.1. Cây thư mục hoàn chỉnh của MCP Server

```text
xiaozhi-esp32-server/mcp_server/
├── main.py                          # Server WebSocket JSON-RPC 2.0 (Port 8004)
├── test_client.py                   # Script kiểm thử độc lập 9 bài test của MCP Server
├── run_mcp_server.bat               # Khởi động nhanh MCP Server độc lập
├── data/
│   └── sunhouse_knowledge.json      # Sổ tay mã lỗi kỹ thuật chuẩn Sunhouse
└── tools/
    ├── __init__.py                  # Bộ quét Tool Registry (@register_tool, tools_list)
    ├── sunhouse_tool.py             # Tool 1 (Mã lỗi) & Tool 2 (Thông tin doanh nghiệp)
    └── sunhouse_live_search_tool.py # Tool 3 (Cào Web thời gian thực + Bù trừ ASR)
```

---

### 5.2. Hệ thống Script vận hành tiện ích trong `Tools_server/`

Tất cả các dịch vụ được điều khiển dễ dàng qua các file `.bat` trong `Tools_server/`:

* `KHOI_DONG_TAT_CA_SERVER.bat`: Khởi động toàn bộ 5 server (XiaoZhi Core, MCP Hub, Music Gateway, YouTube Relay, Ngrok Tunnel).
* `DUNG_TAT_CA_SERVER.bat`: Quét Port bằng `netstat` và giải phóng triệt để các cổng 8000, 8003, 8004, 3000, 3001.
* `1_KHOI_DONG_XIAOZHI_SERVER.bat` / `DUNG_XIAOZHI_SERVER.bat`: Bật/Tắt riêng XiaoZhi Voice Core.
* `2_KHOI_DONG_MCP_SERVER.bat` / `DUNG_MCP_SERVER.bat`: Bật/Tắt riêng Sunhouse MCP Endpoint Server.

---

### 5.3. Bộ công cụ kiểm thử tự động (Unit Test & Integration Test)

1. **Test MCP Server độc lập (`test_client.py`):**
   * Chạy: `python test_client.py`
   * Kiểm tra: Mã lỗi hợp lệ, mã lỗi không tồn tại, Shark Phú, hotline bảo hành, cào thông số bếp `SHD6805`, cào quạt `SHD7737`, cào tin tức mới. Đạt **9/9 PASS**.
2. **Test Tích Hợp XiaoZhi Backend (`tests/test_mcp_integration.py`):**
   * Chạy: `python tests/test_mcp_integration.py`
   * Mô phỏng: Bắt tay MCP initialize, kéo danh sách tool về backend XiaoZhi, gọi lần lượt cả 3 tools qua WebSocket tunnel và in kết quả. Đạt **100% PASS**.
3. **Test Bộ lọc ASR Filter (`tests/test_asr_filter.py`):**
   * Chạy: `python -m unittest tests.test_asr_filter -v`
   * Kiểm tra: Từ đơn rác bị chặn, từ đơn hợp lệ được qua, câu đầy đủ được qua, mã model/mã lỗi chứa chữ số (`HB82082`, `nhmhp82082`, `SHD6805`, `E1`) được qua 100%. Đạt **6/6 PASS**.

---

## VI. BẢNG RỦI RO TIỀM TÀNG & KẾ HOẠCH PHÒNG VỆ MỞ RỘNG

| Tình huống rủi ro | Dấu hiệu nhận biết | Nguyên nhân gốc rễ | Giải pháp kỹ thuật chuẩn xác đã tích hợp |
| :--- | :--- | :--- | :--- |
| **1. Bot bị "điếc" khi đọc mã model** | Nói model `HB82082` hoặc `6805` bot im lặng. Log báo `Từ đơn ngoài Whitelist`. | `asr_filter.py` gom thành từ 1 âm tiết và nhầm là tiếng tặc lưỡi. | Bổ sung quy tắc: Mọi từ chứa chữ số (`\d`) được duyệt qua 100%. Bổ sung danh từ thiết bị vào whitelist. |
| **2. Người dùng đọc thiếu tiền tố model** | Khách chỉ nói *"Bếp từ đơn 6805"* hoặc *"Quạt 7737"*. | Khách không nhớ chữ cái `SHD`, `SHB`. | Prompt Mục 10 + Hàm `generate_model_candidates` tự động ghép tiền tố theo danh mục thiết bị tương ứng. |
| **3. ASR nghe ngọng vần chữ cái** | Whisper phiên âm *"ét hát đê"* hoặc *"s đê"*. | ASR tiếng Việt nhận diện chữ viết tắt thành âm tiết rời rạc. | Tích hợp hàm `normalize_asr_phonetics()` tự động quy đổi âm vần về chữ cái viết tắt chuẩn. |
| **4. Trang web Sunhouse đổi giao diện HTML** | Không bóc tách được các thẻ `<li>` thông số kỹ thuật. | Cấu trúc DOM trang chi tiết thay đổi. | Thiết kế bộ bóc tách linh hoạt duyệt toàn bộ `div/li`, kết hợp Fallback tự động sang Bing Web Search. |
| **5. LLM tự bịa công suất hoặc mã lỗi** | Bot nói công suất sai lệch với nhãn máy. | LLM dùng kiến thức nội suy cũ. | Kỷ luật thép trong Prompt cấm tuyệt đối bịa số liệu kỹ thuật, bắt buộc gọi MCP Tool. |
| **6. Quá tải request lên sunhouse.com.vn** | Web hãng phản hồi chậm hoặc chặn IP tạm thời. | Nhiều thiết bị cùng truy vấn 1 model liên tục. | Tích hợp bộ nhớ đệm `_CACHE` với thời gian sống TTL 10 phút. |

---

## VII. TIÊU CHÍ NGHIỆM THU ĐẠT CHUẨN THƯƠNG MẠI (DEFINITION OF DONE - DoD)

Một hệ thống MCP Endpoint Server được công nhận hoàn thành và đạt chuẩn thương mại khi thỏa mãn toàn bộ 8 tiêu chí khắt khe sau:

- [x] **Tiêu chí 1 (Chuẩn Kiến trúc Độc lập):** Dịch vụ MCP Endpoint Server chạy độc lập tại Port `8004`, có trang giám sát kết nối `/mcp_endpoint/health` hoạt động ổn định.
- [x] **Tiêu chí 2 (Tự động khám phá 100%):** XiaoZhi Server tự động kéo danh sách cả 3 Tool về khi khởi động mà không cần can thiệp gõ code thủ công trên backend giọng nói.
- [x] **Tiêu chí 3 (Độ chính xác tuyệt đối từ sổ tay):** Khi hỏi các mã lỗi kỹ thuật (E0-E4 bếp từ, E1 quạt điều hòa...), kết quả phản hồi của AI khớp 100% với tài liệu kỹ thuật Sunhouse.
- [x] **Tiêu chí 4 (Thông tin doanh nghiệp chuẩn xác):** Phản hồi chính xác về Chủ tịch Nguyễn Xuân Phú (Shark Phú), cụm 8 nhà máy, hotline miễn cước 1800.6680.
- [x] **Tiêu chí 5 (Cào Web thời gian thực):** Tự động bóc tách thông số kỹ thuật chi tiết của bất kỳ model Sunhouse nào trên `sunhouse.com.vn` (công suất, kích thước, mặt kính, bảo hành).
- [x] **Tiêu chí 6 (Tự phục hồi lỗi phát âm ASR):** Tự động sửa lỗi ngọng "ét hát đê" ➔ `SHD`, tự động ghép tiền tố khi khách chỉ nói số (ví dụ: `6805` ➔ `SHD6805`, `82082` ➔ `SHB82082-VMD`).
- [x] **Tiêu chí 7 (Triệt tiêu lỗi ASR Filter):** Người dùng đọc mã model cộc lốc hoặc dính chữ (`HB82082`, `nhmhp82082`, `E1`) không bao giờ bị bộ lọc ASR chặn nhầm.
- [x] **Tiêu chí 8 (Hiệu năng thời gian thực):** Thời gian phản hồi mã lỗi nội bộ `< 2 mili-giây`; thời gian cào web có cache `< 5 mili-giây`, cào mới `< 2 giây`.
