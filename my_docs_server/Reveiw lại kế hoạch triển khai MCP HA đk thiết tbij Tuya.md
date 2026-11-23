# BÁO CÁO PHẢN BIỆN KIẾN TRÚC & CHỈ THỊ HIỆU CHỈNH TÀI LIỆU KẾ HOẠCH TRIỂN KHAI MCP SMART HOME (CHUẨN MP)

> **DÀNH CHO AI CODING AGENT / TECHNICAL WRITER AGENT:**
> Tài liệu này chứa toàn bộ đánh giá kỹ thuật chuyên sâu và danh sách các yêu cầu sửa đổi (Change Requests) đối với tài liệu gốc: `KẾ HOẠCH TRIỂN KHAI MCP HOME ASISSTANT SERVER điều khiển thiết bị IoT hãng Tuya.md`.
> **Nhiệm vụ của Agent:** Đọc kỹ các phân tích dưới đây, giữ nguyên các ưu điểm cốt lõi của kiến trúc đã chọn và thực hiện cập nhật, bổ sung vào đúng các mục tương ứng trong tài liệu kế hoạch gốc.

---

## 1. ĐÁNH GIÁ TỔNG QUAN & CÁC ĐIỂM SÁNG KIẾN TRÚC (GIỮ NGUYÊN)

Quyết định lựa chọn **Kiến trúc Hybrid Cloud-to-Cloud qua Server-side MCP** trong tài liệu gốc là **hoàn toàn chính xác và thực tế nhất** cho bài toán sản xuất hàng loạt (Mass Production - MP). Các nguyên tắc thiết kế dưới đây rất xuất sắc và **bắt buộc phải giữ nguyên** khi hiệu chỉnh tài liệu:

1. **Bảo toàn tuyệt đối tài nguyên biên (ESP32-S3 Thin Client):**
   * Trên ESP32-S3, các tác vụ DSP âm thanh (AEC, VAD), giải mã Opus và nhận diện Wake Word đã tiêu tốn phần lớn băng thông bộ nhớ và chu kỳ CPU.
   * Việc giữ ESP32 làm Voice Endpoint mỏng và đẩy toàn bộ logic MCP lên Server giúp loại bỏ hoàn toàn nguy cơ phân mảnh bộ nhớ (Heap Fragmentation) do phải duy trì nhiều phiên TLS/HTTPS tới các Cloud khác nhau, đồng thời giữ chi phí BOM tăng thêm ở mức $0\text{ VNĐ}$.
2. **Tư duy Sản phẩm (Product UX) sắc bén đối với bài toán App Lily + Phicomm R1 (Mục 2.4):**
   * Phân tích rất chuẩn xác cơ chế QR-Ticket và PIN Pairing của App Lily, đồng thời chỉ ra đúng 2 điểm yếu chí mạng đối với người dùng phổ thông: bất cập khi chỉ có 1 điện thoại để quét mã QR và lỗi không tự đồng bộ khi đổi tên thiết bị.
   * Giải pháp kết hợp **Dual Authorization Flow** (OAuth2 Webview + QR Ticket) và tận dụng màn hình **OLED $128\times 64$** có sẵn trên mạch Xiaozhi để hiển thị PIN/QR là hướng tiếp cận tối ưu.
3. **Giải quyết gọn bài toán NAT Traversal cho Home Assistant (Mục 3.1 & 5.3):**
   * Thiết kế **Reverse WebSocket MCP Bridge** (`/xiaozhi/v1/ha/tunnel`) để Home Assistant của khách hàng chủ động mở kết nối lên Server giúp loại bỏ hoàn toàn việc bắt người dùng mở port modem (Port Forwarding) hoặc mua Nabu Casa.
4. **Cô lập lỗi (Fault Isolation) bảo vệ luồng thoại (Mục 4.1.4):**
   * Tách biệt cổng WebSocket của Home Assistant khỏi cổng WebSocket truyền luồng thoại Opus (`/xiaozhi/v1/`), kết hợp với `asyncio.wait_for(..., timeout=1.5)` (Hard Timeout $1.5\text{s}$) ở tầng Dispatcher là thiết kế chuẩn mực để đảm bảo sự cố mạng IoT không bao giờ làm treo luồng TTS/STT của loa.

---

## 2. PHÂN TÍCH 6 "ĐIỂM MÙ" KỸ THUẬT & RỦI RO VẬN HÀNH CẦN KHẮC PHỤC

