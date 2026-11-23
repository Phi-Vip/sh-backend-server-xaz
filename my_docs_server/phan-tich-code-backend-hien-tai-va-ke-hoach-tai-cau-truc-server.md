# Phân tích code backend hiện tại và kế hoạch tái cấu trúc server

> **Tài liệu kiểm toán kỹ thuật (Technical Audit), mổ xẻ các điểm nghẽn kiến trúc và lộ trình tái cấu trúc Backend XiaoZhi đạt chuẩn Production tại Việt Nam**  
> *Đối tượng kiểm toán: Thư mục `xiaozhi-esp32-server/main/xiaozhi-server`*  
> *Đối chiếu với mã nguồn mở gốc: [https://github.com/xinnan-tech/xiaozhi-esp32-server](https://github.com/xinnan-tech/xiaozhi-esp32-server)*

---

## MỤC LỤC

1. [Tuyên ngôn mục tiêu & Bối cảnh kiểm toán](#1-tuyên-ngôn-mục-tiêu--bối-cảnh-kiểm-toán)
2. [Bảng so sánh đối chiếu: Backend gốc GitHub vs Backend hiện tại](#2-bảng-so-sánh-đối-chiếu-backend-gốc-github-vs-backend-hiện-tại)
3. [Mổ xẻ 5 "vùng rối như tơ vò, chắp vá và cẩu thả"](#3-mổ-xẻ-5-vùng-rối-như-tơ-vò-chắp-vá-và-cẩu-thả)
   - [3.1 Vùng 1: "Rừng" Regex thô thiển trong `fast_router.py`](#31-vùng-1-rừng-regex-thô-thiển-trong-fast_routerpy)
   - [3.2 Vùng 2: Cắt xén Schema thô bạo (`desc[:160]`) và Hardcode vào lõi](#32-vùng-2-cắt-xén-schema-thô-bạo-desc160-và-hardcode-vào-lõi)
   - [3.3 Vùng 3: Lỗ hổng Streaming Parser làm rò rỉ ký tự JSON ra Loa & LCD](#33-vùng-3-lỗ-hổng-streaming-parser-làm-rò-rỉ-ký-tự-json-ra-loa--lcd)
   - [3.4 Vùng 4: Luồng logic lỏng lẻo gây ảo giác (Hallucination - "Hứa lèo")](#34-vùng-4-luồng-logic-lỏng-lẻo-gây-ảo-giác-hallucination---hứa-lèo)
   - [3.5 Vùng 5: Hạ tầng phân mảnh, nhị phân trôi nổi và "bắc cầu 4 mái nhà"](#35-vùng-5-hạ-tầng-phân-mảnh-nhị-phân-trôi-nổi-và-bắc-cầu-4-mái-nhà)
4. [Phân tích nguyên nhân gốc rễ (Root Cause Analysis - RCA)](#4-phân-tích-nguyên-nhân-gốc-rễ-root-cause-analysis---rca)
5. [Kế hoạch tái cấu trúc toàn diện (Refactoring Roadmap)](#5-kế-hoạch-tái-cấu-trúc-toàn-diện-refactoring-roadmap)
   - [5.1 Năm nguyên tắc kiến trúc cốt tử & Sơ đồ thư mục phân tách](#51-năm-nguyên-tắc-kiến-trúc-cốt-tử--sơ-đồ-thư-mục-phân-tách)
   - [5.2 Giai đoạn 0: Thiết lập nhánh sạch Git & Khung mở rộng độc lập](#52-giai-đoạn-0-thiết-lập-nhánh-sạch-git--khung-mở-rộng-độc-lập-clean-slate--architecture-setup)
   - [5.3 Giai đoạn 1: Chuẩn hóa MCP Passthrough & Generic Schema Sanitizer](#53-giai-đoạn-1-chuẩn-hóa-mcp-passthrough--generic-schema-sanitizer-zero-hardcode)
   - [5.4 Giai đoạn 2: Màng lọc luồng phòng thủ chống rò rỉ cú pháp JSON](#54-giai-đoạn-2-màng-lọc-luồng-phòng-thủ-chống-rò-rỉ-cú-pháp-json-defensive-stream-guard)
   - [5.5 Giai đoạn 3: Module hóa bộ định tuyến ý định tiếng Việt](#55-giai-đoạn-3-module-hóa-bộ-định-tuyến-ý-định-tiếng-việt-vietnamese-semantic-router)
   - [5.6 Giai đoạn 4: Tích hợp PiperTTS tiếng Việt siêu tốc & Tinh gọn âm thanh](#56-giai-đoạn-4-tích-hợp-pipertts-tiếng-việt-siêu-tốc--tinh-gọn-âm-thanh-audio-pipeline-integration)
   - [5.7 Giai đoạn 5: Đóng gói Docker Production & Cloud Việt Nam (TẠM HOÃN)](#57-giai-đoạn-5-đóng-gói-docker-production--cloud-việt-nam-tạm-hoãn---deferred)
   - [5.8 Bảng ma trận nghiệm thu các giai đoạn (Master Verification Matrix)](#58-bảng-ma-trận-nghiệm-thu-các-giai-đoạn-master-verification-matrix)
6. [Tiêu chuẩn đánh giá sau tái cấu trúc (Acceptance Criteria)](#6-tiêu-chuẩn-đánh-giá-sau-tái-cấu-trúc-acceptance-criteria)
7. [Chiến lược "Đập đi xây lại" (Clean Rebase từ GitHub): Đánh giá chuyên sâu](#7-chiến-lược-đập-đi-xây-lại-clean-rebase-từ-github-đánh-giá-chuyên-sâu)
8. [Bảng đối chiếu thành bại: Những gì cần giữ lại vs Những gì phải vứt bỏ](#8-bảng-đối-chiếu-thành-bại-những-gì-cần-giữ-lại-vs-những-gì-phải-vứt-bỏ)

---

## 1. TUYÊN NGÔN MỤC TIÊU & BỐI CẢNH KIỂM TOÁN

- **Thực tế kiểm chứng:** Thiết bị phần cứng ESP32-S3 hiện tại đang chạy rất ổn định và mượt mà khi kết nối về cụm máy chủ chính thức của XiaoZhi đặt tại Trung Quốc. Điều này chứng minh: **Phần cứng, driver audio I2S, mic thu âm và firmware ESP32 của bạn hoàn toàn đạt chuẩn**.
- **Vấn đề cốt tử:** Mọi sự cố chập chờn, giật lag, ảo giác, đọc ra ký tự JSON hay phản hồi sai lệch hiện nay **hoàn toàn xuất phát từ sự rối ren, chắp vá và sai lệch logic bên trong cụm Backend Python cục bộ**.
- **Mục tiêu tối thượng:** Tái thiết kế toàn bộ Backend đặt tại Việt Nam để đạt:
  1. **Hiệu suất tương đương hoặc vượt trội server gốc TQ** (Độ trễ tổng thể < 500ms).
  2. **100% tuân thủ bản chất MCP (Model Context Protocol)**: Server là trạm trung chuyển trong suốt, không can thiệp méo mó schema, không hardcode nghiệp vụ thiết bị vào lõi.
  3. **Xóa bỏ triệt để mọi lỗi vặt:** Chấm dứt hiện tượng chatbot "nói một đằng làm một nẻo", chấm dứt rò rỉ JSON ra loa, chấm dứt phụ thuộc vào các đường hầm tạm bợ (Ngrok/Vercel).

---

## 2. BẢNG SO SÁNH ĐỐI CHIẾU: BACKEND GỐC GITHUB VS BACKEND HIỆN TẠI

| Tiêu chí kỹ thuật | Backend gốc GitHub (`xinnan-tech`) | Backend hiện tại của bạn (Sau các đợt vá) | Đánh giá & Rủi ro |
| :--- | :--- | :--- | :--- |
| **Triết lý kiến trúc** | **Passthrough (Truyền dẫn trong suốt)**: Nhận schema gì từ ESP32 thì chuyển nguyên vẹn lên LLM. | **Intercept & Patch (Chặn và Vá)**: Sửa schema, cắt ngắn mô tả, can thiệp tham số. | 🔴 **Nghiêm trọng**: Làm mất ngữ cảnh của LLM, vi phạm bản chất MCP. |
| **Độ dài mô tả Tool** | Giữ nguyên văn mô tả từ firmware gửi lên. | Cắt cụt còn 160 ký tự (`desc[:160]`) trong `mcp_client.py`. | 🔴 **Nghiêm trọng**: Cắt mất câu hướng dẫn kích hoạt tool khiến AI không hiểu khi nào cần gọi. |
| **Định tuyến ý định (Router)** | Không có router: Mọi câu hỏi đều gửi kèm toàn bộ Tool Schema lên LLM. | Dùng Regex thô thiển (`fast_router.py`) với hàng chục từ khóa cứng. | 🟡 **Chắp vá**: Tiết kiệm được token nhưng dễ gãy khi người dùng nói câu biến thể. |
| **Xử lý Function Call** | Trông cậy hoàn toàn vào `tool_calls` delta chuẩn từ OpenAI API. | Thêm code vét chuỗi text (`trimmed.startswith('{"name"')`). | 🟡 **Khập khiễng**: Cần thiết khi dùng Groq OSS nhưng xử lý chắp vá gây rò rỉ âm thanh. |
| **Bảo toàn tính tổng quát** | Lõi hoàn toàn trung lập, không biết quạt hay bài hát nào cụ thể. | Hardcode cứng bài hát "Địa Đàng", quạt Sunhouse ở prompt và code. | 🔴 **Nghiêm trọng**: Phá vỡ cấu trúc Clean Architecture, khó mở rộng thiết bị khác. |
| **Môi trường & Binary** | Sạch sẽ, quản lý dependencies chuẩn qua `requirements.txt`. | Trôi nổi các file `.exe`, `.dll`, thư mục `scratch/`, test tạm bợ. | 🟡 **Cẩu thả**: Rủi ro khi đóng gói lên Linux Docker server. |
| **Chuỗi truyền dẫn Media** | Tích hợp trực tiếp hoặc stream HTTP nội bộ. | 4 mắt xích: ESP32 ➔ Vercel ➔ Ngrok ➔ Node.js Relay ➔ YouTube. | 🔴 **Nghiêm trọng**: Quá nhiều điểm chết (SPOF), ngrok timeout là chết luồng nhạc. |

---

## 3. MỔ XẺ 5 "VÙNG RỐI NHƯ TƠ VÒ, CHẮP VÁ VÀ CẨU THẢ"

Kiểm toán trực tiếp qua `git diff`, hiện có **22 file mã nguồn bị can thiệp** với **684 dòng thêm vào** và **303 dòng bị xóa**. Dưới đây là 5 ổ bệnh kiến trúc lớn nhất:

### 3.1 Vùng 1: "Rừng" Regex thô thiển trong `fast_router.py`
- **Hiện trạng:** Để giải quyết bài toán giới hạn 8.000 TPM của Groq, file `fast_router.py` được tạo ra với hàng trăm từ khóa regex tiếng Việt (`mật quạc`, `bật hoạt`, `tắt hoạt`, `tăng lông lượng`, `ôm lượng`, `nông lượng`...).
- **Cẩu thả ở đâu?**
  - Đây là phương pháp **"chữa cháy triệu chứng" (Symptom patching)**. Cứ mỗi lần ASR nhận diện sai một từ tiếng Việt, lập trình viên lại mở code ra thêm một dòng regex mới.
  - Ngôn ngữ tự nhiên có hàng vạn cách nói. Một câu lệnh ngắn như *"Tăng lên 40%"* hoặc *"Mát quá rồi"* bị lọt lưới regex ➔ Fast-router kết luận là "chat thường" ➔ Không đính kèm Tool ➔ Chatbot không có tool để gọi!

### 3.2 Vùng 2: Cắt xén Schema thô bạo (`desc[:160]`) và Hardcode vào lõi
- **Hiện trạng:**
  - Trong `core/providers/tools/device_mcp/mcp_client.py` và `unified_tool_manager.py`:
    ```python
    # Code chắp vá cắt cụt mô tả
    if len(desc) > 160:
        desc = desc[:160]
    ```
  - Đồng thời gán cứng bài hát:
    ```python
    if tool_name in ("play_online_music", "self.music.play"):
        desc = "Phát nhạc trực tuyến... BẮT BUỘC gọi tool này..."
    ```
- **Hậu quả kiến trúc:**
  - Vi phạm trực tiếp **Bản chất của MCP**: Backend là ống dẫn, không được là "kéo cắt tóc". Firmware ESP32 viết hướng dẫn kỹ lưỡng bao nhiêu thì lên backend bị xén cụt bấy nhiêu.
  - Khi ESP32 sinh ra tool mới trong tương lai (Nồi cơm, Máy lọc nước), Backend lại phải mở code ra viết thêm `if tool_name == ...`! Đây là lối tư duy code cực kỳ cẩu thả và phản kiến trúc.

### 3.3 Vùng 3: Lỗ hổng Streaming Parser làm rò rỉ ký tự JSON ra Loa & LCD
- **Hiện tượng thực tế:** Người dùng nói một câu ra lệnh hoặc hết thời gian chờ (timeout), loa bất ngờ đọc: *"ngoặc nhọn, nháy kép, nây-mờ, han-đồ-e-xít..."* và màn hình LCD in ra một chuỗi JSON ngoằng ngoèo.
- **Nguyên nhân cốt lõi:**
  - Mô hình mã nguồn mở trên Groq (`openai/gpt-oss-120b`) không phải lúc nào cũng xuất tool_call qua cấu trúc JSON có sẵn. Khi bối rối, nó nôn thẳng chuỗi text:
    `Hẹn gặp lại bạn sau nhé!{"name": "handle_exit_intent", "arguments": {}}`
  - Bộ đọc luồng âm thanh `to_tts_stream` nhận dữ liệu dạng stream từng từ (Token Streaming). Vì thấy có chữ, nó đẩy ngay vào hàng đợi TTS (`tts_text_queue`).
  - Hậu quả: Bộ tổng hợp giọng nói (Piper/Edge) đọc to toàn bộ đoạn JSON thô ra loa!
- **Sự chắp vá hiện tại:** Chúng ta đang chữa cháy bằng cách viết regex lọc trong `tts.py`, chèn cờ `tool_call_flag` trong `connection.py` và gán cứng `direct_text` trong `receiveAudioHandle.py`. Code bị rải rác ở 4 file khác nhau thay vì có một bộ **Defensive Stream Decoder** tập trung.

### 3.4 Vùng 4: Luồng logic lỏng lẻo gây ảo giác (Hallucination - "Hứa lèo")
- **Hiện tượng:** Chatbot vui vẻ trả lời: *"Dạ, tôi đã mở bài Địa Đàng cho bạn rồi nhé!"* hoặc *"Đã chỉnh âm lượng lên 40% rồi nhé"* nhưng quạt không quay, nhạc không phát, âm lượng không đổi.
- **Tại sao lại có hiện tượng này?**
  - Trong `core/connection.py`, khi luồng gọi tool bị lỗi hoặc khi Fast-router không gửi tool lên, code bị rơi vào nhánh rẽ (fallback): LLM nhận câu hỏi mà không có quyền gọi hàm ➔ LLM tự suy diễn văn bản trả lời như thể mình đã làm xong việc đó!
  - Bản gốc XiaoZhi không bao giờ cho phép trả lời tích cực nếu kết quả thực thi tool chưa thành công. Sự thiếu chặt chẽ trong luồng quản lý trạng thái (State Machine) của Backend hiện tại đã gây ra căn bệnh "nói dối" này.

### 3.5 Vùng 5: Hạ tầng phân mảnh, nhị phân trôi nổi và "bắc cầu 4 mái nhà"
- **Hiện trạng thư mục:**
  - Trong `main/xiaozhi-server/` chứa lẫn lộn: `ffmpeg.exe`, `ffprobe.exe`, `opus.dll`, thư mục `scratch/`, file `test_handshake.py` không rõ nguồn gốc.
  - Luồng Media: Phụ thuộc vào `start_ngrok_tunnel.bat` (Ngrok free port 3001) + `serverlessmusicapi.vercel.app` (Vercel gateway) + `index.js` (Node.js).
- **Rủi ro vận hành:**
  - Chỉ cần một mắt xích bị nghẽn mạng quốc tế hoặc đổi IP là toàn bộ hệ thống tê liệt.
  - Không thể đưa lên Cloud VPS Linux nếu mã nguồn vẫn đang gọi trực tiếp các file `.exe` của Windows!

---

## 4. PHÂN TÍCH NGUYÊN NHÂN GỐC RỄ (ROOT CAUSE ANALYSIS - RCA)

Tại sao mã nguồn lại bị biến thành một "mớ bòng bong"?
1. **Áp lực vá lỗi cục bộ (Symptom-driven development):** Khi gặp lỗi (Groq 400, Groq 429, ASR nghe sai, JSON rò rỉ, timeout crash), chúng ta liên tục áp dụng các miếng vá khẩn cấp (Monkey Patches) chèn trực tiếp vào giữa các hàm xử lý luồng âm thanh thay vì dừng lại thiết kế lại cấu trúc.
2. **Xung đột giữa Model mã nguồn mở và Framework OpenAI:** Code XiaoZhi gốc được tối ưu cho OpenAI GPT-4o-mini (rất chuẩn chỉ về function call). Khi ép nó chạy với Groq `gpt-oss-120b`, mô hình này hành xử không chuẩn mực (đôi khi sinh text thay vì function call, không chấp nhận `null` trong schema string), dẫn đến việc phải viết code bẫy lỗi ở khắp nơi.
3. **Trộn lẫn tầng nghiệp vụ (Domain Logic) và tầng hạ tầng (Infrastructure):** Nghiệp vụ của chiếc loa Sunhouse (bài hát Địa Đàng, quạt Sunhouse, tiếng Việt) bị đổ lẫn vào trong lõi máy chủ WebSocket chung.

---

## 5. KẾ HOẠCH TÁI CẤU TRÚC TOÀN DIỆN (REFACTORING ROADMAP)

Để đưa Backend trở về trạng thái sạch sẽ, chuyên nghiệp, chạy mượt mà ngang ngửa và ổn định hơn server gốc Trung Quốc, chúng ta không thể tiếp tục "vá đè lên miếng vá" mà phải tái cấu trúc toàn diện theo phương pháp luận công nghiệp.

---

### 5.1 Năm nguyên tắc kiến trúc cốt tử & Sơ đồ thư mục phân tách

Kế hoạch tái cấu trúc tuân thủ nghiêm ngặt **5 nguyên tắc kỹ thuật phần mềm cốt tử**:

1. **Nguyên tắc "Chia để trị" (Divide & Conquer):**
   - Phân rã hệ thống thành các bài toán con độc lập: *Kết nối mạng*, *Chuẩn hóa Schema*, *Lọc luồng phòng thủ*, *Định tuyến ý định*, và *Tổng hợp âm thanh*. Mỗi bài toán được giải quyết triệt để tại phân tầng chuyên trách, không xử lý chéo luồng.
2. **Nguyên tắc "Module hóa độc lập" (Strict Modularization):**
   - Mọi tính năng mở rộng đặc thù của Việt Nam (Router tiếng Việt, PiperTTS, Stream Guard, Groq Sanitizer) phải được đóng gói thành các package độc lập, có thể cắm/rút hoặc bật/tắt qua file cấu hình mà không làm sập server.
3. **Nguyên tắc "Phân luồng rõ ràng mạch lạc" (Explicit Separation of Pipelines):**
   - Tách bạch 3 luồng dữ liệu độc lập:
     - **Luồng Điều khiển Máy móc (Machine Control Pipeline):** Đi theo chuẩn JSON-RPC 2.0 / MCP Tool Calls.
     - **Luồng Đàm thoại Con người (Human Audio/Text Pipeline):** Đi từ LLM Text ➔ Bộ lọc phòng thủ ➔ TTS ➔ Loa. Tuyệt đối không để dữ liệu máy móc (JSON) tràn sang luồng con người.
     - **Luồng Định tuyến Ngữ nghĩa (Intent Classification Pipeline):** Tiền xử lý ngữ âm và lọc công cụ trước khi gửi context lên LLM.
4. **Nguyên tắc "Cấu trúc thư mục phân tách rõ ràng" (Dedicated Extensions Architecture):**
   - Toàn bộ mã nguồn mở rộng tự phát triển được cô lập hoàn toàn vào thư mục riêng: `core/extensions/`. Không tạo các file trôi nổi lẫn lộn vào thư mục mã nguồn gốc.
5. **Nguyên tắc "Bảo toàn cấu trúc lõi server gốc" (Preserve Upstream Core):**
   - Giữ nguyên bản 100% các file lõi của XiaoZhi gốc (`core/connection.py`, `core/handle/`, `core/providers/tools/device_mcp/mcp_client.py`). Việc tích hợp các module mở rộng chỉ thông qua Middleware Interface hoặc Hook chuẩn hóa một dòng, tuyệt đối không cấy code `if tool_name == ...` hay regex vá lỗi vào lõi.

#### Sơ đồ cấu trúc thư mục module hóa phân tách:

```
xiaozhi-server/
├── core/
│   ├── connection.py                 # [LÕI GỐC] Giữ nguyên bản, chỉ tiếp nhận kết nối & gọi middleware
│   ├── handle/                       # [LÕI GỐC] Các handler xử lý sự kiện mặc định
│   ├── providers/                    # [LÕI GỐC] Các provider chuẩn (LLM, TTS, ASR, Tools)
│   │   └── tts/
│   │       └── piper.py              # Provider PiperTTS tiếng Việt (kế thừa sạch từ BaseTTS)
│   │
│   └── extensions/                   # ⭐️ [VÙNG MỞ RỘNG ĐỘC LẬP - TOÀN BỘ CODE TÙY BIẾN Ở ĐÂY]
│       ├── __init__.py
│       │
│       ├── schema_adapter/           # 📦 MODULE 1: Chuẩn hóa Schema LLM đa nền tảng
│       │   ├── __init__.py
│       │   └── sanitizer.py          # Hàm đệ quy biến non-required thành ["type", "null"] (Generic)
│       │
│       ├── stream_guard/             # 📦 MODULE 2: Màng lọc phòng thủ chống rò rỉ cú pháp JSON
│       │   ├── __init__.py
│       │   ├── buffer.py             # Lookahead Stream Buffer (Bộ đệm cửa sổ trượt ~30 ký tự)
│       │   └── detector.py           # Bộ nhận diện cú pháp dị thường & phục hồi Tool Call ngầm
│       │
│       ├── intent_router/            # 📦 MODULE 3: Bộ định tuyến ý định tiếng Việt (thay fast_router)
│       │   ├── __init__.py
│       │   ├── normalizer.py         # Tiền xử lý ngữ âm tiếng Việt & biến âm ASR
│       │   └── matcher.py            # Phân loại ý định ngữ nghĩa theo nhóm lệnh (Device/Media/Chat)
│       │
│       └── state_guard/              # 📦 MODULE 4: Kiểm soát trạng thái & Chống nói dối (No-Fake-Action)
│           ├── __init__.py
│           └── validator.py          # Xác thực phản hồi vật lý từ ESP32 trước khi cho phép AI xác nhận
│
├── data/
│   ├── models/                       # Thư mục chứa tài nguyên AI tĩnh (Tách rời khỏi mã nguồn)
│   │   ├── piper/                    # Model giọng đọc Piper tiếng Việt (.onnx + .json)
│   │   └── vad/                      # Model Silero VAD
│   └── .config.yaml                  # File cấu hình trung tâm (sạch sẽ, có chú thích đầy đủ)
│
├── tests/
│   └── extensions/                   # Thư mục Unit Test độc lập cho từng module mở rộng
│       ├── test_sanitizer.py
│       ├── test_stream_guard.py
│       └── test_intent_router.py
│
└── app.py                            # Điểm khởi động ứng dụng
```

---

### 5.2 Giai đoạn 0: Thiết lập nhánh sạch Git & Khung mở rộng độc lập (Clean Slate & Architecture Setup)

- **Mục tiêu cốt lõi:** Bảo toàn 100% dữ liệu của phiên bản hiện tại bằng nhánh lưu trữ Git; đưa codebase về trạng thái sạch nguyên bản từ GitHub (`xinnan-tech/xiaozhi-esp32-server`); dựng sẵn khung thư mục mở rộng cách ly.
- **Phân luồng trách nhiệm:** Hạ tầng mã nguồn & Quản trị phiên bản (Git Versioning).

#### Các đầu mục công việc nhỏ:
1. **0.1 Đóng băng phiên bản cũ:** Tạo nhánh Git `backup/patched-server-v1` để lưu lại toàn bộ 22 file đã sửa đổi và các file tạm thời. Đảm bảo bất cứ lúc nào cần tra cứu lại code cũ đều mở ra được.
2. **0.2 Khởi tạo nhánh làm việc sạch:** Tạo nhánh `feat/clean-rebuild-v2` từ commit sạch mới nhất của `origin/main` (upstream GitHub).
3. **0.3 Khởi tạo khung thư mục `core/extensions/`:** Tạo đầy đủ các thư mục con và các file `__init__.py` theo đúng kiến trúc phân tách đã phê duyệt.
4. **0.4 Di chuyển tài nguyên tĩnh vào thư mục chuẩn:** Đưa model giọng đọc Piper tiếng Việt (`.onnx`) và cấu hình SileroVAD vào `data/models/`; cấu hình `.gitignore` chặn toàn bộ file binary Windows rác (`.exe`, `.dll`), thư mục test tạm bợ trôi nổi.

#### Bảng Checklist Giai đoạn 0:
- [x] Nhánh Git `backup/patched-server-v1` đã được tạo và lưu trữ an toàn (Commit `919508c`).
- [x] Nhánh `feat/clean-rebuild-v2` chuyển đổi thành công từ `origin/main`, `git status` báo working tree clean 100%.
- [x] Đã tạo cây thư mục `core/extensions/{schema_adapter, stream_guard, intent_router, state_guard}` và `tests/extensions/`.
- [x] File `.gitignore` đã chặn các file rác: `*.exe`, `*.dll`, `scratch/`, `.tmp*`.
- [x] Thư mục `data/models/piper/` đã sẵn sàng chứa model âm thanh offline.
- [x] Thiết lập `sitecustomize.py` trong venv giúp nạp DLL Windows và mã hóa UTF-8 tự động mà không cần sửa bất kỳ file mã nguồn gốc nào.

#### 🎯 Bài test Pass Giai đoạn 0: Baseline Clean Server Startup Test
- **Lệnh thực thi:**
  ```bash
  python app.py
  ```
- **Kỳ vọng kết quả (Pass Criteria):**
  - Server khởi động thành công trên cổng cấu hình (mặc định 8000).
  - Không xuất hiện bất kỳ lỗi `ImportError`, `SyntaxError` hay cảnh báo thiếu file rác nào.
  - Console log hiển thị luồng khởi tạo sạch sẽ của upstream XiaoZhi.
  - Client WebSocket kiểm thử bắt tay (Handshake) thành công theo chuẩn giao thức gốc.

---

### 5.3 Giai đoạn 1: Chuẩn hóa MCP Passthrough & Generic Schema Sanitizer (Zero-Hardcode)

- **Mục tiêu cốt lõi:** Khôi phục bản chất trong suốt (Transparent Passthrough) của MCP; xóa bỏ triệt để việc cắt cụt mô tả; giải quyết vĩnh viễn lỗi Groq 400 Bad Request bằng hàm chuẩn hóa generic đệ quy; loại bỏ toàn bộ hardcode thiết bị Sunhouse khỏi lõi server; thiết lập cơ chế chống "hứa lèo".
- **Phân luồng trách nhiệm:** Tầng giao thức MCP & Quản lý Schema LLM.

#### Các đầu mục công việc nhỏ:
1. **1.1 Khôi phục 100% mô tả MCP nguyên bản:**
   - Xóa bỏ triệt để dòng `desc = desc[:160]` trong `core/providers/tools/device_mcp/mcp_client.py`. Giữ nguyên văn toàn bộ hướng dẫn kích hoạt tool từ ESP32 gửi lên.
2. **1.2 Xây dựng Module `core/extensions/schema_adapter/sanitizer.py`:**
   - Viết hàm tổng quát `sanitize_schema_for_llm(schema: dict) -> dict`:
     - Sử dụng thuật toán duyệt đệ quy (Recursive Traversal) toàn bộ cây JSON Schema của công cụ.
     - Tự động nhận diện mọi thuộc tính (properties) không nằm trong danh sách `required`.
     - Tự động chuyển đổi `type: "string"` thành `type: ["string", "null"]` (hoặc `anyOf`).
     - **Nguyên tắc tuyệt đối:** Không chứa bất kỳ câu lệnh `if tool_name == '...'` nào. Hàm hoạt động tự động cho 100% công cụ (quạt, đèn, rèm, bếp từ, máy pha cà phê...).
3. **1.3 Xây dựng Module `core/extensions/state_guard/validator.py` (Chống nói dối / No-Fake-Actions):**
   - Thiết lập bộ kiểm soát trạng thái: Bắt buộc nhận được `tool_result` thành công từ ESP32 mới cho phép State Machine xác nhận tác vụ hoàn tất.
   - Nếu ESP32 timeout, mất mạng hoặc báo lỗi phần cứng: Trả về câu thông báo lỗi dịch vụ trung thực (*"Không thể kết nối với thiết bị"*), chặn đứng việc LLM tự hứa lèo (*"Đã bật thiết bị rồi nhé"*).
4. **1.4 Trục xuất hoàn toàn Hardcode ra khỏi lõi:**
   - Xóa sạch các chuỗi *"Địa Đàng"*, *"sunhouse_fan"*, các bài hát mặc định ra khỏi `core/connection.py` và `mcp_client.py`.
   - Lõi server chỉ là trạm trung chuyển trong suốt, việc chọn bài hát mặc định hay tên thiết bị thuộc thẩm quyền của firmware ESP32 hoặc tham số người dùng.

#### Bảng Checklist Giai đoạn 1:
- [ ] `mcp_client.py` không còn dòng lệnh cắt ngắn chuỗi `[:160]`.
- [ ] Module `schema_adapter/sanitizer.py` được viết xong và có unit test độc lập.
- [ ] Tích hợp `sanitizer.py` vào điểm nạp tool của server thông qua hook chuẩn, không sửa code lõi.
- [ ] Xóa sạch 100% từ khóa hardcode riêng lẻ ("Địa Đàng", "quạt Sunhouse") khỏi `connection.py`.
- [ ] Module `state_guard/validator.py` can thiệp chặn thành công câu trả lời khẳng định khi tool chưa thực thi xong.

#### 🎯 Bài test Pass Giai đoạn 1: MCP Dynamic Schema & Truthful State Test
- **Kịch bản kiểm thử 1 (Dynamic Schema không lỗi 400):**
  - Giả lập nạp 3 công cụ MCP hoàn toàn mới từ firmware: `air_conditioner_set_temp` (nhiệt độ, chế độ gió - có optional), `rice_cooker_cook` (hẹn giờ - optional), `robot_vacuum_clean` (khu vực - optional).
  - Gửi yêu cầu qua LLM Groq: *"Hãy nấu cơm chế độ nấu nhanh"*.
  - **Tiêu chí Pass:** Groq tiếp nhận schema trơn tru, không phát sinh lỗi HTTP 400 Bad Request, sinh ra `tool_calls` chuẩn xác với các tham số tương ứng.
- **Kịch bản kiểm thử 2 (Trung thực, không nói dối):**
  - Giả lập ngắt kết nối phần cứng (hoặc mô phỏng ESP32 trả về lỗi execution timeout).
  - Người dùng ra lệnh: *"Bật quạt số 3"*.
  - **Tiêu chí Pass:** Server trả về thông báo lỗi trung thực: *"Không thể điều khiển quạt lúc này"*. **Tuyệt đối 0% trường hợp loa phát ra câu khẳng định: "Đã bật quạt số 3 rồi nhé"**.

---

### 5.4 Giai đoạn 2: Màng lọc luồng phòng thủ chống rò rỉ cú pháp JSON (Defensive Stream Guard)

- **Mục tiêu cốt lõi:** Triệt tiêu 100% hiện tượng loa phát ra âm thanh ngoặc nhọn `{`, nháy kép `"name":` hoặc màn hình LCD hiển thị chuỗi JSON vô nghĩa; thu hồi các đoạn vá regex tạm bợ rải rác; phân tách tuyệt đối giữa luồng văn bản con người và luồng lệnh máy móc.
- **Phân luồng trách nhiệm:** Tầng xử lý luồng LLM Streaming & Bộ giải mã luồng.

#### Các đầu mục công việc nhỏ:
1. **2.1 Xây dựng `core/extensions/stream_guard/buffer.py` (Lookahead Window Buffer):**
   - Thiết kế bộ đệm cửa sổ trượt (dung lượng ~30 ký tự) đứng chắn ngay tại ngõ ra của LLM Streaming trước khi dữ liệu được chuyển tiếp sang hàng đợi TTS.
   - Khi token bắt đầu đổ về, bộ đệm tạm giữ lại trong vài mili-giây để xác thực cấu trúc cú pháp.
2. **2.2 Xây dựng `core/extensions/stream_guard/detector.py` (Cơ chế phát hiện dị thường):**
   - Thuật toán nhận diện cú pháp máy móc thời gian thực: Bắt các mẫu `{"name":`, `{"parameters":`, ````json`, `<tool_call>`, `{"tool_name":`.
3. **2.3 Cơ chế phân luồng & Tái sinh Tool Call ngầm:**
   - **Nhánh Văn bản Tự nhiên:** Nếu các ký tự đầu tiên là chữ cái tiếng Việt/tiếng Anh thông thường ➔ Lập tức giải phóng đệm sang hàng đợi TTS (độ trễ bổ sung < 5ms).
   - **Nhánh Tool Call bị rớt vào Text (Lỗi đặc thù của Groq/OpenAI OSS):** Nếu phát hiện dấu hiệu JSON ➔ Khóa van phát âm thanh của TTS ngay lập tức. Nuốt toàn bộ chuỗi JSON vào bộ nhớ đệm, tự động phân tích cú pháp (parse JSON) và chuyển đổi thành Function Call hợp lệ để kích hoạt ESP32.
   - Màn hình LCD và Loa hoàn toàn tĩnh lặng, sạch bóng ký tự kỹ thuật.
4. **2.4 Dọn sạch các miếng vá chắp vá rải rác:**
   - Xóa bỏ các đoạn regex bắt JSON tạm bợ trong `core/utils/tts.py`, `core/providers/tts/base.py`, và `core/handle/helloHandle.py`. Toàn bộ trách nhiệm bảo vệ luồng thuộc về duy nhất module `stream_guard`.

#### Bảng Checklist Giai đoạn 2:
- [ ] Module `stream_guard/buffer.py` và `detector.py` hoàn thành với độ trễ xử lý < 5ms.
- [ ] Màng lọc được cắm vào luồng stream tại một điểm duy nhất trước khi text tới TTS Queue.
- [ ] Các file `tts.py`, `base.py` được trả lại nguyên bản sạch sẽ, không còn regex vá víu.
- [ ] Tính năng nuốt chuỗi JSON và phục hồi Tool Call ngầm hoạt động ổn định.

#### 🎯 Bài test Pass Giai đoạn 2: Zero-Leakage & Stream Hijacking Stress Test
- **Kịch bản kiểm thử:**
  - Bơm liên tục 50 chuỗi stream dị thường giả lập vào ngõ ra LLM:
    - 20 chuỗi chứa JSON thuần: `{"name": "fan_control", "parameters": {"speed": 2}}`.
    - 15 chuỗi chứa markdown: ````json {"name": "play_music", "song": "Ha Noi"} ````.
    - 10 chuỗi thoại chứa ký tự đặc biệt hợp lệ: *"Nhiệt độ phòng là {28 độ C}, bạn có muốn bật quạt không?"*.
    - 5 chuỗi ngắt kết nối đột ngột giữa chừng khi đang sinh JSON.
- **Tiêu chí Pass:**
  - **Tỷ lệ rò rỉ ký tự JSON/XML ra hàng đợi TTS và LCD = 0.0%**.
  - Các chuỗi JSON điều khiển quạt/nhạc được phục hồi và kích hoạt lệnh thực thi ngầm thành công.
  - Chuỗi thoại bình thường (*"Nhiệt độ phòng..."*) vẫn được phát âm thanh đầy đủ, không bị nuốt chữ hay ngắt quãng.

---

### 5.5 Giai đoạn 3: Module hóa bộ định tuyến ý định tiếng Việt (Vietnamese Semantic Router)

- **Mục tiêu cốt lõi:** Khai tử hoàn toàn file `fast_router.py` chứa hàng chục dòng regex thô thiển (`mật quạc`, `tăng lông lượng`...); xây dựng bộ định tuyến ngữ nghĩa tiếng Việt thông minh, hiểu mọi cách nói lóng, nói tắt, tiếng địa phương mà không cần bảo trì danh sách từ khóa thủ công; triển khai cơ chế Dynamic Tool Injection và Safe Fallback.
- **Phân luồng trách nhiệm:** Tầng định tuyến ý định (Semantic Intent Routing) & Tối ưu hóa Context LLM.

#### Các đầu mục công việc nhỏ:
1. **3.1 Xóa bỏ hoàn toàn mã nguồn cũ của `fast_router.py`:**
   - Loại bỏ toàn bộ danh sách từ khóa lỗi chính tả viết tay, giải phóng codebase khỏi sự bừa bãi.
2. **3.2 Xây dựng `core/extensions/intent_router/normalizer.py` (Chuẩn hóa ngữ âm tiếng Việt):**
   - Viết bộ chuẩn hóa tiền xử lý:
     - Khử nhiễu khoảng trắng, chuẩn hóa dấu thanh Unicode (NFC/NFD).
     - Xử lý các biến âm ASR phổ biến mà không cần liệt kê từng từ (ví dụ: các âm bật/bạt, quạt/vạt, to/nhỏ).
     - Chuẩn hóa số từ tự nhiên thành chữ số (*"hai mươi phần trăm"* ➔ *"20%"*, *"số một"* ➔ *"1"*).
3. **3.3 Xây dựng `core/extensions/intent_router/matcher.py` (Phân loại nhóm ý định):**
   - Phân loại câu lệnh người dùng vào 3 nhóm ý định chính:
     - `DEVICE_CONTROL`: Điều khiển thiết bị phần cứng (quạt, đèn, âm lượng, tốc độ, hẹn giờ...).
     - `MEDIA_ENTERTAINMENT`: Giải trí âm nhạc (phát nhạc, bài hát, truyện, podcast...).
     - `GENERAL_CONVERSATION`: Đàm thoại thông thường, hỏi đáp tri thức, chào hỏi, thời tiết.
4. **3.4 Thiết lập Dynamic Tool Injection & Safe Fallback:**
   - **Tối ưu hóa Context:** Khi người dùng chỉ muốn nghe nhạc ➔ Chỉ gửi tool `play_music` lên LLM (tiết kiệm token, giảm thời gian xử lý của LLM).
   - **Chế độ Safe Fallback (Bảo vệ thông minh):** Nếu bộ định tuyến không chắc chắn (Độ tin cậy Confidence Score < 0.7) ➔ Tự động gửi **Full Tools** lên LLM. Tuyệt đối không tự tiện tước đoạt công cụ của AI khiến AI bị "mù" tính năng.

#### Bảng Checklist Giai đoạn 3:
- [ ] Toàn bộ code regex cũ trong `fast_router.py` đã bị xóa bỏ.
- [ ] Module `normalizer.py` xử lý tốt ngữ âm tiếng Việt và chuyển đổi số/phần trăm tự nhiên.
- [ ] Module `matcher.py` phân loại chính xác 3 nhóm ý định chủ đạo.
- [ ] Cơ chế Dynamic Tool Injection chỉ nạp các tool cần thiết tương ứng với ý định.
- [ ] Cơ chế Safe Fallback nạp Full Tools khi độ tin cậy thấp được kích hoạt kiểm chứng.

#### 🎯 Bài test Pass Giai đoạn 3: Semantic Accuracy & Dialect Test
- **Kịch bản kiểm thử:**
  - Chạy bộ test suite tự động gồm 100 câu thoại tiếng Việt khẩu ngữ thực tế:
    - 40 câu điều khiển thiết bị với cách diễn đạt đa dạng: *"cho gió mạnh tí đi"*, *"vặn to mồm lên"*, *"tăng lên 40 phần trăm"*, *"bật quạt số 2 giúp mình"*, *"thôi tắt đi giùm cái"*, *"chuyển hướng gió sang trái"*.
    - 30 câu yêu cầu âm nhạc: *"mở bài gì sôi động vui vẻ của Sơn Tùng"*, *"hát cho nghe bài Hà Nội mùa vắng những cơn mưa"*, *"cho nghe nhạc không lời thư giãn"*.
    - 30 câu hỏi đáp kiến thức & trò chuyện: *"Hôm nay trời có mưa không"*, *"Thủ đô của nước Pháp là gì"*, *"Bạn có mệt không"*, *"Kể một câu chuyện cười đi"*.
- **Tiêu chí Pass:**
  - **Tỷ lệ phân loại chính xác ý định đạt >= 96%**.
  - 100% các câu điều khiển thiết bị và âm nhạc đều nhận diện đúng nhóm công cụ cần thiết.
  - Tuyệt đối không có trường hợp câu lệnh điều khiển quạt bị đẩy nhầm sang nhóm tán gẫu thông thường (Zero False Negative trên tập lệnh thiết bị).

---

### 5.6 Giai đoạn 4: Tích hợp PiperTTS tiếng Việt siêu tốc & Tinh gọn âm thanh (Audio Pipeline Integration)

- **Mục tiêu cốt lõi:** Kế thừa thành tựu PiperTTS tiếng Việt offline siêu tốc (~100ms) vào một Provider độc lập chuẩn mực; tối ưu hóa bộ chia câu để giảm First-Chunk Latency xuống dưới 150ms; kế thừa cấu hình VAD nhạy bén; nội bộ hóa luồng trích xuất âm thanh YouTube.
- **Phân luồng trách nhiệm:** Tầng xử lý tín hiệu âm thanh (Audio Processing Task) & Tổng hợp giọng nói (TTS Provider).

#### Các đầu mục công việc nhỏ:
1. **4.1 Đóng gói Provider `core/providers/tts/piper.py` chuẩn mực:**
   - Kế thừa 100% interface trừu tượng của `BaseTTS` trong kiến trúc gốc của XiaoZhi.
   - Quản lý vòng đời tiến trình Piper inference: nạp model một lần duy nhất vào RAM khi khởi động server, giải phóng an toàn khi dừng server.
2. **4.2 Tối ưu hóa Bộ phân câu tiếng Việt (Vietnamese Sentence Chunking):**
   - Viết thuật toán cắt câu thông minh dựa trên ngữ pháp tiếng Việt: Tách câu ngay khi gặp các dấu ngắt nhịp (`,`, `.`, `?`, `!`, `-`, `...`).
   - Đảm bảo ngay khi LLM sinh xong vế câu đầu tiên (ví dụ: *"Dạ vâng,"*), Piper lập tức nhận text và tổng hợp âm thanh trong < 100ms, giúp loa phát tiếng ngay lập tức trong khi LLM vẫn đang tiếp tục sinh vế sau.
3. **4.3 Đồng bộ cấu hình SileroVAD (Voice Activity Detection):**
   - Đưa cấu hình SileroVAD tối ưu vào `data/.config.yaml`: ngưỡng phát hiện giọng nói `threshold: 0.5`, khoảng lặng kết thúc câu `speech_pad_ms: 300ms` (phù hợp với tốc độ nhả chữ của người Việt).
4. **4.4 Nội bộ hóa dịch vụ Audio Stream Relay:**
   - Tinh gọn service Node.js phát nhạc YouTube: Chạy cục bộ trực tiếp trên cổng nội bộ (`localhost:3000`), kết nối qua mạng loopback máy chủ mà không thông qua Vercel hay Ngrok.

#### Bảng Checklist Giai đoạn 4:
- [ ] Provider `piper.py` hoàn thành và tuân thủ chặt chẽ interface `BaseTTS`, không vá code trong `base.py`.
- [ ] Model giọng đọc Piper tiếng Việt được nạp thành công từ `data/models/piper/`.
- [ ] Bộ chia câu tiếng Việt đẩy audio chunk đầu tiên tới hàng đợi trong vòng < 150ms.
- [ ] Cấu hình SileroVAD bắt nhạy khoảng dừng lời nói, không bị cướp lời hoặc cắt cụt câu.
- [ ] Dịch vụ YouTube Relay hoạt động ổn định trên cổng nội bộ 3000.

#### 🎯 Bài test Pass Giai đoạn 4: End-to-End Latency & Hardware Smoothness Test
- **Kịch bản kiểm thử:**
  - Kết nối bo mạch phần cứng ESP32-S3 thực tế với Backend.
  - Người dùng nói trực tiếp qua micro: *"Bật quạt số 3 và mở bài hát Lạc Trôi"*.
- **Tiêu chí Pass:**
  1. **Độ trễ phản hồi tổng thể (E2E Latency):** Từ khoảnh khắc người dùng dứt lời đến khi loa ESP32 cất tiếng phản hồi đạt **dưới 550ms**.
  2. **Chất lượng âm thanh:** Giọng nói tiếng Việt ấm áp, rõ ràng, không giật cục, không bị nghẽn buffer âm thanh I2S.
  3. **Thực thi phần cứng:** Quạt nhận tín hiệu bật đúng số 3; sau câu phản hồi, bài hát được stream trực tiếp về ESP32 mượt mà trong vòng < 1.5 giây.

---

### 5.7 Giai đoạn 5: Đóng gói Docker Production & Cloud Việt Nam (TẠM HOÃN - DEFERRED)

> [!WARNING]
> **THÔNG BÁO QUAN TRỌNG: GIAI ĐOẠN 5 TẠM THỜI ĐÓNG BĂNG**  
> Theo định hướng chiến lược đã thống nhất, **Giai đoạn 5 tạm thời chưa triển khai ngay**.  
> **Điều kiện tiên quyết để mở lại Giai đoạn 5:** Toàn bộ Giai đoạn 0, Giai đoạn 1, Giai đoạn 2, Giai đoạn 3 và Giai đoạn 4 phải hoàn thành 100% và vượt qua tất cả các bài kiểm tra nghiệm thu (Pass Tests) trên môi trường phát triển cục bộ (Local).

#### Nội dung dự kiến khi kích hoạt lại Giai đoạn 5:
- **5.1 Đóng gói Docker Container đa tầng (Multi-stage Build):**
  - Đóng gói toàn bộ XiaoZhi Server (Python 3.11 Slim) và Audio Relay (Node.js LTS) vào các container Linux độc lập, chuẩn hóa môi trường, loại bỏ hoàn toàn các phụ thuộc Windows (.exe, .dll).
- **5.2 Thiết lập cụm Docker Compose thống nhất:**
  - File `docker-compose.yml` tích hợp sẵn: `xiaozhi-backend`, `audio-relay`, và `nginx-proxy` trong cùng một mạng ảo nội bộ (bridge network).
- **5.3 Triển khai lên Cloud VPS tại Việt Nam:**
  - Cài đặt trên hạ tầng đám mây nội địa (Viettel IDC / FPT Cloud / CMC Telecom) với IP tĩnh, băng thông trong nước 1Gbps, độ trễ ping < 10ms.
  - Thiết lập tên miền riêng với chứng chỉ SSL/TLS bảo mật (WSS: `wss://loa.sunhouse.com.vn/ws`), chính thức xóa bỏ hoàn toàn các giải pháp đường hầm tạm bợ (Ngrok, Cloudflared).

#### 🎯 Bài test Pass Giai đoạn 5 (Dự kiến trong tương lai):
- 50 thiết bị ESP32 kết nối đồng thời 24/7 trong 7 ngày liên tục: Tỷ lệ mất kết nối < 0.1%, độ trễ mạng trong nước < 25ms, máy chủ hoạt động ổn định không rò rỉ RAM (Zero Memory Leak).

---

### 5.8 Bảng ma trận nghiệm thu các giai đoạn (Master Verification Matrix)

Bảng đối chiếu tiêu chí chất lượng bắt buộc phải đạt được trước khi chuyển giao giữa các giai đoạn:

| Giai đoạn | Tên Giai đoạn | Trọng tâm can thiệp | Bài Test Pass Bắt Buộc | Chỉ số Pass (KPI) | Trạng thái |
| :---: | :--- | :--- | :--- | :--- | :---: |
| **GĐ 0** | **Clean Slate & Architecture Setup** | Git branching, khung thư mục `core/extensions/` | **Baseline Clean Server Startup Test** | Khởi động sạch, 0 lỗi import, bắt tay WebSocket thành công | ✅ **ĐÃ PASS** |
| **GĐ 1** | **MCP Dynamic Passthrough & No-Fake** | `mcp_client.py`, `schema_adapter/sanitizer.py` | **MCP Dynamic Schema & Truthful State Test** | 0 lỗi Groq 400; 100% không nói dối khi phần cứng lỗi | ⏳ **Sẵn sàng thực hiện** |
| **GĐ 2** | **Defensive Stream Guard** | `stream_guard/{buffer, detector}.py` | **Zero-Leakage Stress Test** | 0.0% ký tự JSON/XML rò rỉ ra Loa & LCD; phục hồi tool ngầm | ⏳ Chờ GĐ 1 |
| **GĐ 3** | **Vietnamese Semantic Router** | `intent_router/{normalizer, matcher}.py` | **Semantic Accuracy & Dialect Test** | Độ chính xác định tuyến >= 96%; 0% câu lệnh quạt bị nhầm | ⏳ Chờ GĐ 2 |
| **GĐ 4** | **PiperTTS & Audio Pipeline Integration** | `piper.py`, VAD, local YouTube relay | **End-to-End Latency & Smoothness Test** | Độ trễ E2E < 550ms; phát âm tiếng Việt chuẩn, không giật | ⏳ Chờ GĐ 3 |
| **GĐ 5** | **Docker Production & Cloud VN** | Docker Compose, Nginx SSL, VPS Viettel/FPT | **24/7 Concurrency Cloud Test** | 50 thiết bị chạy ổn định 7 ngày; WSS domain riêng, bỏ Ngrok | ⏸️ **TẠM HOÃN** |

---

## 6. TIÊU CHUẨN ĐÁNH GIÁ SAU TÁI CẤU TRÚC (ACCEPTANCE CRITERIA)

Một Backend đạt chuẩn Production tại Việt Nam phải vượt qua 5 bài kiểm tra nghiệm thu khắt khe sau:

1. **Tiêu chuẩn "Không rò rỉ" (Zero Syntax Leakage):** Trò chuyện 100 lượt liên tục (bao gồm cả các câu lệnh timeout, chào tạm biệt, hủy lệnh), tuyệt đối không xuất hiện 1 ký tự JSON hay XML nào trên màn hình LCD và loa.
2. **Tiêu chuẩn "Nói thật làm thật" (No Fake Actions):** Bất cứ khi nào loa nói *"Đã bật/tắt..."* thì thiết bị phần cứng (hoặc quạt Sunhouse) **bắt buộc 100% phải thay đổi trạng thái thật**. Nếu tool không chạy, loa phải báo lỗi kết nối.
3. **Tiêu chuẩn "Bảo toàn Schema" (Transparent MCP):** Firmware ESP32 nạp thêm bất kỳ tool mới nào (ví dụ: `rice_cooker_cook`), Backend tự động nhận diện và LLM gọi được ngay mà không cần sửa 1 dòng code Python nào.
4. **Tiêu chuẩn "Tốc độ phản hồi" (Low Latency):** Thời gian từ khi người dùng dứt câu nói đến khi loa phát tiếng đạt **dưới 600ms** (ở môi trường mạng Việt Nam).
5. **Tiêu chuẩn "Độc lập hạ tầng" (Zero-Ngrok):** Hệ thống chạy liên tục 24/7 trên Docker mà không phụ thuộc vào bất kỳ cửa sổ dòng lệnh hay máy tính cá nhân nào (Sau khi triển khai GĐ5).

---

## 7. CHIẾN LƯỢC "ĐẬP ĐI XÂY LẠI" (CLEAN REBASE TỪ GITHUB): ĐÁNH GIÁ CHUYÊN SÂU

### 7.1 Có nên xóa code cũ và làm lại từ bản gốc GitHub không?
👉 **CÂU TRẢ LỜI LÀ: RẤT NÊN VÀ ĐÂY LÀ QUYẾT ĐỊNH CỰC KỲ SÁNG SUỐT!**

Trong kỹ thuật phần mềm chuyên nghiệp, khi một hệ thống đã có tới 22 file bị sửa đổi chéo với hàng ngàn dòng code vá víu, việc tiếp tục ngồi "vá đè lên miếng vá" sẽ dẫn tới **hiệu ứng tuyết lăn (Snowball Effect)**:
- Bạn sửa được lỗi này thì vô tình làm vỡ một logic khác (Regression Bug).
- Bạn không còn nhớ được đâu là code chuẩn mực của tác giả gốc, đâu là đoạn code do mình chèn thêm để chữa cháy.
- Code gốc của XiaoZhi trên GitHub (`xinnan-tech/xiaozhi-esp32-server`) là một kiến trúc rất đẹp, sạch sẽ và mạch lạc. Lỗi không nằm ở mã nguồn gốc, mà nằm ở việc chúng ta trong quá trình thử nghiệm đã nhồi nhét quá nhiều logic nghiệp vụ riêng lẻ vào giữa các hàm xử lý luồng cốt lõi.

### 7.2 Quy trình thực hiện "Clean Rebase" an toàn 100% (Không bao giờ mất code cũ)
Chúng ta hoàn toàn không cần phải xóa mất dữ liệu một cách mạo hiểm, mà sử dụng Git để quản lý chuyên nghiệp:
1. **Bước 1: Tạo nhánh lưu trữ hiện trạng (Archive Branch):**
   ```bash
   git branch backup-current-patched-server
   ```
   Toàn bộ mã nguồn hiện tại, các file `.config.yaml`, các hàm đã viết đều được đóng băng an toàn vĩnh viễn trên nhánh này. Bất cứ lúc nào cần copy lại đều mở ra xem được.
2. **Bước 2: Tạo nhánh làm việc mới từ bản gốc sạch của GitHub:**
   ```bash
   git checkout -b clean-refactor-v2 origin/main
   ```
   Ngay lập tức, bạn có trong tay 100% mã nguồn gốc nguyên bản, sạch sẽ, không một vết vá víu.
3. **Bước 3: Tích hợp từng module đã tinh lọc (Clean Modular Integration):**
   Mang các công thức đã thành công từ nhánh cũ sang nhưng **đóng gói thành các module độc lập**, tuyệt đối không chắp vá vào giữa các file lõi:
   - Module PiperTTS tiếng Việt độc lập.
   - Module Dynamic Schema Sanitizer độc lập.
   - Module Stream Guard độc lập.

---

## 8. BẢNG ĐỐI CHIẾU THÀNH BẠI: NHỮNG GÌ CẦN GIỮ LẠI VS NHỮNG GÌ PHẢI VỨT BỎ

Bảng tổng hợp này đóng vai trò là **Sổ tay kim chỉ nam** cho quá trình tái thiết kế server mới:

| Hạng mục / Tính năng | Hiện trạng ở Server cũ | Đánh giá chuyên môn | Hướng xử lý ở Server mới |
| :--- | :--- | :--- | :--- |
| **PiperTTS Tiếng Việt Offline** | Đã cấu hình chạy được offline trên PC, độ trễ thấp ~100ms. | 🟢 **THÀNH CÔNG (CẦN GIỮ LẠI)** | Mang module `piper.py` và model giọng đọc sang bản mới, viết adapter sạch sẽ theo chuẩn `BaseTTS`. |
| **SileroVAD (Voice Activity)** | Bắt khoảng dừng giọng nói nhạy, chạy local offline ổn định. | 🟢 **THÀNH CÔNG (CẦN GIỮ LẠI)** | Kế thừa nguyên vẹn cấu hình VAD sang file `.config.yaml` mới. |
| **Hạ tầng YouTube Relay (`audio_stream_relay`)** | Trích xuất stream MP3 128kbps ổn định cho ESP32. | 🟢 **THÀNH CÔNG (CẦN GIỮ LẠI)** | Giữ lại service Node.js này, nhưng tích hợp gọi trực tiếp qua port nội bộ, không phụ thuộc Vercel. |
| **Bảo toàn Groq Schema Nullable** | Đã tìm ra cơ chế `type: [type, "null"]` giúp Groq không báo lỗi 400. | 🟢 **BÀI HỌC QUÝ (KẾ THỪA CHUẨN HÓA)** | Viết thành 1 hàm generic duy nhất trong `unified_tool_manager.py`. Tự động áp dụng cho mọi tool động mà không cần hardcode `if tool_name`. |
| **Fast-Router Regex (`fast_router.py`)** | Hàng chục dòng regex bắt lỗi chính tả (`mật quạc`, `tăng lông lượng`...). | 🔴 **HỎNG / VỨT BỎ (DISCARD)** | **Xóa bỏ hoàn toàn.** Thay thế bằng bộ tiền xử lý ngữ âm chuẩn (Phonetic Normalizer) hoặc bộ phân loại ý định gọn nhẹ. |
| **Hardcode "Địa Đàng" & Quạt vào lõi** | Kiểm tra cứng tên tool `play_online_music` và gán cứng tên bài hát trong lõi Python. | 🔴 **CẨU THẢ / VỨT BỎ (DISCARD)** | **Xóa bỏ hoàn toàn.** Backend chỉ chuyển tiếp nguyên vẹn mô tả từ ESP32; bài hát mặc định được giải quyết tại ESP32 firmware hoặc trong prompt sạch. |
| **Cắt xén Schema (`desc[:160]`)** | Tự tiện cắt cụt mô tả công cụ còn 160 ký tự trong `mcp_client.py`. | 🔴 **SAI BẢN CHẤT / VỨT BỎ (DISCARD)** | **Xóa bỏ hoàn toàn.** Giữ nguyên 100% mô tả từ ESP32 gửi lên để LLM hiểu đầy đủ ngữ cảnh khi nào cần gọi tool. |
| **Vá lỗi rò rỉ JSON rải rác** | Đặt regex lọc markdown và bẫy lỗi ở 4 file khác nhau (`tts.py`, `base.py`, `connection.py`...). | 🔴 **CHẮP VÁ / VỨT BỎ (DISCARD)** | **Xóa bỏ các đoạn vá rải rác.** Thay thế bằng một màng lọc đệm thông minh tập trung (`stream_guard.py`) trước khi text tới hàng đợi TTS. |
| **Rác nhị phân & file test trôi nổi** | `ffmpeg.exe`, `opus.dll`, `scratch/`, `test_handshake.py` nằm lẫn trong repo. | 🔴 **RÁC PHÁT TRIỂN / DỌN SẠCH** | Không lưu binary Windows lẫn vào thư mục code, quản lý thư viện chuẩn qua `requirements.txt`. |
