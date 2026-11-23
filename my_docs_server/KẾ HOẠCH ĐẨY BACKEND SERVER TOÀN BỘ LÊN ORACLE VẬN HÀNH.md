# KẾ HOẠCH ĐẨY BACKEND SERVER TOÀN BỘ LÊN ORACLE VẬN HÀNH (24/7 PRODUCTION DEPLOYMENT)

> **Tài liệu kỹ thuật nội bộ hệ thống XiaoZhi Voice Assistant & Sunhouse IoT Ecosystem**  
> **Cơ sở hạ tầng mục tiêu:** Oracle Cloud Infrastructure (OCI) — Gói tài nguyên miễn phí trọn đời (Always Free Tier: 4 OCPU ARM Ampere A1, 24 GB RAM, 200 GB NVMe SSD, 1 IPv4 Public Static IP).  
> **Phương thức cập nhật chuẩn hóa:** **Git Workflow & Script tự động cập nhật 5 giây** (Code được kiểm thử 100% trên môi trường Local Dev trước khi đẩy lên Oracle Production).  
> **Bộ nguyên tắc thiết kế bất khả xâm phạm:** Chia để trị, Module hóa độc lập, Bảo toàn cấu trúc hệ thống, Không phá vỡ các module hiện có.  
> **Thời gian khởi tạo:** Tháng 10/2026 | **Trạng thái:** Kế hoạch hành động chuẩn mực (Action Roadmap & Quality Gate Checklist).

---

## 📑 MỤC LỤC CHI TIẾT