Dù định hướng kiến trúc đúng, bản kế hoạch gốc đang tồn tại **6 điểm nghẽn thực tế** có thể gây lỗi hệ thống hoặc đội chi phí vận hành khi đưa vào Mass Production (MP):

### ⚠️ Điểm mù 1: "Bẫy" chi phí Tuya Cloud API và lỗi thiết kế Auto-Sync Polling Worker (Giai đoạn 2 - Mục 2.1.5)
* **Hiện trạng trong tài liệu gốc:** Mục 2.1.5 đề xuất xây dựng *Background Device Auto-Sync Worker* chạy định kỳ gọi API Tuya để đồng bộ danh mục thiết bị về `device_cache` nhằm khắc phục nhược điểm đổi tên thiết bị của App Lily.
* **Rủi ro thực tế:** Chính sách tính phí của Tuya Cloud Enterprise rất đắt đỏ theo số lượng API Call và số lượng thiết bị kích hoạt. Nếu hệ thống có $10.000$ người dùng và Worker chạy polling định kỳ (ví dụ mỗi $5 - 10\text{ phút/lần}$), hệ thống sẽ đốt sạch hạn ngạch (Quota) API của Tuya, gây thiệt hại lớn về OPEX và bị dính Rate Limit ngay lập tức.
* **Giải pháp khắc phục:** Tuyệt đối **không dùng Polling Worker** quét định kỳ. Phải chuyển sang cơ chế **Event-Driven (Hướng sự kiện)** thông qua **Tuya Message Service (Apache Pulsar / WebSocket)** để nhận sự kiện Push (`nameUpdate`, `deviceBind`, `deviceUnbind`) theo thời gian thực khi người dùng thao tác trên app Smart Life, kết hợp với cơ chế **Lazy Sync** (chỉ gọi API đồng bộ khi người dùng mở App Sunhouse hoặc khi xảy ra Cache Miss/lỗi điều khiển).

### ⚠️ Điểm mù 2: Rào cản quyền hạn OAuth2 / QR-Ticket của hệ sinh thái Tuya Smart Life (Giai đoạn 1 & 2)
* **Hiện trạng trong tài liệu gốc:** Tài liệu giả định chỉ cần đăng ký tài khoản trên `iot.tuya.com` và tạo Cloud Project là có thể dùng OAuth2 liên kết tài khoản Smart Life hoặc dùng API `POST /v1.0/token/qr/create` cho mọi người dùng cuối.
* **Rủi ro thực tế:** Tuya kiểm soát rất chặt việc ứng dụng bên thứ 3 truy cập vào hệ sinh thái App **Smart Life** chính chủ. Nếu không đăng ký gói OEM App hoặc cổng Voice Third-Party chính thức (như Google Home/Alexa), tài khoản Smart Life của người dùng phổ thông có thể bị từ chối quyền quét QR hoặc OAuth2 vào Project (trừ khi người dùng tự link tài khoản vào Cloud Project ở chế độ Developer).
* **Giải pháp khắc phục:** Bổ sung bước **Kiểm chứng Pháp lý & Quyền hạn API (PoC Gate)** ngay tuần đầu tiên của **Giai đoạn 1**: Thực hiện kiểm thử cơ chế `/v1.0/token/qr/create` và OAuth2 với một tài khoản Smart Life thương mại độc lập để xác nhận chính sách cấp phép của Tuya trước khi phát triển toàn bộ Backend.

### ⚠️ Điểm mù 3: Thuật toán Fuzzy Matching tại Dispatcher sẽ thất bại với ngôn ngữ tự nhiên tiếng Việt (Giai đoạn 4 - Mục 4.1.2)
* **Hiện trạng trong tài liệu gốc:** LLM trích xuất tham số `device_name` (chuỗi văn bản) và `room`, sau đó `dispatch_command()` dùng thuật toán so khớp chuỗi không dấu (Fuzzy Matching) với `device_cache`.
* **Rủi ro thực tế:** Ngôn ngữ tự nhiên của người Việt rất đa dạng về từ đồng nghĩa. Ví dụ: Trên app Smart Life, người dùng đặt tên công tắc là *"Lộ đèn 1"* hoặc *"Quạt Toshiba"*, nhưng khi ra lệnh giọng nói lại gọi là *"Bật đèn chùm phòng khách"* hoặc *"Bật cái quạt cây"*. Thuật toán Fuzzy Matching (Levenshtein/Jaro-Winkler) trên chuỗi không dấu sẽ thất bại hoàn toàn trong trường hợp này, làm tỷ lệ nhận diện rơi xuống dưới mức $95\%$ yêu cầu ở Giai đoạn 5.
* **Giải pháp khắc phục:** Thay thế hoặc bổ trợ Fuzzy Matching bằng kỹ thuật **Dynamic Context Injection (Tiêm ngữ cảnh động)**. Vì `device_cache` của user đã nằm sẵn trong RAM (TTL $10\text{ phút}$), ngay khi khởi tạo phiên hội thoại của loa, hệ thống tiêm danh sách thiết bị rút gọn của user đó (`[device_id, device_name, room, platform, category]`) vào System Prompt hoặc mô tả công cụ `smarthome_control`. Nhờ đó, chính LLM sẽ thực hiện đối sánh ngữ nghĩa (Semantic Matching) và trả về thẳng mã `device_id` chính xác trong lệnh Function Call.

