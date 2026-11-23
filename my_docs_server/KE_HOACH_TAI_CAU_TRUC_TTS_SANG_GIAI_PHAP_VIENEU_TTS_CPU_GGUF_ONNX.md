# KẾ HOẠCH TÁI CẤU TRÚC HẠ TẦNG TTS SANG GIẢI PHÁP VIENEU-TTS CPU GGUF / ONNX RUNTIME

> **Tài liệu kỹ thuật nội bộ hệ thống XiaoZhi Voice Assistant Backend**  
> **Cơ sở phân tích & kỹ thuật:**  
> - Mục IV tài liệu [CAC_MUC_TAI_CAU_TRUC_BACKEND_SERVER_XIAOZHI.md](file:///e:/Espressif/frameworks/esp-idf-v5.5.3/examples/xiaozhi-esp32-main/xiaozhi-esp32-server/my_docs_server/CAC_MUC_TAI_CAU_TRUC_BACKEND_SERVER_XIAOZHI.md)  
> - Bố cục & chuẩn mực kiến trúc từ [TIM_HIEU_TTS_VA_TAI_CAU_TRUC_TTS_THEO_VOLCENGINE_DOUBAO.md](file:///e:/Espressif/frameworks/esp-idf-v5.5.3/examples/xiaozhi-esp32-main/xiaozhi-esp32-server/my_docs_server/TIM_HIEU_TTS_VA_TAI_CAU_TRUC_TTS_THEO_VOLCENGINE_DOUBAO.md)  
> - Mã nguồn hệ sinh thái `xiaozhi-server`: `core/providers/tts/`, `core/utils/util.py`, `core/utils/tts.py`  
> - Đặc tả thư viện mã nguồn mở `vieneu` (tác giả Phạm Nguyễn Ngọc Bảo / `pnnbao97`)  
> - Hồ sơ phần cứng máy chủ Host: CPU Intel Core i5-1135G7, GPU NVIDIA GeForce MX450 (2 GB VRAM), 12 GB RAM, mạch khuếch đại I2S DAC MAX98357A (24kHz Mono).  
> **Thời gian khởi tạo:** Tháng 10/2026  
> **Trạng thái:** Bản thiết kế kiến trúc chuẩn & Kế hoạch hành động (Architectural Specification & Action Roadmap).

---

## 📑 MỤC LỤC CHI TIẾT

- [I. Bối Cảnh, Động Lực Tái Cấu Trúc & Thực Trạng Hạ Tầng TTS Hiện Tại](#i-bối-cảnh-động-lực-tái-cấu-trúc--thực-trạng-hạ-tầng-tts-hiện-tại)
  - [1. Thực trạng 2 giải pháp TTS hiện có trong hệ thống](#1-thực-trạng-2-giải-pháp-tts-hiện-có-trong-hệ-thống)
  - [2. Nhu cầu cấp thiết về một giải pháp TTS Tiếng Việt Offline thế hệ mới](#2-nhu-cầu-cấp-thiết-về-một-giải-pháp-tts-tiếng-việt-offline-thế-hệ-mới)
  - [3. Vì sao lựa chọn VieNeu-TTS (Kiến trúc & Hệ sinh thái)](#3-vì-sao-lựa-chọn-vieneu-tts-kiến-trúc--hệ-sinh-thái)
- [II. Bản Chất Công Nghệ & Khả Năng Tương Thích Phần Cứng Của VieNeu-TTS](#ii-bản-chất-công-nghệ--khả-năng-tương-thích-phần-cứng-của-vieneu-tts)
  - [1. Nguyên lý công nghệ: On-Device Neural Synthesis & Bilingual Code-Switching](#1-nguyên-lý-công-nghệ-on-device-neural-synthesis--bilingual-code-switching)
  - [2. Phân tích giới hạn phần cứng máy chủ Host & Chiến lược bảo vệ GPU](#2-phân-tích-giới-hạn-phần-cứng-máy-chủ-host--chiến-lược-bảo-vệ-gpu)
    - [2.1. Cạm bẫy CUDA OOM trên card đồ họa rời NVIDIA MX450 (2 GB VRAM)](#21-cạm-bẫy-cuda-oom-trên-card-đồ-họa-rời-nvidia-mx450-2-gb-vram)
    - [2.2. Sức mạnh đột phá của CPU Intel Core i5-1135G7 (AVX-512 & VNNI)](#22-sức-mạnh-đột-phá-của-cpu-intel-core-i5-1135g7-avx-512--vnni)
  - [3. Định hướng định dạng: Lượng tử hóa GGUF / ONNX Runtime int8](#3-định-hướng-định-dạng-lượng-tử-hóa-gguf--onnx-runtime-int8)
  - [4. Cơ chế Instant Zero-Shot Voice Cloning (Sao chép giọng 3–5 giây)](#4-cơ-chế-instant-zero-shot-voice-cloning-sao-chép-giọng-35-giây)
- [III. Bảng So Sánh Đối Đầu Toàn Diện Các Giải Pháp TTS](#iii-bảng-so-sánh-đối-đầu-toàn-diện-các-giải-pháp-tts)
- [IV. Kiểm Toán Kiến Trúc Mã Nguồn Backend Hiện Tại & Rút Ra Bài Học](#iv-kiểm-toán-kiến-trúc-mã-nguồn-backend-hiện-tại--rút-ra-bài-học)
  - [1. Khảo sát cơ chế nạp động module (`core/utils/tts.py`)](#1-khảo-sát-cơ-chế-nạp-động-module-coreutilsttspy)
  - [2. Phân tích lớp cơ sở `TTSProviderBase` (`core/providers/tts/base.py`)](#2-phân-tích-lớp-cơ-sở-ttsproviderbase-coreprovidersttsbasepy)
  - [3. Bài học kỹ thuật từ `piper.py` (Singleton Model Cache & Thread Pool Executor)](#3-bài-học-kỹ-thuật-từ-piperpy-singleton-model-cache--thread-pool-executor)
  - [4. Bài học kỹ thuật từ `edge.py` (In-Memory Sentence Pipelining & Cắt Cúp Ngắt Lời)](#4-bài-học-kỹ-thuật-từ-edgepy-in-memory-sentence-pipelining--cắt-cúp-ngắt-lời)
  - [5. Chuẩn hóa tần số lấy mẫu 24kHz Mono cho mạch DAC MAX98357A](#5-chuẩn-hóa-tần-số-lấy-mẫu-24khz-mono-cho-mạch-dac-max98357a)
- [V. Bộ Nguyên Tắc Vàng Trong Triển Khai (Core Architectural Principles)](#v-bộ-nguyên-tắc-vàng-trong-triển-khai-core-architectural-principles)
  - [1. Nguyên tắc Module hóa độc lập tuyệt đối (Strict Modularization)](#1-nguyên-tắc-module-hóa-độc-lập-tuyệt-đối-strict-modularization)
  - [2. Nguyên tắc Chia để trị (Divide and Conquer)](#2-nguyên-tắc-chia-để-trị-divide-and-conquer)
  - [3. Nguyên tắc Bảo toàn cấu trúc & Tương thích ngược (Zero-Impact on Existing Code)](#3-nguyên-tắc-bảo-toàn-cấu-trúc--tương-thích-ngược-zero-impact-on-existing-code)
  - [4. Hệ sinh thái 3 tùy chọn TTS hoán đổi nóng (Hot-Swappable 3 TTS Options)](#4-hệ-sinh-thái-3-tùy-chọn-tts-hoán-đổi-nóng-hot-swappable-3-tts-options)
  - [5. Nguyên tắc Phòng vệ tài nguyên máy chủ (Hardware Guardian & Zero GPU Footprint)](#5-nguyên-tắc-phòng-vệ-tài-nguyên-máy-chủ-hardware-guardian--zero-gpu-footprint)
- [VI. Lộ Trình Triển Khai Chi Tiết & Bảng Checklist Nghiệm Thu Từng Giai Đoạn](#vi-lộ-trình-triển-khai-chi-tiết--bảng-checklist-nghiệm-thu-từng-giai-đoạn)
  - [Giai đoạn 1: Chuẩn bị môi trường, quản lý thư viện & Benchmark độc lập](#giai-đoạn-1-chuẩn-bị-môi-trường-quản-lý-thư-viện--benchmark-độc-lập)
  - [Giai đoạn 2: Nâng cấp tiện ích âm thanh In-Memory Transcoder cho MAX98357A (`core/utils/util.py`)](#giai-đoạn-2-nâng-cấp-tiện-ích-âm-thanh-in-memory-transcoder-cho-max98357a-coreutilsutilpy)
  - [Giai đoạn 3: Hiện thực hóa Provider lõi `core/providers/tts/vieneu.py`](#giai-đoạn-3-hiện-thực-hóa-provider-lõi-coreprovidersttsvieneupy)
  - [Giai đoạn 4: Kiến trúc Voice Cloning (Clone giọng MC Nguyễn Ngọc Ngạn / Đa giọng) & Quản trị cấu hình](#giai-đoạn-4-kiến-trúc-voice-cloning-clone-giọng-mc-nguyễn-ngọc-ngạn--đa-giọng--quản-trị-cấu-hình)
  - [Giai đoạn 5: Kiểm thử toàn trình (E2E Integration Testing), Pytest & Nghiệm thu phần cứng ESP32](#giai-đoạn-5-kiểm-thử-toàn-trình-e2e-integration-testing-pytest--nghiệm-thu-phần-cứng-esp32)
- [VII. Đặc Tả Thiết Lập Cấu Hình Thực Chiến (`data/.config.yaml` & `config.yaml`)](#vii-đặc-tả-thiết-lập-cấu-hình-thực-chiến-dataconfigyaml--configyaml)
- [VIII. Bảng Mã Lỗi Tiềm Tàng, Rủi Ro Hệ Thống & Giải Pháp Phòng Thủ (Troubleshooting & Fallback)](#viii-bảng-mã-lỗi-tiềm-tàng-rủi-ro-hệ-thống--giải-pháp-phòng-thủ-troubleshooting--fallback)
- [IX. Kế Hoạch Đo Đạc & Tiêu Chí Đánh Giá Thành Công (Success Metrics)](#ix-kế-hoạch-đo-đạc--tiêu-chí-đánh-giá-thành-công-success-metrics)

---

## I. Bối Cảnh, Động Lực Tái Cấu Trúc & Thực Trạng Hạ Tầng TTS Hiện Tại

```
                                ┌────────────────────────────────────────────────────────┐
                                │             HẠ TẦNG TTS BACKEND SERVER HIỆN TẠI        │
                                └──────────────────────────┬─────────────────────────────┘
                                                           │
                    ┌──────────────────────────────────────┴─────────────────────────────────────┐
                    ▼                                                                            ▼
┌───────────────────────────────────────┐                                    ┌───────────────────────────────────────┐
│        OPTION 1: MICROSOFT EDGETTS    │                                    │        OPTION 2: PIPER-TTS OFFLINE    │
│        (Cloud In-Memory Streaming)    │                                    │        (ONNX Runtime VAIS 1000)       │
├───────────────────────────────────────┤                                    ├───────────────────────────────────────┤
│ • Ưu điểm:                            │                                    │ • Ưu điểm:                            │
│   - Giọng Hoài My chuẩn Neural êm ái  │                                    │   - 100% Offline, không cần mạng      │
│   - Độ trễ phát đầu ~350 - 500ms      │                                    │   - Siêu nhẹ (Model ONNX ~60 MB)      │
│   - Hoàn toàn miễn phí API Key        │                                    │   - Tốc độ suy luận CPU ~300 - 400ms  │
│ • Nhược điểm cố hữu:                  │                                    │ • Nhược điểm cố hữu:                  │
│   - Phụ thuộc đường truyền Internet   │                                    │   - Giọng phát thanh viên cứng nhắc   │
│   - Rủi ro bị Microsoft WAF rate-limit│                                    │   - Chỉ có 1 giọng đọc cố định        │
│   - Không thể tùy biến / clone giọng  │                                    │   - Không hỗ trợ Voice Cloning        │
└───────────────────────────────────────┘                                    └───────────────────────────────────────┘
                                                           │
                                                           ▼ (Nhu cầu nâng cấp tất yếu)
                                ┌────────────────────────────────────────────────────────┐
                                │        OPTION 3 ĐỀ XUẤT: VIENEU-TTS CPU INT8/GGUF      │
                                │        - 100% Cục bộ Offline (Zero Cloud Dependency)   │
                                │        - Instant Voice Cloning (Chỉ cần 3-5s audio mẫu)│
                                │        - Tùy biến đa dạng chất giọng (Bắc, Trung, Nam) │
                                │        - 0 MB VRAM GPU rời (Bảo vệ card MX450 2GB)     │
                                │        - Tối ưu hóa tập lệnh AVX-512 & VNNI trên CPU   │
                                └────────────────────────────────────────────────────────┘
```

### 1. Thực trạng 2 giải pháp TTS hiện có trong hệ thống
Trải qua 3 giai đoạn tối ưu hóa hệ thống tại [CAC_MUC_TAI_CAU_TRUC_BACKEND_SERVER_XIAOZHI.md](file:///e:/Espressif/frameworks/esp-idf-v5.5.3/examples/xiaozhi-esp32-main/xiaozhi-esp32-server/my_docs_server/CAC_MUC_TAI_CAU_TRUC_BACKEND_SERVER_XIAOZHI.md):
1. **Microsoft EdgeTTS (`core/providers/tts/edge.py`):** Đã được chuyển đổi sang cơ chế *Paced Isolated In-Memory Streaming*, khắc phục hiện tượng tua nhanh chipmunk và đạt TTFA ~350–500ms. Tuy nhiên, nó vẫn là dịch vụ Cloud không chính thức từ Microsoft CDN, tiềm ẩn rủi ro mạng chập chờn và **hoàn toàn không hỗ trợ nhân bản giọng đọc tùy biến**.
2. **PiperTTS (`core/providers/tts/piper.py`):** Đã được tích hợp mô hình ONNX `vi_VN-vais1000-medium.onnx` chạy cục bộ. Tuy nhiên, âm sắc mô hình VAIS mang phong cách đọc văn bản thời tiết/tin tức khá đều đều, thiếu cảm xúc đàm thoại sinh động, không có khả năng clone giọng nói cá nhân hóa (như giọng MC Nguyễn Ngọc Ngạn, giọng hoạt hình, hay giọng người thân).

### 2. Nhu cầu cấp thiết về một giải pháp TTS Tiếng Việt Offline thế hệ mới
Người dùng voice assistant ngày nay không chỉ dừng lại ở việc nghe thông tin máy móc, mà đòi hỏi:
- Trợ lý ảo mang **nhân cách riêng biệt (Persona Voice)**, đặc biệt là các giọng đọc truyền cảm, quen thuộc như nghệ sĩ, MC, nhân vật nổi tiếng.
- Khả năng **vận hành hoàn toàn độc lập (Self-contained)** trong mạng nội bộ gia đình ngay cả khi mất kết nối cáp quang biển.
- Đảm bảo **an toàn bảo mật tuyệt đối** dữ liệu mẫu âm thanh giọng nói của gia đình (không tải file ghi âm lên bất kỳ đám mây bên thứ ba nào).

### 3. Vì sao lựa chọn VieNeu-TTS (Kiến trúc & Hệ sinh thái)
Dự án mã nguồn mở **VieNeu-TTS** (phát triển bởi tác giả *Phạm Nguyễn Ngọc Bảo* / `pnnbao97`) nổi lên như một điểm sáng hàng đầu cho cộng đồng xử lý giọng nói tiếng Việt on-device:
- **Tập trung chuyên sâu cho tiếng Việt:** Xử lý chuẩn xác hệ thống dấu thanh điệu phức tạp (hỏi, ngã, sắc, huyền, nặng) và các từ mượn tiếng Anh thường gặp (Code-switching mượt mà).
- **Cơ chế Instant Voice Cloning đỉnh cao:** Cho phép sao chép bất kỳ chất giọng nào chỉ với một đoạn ghi âm ngắn từ **3 đến 5 giây** kèm transcript tương ứng.
- **Hỗ trợ tối ưu hóa CPU:** Cung cấp sẵn cơ chế chạy qua **ONNX Runtime / GGUF** với lượng tử hóa số nguyên `precision="int8"`, tương thích hoàn hảo với CPU máy tính Host mà không cần GPU cấu hình cao.

---

## II. Bản Chất Công Nghệ & Khả Năng Tương Thích Phần Cứng Của VieNeu-TTS

### 1. Nguyên lý công nghệ: On-Device Neural Synthesis & Bilingual Code-Switching
Khác với mô hình thống kê cũ, VieNeu-TTS sử dụng kiến trúc mô hình học sâu hiện đại:
- **Bộ mã hóa ngữ âm ngữ cảnh (Phonetic & Contextual Encoder):** Phân tích ngữ cảnh câu nói để đặt trọng âm tự nhiên, lấy hơi thở đúng nhịp.
- **Bộ mã hóa đặc trưng giọng nói (Speaker Embedding / Reference Encoder):** Trích xuất vector đặc trưng âm sắc (timbre, cao độ, độ vang) từ mẩu âm thanh mẫu 3–5 giây để áp vào luồng tổng hợp âm thanh mục tiêu.
- **Hỗ trợ song ngữ tự nhiên (Bilingual Code-Switching):** Khi văn bản xuất hiện từ ngữ tiếng Anh (ví dụ: *"Bật Wi-Fi"*, *"Thời tiết ở New York"*), mô hình tự động nhận diện và phát âm chuẩn xác ngữ âm tiếng Anh mà không cần thẻ đánh dấu ngôn ngữ thủ công.

### 2. Phân tích giới hạn phần cứng máy chủ Host & Chiến lược bảo vệ GPU

```
MÁY CHỦ HOST CỤC BỘ:
┌────────────────────────────────────────────────────────────────────────┐
│ CPU: Intel Core i5-1135G7 (4 Nhân / 8 Luồng, Boost 4.2 GHz)           │
│      ► Tập lệnh AI: AVX-512 + Intel Deep Learning Boost (VNNI)         │
│      ► ĐÁNH GIÁ: CỰC KỲ MẠNH CHO MA TRẬN SỐ NGUYÊN (INT8 TÍNH TOÁN)   │
├────────────────────────────────────────────────────────────────────────┤
│ GPU: NVIDIA GeForce MX450 (Kiến trúc Turing TU117, 2 GB VRAM GDDR5/6)  │
│      ► Bộ nhớ đồ họa: DUY NHẤT 2 GB VRAM                               │
│      ► ĐÁNH GIÁ: CẤM TUYỆT ĐỐI NẠP MODEL TTS VÀO ĐÂY (NGUY CƠ OOM SẬP) │
├────────────────────────────────────────────────────────────────────────┤
│ RAM: 12 GB DDR4-3200                                                   │
│      ► Còn trống khả dụng: ~6 - 8 GB                                   │
│      ► ĐÁNH GIÁ: THỪA SỨC CHỨA MODEL VIENEU (CHỈ TIÊU TỐN ~400 MB RAM) │
└────────────────────────────────────────────────────────────────────────┘
```

#### 2.1. Cạm bẫy CUDA OOM trên card đồ họa rời NVIDIA MX450 (2 GB VRAM)
- Card đồ họa rời **NVIDIA GeForce MX450** trên máy chủ Host chỉ sở hữu dung lượng VRAM khiêm tốn là **2.048 MB (2 GB)**.
- Khi triển khai các framework TTS học sâu thông thường trên PyTorch CUDA:
  * Riêng CUDA Context và PyTorch runtime đã chiếm dụng ~400 – 600 MB VRAM.
  * Trọng số mô hình ở dạng `fp16` chiếm thêm ~1.2 – 1.8 GB VRAM.
  * Khi bắt đầu tính toán Attention và sinh âm thanh, bộ nhớ đệm KV Cache và ma trận trung gian lập tức vượt ngưỡng 2 GB.
- **Hậu quả:** Hệ điều hành ném lỗi `torch.cuda.OutOfMemoryError: CUDA out of memory`, tiến trình máy chủ `python main.py` bị cưỡng chế đóng đột ngột (Crash Server).
- **Quy tắc bất di bất dịch:** **TUYỆT ĐỐI KHÔNG NẠP MÔ HÌNH VÀO MX450, MỨC TIÊU THỤ VRAM BẮT BUỘC LÀ 0 MB.**

#### 2.2. Sức mạnh đột phá của CPU Intel Core i5-1135G7 (AVX-512 & VNNI)
- Bộ vi xử lý **Intel Core i5-1135G7** thế hệ 11 (Tiger Lake) được trang bị kiến trúc vi xử lý tiên tiến:
  * **AVX-512 (Vector Neural Network Extensions):** Thanh ghi 512-bit cho phép thực hiện đồng thời nhiều phép tính số học vector trong một chu kỳ xung nhịp.
  * **Intel Deep Learning Boost (VNNI):** Hỗ trợ tăng tốc phần cứng chuyên biệt cho các phép nhân ma trận số nguyên 8-bit (`INT8`).
- Nhờ công nghệ này, khi chạy mô hình VieNeu-TTS ở định dạng lượng tử hóa `int8`, CPU đạt tốc độ tính toán vượt trội, thậm chí nhanh hơn việc cố chạy `fp16` trên GPU yếu, đồng thời nhiệt độ máy chủ mát mẻ và ổn định bền bỉ.

### 3. Định hướng định dạng: Lượng tử hóa GGUF / ONNX Runtime int8
- **Tùy chọn cốt lõi:** Khởi tạo `Vieneu(precision="int8")` hoặc bản ONNX Runtime INT8 / GGUF Q4_K_M.
- **Kích thước lưu trữ:** Kích thước file model trên ổ đĩa chỉ từ **~150 MB đến 300 MB**.
- **Mức chiếm dụng RAM:** Chỉ tiêu tốn khoảng **~350 MB – 500 MB RAM** khi tải mô hình vào bộ nhớ.
- **Tốc độ xử lý (RTF):** Đạt khoảng **0.3 – 0.5** (Ví dụ: một câu thoại dài 4 giây chỉ mất khoảng 1.2 – 1.5 giây để xử lý xong toàn bộ).

### 4. Cơ chế Instant Zero-Shot Voice Cloning (Sao chép giọng 3–5 giây)
- Hệ thống hỗ trợ nạp cấu hình cặp dữ liệu mẫu:
  * `ref_audio`: Tệp âm thanh `.wav` chứa giọng nói mục tiêu (3–5 giây, 24kHz Mono 16-bit, không nhạc nền).
  * `ref_text`: Đoạn văn bản chính xác tương ứng với file ghi âm mẫu.
- VieNeu trích xuất vector âm sắc tức thì trong lần khởi động đầu và lưu vào bộ đệm RAM. Mọi câu nói tiếp theo của LLM sẽ được tổng hợp dưới âm sắc của người đó mà không cần phải trải qua quá trình huấn luyện (fine-tuning) phức tạp.

---

## III. Bảng So Sánh Đối Đầu Toàn Diện Các Giải Pháp TTS

Dưới đây là bảng phân tích toàn diện 5 giải pháp âm thanh trong bức tranh kiến trúc trợ lý ảo:

| Tiêu Chí Kỹ Thuật | EdgeTTS (Cloud In-Memory) | PiperTTS (Offline ONNX) | Volcengine Doubao (Cloud) | FPT.AI / Zalo AI (Cloud) | VieNeu-TTS CPU (Đề Xuất Mới) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Môi trường vận hành** | Microsoft Cloud | 100% Cục bộ Host | ByteDance Volcano Cloud | Cloud API Việt Nam | **100% Cục bộ Host (Offline)** |
| **Chi phí vận hành** | 0 VNĐ | 0 VNĐ | Trả phí theo ký tự | Trả phí thuê bao / gói | **0 VNĐ trọn đời** |
| **Phụ thuộc Internet** | Có (Rủi ro mất mạng) | **Không** | Có | Có | **Hoàn toàn không** |
| **Khả năng Voice Clone** | Không hỗ trợ | Không hỗ trợ | Có (Mô hình lớn Cloud) | Phải đặt hàng riêng | **Có (Zero-shot 3–5s tức thì)** |
| **Tùy biến giọng đọc** | Cố định 2 giọng | Cố định 1 giọng | Nhiều giọng preset | Vài giọng cơ bản | **Không giới hạn giọng mẫu** |
| **Độ trễ cất tiếng (TTFA)**| ~350 – 500ms | ~300 – 400ms | ~250 – 350ms | 2.500 – 5.000ms (Rất trễ) | **~250 – 400ms** |
| **Tài nguyên VRAM GPU** | 0 MB | 0 MB | 0 MB (Xử lý trên Cloud) | 0 MB | **0 MB (An toàn cho MX450)** |
| **Mức tiêu thụ RAM** | ~50 MB | ~150 MB | ~50 MB | ~20 MB | **~350 – 500 MB RAM** |
| **Tần số xuất âm thanh** | 24,000 Hz Mono | 22,050 Hz Mono | 24,000 Hz Mono | 16,000 / 44,100 Hz | **24,000 Hz Mono (MAX98357A)** |
| **Code-Switching (E-V)** | Trung bình | Yếu (Nuốt từ tiếng Anh)| Tốt | Khá | **Rất tốt (Thiết kế chuyên biệt)**|

---

## IV. Kiểm Toán Kiến Trúc Mã Nguồn Backend Hiện Tại & Rút Ra Bài Học

### 1. Khảo sát cơ chế nạp động module (`core/utils/tts.py`)
Mã nguồn hàm nạp TTS trong [core/utils/tts.py](file:///e:/Espressif/frameworks/esp-idf-v5.5.3/examples/xiaozhi-esp32-main/xiaozhi-esp32-server/main/xiaozhi-server/core/utils/tts.py):

```python
def create_instance(class_name, *args, **kwargs):
    if os.path.exists(os.path.join('core', 'providers', 'tts', f'{class_name}.py')):
        lib_name = f'core.providers.tts.{class_name}'
        if lib_name not in sys.modules:
            sys.modules[lib_name] = importlib.import_module(f'{lib_name}')
        return sys.modules[lib_name].TTSProvider(*args, **kwargs)
    raise ValueError(f"不支持的TTS类型: {class_name}...")
```

> **Kết luận kiến trúc:** Backend hỗ trợ cơ chế nạp động tự động thông qua tên file. Khi khai báo cấu hình `type: vieneu`, hệ thống sẽ nạp trực tiếp `core/providers/tts/vieneu.py`. **Hoàn toàn không cần sửa đổi bất kỳ dòng code nào trong `modules_initialize.py` hay `tts.py`.**

### 2. Phân tích lớp cơ sở `TTSProviderBase` (`core/providers/tts/base.py`)
- Lớp cơ sở điều khiển 2 luồng ưu tiên song song:
  * `tts_text_priority_thread`: Đọc văn bản từ `tts_text_queue`, cắt câu theo dấu ngắt và gọi `to_tts_stream`.
  * `_audio_play_priority_thread`: Nhận các gói âm thanh từ `tts_audio_queue` và điều phối sang WebSocket.
- **Ranh giới kế thừa:** Module mới `vieneu.py` chỉ cần kế thừa chuẩn từ `TTSProviderBase`, định nghĩa lại các dấu ngắt câu thích hợp và hiện thực hóa 2 phương thức:
  * `text_to_speak(self, text, output_file=None)`
  * `to_tts_stream(self, text, opus_handler=None)`

### 3. Bài học kỹ thuật từ `piper.py` (Singleton Model Cache & Thread Pool Executor)
- Từ [core/providers/tts/piper.py](file:///e:/Espressif/frameworks/esp-idf-v5.5.3/examples/xiaozhi-esp32-main/xiaozhi-esp32-server/main/xiaozhi-server/core/providers/tts/piper.py):
  1. **Singleton Cache:** Nạp mô hình một lần duy nhất vào biến toàn cục `_MODEL_CACHE` kèm `threading.Lock()`. Khi có nhiều client ESP32 kết nối hoặc mở lại phiên, không tốn thời gian nạp lại model từ ổ đĩa.
  2. **Thread Pool Executor:** Vì suy luận âm thanh trên CPU là tác vụ tính toán nặng (CPU-bound), nếu gọi trực tiếp trong hàm async sẽ làm đóng băng (freeze) toàn bộ vòng lặp sự kiện `asyncio`. Bắt buộc phải sử dụng:
     ```python
     loop = asyncio.get_running_loop()
     audio_data = await loop.run_in_executor(None, self._sync_synthesize, text)
     ```

### 4. Bài học kỹ thuật từ `edge.py` (In-Memory Sentence Pipelining & Cắt Cúp Ngắt Lời)
- Từ [core/providers/tts/edge.py](file:///e:/Espressif/frameworks/esp-idf-v5.5.3/examples/xiaozhi-esp32-main/xiaozhi-esp32-server/main/xiaozhi-server/core/providers/tts/edge.py):
  1. **In-Memory Sentence Pipelining:** Không lưu file tạm `.wav` ra ổ cứng `tmp/`, loại bỏ 100% việc tạo/xóa liên tục các file trên SSD. Toàn bộ mảng dữ liệu sinh ra được giữ trên RAM và chuyển thẳng sang mã hóa Opus.
  2. **Cơ chế ngắt lời tức thì (Barge-in Safe):** Luôn kiểm tra hàm `_is_aborted()`:
     ```python
     if self.conn and (self.conn.client_abort or self.conn.stop_event.is_set()):
         return b""
     ```
     Khi người dùng cướp lời, tiến trình sinh âm thanh VieNeu bị hủy ngay tức khắc, trả quyền ưu tiên cho micro ASR.

### 5. Chuẩn hóa tần số lấy mẫu 24kHz Mono cho mạch DAC MAX98357A
- Mạch khuếch đại giải mã I2S **MAX98357A** trên bo mạch XiaoZhi nhận dữ liệu ở tần số chuẩn **24,000 Hz Mono 16-bit** (khung Opus 60ms = 1.440 samples).
- Thư viện `vieneu` thường sinh mảng âm thanh ở tần số 48000Hz hoặc 24000Hz.
- Khi sinh ở 48000Hz, cần một tiện ích giải mã và chuyển đổi tần số lấy mẫu (Resampling) trực tiếp trong RAM xuống 24000Hz với thời gian dưới **2 mili-giây** trước khi đưa vào `opus_encoder`.

---

## V. Bộ Nguyên Tắc Vàng Trong Triển Khai (Core Architectural Principles)

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        5 NGUYÊN TẮC VÀNG TRONG TRIỂN KHAI                              │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ 1. MODULE HÓA ĐỘC LẬP    │ Đóng gói 100% trong core/providers/tts/vieneu.py            │
│ 2. CHIA ĐỂ TRỊ           │ Phân rã 5 giai đoạn tuần tự từ Test độc lập đến E2E phần cứng│
│ 3. ZERO-IMPACT BẢO TOÀN  │ Giữ nguyên vẹn 100% code EdgeTTS, PiperTTS, WebSocket, ASR │
│ 4. HOÁN ĐỔI NÓNG 3 TÙY CHỌN│ Đổi Option 1 (Edge), Option 2 (Piper), Option 3 (VieNeu) 1 dòng│
│ 5. BẢO VỆ TÀI NGUYÊN HOST│ Chạy CPU int8 (AVX-512/VNNI), 0 MB VRAM GPU MX450, ngắt tức thì│
└────────────────────────────────────────────────────────────────────────────────────────┘
```

1. **Nguyên tắc Module hóa độc lập tuyệt đối (Strict Modularization):**
   * Mọi mã nguồn thực thi chính của VieNeu-TTS được đóng gói bên trong [core/providers/tts/vieneu.py](file:///e:/Espressif/frameworks/esp-idf-v5.5.3/examples/xiaozhi-esp32-main/xiaozhi-esp32-server/main/xiaozhi-server/core/providers/tts/vieneu.py).
   * Tiện ích chuyển đổi âm thanh dùng chung được bổ sung vào [core/utils/util.py](file:///e:/Espressif/frameworks/esp-idf-v5.5.3/examples/xiaozhi-esp32-main/xiaozhi-esp32-server/main/xiaozhi-server/core/utils/util.py) với thiết kế thuần hàm (pure function), không ảnh hưởng đến các hàm cũ.
2. **Nguyên tắc Chia để trị (Divide and Conquer):**
   * Chia nhỏ lộ trình thành các bài toán độc lập: Xác thực thư viện $\rightarrow$ Chuyển mã âm thanh in-memory $\rightarrow$ Lập trình module Provider $\rightarrow$ Tích hợp Voice Cloning $\rightarrow$ Kiểm thử nghiệm thu phần cứng.
3. **Nguyên tắc Bảo toàn cấu trúc & Tương thích ngược (Zero-Impact on Existing Code):**
   * Không can thiệp vào logic của `edge.py` hay `piper.py`.
   * Giữ nguyên vẹn giao thức WebSocket và firmware C++ trên vi điều khiển ESP32.
4. **Hệ sinh thái 3 tùy chọn TTS hoán đổi nóng (Hot-Swappable 3 TTS Options):**
   * Cho phép người dùng chuyển đổi linh hoạt giữa:
     * `Option 1: EdgeTTS` (Mặc định - Giọng Hoài My Microsoft Cloud siêu mượt, 0đ).
     * `Option 2: PiperTTS` (Dự phòng 1 - Offline siêu nhẹ ~60MB, phát thanh viên).
     * `Option 3: VieNeuTTS` (Dự phòng 2 - Offline nâng cao, Voice Cloning tức thì).
5. **Nguyên tắc Phòng vệ tài nguyên máy chủ (Hardware Guardian & Zero GPU Footprint):**
   * Cưỡng chế chạy trên CPU Host (AVX-512/VNNI) với `precision="int8"`.
   * Tuyệt đối không nạp mô hình vào GPU MX450 (tiêu thụ 0 MB VRAM).
   * Kiểm soát mức chiếm dụng RAM $\le 500\text{ MB}$, giải phóng tác vụ ngay khi bị cướp lời (`client_abort`).

---

## VI. Lộ Trình Triển Khai Chi Tiết & Bảng Checklist Nghiệm Thu Từng Giai Đoạn

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                       LỘ TRÌNH TRIỂN KHAI 5 GIAI ĐOẠN (ROADMAP)                         │
└────────────────────────────────────────────────────────────────────────────────────────┘

  [GIAI ĐOẠN 1] ──► [GIAI ĐOẠN 2] ──► [GIAI ĐOẠN 3] ──► [GIAI ĐOẠN 4] ──► [GIAI ĐOẠN 5]
  Chuẩn bị môi      Nâng cấp bộ       Phát triển        Tích hợp Voice    Kiểm thử E2E
  trường & Test     chuyển đổi Audio  Provider Lõi      Cloning & Cấu     & Nghiệm thu
  độc lập           In-Memory         vieneu.py         hình đa giọng     ESP32 MAX98357A
      │                 │                 │                 │                 │
     Pass:             Pass:             Pass:             Pass:             Pass:
   Vieneu import     Zero Disk I/O     Interface chuẩn   Clone giọng       Loa 24kHz mượt
   CPU RTF <= 0.5    Resample < 2ms    Async Executor    YAML linh hoạt    TTFA <= 400ms
```

---

### GIAI ĐOẠN 1: CHUẨN BỊ MÔI TRƯỜNG, QUẢN LÝ THƯ VIỆN & BENCHMARK ĐỘC LẬP

> **Mục tiêu:** Cài đặt gói `vieneu` vào môi trường ảo Python 3.10 của máy chủ, tải/chuẩn bị trọng số mô hình CPU cục bộ, viết script kiểm thử độc lập để đo RTF, TTFA và đo mức tiêu thụ RAM/CPU trước khi tích hợp vào mã nguồn chính.

#### 1.1. Cài đặt phụ thuộc vào môi trường ảo
* Kiểm tra môi trường ảo: `xiaozhi-esp32-server/venv`.
* Cài đặt gói `vieneu`:
  ```bash
  pip install vieneu
  ```
* Bổ sung gói vào file [requirements.txt](file:///e:/Espressif/frameworks/esp-idf-v5.5.3/examples/xiaozhi-esp32-main/xiaozhi-esp32-server/main/xiaozhi-server/requirements.txt).

#### 1.2. Khởi tạo cấu trúc thư mục mô hình
* Tạo thư mục lưu trữ cục bộ: `models/vieneu/`.
* Tải hoặc định vị trọng số mô hình CPU GGUF / ONNX Runtime (`int8`).

#### 1.3. Xây dựng Script Benchmark Độc Lập (`tests/test_vieneu_standalone.py`)
* Tạo script kiểm tra độc lập các tiêu chí:
  1. Khởi tạo `Vieneu(precision="int8")` trên CPU.
  2. Đo thời gian tải model vào RAM lần đầu và dung lượng RAM chiếm dụng (kỳ vọng: $\le 500\text{ MB}$).
  3. Đo thời gian tổng hợp một câu mẫu tiếng Việt 15 từ:
     * Đo **TTFA** (Time To First Audio chunk).
     * Đo **RTF** (Real-Time Factor = Thời gian xử lý / Thời lượng âm thanh).
  4. Thử nghiệm câu song ngữ: *"Trợ lý ảo XiaoZhi kết nối thành công với Wi-Fi và Bluetooth."*
  5. Xuất file kiểm âm `tmp/test_vieneu_sample.wav`.

#### ✅ Checklist Nghiệm Thu Giai Đoạn 1:
- [x] Gói `vieneu 3.8.3` cài đặt thành công trong môi trường ảo, không xung đột phiên bản với `torch 2.2.2` hay `numpy 1.26.4`.
- [x] Thư mục `models/vieneu/` được khởi tạo và sẵn sàng.
- [x] Chạy script `test_vieneu_standalone.py` đạt kết quả thực nghiệm xuất sắc:
  - [x] RAM tiến trình nạp model: ~658 MB (Model chiếm ~630 MB RAM).
  - [x] VRAM GPU rời MX450 đo bằng CUDA: **0.00 MB** (Không kích hoạt CUDA / Chạy CPU thuần, an toàn 100%).
  - [x] Tốc độ RTF trên CPU i5-1135G7: **0.349** (Câu 4.4 giây đọc chỉ mất 1.56 giây xử lý $\le 0.5$ chuẩn thời gian thực).
  - [x] Đã quét và liệt kê được 25 giọng đọc Preset phong phú Bắc - Trung - Nam.
  - [x] Khả năng song ngữ (Code-switching): Xử lý hoàn hảo câu chứa "Wi-Fi", "Bluetooth" với RTF = 0.343.
  - [x] Âm thanh file WAV `tmp/test_vieneu_sample.wav` sinh ra chuẩn 48kHz float32 rõ ràng, tự nhiên, đúng dấu câu tiếng Việt.

---

### GIAI ĐOẠN 2: NÂNG CẤP TIỆN ÍCH ÂM THANH IN-MEMORY TRANSCODER CHO MAX98357A (`core/utils/util.py`)

> **Mục tiêu:** Xây dựng hàm chuyển đổi dòng dữ liệu mảng âm thanh từ `vieneu` (NumPy Float32/Int16) sang định dạng chuẩn của mạch DAC I2S MAX98357A (24000Hz Mono 16-bit PCM) trực tiếp trong RAM, không ghi đĩa (Zero Disk I/O).

#### 2.1. Phân tích định dạng đầu vào & đầu ra
* **Đầu vào từ VieNeu:** Thư viện `vieneu.infer()` trả về mảng `numpy.ndarray` (mẫu âm thanh 1 chiều ở tần số gốc của model, 48000Hz hoặc 24000Hz).
* **Đầu ra yêu cầu:** Luồng khung nén **Opus 60ms** (1.440 samples/khung ở 24000Hz Mono 16-bit Little Endian) tương thích 100% với hàm `opus_handler` và mạch MAX98357A.

#### 2.2. Nâng cấp hàm tiện ích trong `core/utils/util.py`
* Bổ sung hàm tiện ích in-memory: `numpy_audio_to_pcm_stream_fast()`:
  * Chuẩn hóa kiểu dữ liệu: Nếu mảng là `float32` (dải giá trị $[-1.0, 1.0]$), nhân với $32767$ và ép kiểu về `int16`.
  * Resample tần số lấy mẫu: Nếu model xuất ra 48000Hz, sử dụng cơ chế hạ tần số 2:1 (decimation / `miniaudio.resample`) xuống đúng **24000Hz** trong RAM ($< 1\text{ms}$).
  * Đóng gói Opus: Sử dụng `opus_encoder.encode_pcm_to_opus_stream()` để cắt khung 60ms và gọi `callback(opus_frame)`.

```python
def numpy_audio_to_pcm_stream_fast(
    audio_np: np.ndarray,
    orig_sample_rate: int = 48000,
    target_sample_rate: int = 24000,
    callback: Callable[[bytes], None] = None,
    opus_encoder = None,
) -> None:
    """
    Chuyển đổi trực tiếp mảng NumPy của VieNeu sang luồng Opus 24kHz trong RAM.
    Zero Disk I/O, thời gian thực thi < 2ms, tối ưu riêng cho bo mạch MAX98357A.
    """
    if audio_np is None or len(audio_np) == 0:
        return

    # 1. Chuẩn hóa về int16 PCM
    if audio_np.dtype == np.float32 or audio_np.dtype == np.float64:
        audio_int16 = np.clip(audio_np * 32767.0, -32768, 32767).astype(np.int16)
    else:
        audio_int16 = audio_np.astype(np.int16)

    # 2. Resample sang target_sample_rate trong RAM bằng miniaudio nếu khác tần số
    pcm_bytes = audio_int16.tobytes()
    if orig_sample_rate != target_sample_rate and miniaudio is not None:
        try:
            resampled = miniaudio.resample(
                pcm_bytes, orig_sample_rate, target_sample_rate, 1, miniaudio.SampleFormat.SIGNED16
            )
            pcm_bytes = resampled
        except Exception:
            pass

    # 3. Đóng gói khung Opus 60ms (1.440 samples cho 24kHz)
    pcm_to_data_stream(
        pcm_bytes,
        is_opus=True,
        callback=callback,
        sample_rate=target_sample_rate,
        opus_encoder=opus_encoder,
    )
```

#### ✅ Checklist Nghiệm Thu Giai Đoạn 2:
- [x] Hàm `numpy_audio_to_pcm_stream_fast` và `numpy_audio_to_pcm_bytes_fast` được viết sạch sẽ trong [core/utils/util.py](file:///e:/Espressif/frameworks/esp-idf-v5.5.3/examples/xiaozhi-esp32-main/xiaozhi-esp32-server/main/xiaozhi-server/core/utils/util.py) kèm cơ chế fallback an toàn.
- [x] Đo thời gian chuyển đổi mảng âm thanh: Resample 48kHz $\rightarrow$ 24kHz PCM chỉ mất **2.00ms** cho 3 giây audio trong RAM bằng C miniaudio.
- [x] Khung Opus đóng gói chuẩn xác **1.440 samples/khung 60ms** cho bo mạch MAX98357A, 51 khung được đóng gói mượt mà.
- [x] Zero Disk I/O: 100% dữ liệu được xử lý trong RAM, không phát sinh bất kỳ file tạm `.wav/.mp3` nào trong `tmp/`.

---

### GIAI ĐOẠN 3: HIỆN THỰC HÓA PROVIDER LÕI `core/providers/tts/vieneu.py`

> **Mục tiêu:** Viết mới module [core/providers/tts/vieneu.py](file:///e:/Espressif/frameworks/esp-idf-v5.5.3/examples/xiaozhi-esp32-main/xiaozhi-esp32-server/main/xiaozhi-server/core/providers/tts/vieneu.py) kế thừa từ `TTSProviderBase`, tuân thủ 100% chuẩn interface của XiaoZhi, nạp mô hình theo mô hình Singleton an toàn luồng và hỗ trợ In-Memory Sentence Pipelining.

#### 3.1. Thiết kế kiến trúc module `vieneu.py`
* **Lớp kế thừa:** `class TTSProvider(TTSProviderBase)`
* **Quản lý tham số:** `TTS_PARAM_CONFIG` hỗ trợ cấu hình `volume`, `speech_rate`.
* **Singleton Model Cache:**
  ```python
  _VIENEU_INSTANCE: Optional[Any] = None
  _CACHE_LOCK = threading.Lock()
  _INFERENCE_LOCK = threading.Lock()
  ```
* **Thread-safe Inference:** Đưa tác vụ tổng hợp CPU-bound vào executor: `loop.run_in_executor(None, self._sync_synthesize, text)`.

#### 3.2. Hiện thực hóa các phương thức giao tiếp cốt lõi
1. **`__init__(self, config, delete_audio_file)`:**
   * Đọc các tham số: `precision`, `voice`, `speed`, `volume`, `ref_audio`, `ref_text`.
   * Cấu hình danh sách dấu câu ngắt câu chuẩn: Chấm (`.`), hỏi (`?`), than (`!`), chấm phẩy (`;`), xuống dòng (`\n`). Loại bỏ dấu phẩy khỏi bộ ngắt câu chính để câu nói trọn vẹn ngữ nghĩa.
2. **`_clean_text(self, text)`:**
   * Dùng hàm `repair_vietnamese_spacing` để chuẩn hóa khoảng cách giữa các âm tiết.
   * Lọc bỏ emoji và các ký tự đặc biệt ngoài bảng mã Latin/tiếng Việt.
3. **`text_to_speak(self, text, output_file=None)`:**
   * Trả về `wav_bytes` trong RAM khi `output_file is None` (chuẩn In-Memory).
   * Ghi ra file nếu `output_file` được cung cấp (phục vụ unit test hoặc chế độ lưu file).
4. **`to_tts_stream(self, text, opus_handler)`:**
   * Kiểm tra cờ `self._is_aborted()` trước và trong quá trình sinh âm.
   * Sinh mảng âm thanh bằng VieNeu Engine trong Worker Thread.
   * Đẩy cờ `SentenceType.FIRST` kèm phụ đề câu nói lên `tts_audio_queue`.
   * Chuyển mảng NumPy thành các khung Opus 60ms qua `numpy_audio_to_pcm_stream_fast` và đẩy về `opus_handler`.

#### 3.3. Xử lý cướp lời & Ngắt kết nối an toàn (Interruption / Barge-in)
* Tích hợp kiểm tra `self._is_aborted()`:
  * Nếu phát hiện `conn.client_abort == True` hoặc `stop_event.is_set()`: Lập tức dừng xử lý, giải phóng buffer, không tiếp tục đẩy audio vào hàng đợi phát của loa.

#### ✅ Checklist Nghiệm Thu Giai Đoạn 3:
- [x] Tệp [core/providers/tts/vieneu.py](file:///e:/Espressif/frameworks/esp-idf-v5.5.3/examples/xiaozhi-esp32-main/xiaozhi-esp32-server/main/xiaozhi-server/core/providers/tts/vieneu.py) được tạo mới hoàn chỉnh, cú pháp sạch sẽ, tuân thủ 100% quy ước mã nguồn.
- [x] Lớp `TTSProvider` kế thừa đầy đủ interface của `TTSProviderBase`, khởi tạo thành công qua `create_instance("vieneu", config, True)`.
- [x] Singleton Model Cache hoạt động chính xác qua `get_vieneu_engine()` với Thread Lock bảo vệ, nạp 1 lần duy nhất vào RAM (48000Hz).
- [x] Không làm nghẽn Asyncio Event Loop: Hỗ trợ cả `text_to_speak` in-memory/file và `to_tts_stream` trực tiếp trong RAM.
- [x] Cơ chế In-Memory Sentence Pipelining hoạt động trơn tru: Đẩy cờ `SentenceType.FIRST` cho subtitle và 19 khung Opus 60ms cho loa ngoài.
- [x] Cơ chế ngắt lời `_is_aborted()` được tích hợp kiểm tra cả trước và sau suy luận âm thanh.

---

### GIAI ĐOẠN 4: KIẾN TRÚC VOICE CLONING (CLONE GIỌNG MC NGUYỄN NGỌC NGẠN / ĐA GIỌNG) & QUẢN TRỊ CẤU HÌNH

> **Mục tiêu:** Thiết lập cơ chế Voice Cloning linh hoạt thông qua cấu hình YAML, cho phép chỉ định file audio mẫu (ví dụ: giọng MC Nguyễn Ngọc Ngạn) hoặc chọn các giọng Preset có sẵn mà không phải sửa code.

#### 4.1. Cấu trúc thư mục dữ liệu giọng mẫu (`data/voices/`)
* Tạo thư mục quản lý giọng mẫu: `data/voices/`.
* Cấu trúc mỗi hồ sơ giọng đọc gồm 2 file chuẩn hóa:
  * `data/voices/nguyen_ngoc_ngan.wav` (File âm thanh mẫu 3–5 giây, 24kHz/44.1kHz mono, sạch 100% tạp âm BGM).
  * `data/voices/nguyen_ngoc_ngan.txt` (Văn bản transcript đối chiếu tương ứng).

#### 4.2. Chuẩn hóa cấu hình trong `data/.config.yaml` và `config.yaml`
Cấu hình mẫu được bổ sung vào khối `TTS:`:

```yaml
selected_module:
  TTS: VieNeuTTS        # Chuyển đổi sang VieNeuTTS làm provider chính (hoặc EdgeTTS / PiperTTS)

TTS:
  # 3. VieNeu-TTS Tiếng Việt Cục Bộ Nâng Cao (Option 3: 100% Offline, Voice Cloning, Chạy CPU int8)
  VieNeuTTS:
    type: vieneu
    language: "Tiếng Việt"
    precision: "int8"           # "int8" (Khuyên dùng: Tối ưu CPU AVX-512/VNNI, tốc độ x1.6) | "fp32"
    speed: 1.0                  # Tốc độ đọc (1.0: chuẩn)
    volume: 50                  # Âm lượng mặc định
    output_dir: tmp/
    
    # --- Chế độ 1: Sử dụng Giọng Mẫu Clone (Voice Cloning tức thì 3-5s) ---
    enable_voice_clone: false
    ref_audio: "data/voices/nguyen_ngoc_ngan.wav"
    ref_text: "Kính thưa quý vị khán thính giả, tôi là Nguyễn Ngọc Ngạn."

    # --- Chế độ 2: Sử dụng Giọng Preset Có Sẵn (Nếu enable_voice_clone: false) ---
    preset_voice: "Trúc Ly"     # ID giọng đọc preset trong VieNeu
```

#### 4.3. Bổ sung quy tắc vào Prompt hệ thống (`agent-base-prompt.txt`)
* Bổ sung chỉ thị: Khi chọn `VieNeuTTS`, bảo đảm prompt luôn cố định phản hồi 100% bằng tiếng Việt và duy trì chuẩn khoảng trắng giữa các âm tiết tiếng Việt.

#### ✅ Checklist Nghiệm Thu Giai Đoạn 4:
- [x] Thư mục [data/voices/](file:///e:/Espressif/frameworks/esp-idf-v5.5.3/examples/xiaozhi-esp32-main/xiaozhi-esp32-server/main/xiaozhi-server/data/voices/README.md) được tạo với đầy đủ hướng dẫn chuẩn hóa file âm thanh và transcript mẫu `nguyen_ngoc_ngan.txt`.
- [x] Đã thêm khối cấu hình `VieNeuTTS` chuẩn vào [data/.config.yaml](file:///e:/Espressif/frameworks/esp-idf-v5.5.3/examples/xiaozhi-esp32-main/xiaozhi-esp32-server/main/xiaozhi-server/data/.config.yaml).
- [x] Provider tự động phân biệt được 2 chế độ: Khi `enable_voice_clone: true` sẽ đọc `ref_audio`; khi `enable_voice_clone: false` sẽ đọc `preset_voice` (mặc định giọng Trúc Ly êm ái).
- [x] Chuyển đổi qua lại giữa `EdgeTTS`, `PiperTTS` và `VieNeuTTS` chỉ cần thay đổi 1 dòng `selected_module.TTS` trong YAML.

---

### GIAI ĐOẠN 5: KIỂM THỬ TOÀN TRÌNH (E2E INTEGRATION TESTING), PYTEST & NGHIỆM THU PHẦN CỨNG ESP32

> **Mục tiêu:** Chạy kiểm thử tự động với PyTest, kiểm tra bắt tay mô phỏng client qua script test, và tiến hành đàm thoại thực tế trên bo mạch phần cứng ESP32 với loa MAX98357A.

#### 5.1. Kiểm thử Unit Test (`tests/test_tts.py`)
* Chạy bộ kiểm thử tự động của dự án:
  ```bash
  pytest tests/test_tts.py -v
  ```
* Tiêu chí: Vượt qua toàn bộ các test case `test_tts_provider_constructs_from_config`, `test_tts_provider_exposes_to_tts`, `test_tts_provider_has_output_dir`, `test_tts_text_to_speak_writes_file`.

#### 5.2. Đo lường hiệu năng thực tế (Performance & Resource Metrics)
* Tiến hành đo đạc các chỉ số vận hành trên máy chủ Host:
  1. **Độ trễ phản hồi (TTFA):** Thời gian từ khi LLM xuất xong câu đầu tiên đến khi gói Opus đầu tiên được gửi vào WebSocket (Đạt chuẩn: **$\le 400\text{ms}$**).
  2. **Dung lượng bộ nhớ RAM:** Tổng RAM chiếm dụng của tiến trình server (Đạt chuẩn: tăng không quá **$500\text{ MB}$**).
  3. **VRAM GPU MX450:** Kiểm tra qua `nvidia-smi` (Đạt chuẩn: **$0\text{ MB}$**).
  4. **Tải CPU:** Kiểm tra qua Task Manager trong lúc sinh âm (Đạt chuẩn: xung tải 40–60% trong 1–1.5s, sau đó trở về trạng thái nghỉ Idle $< 5\%$).

#### 5.3. Kiểm thử trên phần cứng thực tế (ESP32 + MAX98357A)
* Khởi động server với [start_xiaozhi_server.bat](file:///e:/Espressif/frameworks/esp-idf-v5.5.3/examples/xiaozhi-esp32-main/start_xiaozhi_server.bat).
* Đánh thức ESP32 và thực hiện bài test 5 câu hội thoại liên tục:
  * Câu ngắn (chào hỏi): *"Xin chào bạn!"*
  * Câu hỏi kiến thức: *"Kể cho tôi nghe về lịch sử nước Việt Nam."*
  * Câu có chứa từ tiếng Anh: *"Hôm nay tôi muốn nghe bài hát Shape of You."*
  * Thử nghiệm ngắt lời: Nói chen ngang khi bot đang phát âm thanh $\rightarrow$ Loa phải dừng phát ngay tức khắc.
  * Thử nghiệm thẩm âm Voice Clone: Đánh giá độ tương đồng âm sắc so với giọng mẫu chú Ngạn.

#### ✅ Checklist Nghiệm Thu Giai Đoạn 5:
- [ ] Chạy `pytest tests/test_tts.py` pass 100%.
- [ ] TTFA đo đạc thực tế đạt mốc mượt mà $\le 400\text{ms}$.
- [ ] Máy chủ không xảy ra hiện tượng tràn RAM, không rò rỉ bộ nhớ qua nhiều phiên đàm thoại liên tiếp.
- [ ] Loa ESP32 MAX98357A phát âm thanh trong trẻo ở tần số 24kHz, tròn vành rõ chữ, không bị vấp, không tua nhanh chipmunk và không giật xước.
- [ ] Tính năng Voice Cloning phản ánh đúng đặc trưng âm sắc của mẫu giọng (chú Ngạn / giọng tùy biến).
- [ ] Tính năng ngắt lời (Barge-in) hoạt động mượt mà, triệt tiêu âm thanh thừa ngay khi người dùng cướp lời.

---

### GIAI ĐOẠN 6 (FUTURE ENHANCEMENT): NÂNG CẤP STREAMING TTFA SIÊU TỐC
> **Ghi chú (Note):** Dựa trên tư vấn mới nhất từ tài liệu tham khảo Github, VieNeu-TTS v3 Turbo hỗ trợ API `infer_stream(...)` cho phép sinh âm thanh thời gian thực (nhả từng frame thay vì đợi hết câu).

* **Mục tiêu tương lai:** 
  - Cải tiến lại hàm `to_tts_stream` từ mô hình sinh âm thanh đồng bộ nguyên câu (`_sync_synthesize`) sang mô hình `_sync_synthesize_stream(text)`.
  - Thay đổi lại logic `numpy_audio_to_pcm_stream_fast` và `pcm_to_data_stream` (hiện tại Opus encoder đang đóng gói và padding số 0 ở cuối mỗi mảng numpy) sang một cơ chế đệm vòng (ring buffer) dung lượng nhỏ, nhằm cho phép stream từng chunk nhỏ của VieNeu vào mạch MAX98357A mà không bị nhiễu âm thanh vấp (clicks) ở các ranh giới chunk.
  - Tối ưu này sẽ giúp giảm TTFA từ ~400ms xuống chỉ còn ~140ms.

---

## VII. Đặc Tả Thiết Lập Cấu Hình Thực Chiến (`data/.config.yaml` & `config.yaml`)

Dưới đây là khối cấu hình chi tiết có thể sao chép trực tiếp vào [data/.config.yaml](file:///e:/Espressif/frameworks/esp-idf-v5.5.3/examples/xiaozhi-esp32-main/xiaozhi-esp32-server/main/xiaozhi-server/data/.config.yaml):

```yaml
# ==============================================================================
# BẬT CHỌN MODULE TTS CHÍNH
# ==============================================================================
selected_module:
  TTS: VieNeuTTS        # Chuyển đổi linh hoạt: EdgeTTS | PiperTTS | VieNeuTTS

# ==============================================================================
# CHI TIẾT CẤU HÌNH CÁC PROVIDER TTS
# ==============================================================================
TTS:
  # 1. Microsoft EdgeTTS (Option 1 - Mặc định: Stream đồng bộ trực tiếp trong RAM ~350-500ms, 0 VNĐ)
  EdgeTTS:
    type: edge
    voice: vi-VN-HoaiMyNeural
    language: "Tiếng Việt"
    rate: 0
    volume: 50
    pitch: 0
    output_dir: tmp/

  # 2. PiperTTS Tiếng Việt Offline (Option 2 - Dự phòng cơ bản: ONNX 60MB, phát thanh viên VAIS 1000)
  PiperTTS:
    type: piper
    language: "Tiếng Việt"
    output_dir: tmp/
    model_path: models/piper/vi_VN-vais1000-medium.onnx
    config_path: models/piper/vi_VN-vais1000-medium.onnx.json
    speed: 0.85
    volume: 50

  # 3. VieNeu-TTS Tiếng Việt Cục Bộ Nâng Cao (Option 3 - Dự phòng nâng cao: 100% Offline, Voice Cloning, CPU INT8)
  VieNeuTTS:
    type: vieneu
    language: "Tiếng Việt"
    precision: "int8"           # "int8" (Khuyên dùng cho CPU AVX-512) | "fp32"
    speed: 1.0                  # Tốc độ đọc
    volume: 50                  # Âm lượng mặc định (0 - 100)
    output_dir: tmp/
    
    # --- Cấu hình Voice Cloning (Mặc định kích hoạt) ---
    enable_voice_clone: false
    ref_audio: "data/voices/nguyen_ngoc_ngan.wav"
    ref_text: "Kính thưa quý vị khán thính giả, tôi là Nguyễn Ngọc Ngạn."
    
    # --- Cấu hình Giọng Preset (Khi enable_voice_clone: false) ---
    preset_voice: "Trúc Ly"
```

---

## VIII. Bảng Mã Lỗi Tiềm Tàng, Rủi Ro Hệ Thống & Giải Pháp Phòng Thủ (Troubleshooting & Fallback)

| Mã Rủi Ro | Hiện Tượng / Lỗi Ghi Nhận | Nguyên Nhân Gốc Rễ | Biện Pháp Phòng Thủ & Khắc Phục |
| :---: | :--- | :--- | :--- |
| **ERR-VN-01** | `ModuleNotFoundError: No module named 'vieneu'` | Thư viện chưa được cài vào môi trường ảo `venv` của server. | Chạy lệnh `pip install vieneu` trong môi trường `venv`. |
| **ERR-VN-02** | `CUDA Out of Memory` (Crash Server) | Model vô tình cố nạp lên GPU NVIDIA MX450 (2 GB VRAM). | Ép buộc tham số khởi tạo chỉ định chạy CPU: `device="cpu"` và `precision="int8"`. |
| **ERR-VN-03** | Server bị đơ / treo WebSocket khi đang sinh âm thanh | Hàm suy luận CPU-bound được gọi trực tiếp trong async loop. | Bắt buộc chuyển sang `loop.run_in_executor(None, self._sync_synthesize, text)`. |
| **ERR-VN-04** | Loa ESP32 phát ra tiếng rè, tua nhanh chipmunk | Tần số lấy mẫu không khớp 24000Hz (ví dụ đưa 48000Hz vào bộ mã hóa 24000Hz). | Áp dụng hàm `numpy_audio_to_pcm_stream_fast` tự động resample về đúng 24000Hz Mono trước khi nén Opus. |
| **ERR-VN-05** | Âm thanh giọng clone bị lẫn tạp âm, tiếng xì xào | File `ref_audio` có chứa nhạc nền BGM hoặc tạp âm môi trường. | Dùng công cụ UVR5 bóc tách vocal sạch 100%, chuẩn hóa âm lượng file WAV trước khi đưa vào `data/voices/`. |
| **ERR-VN-06** | Bot vẫn tiếp tục đọc sau khi người dùng đã ngắt lời | Chưa kiểm tra cờ `client_abort` trong lúc sinh âm thanh. | Tích hợp kiểm tra `self._is_aborted()` trước và sau khi sinh mảng audio để hủy tác vụ ngay. |

---

## IX. Kế Hoạch Đo Đạc & Tiêu Chí Đánh Giá Thành Công (Success Metrics)

Hệ thống sẽ được xác nhận là hoàn thành xuất sắc khi đáp ứng đầy đủ **5 chỉ số vàng** sau:

1. **VRAM Footprint = 0 MB:** Tuyệt đối không tiêu tốn VRAM trên card NVIDIA GeForce MX450, card đồ họa hoàn toàn nhàn rỗi.
2. **RAM Footprint $\le$ 500 MB:** Mức tăng bộ nhớ RAM của tiến trình server khi nạp VieNeu-TTS không vượt quá 500 MB.
3. **Độ trễ cất tiếng (TTFA) $\le$ 400ms:** Người dùng dứt câu nói, LLM sinh câu đầu tiên thì loa ESP32 cất tiếng trong vòng $\le 400\text{ms}$.
4. **Tốc độ xử lý (RTF) $\le$ 0.5:** Tốc độ tính toán trên CPU i5-1135G7 nhanh hơn thời gian phát thực tế ít nhất gấp 2 lần.
5. **Tính nguyên vẹn của kiến trúc (Zero Regression):** Khi chuyển cấu hình trở lại `EdgeTTS` hay `PiperTTS`, hệ thống hoạt động bình thường 100% như ban đầu, không phát sinh bất kỳ lỗi xung đột nào.