- [I. Bối Cảnh, Động Lực Chuyển Đổi & Mục Tiêu Hệ Thống](#i-bối-cảnh-động-lực-chuyển-đổi--mục-tiêu-hệ-thống)
- [II. Bộ Nguyên Tắc Vàng Trong Triển Khai (Core Architectural Principles)](#ii-bộ-nguyên-tắc-vàng-trong-triển-khai-core-architectural-principles)
- [III. Phân Tích Khả Năng Tương Thích & Cân Đối Tài Nguyên OCI ARM64](#iii-phân-tích-khả-năng-tương-thích--cân-đối-tài-nguyên-oci-arm64)
- [IV. Sơ Đồ Kiến Trúc Tương Tác Toàn Trình (End-to-End Architecture)](#iv-sơ-đồ-kiến-trúc-tương-tác-toàn-trình-end-to-end-architecture)
- [V. Lộ Trình Triển Khai 5 Hạng Mục Lớn & Bảng Checklist Nghiệm Thu Từng Hạng Mục](#v-lộ-trình-triển-khai-5-hạng-mục-lớn--bảng-checklist-nghiệm-thu-từng-hạng-mục)
  - [HẠNG MỤC 1: Khởi Tạo & Thiết Lập Hạ Tầng Máy Chủ Oracle Cloud](#hạng-mục-1-khởi-tạo--thiết-lập-hạ-tầng-máy-chủ-oracle-cloud)
  - [HẠNG MỤC 2: Module Hóa & Container Hóa Độc Lập Từng Dịch Vụ](#hạng-mục-2-module-hóa--container-hóa-độc-lập-từng-dịch-vụ)
  - [HẠNG MỤC 3: Tổng Hợp Hệ Sinh Thái Bằng Docker Compose & Mạng Nội Bộ 0ms](#hạng-mục-3-tổng-hợp-hệ-sinh-thái-bằng-docker-compose--mạng-nội-bộ-0ms)
  - [HẠNG MỤC 4: Thiết Lập Git Workflow & Tự Động Hóa Cập Nhật 5 Giây](#hạng-mục-4-thiết-lập-git-workflow--tự-động-hóa-cập-nhật-5-giây)
  - [HẠNG MỤC 5: Đồng Bộ Firmware ESP32 & Nghiệm Thu Toàn Trình E2E](#hạng-mục-5-đồng-bộ-firmware-esp32--nghiệm-thu-toàn-trình-e2e)
- [VI. Bảng Mã Lỗi Tiềm Tàng, Rủi Ro & Kế Hoạch Phòng Vệ (Troubleshooting)](#vi-bảng-mã-lỗi-tiềm-tàng-rủi-ro--kế-hoạch-phòng-vệ-troubleshooting)
- [VII. Tiêu Chí Nghiệm Thu Tổng Thể Cuối Cùng (Definition of Done)](#vii-tiêu-chí-nghiệm-thu-tổng-thể-cuối-cùng-definition-of-done)

---

## I. Bối Cảnh, Động Lực Chuyển Đổi & Mục Tiêu Hệ Thống

### 1. Thực trạng khi vận hành Local trên máy tính cá nhân
- **Rủi ro đứt gãy mạng do DHCP cấp lại IP:** Khi đổi sóng Wi-Fi, restart router hoặc mạng công ty cấp phát lại địa chỉ IP (`172.16.2.194` $\rightarrow$ `172.16.3.54`), hệ thống bị mất kết nối hoàn toàn, đòi hỏi phải rà soát và sửa đổi thủ công nhiều file cấu hình trên cả backend và firmware ESP32.
- **Ràng buộc phần cứng cá nhân:** Máy tính cá nhân phải mở 24/7, không thể tắt máy hoặc mang đi nơi khác; quạt tản nhiệt quay khi suy luận VieNeu-TTS.
- **Giới hạn phạm vi địa lý:** Loa ESP32 chỉ hoạt động khi ở chung dải mạng LAN Wi-Fi với máy tính, không thể mang đi biểu diễn (Demo), quán cafe hay văn phòng.

### 2. Mục tiêu chiến lược khi chuyển dịch lên Oracle Cloud
1. **Độc lập phần cứng 100%:** Toàn bộ hệ thống chạy ngầm 24/7/365 trên hạ tầng Cloud của Oracle với cam kết Uptime 99.9%.
2. **Cố định IP vĩnh viễn (Zero Re-configuration):** Sử dụng 1 địa chỉ IPv4 Public Static duy nhất được cấp miễn phí trọn đời.
3. **Plug & Play toàn cầu:** Loa ESP32 chỉ cần có Wi-Fi (bất kể ở đâu: nhà, quán cafe, 4G phát từ điện thoại) là tự động kết nối và đàm thoại ngay lập tức.
4. **Chi phí vận hành 0 VNĐ:** Tận dụng triệt để chính sách Oracle Always Free.

---

## II. Bộ Nguyên Tắc Vàng Trong Triển Khai (Core Architectural Principles)

Để đảm bảo quá trình di trú lên Cloud diễn ra chuẩn mực, an toàn, **"làm đến đâu gọn gàng chuẩn chỉ đến đó"**, toàn bộ quá trình bắt buộc phải tuân thủ 4 nguyên tắc vàng sau:

```text
┌──────────────────────────────────────────────────────────────────┐
│             BỘ 4 NGUYÊN TẮC VÀNG TRONG TRIỂN KHAI CLOUD          │
├──────────────────────────────────────────────────────────────────┤
│ 1. CHIA ĐỂ TRỊ (Divide and Conquer):                             │
│    Chia quy trình thành 5 Giai đoạn độc lập. Mỗi giai đoạn có    │
│    Checklist PASS riêng, xong mục nào dứt điểm mục đó.           │
│                                                                  │
│ 2. MODULE HÓA ĐỘC LẬP (Strict Modularization):                   │
│    4 microservices (XiaoZhi, YouTube Relay, Music API, MCP)      │
│    đóng gói riêng biệt, có Dockerfile, biến môi trường và        │
│    kịch bản test độc lập, không dính líu chéo.                   │
│                                                                  │
│ 3. BẢO TOÀN CẤU TRÚC HIỆN TẠI (Zero-Impact / Zero-Regression):   │
│    Giữ nguyên 100% cấu trúc thư mục và mã nguồn Local. Môi       │
│    trường Local vẫn hoạt động bình thường, cấu hình Cloud        │
│    tách biệt trong file môi trường chuyên biệt.                  │
│                                                                  │
│ 4. GIT WORKFLOW STAGING-TO-PROD (Kiểm thử trước khi đẩy):        │
│    Máy tính cá nhân là môi trường DEV / STAGING. Code phải test  │
│    chạy ổn định local mới commit & git push. Trên Oracle VPS     │
│    chỉ kéo code đã kiểm thử và cập nhật tự động trong 5 giây.    │
└──────────────────────────────────────────────────────────────────┘
```

---

## III. Phân Tích Khả Năng Tương Thích & Cân Đối Tài Nguyên OCI ARM64

### 1. Hồ sơ phần cứng OCI Always Free Tier
- **Shape máy ảo:** `VM.Standard.A1.Flex` (Ampere Altra ARM64 - aarch64).
- **Tài nguyên được cấp:** 4 OCPU (xung nhịp cố định 3.0 GHz) + 24 GB RAM + 200 GB SSD NVMe.
- **Mạng:** 1 IPv4 tĩnh công khai cố định vĩnh viễn, băng thông mạng 4 Gbps, 10 TB Egress/tháng.

### 2. Khả năng tương thích của VieNeu-TTS (CPU INT8 / ONNX ARM64)
- Thư viện `onnxruntime` có bản build chính thức hỗ trợ tập lệnh **ARM NEON**, giúp tối ưu hóa ma trận INT8 trên nhân ARM Ampere với tốc độ cực nhanh.
- Thời gian suy luận dự kiến: **Real-Time Factor (RTF) $\approx 0.35 - 0.45$** (câu thoại 3 giây chỉ mất ~1.1s để tổng hợp), hoàn toàn đạt chuẩn phản xạ thời gian thực.
- Dung lượng RAM: Mô hình VieNeu-TTS nạp vào RAM chiếm ~1.2 GB. Với 24 GB RAM của Oracle, hệ thống chỉ dùng **5% tổng RAM**, loại bỏ 100% rủi ro OOM (Out of Memory).

### 3. Cân đối tài nguyên & Bộ đệm an toàn (Resource Headroom)

```text
┌──────────────────────────────────────────────────────────────────┐
│             TÀI NGUYÊN ORACLE CLOUD: 4 OCPU & 24 GB RAM          │
└────────────────────────────────┬─────────────────────────────────┘
                                 │
  ┌──────────────────────────────┴──────────────────────────────┐
  │ • xiaozhi-server + VieNeu-TTS : RAM ~ 1.8 GB  | CPU ~ 1.8   │
  │ • audio-relay + ffmpeg Stream : RAM ~ 300 MB  | CPU ~ 0.4   │
  │ • serverless-music-api        : RAM ~ 150 MB  | CPU ~ 0.1   │
  │ • mcp-endpoint-server         : RAM ~ 150 MB  | CPU ~ 0.1   │
  ├─────────────────────────────────────────────────────────────┤
  │ ➔ TỔNG TIÊU THỤ THỰC TẾ       : ~ 2.6 GB RAM  | CPU ~ 2.4   │
  │ ➔ BỘ ĐỆM DỰ PHÒNG CÒN TRỐNG   :  21.4 GB RAM (89% CÒN TRỐNG)│
  └─────────────────────────────────────────────────────────────┘
```

---

## IV. Sơ Đồ Kiến Trúc Tương Tác Toàn Trình (End-to-End Architecture)

Sơ đồ được chuẩn hóa theo định dạng chiều dọc gọn gàng (dưới 68 ký tự), hiển thị hoàn hảo trên mọi màn hình:

```text
====================================================================
      SƠ ĐỒ TỔNG THỂ KIẾN TRÚC TƯƠNG TÁC TOÀN TRÌNH TRÊN ORACLE
====================================================================

  ┌──────────────────────────────────────────────────────────────┐
  │                 THIẾT BỊ ĐẦU CUỐI (CLIENTS)                  │
  │   • Loa Thông Minh ESP32-S3 (Mic / Loa / Màn hình LCD)       │
  │   • Kết nối Wi-Fi bất kỳ (Gia đình / Quán Cafe / 4G Hotspot) │
  └──────────────────────────────┬───────────────────────────────┘
                                 │
             ┌───────────────────┴───────────────────┐
             │ [1] HTTP GET /xiaozhi/ota/            │ [2] WebSocket ws://:8000
             │     (Port 8003: Cấp cấu hình)         │     (Port 8000: Âm thanh)
             ▼                                       ▼
┌──────────────────────────────────────────────────────────────────┐
│      HẠ TẦNG CLOUD ORACLE (PUBLIC STATIC IP HOẠT ĐỘNG 24/7)      │
│                                                                  │
│  [ TƯỜNG LỬA BẢO VỆ (OCI SECURITY LIST & UBUNTU IPTABLES) ]      │
│  • Mở cổng: 8000 (WS) | 8003 (OTA) | 3000 (Music) | 3001 (Relay) │
│──────────────────────────────────────────────────────────────────│
│                                                                  │
│  [ MẠNG NỘI BỘ DOCKER BRIDGE (xiaozhi_net - ĐỘ TRỄ NỘI BỘ 0ms) ] │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ [CONTAINER 1: xiaozhi-server]                              │  │
│  │ • Cổng lắng nghe: 8000 (WS Audio) & 8003 (HTTP OTA)        │  │
│  │ • Audio Pipeline: Silero VAD + Gói nén Opus 60ms           │  │
│  │ • TTS Cục bộ: VieNeu-TTS (CPU INT8 / ONNX ARM64 4 Cores)   │  │
│  │ • Quản lý hội thoại & Phối hợp gọi công cụ MCP             │  │
│  └──────────────┬───────────────────────────────┬─────────────┘  │
│                 │                               │                │
│       [3] Gọi nội bộ 0ms              [4] Gọi nội bộ 0ms         │
│                 ▼                               ▼                │
│  ┌────────────────────────────┐   ┌───────────────────────────┐  │
│  │ [CONTAINER 3: music-api]   │   │ [CONTAINER 4: mcp-server] │  │
│  │ • Cổng: 3000 (HTTP)        │   │ • Cổng: Nội bộ            │  │
│  │ • Phân giải ZingMP3/YouTube│   │ • Điều khiển IoT Sunhouse │  │
│  └──────────────┬─────────────┘   └───────────────────────────┘  │
│                 │                                                │
│        [5] Chuyển tiếp luồng nhạc                                │
│                 ▼                                                │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ [CONTAINER 2: youtube-relay]                               │  │
│  │ • Cổng: 3001 (HTTP)                                        │  │
│  │ • Chuyển mã ffmpeg sang Opus/MP3 + Lưu đệm cache NVMe      │  │
│  └──────────────┬─────────────────────────────────────────────┘  │
└─────────────────┼────────────────────────────────────────────────┘
                  │
                  │ [6] Stream âm thanh trực tiếp về Loa (Port 3001)
                  ▼
┌──────────────────────────────────────────────────────────────────┐
│              DỊCH VỤ TRÍ TUỆ NHÂN TẠO CLOUD QUỐC TẾ              │
│  • Groq Cloud LPU  : Nhận dạng giọng nói siêu tốc (Whisper ASR)  │
│  • DeepSeek API    : Tư duy ngôn ngữ & Gọi công cụ (LLM V3/R1)   │
└──────────────────────────────────────────────────────────────────┘
```

#### Bảng Diễn Giải Luồng Dữ Liệu Tương Tác Chi Tiết (Call Flow):
1. **[1] Khởi tạo & Cấp phát OTA (Port 8003):** ESP32 gửi `HTTP POST /xiaozhi/ota/` mang theo MAC và version $\rightarrow$ Container `xiaozhi-server` trả về thông số kết nối WebSocket và Vision AI.
2. **[2] Thiết lập kênh đàm thoại WebSocket (Port 8000):** ESP32 mở kết nối `ws://<IP_ORACLE>:8000/xiaozhi/v1/`. Kênh âm thanh 2 chiều được giữ liên tục (Streaming Opus 60ms/frame).
3. **[3] Nhận dạng giọng nói & Trí tuệ LLM:** Khi người dùng nói, `xiaozhi-server` cắt gói âm thanh gửi sang **Groq Whisper ASR** $\rightarrow$ Text nhận dạng được chuyển sang **DeepSeek LLM** để xử lý ý đồ.
4. **[4] Tổng hợp tiếng nói VieNeu-TTS:** Văn bản trả lời của AI được nạp vào engine **VieNeu-TTS (CPU INT8)** chạy trực tiếp trên 4 nhân ARM của máy chủ Oracle $\rightarrow$ sinh âm thanh 24kHz trong < 0.5s và stream ngược về ESP32.
5. **[5] Phân giải nhạc trực tuyến (Port 3000):** Khi có câu lệnh nghe nhạc, DeepSeek gọi tool `play_music` $\rightarrow$ `xiaozhi-server` gọi qua mạng nội bộ Docker tới `serverless-music-api` để tìm bài hát trên ZingMP3 / YouTube.
6. **[6] Chuyển mã & Stream nhạc (Port 3001):** `youtube-relay` dùng `ffmpeg` chuyển đổi luồng âm thanh YouTube thành Opus/MP3 và stream trực tiếp về loa ESP32, đồng thời lưu đệm vào ổ cứng NVMe để phát lại tức thì lần sau.

---

## V. Lộ Trình Triển Khai 5 Hạng Mục Lớn & Bảng Checklist Nghiệm Thu Từng Hạng Mục

---

### HẠNG MỤC 1: Khởi Tạo & Thiết Lập Hạ Tầng Máy Chủ Oracle Cloud
*Mục tiêu: Thiết lập máy ảo Ubuntu 22.04 LTS kiến trúc ARM64, cố định Public IP tĩnh, mở tường lửa 2 lớp và cài đặt môi trường Docker.*

#### Các bước triển khai chi tiết:
- **1.1. Khởi tạo Compute Instance:**
  - Truy cập `cloud.oracle.com` $\rightarrow$ Compute $\rightarrow$ Instances $\rightarrow$ Create instance.
  - Image: **Ubuntu 22.04 Minimal / LTS** (aarch64).
  - Shape: `VM.Standard.A1.Flex` $\rightarrow$ Cấu hình **4 OCPU, 24 GB RAM, 200 GB Boot Volume**.
  - Networking: Gán Public IPv4 cố định. Tải SSH Key (`oracle_key.pem`) về máy tính cá nhân.
- **1.2. Mở cổng Firewall Lớp 1 (OCI Cloud VCN Security List):**
  - Vào Virtual Cloud Network (VCN) $\rightarrow$ Default Security List $\rightarrow$ Add Ingress Rules.
  - Thêm Ingress Rule cho Source `0.0.0.0/0`, Protocol `TCP`, Ports: `8000, 8003, 3000, 3001, 22`.
- **1.3. Mở cổng Firewall Lớp 2 (Hệ điều hành Ubuntu trên VPS):**
  - Chạy lệnh iptables cho phép traffic đi qua các cổng:
    ```bash
    sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 8000 -j ACCEPT
    sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 8003 -j ACCEPT
    sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 3000 -j ACCEPT
    sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 3001 -j ACCEPT
    sudo apt-get install -y iptables-persistent
    sudo netfilter-persistent save
    ```
- **1.4. Cài đặt Docker & Các gói công cụ hệ thống:**
  ```bash
  sudo apt update && sudo apt upgrade -y
  curl -fsSL https://get.docker.com | bash
  sudo usermod -aG docker $USER
  sudo apt install -y ffmpeg git htop
  # Thiết lập múi giờ chuẩn Việt Nam
  sudo timedatectl set-timezone Asia/Ho_Chi_Minh
  ```

#### 📋 CHECKLIST PASS HẠNG MỤC 1:
| STT | Tiêu chí nghiệm thu | Lệnh kiểm tra xác thực (Verification) | Kết quả kỳ vọng (Expected) | Trạng thái |
|:---:|---|---|---|:---:|
| 1.1 | Kết nối SSH thành công | `ssh -i oracle_key.pem ubuntu@<IP_ORACLE>` | Đăng nhập vào shell Ubuntu 22.04 | [ ] PASS |
| 1.2 | Kiến trúc CPU đúng chuẩn ARM64 | `uname -m && nproc` | Trả về `aarch64` và `4` nhân CPU | [ ] PASS |
| 1.3 | Dung lượng RAM đạt 24GB | `free -h` | Hiển thị Total RAM: `23Gi` hoặc `24Gi` | [ ] PASS |
| 1.4 | Docker Engine hoạt động | `docker --version && docker compose version` | Docker `>= 24.x`, Compose `>= 2.x` | [ ] PASS |
| 1.5 | ffmpeg đã sẵn sàng | `ffmpeg -version` | Trả về thông tin build của ffmpeg | [ ] PASS |
| 1.6 | Tường lửa không chặn cổng | `sudo iptables -L INPUT -n -v \| grep -E '8000\|8003\|3000\|3001'` | Có 4 luật ACCEPT cho các cổng | [ ] PASS |

---

### HẠNG MỤC 2: Module Hóa & Container Hóa Độc Lập Từng Dịch Vụ
*Mục tiêu: Đóng gói từng dịch vụ thành Docker Image độc lập, kiểm thử riêng lẻ từng container, đảm bảo không có sự phụ thuộc chéo làm phá vỡ cấu trúc module.*

#### Các bước triển khai chi tiết:
- **2.1. Module hóa `xiaozhi-server` (kèm VieNeu-TTS ARM64):**
  - Tách Dockerfile riêng [`xiaozhi-esp32-server/Dockerfile-server`](file:///e:/Espressif/frameworks/esp-idf-v5.5.3/examples/xiaozhi-esp32-main/xiaozhi-esp32-server/Dockerfile-server).
  - Tích hợp thư viện `vieneu==3.8.3` cùng bản build `onnxruntime` hỗ trợ ARM64.
  - Chạy thử nghiệm độc lập và benchmark tốc độ sinh âm thanh:
    ```bash
    python tests/test_vieneu_standalone.py
    ```
    *Đảm bảo thời gian tổng hợp đạt RTF < 0.5 trên 4 nhân ARM.*
- **2.2. Module hóa `audio-stream-relay` (Port 3001):**
  - Tách Dockerfile riêng cho Node.js Express + ffmpeg.
  - Mount thư mục cache ra ổ cứng để lưu trữ các bài hát đã tải từ YouTube.
- **2.3. Module hóa `serverless-music-api` (Port 3000):**
  - Đóng gói cổng tìm kiếm ZingMP3 / YouTube. Cấu hình biến môi trường `AUDIO_RELAY_BASE_URL` trỏ tới container relay nội bộ.
- **2.4. Module hóa `mcp-endpoint-server`:**
  - Đảm bảo các tool IoT Sunhouse (quạt, đèn, cảm biến) được nạp chuẩn xác qua giao thức MCP.

#### 📋 CHECKLIST PASS HẠNG MỤC 2:
| STT | Tiêu chí nghiệm thu | Lệnh kiểm tra xác thực (Verification) | Kết quả kỳ vọng (Expected) | Trạng thái |
|:---:|---|---|---|:---:|
| 2.1 | Build image `xiaozhi-server` thành công | `docker build -t test-xiaozhi -f xiaozhi-esp32-server/Dockerfile-server .` | Image build `Successfully` | [ ] PASS |
| 2.2 | Benchmark VieNeu-TTS đạt chuẩn | `python xiaozhi-esp32-server/main/xiaozhi-server/tests/test_vieneu_standalone.py` | RTF $\le 0.5$ (Xuất file WAV chuẩn) | [ ] PASS |
| 2.3 | Build image `youtube-relay` thành công | `docker build -t test-relay -f audio_stream_relay/Dockerfile audio_stream_relay/` | Image build `Successfully` | [ ] PASS |
| 2.4 | Build image `music-api` thành công | `docker build -t test-music -f serverless_music_api/Dockerfile serverless_music_api/` | Image build `Successfully` | [ ] PASS |
| 2.5 | Độc lập mã nguồn | Kiểm tra cấu trúc thư mục local không bị thay đổi | Không có file rác bị ghi đè | [ ] PASS |

---

### HẠNG MỤC 3: Tổng Hợp Hệ Sinh Thái Bằng Docker Compose & Mạng Nội Bộ 0ms
*Mục tiêu: Tạo file cấu hình `docker-compose.prod.yml` duy nhất để dàn dựng (Orchestrate) toàn bộ 4 dịch vụ, kết nối mạng nội bộ 0ms và phân tách dữ liệu lưu trữ bền vững.*

#### Các bước triển khai chi tiết:
- **3.1. Thiết lập Mạng ảo Docker Bridge `xiaozhi_net`:**
  - Cho phép các container phân giải tên miền nội bộ của nhau mà không cần biết địa chỉ IP.
  - `xiaozhi-server` gọi `http://music-api:3000`, `music-api` gọi `http://youtube-relay:3001` với độ trễ nội bộ < 0.2ms.
- **3.2. Cấu hình Mount Thư mục Bền vững (Persistence Storage):**
  - Mount file cấu hình: `./data:/opt/xiaozhi-esp32-server/data`
  - Mount cache âm thanh: `./audio_stream_relay/cache:/app/cache`
  - Mount mô hình giọng đọc: `./models/vieneu:/opt/xiaozhi-esp32-server/models/vieneu`
- **3.3. Thiết lập Giới hạn Tài nguyên (Resource Constraints & Log Rotation):**
  - Khống chế log Docker tối đa 50MB/file để không làm đầy ổ đĩa 200GB.
  - Phân bổ CPU: `xiaozhi-server` (max 3.0 cores), `youtube-relay` (max 1.0 core), `music-api` (max 0.5 core).

#### 📋 CHECKLIST PASS HẠNG MỤC 3:
| STT | Tiêu chí nghiệm thu | Lệnh kiểm tra xác thực (Verification) | Kết quả kỳ vọng (Expected) | Trạng thái |
|:---:|---|---|---|:---:|
| 3.1 | Cú pháp Compose hợp lệ | `docker compose -f docker-compose.prod.yml config` | Cú pháp hợp lệ, không báo lỗi YAML | [ ] PASS |
| 3.2 | Khởi động đồng loạt 3 container | `docker compose -f docker-compose.prod.yml up -d` | Cả 3 container hiển thị `Started` | [ ] PASS |
| 3.3 | Trạng thái Container khỏe mạnh | `docker compose -f docker-compose.prod.yml ps` | Tất cả container ở trạng thái `Up` | [ ] PASS |
| 3.4 | Giao tiếp mạng nội bộ 0ms | `docker exec xiaozhi-server curl -s http://music-api:3000/health` | Nhận phản hồi JSON status OK | [ ] PASS |
| 3.5 | Dung lượng RAM dưới ngưỡng an toàn | `docker stats --no-stream` | Tổng RAM 3 container < 3.5 GB | [ ] PASS |

---

### HẠNG MỤC 4: Thiết Lập Git Workflow & Tự Động Hóa Cập Nhật 5 Giây
*Mục tiêu: Đưa vào vận hành quy trình "Code test Local xong mới Push lên Oracle". Tạo script cập nhật 1 lệnh trên VPS để pull code và reload container trong vòng 5 giây mà không làm gián đoạn hệ thống.*

#### Các bước triển khai chi tiết:
- **4.1. Chuẩn hóa Git Repository & Loại trừ file nhạy cảm:**
  - Đảm bảo file `.gitignore` loại trừ các file chứa thông tin máy tính local, token, key cá nhân.
  - Đưa toàn bộ source code đã chuẩn hóa lên Git Remote (GitHub/GitLab Private).
- **4.2. Xây dựng Script tự động cập nhật `deploy.sh` trên Oracle VPS:**
  Tạo file `/home/ubuntu/xiaozhi-project/deploy.sh` với nội dung tự động hóa:
  ```bash
  #!/bin/bash
  set -e
  echo "🚀 [1/3] Đang kéo mã nguồn mới nhất từ Git..."
  git pull origin main

  echo "🔍 [2/3] Kiểm tra tính hợp lệ của file cấu hình YAML..."
  python3 -c "import yaml; yaml.safe_load(open('xiaozhi-esp32-server/main/xiaozhi-server/data/.config.yaml'))"

  echo "🔄 [3/3] Khởi động lại dịch vụ Backend..."
  docker compose -f docker-compose.prod.yml restart xiaozhi-server

  echo "=========================================================="
  echo "✓ CẬP NHẬT HOÀN TẤT TRONG 3 GIÂY! HỆ THỐNG ĐÃ ONLINE 24/7."
  echo "=========================================================="
  ```
  Cấp quyền thực thi: `chmod +x deploy.sh`.

- **4.3. Quy trình vận hành thực chiến hàng ngày:**
  ```text
  [Máy tính cá nhân] Sửa code ➔ Test chạy OK ➔ git commit & git push
                                                         │
                                                         ▼
  [Oracle Cloud VPS]  Chạy 1 lệnh: ./deploy.sh ➔ Cập nhật xong sau 3-5s
  ```

#### 📋 CHECKLIST PASS HẠNG MỤC 4:
| STT | Tiêu chí nghiệm thu | Lệnh kiểm tra xác thực (Verification) | Kết quả kỳ vọng (Expected) | Trạng thái |
|:---:|---|---|---|:---:|
| 4.1 | Script `deploy.sh` có quyền chạy | `ls -l deploy.sh` | Quyền file `-rwxr-xr-x` | [ ] PASS |
| 4.2 | Git Pull hoạt động mượt mà | `git pull origin main` | Kéo code về thành công (Already up to date hoặc Files changed) | [ ] PASS |
| 4.3 | Thời gian chạy script $\le 5$ giây | `time ./deploy.sh` | Tổng thời gian thực thi < 5.0s | [ ] PASS |
| 4.4 | Không làm rớt container | `docker compose -f docker-compose.prod.yml ps` | Container không bị thoát mã lỗi | [ ] PASS |
| 4.5 | Tính toàn vẹn cấu hình | File `data/.config.yaml` trên VPS giữ nguyên Public IP của Oracle | Cấu hình không bị đè bởi IP local | [ ] PASS |

---

### HẠNG MỤC 5: Đồng Bộ Firmware ESP32 & Nghiệm Thu Toàn Trình E2E
*Mục tiêu: Nạp địa chỉ IP Public của Oracle vào firmware bo mạch ESP32, kiểm thử toàn trình đàm thoại tiếng Việt, phát nhạc trực tuyến và kiểm tra khả năng hoạt động độc lập khi tắt máy tính.*

#### Các bước triển khai chi tiết:
- **5.1. Cập nhật Firmware cấu hình tập trung:**
  Mở file [`main/local_server_config.h`](file:///e:/Espressif/frameworks/esp-idf-v5.5.3/examples/xiaozhi-esp32-main/main/local_server_config.h):
  ```c
  #define USE_LOCAL_SERVER        1
  // Điền địa chỉ IP Public tĩnh của Oracle Cloud:
  #define LOCAL_SERVER_IP         "<IP_PUBLIC_ORACLE>"
  ```
- **5.2. Biên dịch & Nạp Firmware vào Bo mạch:**
  ```bash
  idf.py -p <COM_PORT> flash monitor
  ```
- **5.3. Thực hiện chuỗi 3 bài kiểm thử thực chiến (Test Scenarios):**
  - **Kịch bản A (Đàm thoại thông minh):** Đánh thức "Xin chào XiaoZhi" $\rightarrow$ Hỏi thời tiết, kể chuyện $\rightarrow$ Nghe giọng đọc VieNeu-TTS phát ra từ loa.
  - **Kịch bản B (Phát nhạc trực tuyến):** Ra lệnh "Mở bài hát Cắt đôi nỗi sầu" $\rightarrow$ ESP32 gọi `music-api` $\rightarrow$ `youtube-relay` stream nhạc về loa trơn tru.
  - **Kịch bản C (Kiểm thử độc lập phần cứng):** Tắt hoàn toàn máy tính cá nhân, rút nguồn loa và cắm lại ở một mạng Wi-Fi khác (hoặc phát 4G từ điện thoại) $\rightarrow$ Loa tự động kết nối và phản hồi bình thường.

#### 📋 CHECKLIST PASS HẠNG MỤC 5:
| STT | Tiêu chí nghiệm thu | Kịch bản kiểm thử (Test Scenario) | Kết quả kỳ vọng (Expected) | Trạng thái |
|:---:|---|---|---|:---:|
| 5.1 | ESP32 kết nối thành công | Khởi động loa ESP32 và quan sát log serial | Xuất hiện `WS: Connected to server!` | [ ] PASS |
| 5.2 | Đàm thoại VieNeu-TTS trơn tru | Nói câu thoại tiếng Việt thông thường | Loa phát câu trả lời trong < 1.2s, âm thanh rõ, không vấp | [ ] PASS |
| 5.3 | Phát nhạc YouTube thành công | Ra lệnh phát 1 bài hát bất kỳ | Loa nhận luồng stream và phát nhạc mượt mà không giật | [ ] PASS |
| 5.4 | Thử nghiệm tắt máy tính | Tắt nguồn máy tính cá nhân, nói chuyện với loa | Loa vẫn đàm thoại bình thường 24/7 | [ ] PASS |
| 5.5 | Thử nghiệm đổi mạng Wi-Fi | Mang loa ra quán cafe hoặc bắt Wi-Fi 4G | Loa tự kết nối về Oracle và hoạt động ngay tức thì | [ ] PASS |

---

## VI. Bảng Mã Lỗi Tiềm Tàng, Rủi Ro & Kế Hoạch Phòng Vệ (Troubleshooting)

| Mã lỗi / Triệu chứng | Nguyên nhân gốc rễ | Giải pháp kỹ thuật phòng vệ triệt để |
|---|---|---|
| **`EspTcp: Failed to connect to <IP>:8000, code=0x71`** | Chưa mở cổng trên Oracle VCN Security List hoặc iptables trên Ubuntu VPS. | 1. Vào Oracle Console kiểm tra Ingress Rules cổng 8000/8003.<br/>2. Chạy `sudo iptables -L -n -v` trên VPS để đảm bảo cổng không bị DROP. |
| **`Cannot import vieneu / onnxruntime trên ARM64`** | Phiên bản onnxruntime cũ thiếu cờ biên dịch cho kiến trúc aarch64. | Cài đặt bản build chính thức hỗ trợ ARM: `pip install --upgrade onnxruntime` (bản `>= 1.18.0` hỗ trợ hoàn hảo ARM NEON). |
| **Oracle báo `Out of Host Capacity` khi tạo máy** | Datacenter Oracle khu vực chọn (ví dụ Singapore) tạm thời hết tài nguyên máy ảo ARM miễn phí. | 1. Đổi Availability Domain (từ AD-1 sang AD-2 hoặc AD-3).<br/>2. Hoặc sử dụng công cụ CLI tự động gửi request tạo máy khi có slot trống. |
| **Âm thanh VieNeu-TTS đọc bị chậm hoặc giật** | Chưa kích hoạt chế độ đa luồng CPU trên môi trường ARM. | Bổ sung biến môi trường `OMP_NUM_THREADS=4` trong file Compose để ép ONNX Runtime tận dụng tối đa cả 4 nhân CPU. |
| **Xung đột Git khi chạy `deploy.sh`** | Sửa file trực tiếp trên VPS làm xung đột với commit mới từ Local. | Luôn tuân thủ quy tắc: Không sửa code trên VPS. Nếu bị lệch branch, chạy lệnh `git checkout . && git pull`. |

---

## VII. Tiêu Chí Nghiệm Thu Tổng Thể Cuối Cùng (Definition of Done)

Toàn bộ kế hoạch chỉ được coi là hoàn tất khi và chỉ khi vượt qua đầy đủ 5 tiêu chí nghiệm thu tổng thể:

- [ ] **1. Hoàn tất 100% Checklist của cả 5 Hạng mục:** Toàn bộ các bảng kiểm tra từ Hạng mục 1 đến Hạng mục 5 đều đạt trạng thái `[x] PASS`.
- [ ] **2. Tính ổn định 24/7:** Hệ sinh thái 3 container chạy ổn định trên Oracle Cloud liên tục 48 giờ không có sự cố sập nguồn hay rò rỉ bộ nhớ.
- [ ] **3. Hiệu năng thời gian thực:** VieNeu-TTS suy luận đạt chuẩn RTF $\le 0.5$, độ trễ đàm thoại toàn trình (Voice-to-Voice) dưới 1.5 giây.
- [ ] **4. Độc lập hoàn toàn phần cứng:** Máy tính cá nhân có thể tắt nguồn hoặc mang đi bất kỳ đâu mà loa ESP32 vẫn phục vụ người dùng bình thường.
- [ ] **5. Chi phí vận hành bằng 0:** Hóa đơn hàng tháng của Oracle Cloud Infrastructure hiển thị chính xác **$0.00**.