### ⚠️ Điểm mù 4: Sự phân mảnh Data Point (DP) của thiết bị Tuya (Giai đoạn 2 - Mục 2.1.3)
* **Hiện trạng trong tài liệu gốc:** Xây dựng `Command Normalizer` ánh xạ tĩnh ý định sang các mã DP cố định như `switch_1`, `switch_led`, `bright_value`, `fan_speed`.
* **Rủi ro thực tế:** Các nhà máy sản xuất thiết bị Tuya (công tắc nhiều nút, quạt trần đèn, rèm cửa, điều hòa hồng ngoại) đặt mã DP rất khác nhau (`switch_1`, `switch`, `power`, `work_mode`, `bright_value_v2`, `percent_control`...). Nếu chỉ map cứng vài mã cơ bản, hệ thống sẽ không điều khiển được khoảng $30\% - 40\%$ thiết bị ngoài thị trường.
* **Giải pháp khắc phục:** Tận dụng triệt để cột `raw_schema` đã thiết kế trong bảng `device_cache` ở Giai đoạn 1. Khi đồng bộ thiết bị mới, gọi API `/v1.0/iot-03/devices/{device_id}/specification` của Tuya để lấy và lưu trữ toàn bộ tập lệnh chuẩn (Standard Instruction Set & DP Schema) của thiết bị đó vào `raw_schema`. Module `Command Normalizer` sẽ đọc `raw_schema` của từng `device_id` để ánh xạ lệnh động thay vì dùng từ điển tĩnh.

### ⚠️ Điểm mù 5: Bài toán Scale ngang (Multi-Node / High Availability) cho đường hầm Home Assistant (Giai đoạn 3 - Mục 3.1.2)
* **Hiện trạng trong tài liệu gốc:** Lưu đối tượng kết nối WebSocket của Home Assistant vào biến bộ nhớ cục bộ trên tiến trình server: `active_ha_tunnels[user_id] = websocket_conn`.
* **Rủi ro thực tế:** Thiết kế In-memory Dictionary này chỉ hoạt động khi hệ thống chạy trên **1 Server Node duy nhất**. Khi triển khai Mass Production phục vụ hàng vạn thiết bị, hệ thống bắt buộc phải chạy kiến trúc phân tán gồm nhiều node `xiaozhi-server` đặt sau Load Balancer. Khi đó, Home Assistant của khách hàng có thể đang kết nối WebSocket vào **Server Node A**, nhưng luồng thoại của Loa ESP32 lại được Load Balancer điều phối vào **Server Node B** (nơi biến `active_ha_tunnels[user_id]` không tồn tại).
* **Giải pháp khắc phục:** Bổ sung **Redis Pub/Sub Message Bus** vào kiến trúc Giai đoạn 3. Khi Server Node B cần gửi lệnh JSON-RPC cho `user_id`, nếu không tìm thấy socket cục bộ, nó sẽ publish bản tin lên kênh Redis `ha_tunnel:cmd:{user_id}` để Server Node A (đang giữ kết nối WebSocket thật) chuyển tiếp xuống Home Assistant và trả kết quả về qua kênh `ha_tunnel:res:{request_id}`.

### ⚠️ Điểm mù 6: Chưa rõ lộ trình chuyển đổi Sunhouse IoT và định nghĩa KPI độ trễ chưa sát thực tế (Giai đoạn 4 & 5)
* **Xung đột kiến trúc Sunhouse IoT:**
  * Mục 1.1 nêu hệ thống hiện tại đang điều khiển thiết bị Sunhouse qua **MCP Device-side (`sunhouse_mcp_tools.cc`)** ngay trên ESP32.
  * Mục 4.2 và 4.3 lại thiết kế điều khiển thiết bị Sunhouse từ **Xiaozhi Backend Server qua AWS IoT Core**.
  * Tuy nhiên, trong 5 giai đoạn triển khai chưa có hạng mục viết `AWSIoTPublisher` trên Server cũng như cơ chế vô hiệu hóa/đồng bộ với `sunhouse_mcp_tools.cc` dưới Firmware để tránh việc LLM nhìn thấy 2 công cụ trùng lặp cùng điều khiển thiết bị Sunhouse.
* **Sai lệch định nghĩa KPI độ trễ (Giai đoạn 5):**
  * Bảng tiêu chí nghiệm thu yêu cầu: *"Tổng thời gian phản xạ (Dứt câu nói $\rightarrow$ Thiết bị nhảy trạng thái) cho Tuya qua Cloud $< 900\text{ms}$"*.
  * Về mặt vật lý, tổng thời gian từ lúc **dứt câu nói (End-of-Speech)** bao gồm:
    $$\text{Tổng độ trễ} = t_{\text{VAD}} (\approx 250\text{ms}) + t_{\text{STT}} (\approx 300\text{ms}) + t_{\text{LLM}} (\approx 600\text{ms}) + t_{\text{Tuya API}} (\approx 350\text{ms}) + t_{\text{MQTT}} (\approx 100\text{ms}) \approx 1.600\text{ms}$$
  * Do đó, con số $< 900\text{ms}$ chỉ đúng nếu đo riêng **Độ trễ thực thi tầng MCP Tool (Tool Execution Latency)** tính từ lúc Server nhận Function Call từ LLM cho đến khi thiết bị nhảy trạng thái. Cần tách rõ 2 chỉ số này trong bảng nghiệm thu để đội Dev và QA có cơ sở đo lường chính xác.

---

## 3. CHỈ THỊ HIỆU CHỈNH CHI TIẾT CHO AGENT CODE (ACTIONABLE SPECS)

Agent cần thực hiện cập nhật trực tiếp vào file `KẾ HOẠCH TRIỂN KHAI MCP HOME ASISSTANT SERVER điều khiển thiết bị IoT hãng Tuya.md` theo từng hạng mục dưới đây:

### 🛠️ Chỉ thị 1: Cập nhật Giai đoạn 1 (Mục 5.1)
1. **Tại mục 1.1.1 (Khởi tạo Dự án Tuya Cloud Enterprise):**
   * Bổ sung hạng mục **PoC Kiểm chứng Quyền hạn Liên kết Tài khoản (Account Linking Gate)**: Kiểm thử thực tế luồng OAuth2 và API `POST /v1.0/token/qr/create` với tài khoản ứng dụng Smart Life thương mại độc lập, xác nhận gói dịch vụ Tuya Cloud (Smart Home PaaS / Voice Integration) hỗ trợ quét QR ủy quyền cho người dùng cuối mà không cần thêm tài khoản thủ công vào Developer Console.
2. **Tại mục 1.1.2 (Thiết kế CSDL Multi-Tenant):**
   * Giữ nguyên bảng `device_cache`, nhấn mạnh trường `raw_schema` (kiểu JSONB trên PostgreSQL) dùng để lưu trữ toàn bộ `Standard Instruction Set` và `DP Specification` của từng thiết bị phục vụ ánh xạ lệnh động.

### 🛠️ Chỉ thị 2: Cập nhật Giai đoạn 2 (Mục 5.2)
1. **Tại mục 2.1.2 (Hiện thực Bộ API Nghiệp vụ Bất đồng bộ):**
   * Bổ sung hàm lấy đặc tả kỹ thuật thiết bị:
     `async def get_device_specification(device_id, access_token) -> Dict[str, Any]` (gọi endpoint `/v1.0/iot-03/devices/{device_id}/specification`).
2. **Tại mục 2.1.3 (Xây dựng Bộ Chuẩn hóa Lệnh Thiết bị - Command Normalizer):**
   * Sửa đổi từ cơ chế ánh xạ tĩnh sang **Ánh xạ động dựa trên Schema (Schema-Driven Command Normalization)**:
     * Khi nhận ý định điều khiển (`turn_on`, `set_level`, `set_temperature`...), Normalizer đọc `raw_schema` của `device_id` trong `device_cache` để tự động chọn đúng mã DP tương ứng của thiết bị đó (ví dụ: tự động nhận biết thiết bị dùng `switch_1`, `switch_led`, hay `power_go`).
     * Tự động quy đổi miền giá trị (Value Scaling) dựa vào cấu hình `min`, `max`, `scale`, `step` được định nghĩa trong `raw_schema` của thiết bị (tránh gán cứng dải $[10 - 1000]$ vì nhiều đèn Tuya dùng dải $[1 - 100]$ hoặc $[0 - 255]$).
3. **Tại mục 2.1.5 (Xây dựng Background Device Auto-Sync Worker):**
   * **Đổi tên và sửa lại nội dung mục 2.1.5** thành: **Cơ chế Đồng bộ Thiết bị Hướng Sự Kiện (Event-Driven Sync & Lazy Refresh - Tối ưu chi phí OPEX)**:
     * Loại bỏ cơ chế Polling định kỳ toàn bộ người dùng để tránh vượt hạn ngạch (Rate Limit) và tiết kiệm chi phí API Tuya Cloud.
     * Tích hợp **Tuya Message Service Consumer (WebSocket / Pulsar Client)** lắng nghe các sự kiện thay đổi từ Tuya Cloud (`nameUpdate`, `deviceBind`, `deviceUnbind`, `reset`) để cập nhật tức thời vào `device_cache` đúng của `user_id` phát sinh sự kiện.
     * Bổ sung cơ chế **Lazy Sync**: Tự động kích hoạt đồng bộ lại danh mục thiết bị khi người dùng mở trang Quản lý Nhà thông minh trên App Sunhouse hoặc khi lệnh điều khiển trả về mã lỗi `device_not_found` / `token_invalid`.

### 🛠️ Chỉ thị 3: Cập nhật Giai đoạn 3 (Mục 5.3)
1. **Tại mục 3.1.2 (Cơ chế Bắt tay & Định danh Đường hầm) & 3.1.3 (MCP Forwarder):**
   * Bổ sung thiết kế **Hỗ trợ Phân tán Đa Máy Chủ (Multi-Node Redis Pub/Sub Bridge)**:
     * Ngoài bảng băm cục bộ `local_ha_tunnels[user_id] = websocket_conn` trên từng worker node, đăng ký trạng thái node giữ kết nối vào Redis (`ha:session:{user_id} -> node_id`).
     * Khi `MCP Forwarder` tại một node bất kỳ cần gửi lệnh JSON-RPC xuống Home Assistant của `user_id`, nếu kết nối nằm ở node khác, hệ thống chuyển tiếp bản tin qua **Redis Pub/Sub** (`channel: ha:cmd:{node_id}`) với thời gian chờ phản hồi nội bộ $< 15\text{ms}$, đảm bảo hệ thống sẵn sàng mở rộng ngang (Horizontal Scaling) sau Load Balancer.

### 🛠️ Chỉ thị 4: Cập nhật Giai đoạn 4 (Mục 5.4)
1. **Tại mục 4.1.1 (Thiết kế Schema Function Calling cho LLM) & 4.1.2 (Bộ Định Tuyến Thông Minh):**
   * Thay thế phương pháp chỉ dựa vào Fuzzy Matching bằng cơ chế kết hợp **Dynamic Context Injection (Tiêm danh mục thiết bị động vào Context) + Fallback Fuzzy Matching**:
     * Ngay khi Loa ESP32 bắt đầu phiên kết nối, hệ thống lấy danh sách thiết bị đang hoạt động của `user_id` từ `device_cache` trong RAM và tiêm danh sách rút gọn vào ngữ cảnh của LLM dưới định dạng nén:
       ```json
       [
         {"id": "tuya_bf82a1", "name": "Đèn chùm", "room": "Phòng khách", "platform": "tuya", "type": "light"},
         {"id": "sh_kettle_01", "name": "Bình đun nước", "room": "Phòng bếp", "platform": "sunhouse", "type": "kettle"},
         {"id": "ha_light.bed", "name": "Đèn ngủ", "room": "Phòng ngủ", "platform": "ha", "type": "light"}
       ]
       ```
     * Bổ sung trường `device_id` (string, preferred) vào Schema của tool `smarthome_control`:
       ```json
       {
         "name": "smarthome_control",
         "description": "Điều khiển các thiết bị nhà thông minh của người dùng dựa trên danh mục thiết bị đã cung cấp.",
         "parameters": {
           "type": "object",
           "properties": {
             "device_id": {
               "type": "string",
               "description": "Mã định danh chính xác của thiết bị lấy từ danh sách thiết bị của nhà người dùng (ưu tiên bắt buộc nếu tìm thấy thiết bị tương ứng)."
             },
             "device_name": {
               "type": "string",
               "description": "Tên thiết bị người dùng gọi trong câu lệnh."
             },
             "action": {
               "type": "string",
               "enum": ["turn_on", "turn_off", "set_level", "set_color", "set_temperature", "set_mode", "query_status"]
             },
             "value": {
               "type": ["string", "number", "boolean"],
               "description": "Giá trị điều chỉnh (ví dụ: độ sáng 0-100, nhiệt độ 16-30, màu sắc...)"
             },
             "room": {
               "type": "string",
               "description": "Vị trí phòng nếu người dùng đề cập."
             }
           },
           "required": ["device_name", "action"]
         }
       }
       ```
     * Trong `dispatch_command()`: Nếu LLM đã phân giải được `device_id` hợp lệ, Dispatcher định tuyến trực tiếp trong $O(1)$ tới Client tương ứng (`Tuya`, `Sunhouse AWS IoT`, hoặc `HA Tunnel`). Chỉ khi `device_id` trống hoặc không khớp mới kích hoạt thuật toán Fuzzy Matching không dấu làm lớp dự phòng (Fallback).
2. **Bổ sung mục 4.1.5: Đồng bộ lộ trình chuyển đổi Sunhouse IoT (Device-side sang Server-side):**
   * Xây dựng adapter `SunhouseAWSIoTClient` trên Server để thống nhất quản lý thiết bị Sunhouse cùng với Tuya và Home Assistant.
   * Cấu hình cờ (Feature Flag) để khi phiên kết nối đã bật `smarthome_control` (Server-side MCP), hệ thống tự động ẩn hoặc bỏ qua nhóm công cụ điều khiển IoT trùng lặp dưới Firmware (`sunhouse_mcp_tools.cc`), tránh hiện tượng LLM gọi nhầm giữa Device-side MCP và Server-side MCP.

### 🛠️ Chỉ thị 5: Cập nhật Bảng Tiêu Chí Nghiệm Thu Giai đoạn 5 (Mục 5.5)
Chuẩn hóa lại mục **2. Thời gian phản xạ** trong bảng `BẢNG TIÊU CHÍ NGHIỆM THU XUẤT XƯỞNG TOÀN DIỆN (ACCEPTANCE CRITERIA)` để phân tách rõ độ trễ thực thi của tầng MCP Tool và độ trễ toàn trình:

```text
┌────────────────────────────────────────────────────────────────────────┐
│ BẢNG TIÊU CHÍ NGHIỆM THU XUẤT XƯỞNG TOÀN DIỆN (ĐÃ HIỆU CHỈNH CHUẨN MP) │
├────────────────────────────────────────────────────────────────────────┤
│ 1. Độ chính xác nhận diện thiết bị & ý định giọng nói (Semantic Match):│
│    • Câu lệnh gọi tên trực tiếp hoặc từ đồng nghĩa phổ biến:   >= 95%  │
│ 2A. Độ trễ thực thi tầng MCP Tool (Từ lúc LLM xuất Function Call       │
│     đến khi Thiết bị nhận lệnh nhảy trạng thái):                       │
│    • Thiết bị Tuya qua Cloud OpenAPI:                          < 600ms │
│    • Thiết bị Home Assistant qua Reverse WebSocket Tunnel:     < 350ms │
│    • Thiết bị Sunhouse qua AWS IoT Core:                       < 450ms │
│ 2B. Tổng thời gian phản xạ toàn trình (Từ lúc người dùng dứt câu nói   │
│     qua VAD -> STT -> LLM -> MCP Tool -> Thiết bị nhảy trạng thái):    │
│    • Toàn bộ các nền tảng (trong điều kiện mạng bình thường):  < 1800ms│
│ 3. Khả năng bảo toàn hệ thống (Zero-Breaking Impact):                  │
│    • Tính năng nghe nhạc trực tuyến (Zing MP3 / YouTube):       100%   │
│    • Tính năng nghe Radio trực tuyến (VOV / VOH):               100%   │
│    • Cơ chế ngắt khẩn cấp Emergency Hard Stop khi nói chuyện:   100%   │
│ 4. Độ ổn định khi mất mạng ngoại vi (Hard Timeout 1.5s):               │
│    • Không treo Task âm thanh, không khởi động lại chip ESP32:  100%   │
│ 5. Tiêu chuẩn bảo mật & Chịu tải:                                      │
│    • Mã hóa Token chuẩn AES-256-GCM, hỗ trợ Multi-Node qua Redis.      │
└────────────────────────────────────────────────────────────────────────┘
```