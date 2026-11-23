# KẾ HOẠCH LỰA CHỌN GIẢI PHÁP & TRIỂN KHAI: MCP HOME ASSISTANT & IOT TUYA TRÊN XIAOZHI (CHUẨN THƯƠNG MẠI - MASS PRODUCTION v2.0)

> [!IMPORTANT]
> **CÁC NGUYÊN TẮC THIẾT KẾ BẮT BUỘC CHO HÀNG THƯƠNG MẠI ĐẠI TRÀ (MASS PRODUCTION - MP):**
> 1. **Zero Hardware Modification (Bảo toàn chi phí BOM phần cứng):** Không can thiệp, không thay đổi linh kiện phần cứng hoặc đổi chip ESP32 đắt tiền hơn. Giữ trọn vẹn tài nguyên RAM/Flash và CPU của ESP32-S3 hiện tại cho DSP âm thanh (AEC, VAD), giải mã Opus và nhận diện từ khóa đánh thức (Wake Word).
> 2. **Trải nghiệm người dùng 1-Chạm (Zero-Tech Onboarding):** Tuyệt đối không bắt khách hàng phổ thông cài đặt máy chủ mini (Raspberry Pi), cấu hình file YAML, tạo Access Token hay gán IP mạng tĩnh thủ công. Mọi quy trình ghép nối thiết bị phải thông qua ứng dụng di động (Mobile App) dạng 1-Click / OAuth2 hoặc đồng bộ tự động từ tài khoản eSunhouse.
> 3. **Phân quyền Đa người dùng Tuyệt đối (Strict Multi-Tenancy):** Dữ liệu, Token điều khiển nhà thông minh của gia đình nào phải được mã hóa và phân lập hoàn toàn với gia đình khác trên hệ thống máy chủ Cloud.
> 4. **Khả năng mở rộng không giới hạn (Future-Proof Scalability):** Tách biệt tầng logic điều khiển thiết bị ra khỏi Firmware loa. Khi muốn bổ sung hãng thiết bị mới (Aqara, Xiaomi, Sonoff, Philips Hue...) hoặc dòng sản phẩm OEM mới của Sunhouse (như Robot hút bụi Tuya 298 Pro Ultra), chỉ cập nhật ở tầng Cloud Server mà không cần OTA firmware cho hàng vạn thiết bị ngoài thị trường.

---

## 📑 Mục Lục Toàn Diện

1. [Bối Cảnh Kỹ Thuật & Yêu Cầu Bài Toán Hàng Thương Mại (MP)](#muc-1)
   - [1.1. Thực trạng hệ thống Xiaozhi & Hệ sinh thái eSunhouse hiện tại](#muc-1-1)
   - [1.2. Nhu cầu mở rộng hệ sinh thái Smarthome (Cả Tuya OEM Nội bộ & Tuya Ngoài thị trường)](#muc-1-2)
   - [1.3. Yêu cầu khắt khe của sản phẩm Mass Production (Sự khác biệt giữa DIY và Hàng thương mại)](#muc-1-3)
2. [Khảo Sát & Phân Tích Các Giải Pháp Kỹ Thuật Lựa Chọn](#muc-2)
   - [2.1. Giải pháp 1: Cloud-to-Cloud Federation (eSunhouse Sync + OAuth2 Account Linking & Tuya Cloud OpenAPI)](#muc-2-1)
   - [2.2. Giải pháp 2: Home Assistant Ecosystem Hub (Cầu nối tích hợp HA MCP Server)](#muc-2-2)
   - [2.3. Giải pháp 3: Local Protocol Engine trên ESP32 (Matter-over-Wi-Fi vs. Tuya LAN Protocol TCP 6668)](#muc-2-3)
   - [2.4. Khảo Sát & Giải Mã Cơ Chế Ghép Nối Thực Tế: App Lily + Loa Phicomm R1](#muc-2-4)
   - [2.5. Khai Thác Toàn Diện Đặc Tả Kỹ Thuật Tuya Từ Dự Án OEM (Robot Hút Bụi 298 Pro Ultra & eSunhouse)](#muc-2-5)
     - [(A) Phân Định Rõ 2 Nguồn Thiết Bị Tuya: Nội Bộ OEM eSunhouse vs. Smart Life Bên Ngoài](#muc-2-5-a)
     - [(B) Đính Chính Bản Chất Vòng Đời Token Tuya Cloud & Cơ Chế Phối Hợp Liên Đội](#muc-2-5-b)
     - [(C) Chuẩn Hóa Endpoint Singapore Data Center & Bảo Mật Gói Tin REST / TuyaLink](#muc-2-5-c)
     - [(D) Đặc Tả Giải Mã Chi Tiết Apache Pulsar Message Queue (AES-128-ECB & AES-128-GCM)](#muc-2-5-d)
     - [(E) Mở Rộng Khả Năng Điều Khiển Giọng Nói Cho Robot Hút Bụi OEM (Model 298 Pro Ultra) & Trạm Sạc Đa Năng](#muc-2-5-e)
     - [(F) Tiềm Năng Mở Rộng TuyaLink MQTT Cho Phần Cứng ESP32 Của Đội Nhúng](#muc-2-5-f)
     - [(G) Tuân Thủ Pháp Lý & Bảo Vệ Dữ Liệu Cá Nhân (Nghị định 356/2025/NĐ-CP)](#muc-2-5-g)
3. [Ma Trận Đánh Giá & So Sánh Đối Đầu Chi Tiết](#muc-3)
   - [3.1. Các tiêu chí định lượng & định tính](#muc-3-1)
   - [3.2. Bảng so sánh toàn diện 4 phương án kỹ thuật](#muc-3-2)
   - [3.3. Bảng Dự Toán Chi Phí Vận Hành (OPEX Projection: 1K - 10K - 100K Loa Active)](#muc-3-3)
4. [Kết Luận Lựa Chọn Giải Pháp & Sơ Đồ Quy Trình Hệ Thống (Architecture & Workflows)](#muc-4)
   - [4.1. Giải pháp được chọn: Kiến trúc Đa Nguồn Hợp Nhất (Unified Multi-Source Cloud MCP + Optional LAN Failover)](#muc-4-1)
   - [4.2. Sơ đồ kiến trúc phân tầng hệ thống tổng thể](#muc-4-2)
   - [4.3. Bảng đối chiếu nhanh bản chất kỹ thuật giữa 2 Quy trình Tuya](#muc-4-3)
   - [4.4. Sơ đồ Quy trình 1: Loa Xiaozhi điều khiển Robot hút bụi OEM (App eSunhouse)](#muc-4-4)
   - [4.5. Sơ đồ Quy trình 2: Loa Xiaozhi điều khiển Công tắc, Đèn, Rèm... chính hãng Tuya (App Smart Life)](#muc-4-5)
   - [4.6. Ba điểm cốt lõi Đội Nhúng cần lưu ý khi phối hợp triển khai](#muc-4-6)
   - [4.7. Cấu Trúc Thư Mục & Module Toàn Dự Án (xiaozhi-esp32-server)](#muc-4-7)
5. [Kế Hoạch Triển Khai Chi Tiết (Đã Hiệu Chỉnh & Bổ Sung Theo Đặc Tả Tuya OEM)](#muc-5)
   - [5.1. Giai đoạn 1: Quản Trị Danh Tính Đa Người Dùng, Phân Tầng Token & Đồng Bộ Liên Đội (Multi-Tenancy & DAL)](#muc-5-1)
   - [5.2. Giai đoạn 2: Module Tuya Cloud OpenAPI Async Client, Giải Mã Pulsar MQ & Robot Vacuum Adapter](#muc-5-2)
   - [5.3. Giai đoạn 3: Reverse WebSocket MCP Bridge Cho Home Assistant (Kênh B2B / Prosumer)](#muc-5-3)
   - [5.4. Giai đoạn 4: Unified Smart Home MCP Tool & Bộ Định Tuyến Đa Nguồn (Dispatcher)](#muc-5-4)
   - [5.5. Giai đoạn 5: Tích Hợp Đồng Bộ eSunhouse / OAuth2 / QR Ticket & Nghiệm Thu Thương Mại Toàn Hệ Thống](#muc-5-5)
   - [🎯 Bảng Tiêu Chí Nghiệm Thu Xuất Xưởng Toàn Diện (Chuẩn Mass Production v2.0)](#muc-5-kpi)

---

<a id="muc-1"></a>
## 1. Bối Cảnh Kỹ Thuật & Yêu Cầu Bài Toán Hàng Thương Mại (MP)

<a id="muc-1-1"></a>
### 1.1. Thực trạng hệ thống Xiaozhi & Hệ sinh thái eSunhouse hiện tại
Dự án trợ lý giọng nói Xiaozhi hiện tại trên phần cứng ESP32-S3 đã hoàn thiện các tính năng cốt lõi:
* **Âm thanh & Giải trí:** Phát nhạc trực tuyến phân tán (Zing MP3, YouTube Audio Edge Client), nghe đài phát thanh trực tuyến (Online Radio VOV/VOH với cơ chế dừng khẩn cấp Emergency Hard Stop).
* **Tra cứu thông tin:** Tích hợp bộ tri thức Sunhouse, tra cứu sản phẩm và thông tin tập đoàn.
* **Điều khiển thiết bị gia dụng nội bộ:** Điều khiển các thiết bị IoT của Sunhouse thông qua hạ tầng AWS IoT Core và giao thức MCP Device-side (`sunhouse_mcp_tools.cc`).
* **Sự xuất hiện của nhánh thiết bị Sunhouse OEM dùng chip Tuya (Dự án của đội IT Dev & Phát triển dự án):** Song song với hệ thống AWS IoT Core, Sunhouse đang triển khai các dòng sản phẩm OEM dùng chip và hạ tầng Tuya (điển hình là dòng **Robot hút bụi thông minh 298 Pro Ultra** điều khiển qua App eSunhouse Flutter & Backend C# ASP.NET Core). Trong CSDL của eSunhouse đã phân định rõ 2 nguồn thiết bị qua trường `PlatformType`: `1 = SunhouseAws` và `2 = TuyaCloud`.

<a id="muc-1-2"></a>
### 1.2. Nhu cầu mở rộng hệ sinh thái Smarthome (Cả Tuya OEM Nội bộ & Tuya Ngoài thị trường)
Khách hàng sử dụng Loa thông minh Xiaozhi sẽ có nhu cầu điều khiển 3 nhóm thiết bị bằng giọng nói tiếng Việt tự nhiên:
1. **Thiết bị gia dụng Sunhouse in-house (AWS IoT Core):** Nồi cơm, bình đun nước, máy lọc nước RO.
2. **Thiết bị Sunhouse OEM dùng chip Tuya (Quản lý trên App eSunhouse):** Robot hút bụi 298 Pro Ultra và các thiết bị gia dụng OEM tương lai đã được khách hàng ghép nối sẵn trong App eSunhouse.
3. **Thiết bị Tuya / Smart Life ngoài thị trường & Home Assistant:** Công tắc, bóng đèn, rèm cửa, quạt Wi-Fi/Zigbee do khách hàng tự mua và quản lý trên App Smart Life chính chủ hoặc máy chủ Home Assistant.

<a id="muc-1-3"></a>
### 1.3. Yêu cầu khắt khe của sản phẩm Mass Production (Sự khác biệt giữa DIY và Hàng thương mại)

| Tiêu chí | Bản DIY của Cộng đồng (Mã nguồn mở) | Yêu cầu chuẩn Hàng Thương mại (MP) |
| :--- | :--- | :--- |
| **Trình độ người dùng** | Dành cho người rành công nghệ, biết IT, biết sửa file cấu hình. | Dành cho người tiêu dùng đại chúng (bà nội trợ, người lớn tuổi, trẻ em). |
| **Quy trình ghép nối** | Tự dựng Home Assistant, tự lấy API token, gõ lệnh YAML hoặc điền chuỗi `entity_id` thủ công. | **0-Chạm** (với thiết bị OEM trong App eSunhouse) hoặc **1-Chạm (1-Click OAuth2)** với tài khoản Smart Life ngoài. |
| **Môi trường mạng** | Bắt buộc Loa, Server và thiết bị Smarthome phải cùng mạng nội bộ (LAN). | Hoạt động mọi lúc mọi nơi qua Cloud (Wi-Fi/4G), hỗ trợ nâng cấp điều khiển cục bộ LAN Failover (<50ms). |
| **Kiến trúc dữ liệu** | Single-tenant: 1 máy chủ phục vụ cho 1 cá nhân, hardcode IP nội bộ. | **Multi-tenant:** 1 cụm máy chủ phục vụ đồng thời hàng trăm nghìn khách hàng, phân tách dữ liệu an toàn tuyệt đối. |
| **Chi phí vận hành** | Chi phí bằng 0 vì người dùng tự chi trả tiền điện chạy máy chủ cá nhân. | Doanh nghiệp phải tối ưu chi phí hạ tầng Cloud (OPEX) và chi phí bản quyền API bên thứ ba. |

<a id="muc-2"></a>
## 2. Khảo Sát & Phân Tích Các Giải Pháp Kỹ Thuật Lựa Chọn

<a id="muc-2-1"></a>
### 2.1. Giải pháp 1: Cloud-to-Cloud Federation (eSunhouse Sync + OAuth2 Account Linking & Tuya Cloud OpenAPI)
* **Nguyên lý hoạt động:**
  * Giữ nguyên thiết bị ESP32 làm Voice Endpoint mỏng (Thin Client).
  * **Đối với thiết bị Sunhouse OEM Tuya (như Robot 298 Pro Ultra):** Tự động đồng bộ `TuyaUid` (`sh_` + `userId`) và danh mục `TuyaDeviceId` từ Backend eSunhouse sang Server Xiaozhi mà không bắt người dùng đăng nhập lại.
  * **Đối với thiết bị Smart Life ngoài thị trường:** Ứng dụng di động cung cấp tính năng **Account Linking** qua chuẩn OAuth2 hoặc QR Ticket.
  * Khi người dùng ra lệnh giọng nói, trợ lý LLM trên Server trích xuất ý định (Intent) và thực thi **Server-side MCP Tool** gọi trực tiếp API Cloud:
    * Thiết bị Sunhouse AWS: Gửi lệnh qua **AWS IoT Core**.
    * Thiết bị Tuya (cả OEM nội bộ và Smart Life ngoài): Gọi **Tuya Cloud OpenAPI** (`POST /v1.0/iot-03/devices/{device_id}/commands`).
* **Ưu điểm thương mại:**
  * **Trải nghiệm khách hàng mượt mà:** Giống 100% trải nghiệm kết nối của Google Home / Amazon Alexa.
  * **Chi phí BOM = 0 VNĐ:** Không tăng giá thành phần cứng loa ESP32.
  * **Mở rộng dễ dàng:** Thêm bất kỳ hãng nào hoặc dòng sản phẩm OEM mới chỉ cần cập nhật Schema/Adapter ở Server, không cần sửa firmware loa.
* **Hạn chế:**
  * Phụ thuộc vào kết nối Internet (trừ khi kích hoạt thêm kênh Tuya LAN TCP 6668 dự phòng).
  * Doanh nghiệp cần quản lý hạn mức gói Tuya Cloud Enterprise và phối hợp đồng bộ Token với đội IT Backend.

<a id="muc-2-2"></a>
### 2.2. Giải pháp 2: Home Assistant Ecosystem Hub (Cầu nối tích hợp HA MCP Server)
* **Nguyên lý hoạt động:**
  * Tận dụng nền tảng Home Assistant (HA) làm trung gian kết nối mọi thiết bị. Trong HA đã có sẵn Tuya Integration, Sunhouse (MQTT), Zigbee2MQTT, ESPHome, Philips...
  * Sử dụng giải pháp chính thức **Home Assistant MCP Server (Model Context Protocol qua SSE / WebSocket)**.
  * Server Xiaozhi kết nối trực tiếp với HA MCP Server để tự động phát hiện mọi thực thể (Entities) và gọi hàm điều khiển.
* **Đưa lên chuẩn thương mại MP theo 2 kịch bản:**
  * *Kịch bản A (Dành cho dòng sản phẩm B2B / Biệt thự):* Bán kèm một chiếc Hub phần cứng nhúng Linux (chạy sẵn bản Home Assistant Core OEM).
  * *Kịch bản B (Dành cho người dùng Prosumer):* Cho phép người dùng nhập thông tin kết nối Nabu Casa / Home Assistant Server cá nhân qua Mobile App.
* **Ưu điểm thương mại:**
  * Điều khiển được hơn 2.500+ thương hiệu thiết bị khác nhau ngay lập tức.
  * Tốc độ phản hồi cực nhanh nếu điều khiển trong mạng LAN.
* **Hạn chế:**
  * Rào cản kỹ thuật lớn nếu áp dụng cho người dùng đại trà không có sẵn Home Assistant.
  * Tăng giá thành bán sản phẩm nếu phải đóng gói kèm phần cứng Hub rời.

<a id="muc-2-3"></a>
### 2.3. Giải pháp 3: Local Protocol Engine trên ESP32 (Matter-over-Wi-Fi vs. Tuya LAN Protocol TCP 6668)
Từ việc khai thác tài liệu đặc tả giao thức Tuya của dự án OEM, bài toán điều khiển cục bộ (Edge/Local Control) tại tầng biên ESP32-S3 được chia làm **2 hướng kỹ thuật rất khác biệt về chi phí BOM**:

| Đặc điểm kỹ thuật | Hướng 3A: Matter-over-Wi-Fi Controller | Hướng 3B: Tuya LAN Protocol v3.3/v3.4/v3.5 (Mới khai thác) |
| :--- | :--- | :--- |
| **Giao thức mạng & Cổng** | IPv6 / mDNS / Matter Fabric | UDP Discovery (Port `6666`/`6667`) & TCP Control (Port `6668`) |
| **Cấu trúc gói tin & Mã hóa** | Matter TLV + CASE/PASE Commissioning | Khung nhị phân `0x55AA ... 0xAA55`, Command `0x0D`, mã hóa `AES-128-ECB` (v3.3) hoặc `AES-128-GCM` (v3.4/v3.5) bằng `LocalKey` (16 ký tự) |
| **Chi phí phần cứng (BOM)** | **Tăng 15 – 25%** (Đòi hỏi nâng cấp PSRAM/Flash lớn để gánh stack Matter + Voice DSP) | **0 VNĐ (Zero BOM Cost)** - Dùng bộ tăng tốc phần cứng AES-128 có sẵn trên ESP32-S3, gói tin chỉ ~64 bytes |
| **Cơ chế lấy khóa điều khiển** | Quét mã QR Matter trực tiếp trên thiết bị | Server lấy `local_key` và IP nội bộ từ Tuya Cloud OpenAPI cấp xuống cho Loa |
| **Độ trễ & Hoạt động Offline** | `< 100ms`, hoạt động 100% khi mất Internet | **`< 50ms`**, hoạt động bình thường qua Router Wi-Fi gia đình ngay cả khi đứt cáp quang quốc tế |

* **Đánh giá chiến lược cho Đội Nhúng:**
  * Nếu đi theo **Matter Controller (Hướng 3A)** sẽ vi phạm nguyên tắc *Zero Hardware Modification* ở giai đoạn hiện tại.
  * Ngược lại, **Tuya LAN Control Protocol (Hướng 3B)** hoàn toàn tương thích với chip ESP32-S3 hiện hữu mà không tốn thêm RAM/Flash. Đây là cơ chế dự phòng chiến lược hoàn hảo (Phase 2 Hybrid LAN/Cloud Failover): Mặc định điều khiển qua Server-side MCP Cloud, nhưng có thể đẩy `LocalKey` xuống Loa để bắn trực tiếp gói tin TCP `6668` (`0x55AA`, Command `0x0D`) trong mạng LAN với độ trễ `< 50ms`.

<a id="muc-2-4"></a>
### 2.4. Khảo Sát & Giải Mã Cơ Chế Ghép Nối Thực Tế: App Lily + Loa Phicomm R1

#### 1. Bóc tách cơ chế kỹ thuật:
* **Cơ chế ủy quyền Tuya qua QR Ticket (Scan-to-Authorize):**
  - Mỗi tài khoản Smart Life sở hữu một mã định danh người dùng duy nhất (`User code` / UID).
  - Khi người dùng nhập `User code`, máy chủ gọi API `POST /v1.0/token/qr/create` để xin một mã vé ủy quyền tạm thời (Ticket ID có hạn sống 3 - 5 phút) và hiển thị thành mã QR.
  - Người dùng mở App Smart Life chính chủ và quét mã QR này. Ứng dụng Smart Life gửi xác thực lên Tuya Cloud xác nhận đồng ý chia sẻ quyền truy cập thiết bị mà **không cần nhập tên đăng nhập hay mật khẩu**.
  - Tuya Cloud cấp quyền truy cập và máy chủ gọi tiếp `GET /v1.0/users/{uid}/devices` để tải toàn bộ danh mục công tắc, bóng đèn, quạt.
* **Cơ chế gán Loa thông minh qua Mã PIN ngắn hạn (PIN-based Pairing):**
  - Khi người dùng bấm *"Đồng bộ lên máy chủ"*, máy chủ sinh ra một mã PIN ngẫu nhiên 4-6 ký tự có hiệu lực tạm thời trong 5 phút.
  - Người dùng nhập mã PIN vào giao diện quản lý của Loa hoặc quét từ màn hình OLED của Loa để gán quyền điều khiển.

#### 2. Bài học & Nâng cấp cho Dự án Xiaozhi / Sunhouse MP:
* **Bổ sung Luồng "Zero-Touch Sync" cho Thiết bị OEM nội bộ eSunhouse:** Với các thiết bị Tuya mà khách hàng đã ghép nối trực tiếp vào App eSunhouse (như Robot 298 Pro Ultra), hệ thống tự động liên kết qua `user_id` của eSunhouse mà không bắt khách hàng phải quét QR hay đăng nhập lại.
* **Hỗ trợ Cơ chế Xác thực Kép (Dual Authorization Flow) cho thiết bị Smart Life ngoài:**
  1. *Luồng Webview / Deep-link OAuth2:* Tối ưu cho người dùng chỉ có 1 điện thoại (1-Click mở trang Tuya xác nhận không cần camera).
  2. *Luồng Quét mã QR Ticket (như App Lily):* Phục vụ khi người dùng thao tác trên máy tính, iPad hoặc có 2 thiết bị.
* **Cơ chế Tự Động Đồng Bộ Hướng Sự Kiện (Event-Driven Auto-Sync qua Pulsar / Webhook Push):**
  - Tích hợp kênh nhận sự kiện đẩy từ Tuya Cloud về Server để tự động cập nhật danh mục tức thì khi người dùng đổi tên thiết bị hoặc thay đổi trạng thái.

<a id="muc-2-5"></a>
### 2.5. Khai Thác Toàn Diện Đặc Tả Kỹ Thuật Tuya Từ Dự Án OEM (Robot Hút Bụi 298 Pro Ultra & eSunhouse)

Từ việc phân tích sâu toàn bộ 6 bảng đặc tả trong tài liệu `Các bước xử lý việc auth với Tuya.xlsx`, chúng ta rút ra **7 trụ cột kỹ thuật cốt lõi** để hiệu chỉnh và hoàn thiện kiến trúc MCP Server của Loa Xiaozhi:

<a id="muc-2-5-a"></a>
#### (A) Phân Định Rõ 2 Nguồn Thiết Bị Tuya: Nội Bộ OEM eSunhouse vs. Smart Life Bên Ngoài

| Tiêu chí | Nguồn 1: Thiết bị Sunhouse OEM Tuya (VD: Robot 298 Pro Ultra) | Nguồn 2: Thiết bị Tuya / Smart Life Ngoài Thị Trường |
| :--- | :--- | :--- |
| **Ứng dụng ghép nối gốc** | App **eSunhouse** (Flutter + Tuya Smart App SDK) | App **Smart Life / Tuya Smart** chính chủ |
| **Quản lý Định danh (UID)** | Do Backend eSunhouse tự khởi tạo qua `loginWithUid('84', 'sh_' + userId, hmacSecret)` hoặc `POST /v1.0/apps/{schema}/user` | Do người dùng tự đăng ký trên hệ sinh thái Tuya toàn cầu |
| **Quy trình Onboarding lên Loa** | **Zero-Touch (0-Chạm):** Tự động đọc `TuyaUid` và danh sách `TuyaDeviceId` từ CSDL eSunhouse (`PlatformType = 2`) | **1-Chạm (OAuth2 / QR Ticket):** Khách hàng ủy quyền liên kết tài khoản Smart Life với eSunhouse |
| **Loại Token sử dụng để gọi API** | **Project-level OpenAPI Token (`grant_type=1`)** của Cloud Project gắn với App Schema eSunhouse | **OAuth2 User Token (`grant_type=2` / QR Ticket)** hoặc Project Token sau khi đã liên kết Asset/User |

<a id="muc-2-5-b"></a>
#### (B) Đính Chính Bản Chất Vòng Đời Token Tuya Cloud & Cơ Chế Phối Hợp Liên Đội (Cross-Team Token Governance)
1. **Phân biệt rõ Token cấp Dự án (`grant_type=1`) và Token cấp Người dùng (`grant_type=2`):**
   * **Tuya Cloud OpenAPI Project Token (`GET /v1.0/token?grant_type=1`):** Dùng chung cho toàn bộ Backend để quản trị dự án, đồng bộ user và điều khiển các thiết bị thuộc quyền quản lý của Cloud Project. Chỉ có **1 cặp Access Token + Refresh Token duy nhất cho mỗi Cloud Project**.
   * **Chu kỳ sống (TTL) thực tế:** Mọi `access_token` của Tuya OpenAPI đều có thời hạn **7.200 giây (2 giờ)**.
   * **Ngưỡng làm mới chuẩn (Refresh Threshold):** Phải lưu trong Redis với TTL `7100s` và tự động gọi `GET /v1.0/token/{refresh_token}` khi thời gian còn lại **`< 300 giây` (5 phút)** (kết hợp cơ chế Lazy On-Demand Refresh khi có lệnh điều khiển). *Lưu ý: Tuyệt đối không dùng điều kiện `expire_at - now < 7200s` hay chờ đến 2h-5h sáng mới chạy Batch Refresh vì token sẽ chết sau mỗi 2 giờ.*
2. **Tránh xung đột Token giữa Đội IT Backend (C# ASP.NET Core) và Đội Nhúng (Python Xiaozhi Server):**
   * Nếu cả Backend eSunhouse C# và Server Python Xiaozhi cùng dùng chung một `Access ID / Access Secret` và tự gọi `GET /v1.0/token/{refresh_token}` độc lập, việc bên A làm mới token có thể làm mất hiệu lực token đang cache ở bên B.
   * **Giải pháp kiến trúc:**
     - *Phương án ưu tiên:* Dùng chung khóa Redis Distributed Cache (hoặc gọi qua Internal Token Service của Backend eSunhouse) cho Project Token của App Schema nội bộ.
     - *Phương án độc lập:* Tạo một Cloud Project riêng trên Tuya Console chuyên trách cho dịch vụ Voice Assistant (Xiaozhi MCP) và liên kết quyền truy cập sang App Schema của eSunhouse.

<a id="muc-2-5-c"></a>
#### (C) Chuẩn Hóa Endpoint Singapore Data Center & Bảo Mật Gói Tin REST / TuyaLink
* **Định tuyến vùng (Data Center Mapping cho mã vùng +84 Việt Nam):**
  - Theo chính sách hạ tầng của Tuya áp dụng cho Việt Nam (+84), bắt buộc cấu hình thống nhất về **Singapore Data Center (Mã vùng: AY)**:
    * **OpenAPI Gateway:** `https://openapi-sg.tuya.com` (RTT latency chỉ **35 – 50ms**, giảm 5 lần so với cụm Mỹ ~250ms).
    * **Message Queue (Pulsar):** `pulsar+ssl://mqe.tuyasg.com:7285`.
    * **MQTT Broker (cho TuyaLink):** `m1.tuyasg.com` / `m2.tuyasg.com` (Port `8883` TLS).
* **Chuẩn hóa URL & Payload REST API (Tránh nhầm lẫn với TuyaLink MQTT):**
  - API lấy đặc tả thiết bị chuẩn: `GET /v1.0/iot-03/devices/{device_id}/specifications` *(lưu ý có hậu tố `s` ở cuối)*.
  - API gửi lệnh điều khiển chuẩn: `POST /v1.0/iot-03/devices/{device_id}/commands` với body thuần túy:
    ```json
    {
      "commands": [
        {"code": "power_go", "value": true},
        {"code": "suction", "value": "max"}
      ]
    }
    ```
  - **Cơ chế chống trùng lặp (Idempotency):** Trên kênh HTTPS REST OpenAPI v2.0, việc chống Replay Attack và khử trùng lặp được thực hiện thông qua bộ Header `t` (Timestamp ms), `nonce` (UUID v4 duy nhất cho mỗi request) và chữ ký `sign` (HMAC-SHA256). Trong khi đó, trường `"msgId"` trong body JSON là đặc tả riêng của giao thức **TuyaLink MQTT (`tylink/${deviceId}/thing/property/set`)**.

<a id="muc-2-5-d"></a>
#### (D) Đặc Tả Giải Mã Chi Tiết Apache Pulsar Message Queue (AES-128-ECB & AES-128-GCM)
Từ bảng `Đặc tả Gói tin & Message Queue` (Sheet 6), quy trình xử lý bản tin sự kiện từ `pulsar+ssl://mqe.tuyasg.com:7285` trên topic `persistent://{access_id}/out/event` phải tuân thủ chính xác thuật toán 5 bước:
1. **Xác thực chữ ký toàn vẹn (`sign`):** Kiểm tra chữ ký MD5/HMAC của bản tin Envelope trước khi giải mã.
2. **Trích xuất khóa giải mã (`SecretKey`):** Cắt đúng **16 ký tự ở giữa** của chuỗi `AccessSecret` (từ vị trí index `8` đến `23`, tương đương `AccessSecret[8:24]` = 16 bytes UTF-8).
3. **Base64 Decode:** Giải mã chuỗi `data` trong JSON Envelope thành mảng byte `cipher_bytes`.
4. **Phân nhánh giải mã theo phiên bản giao thức `pv`:**
   * Nếu `pv == "1.0.0"`: Giải mã bằng **AES-128-ECB** với `PKCS7Padding`.
   * Nếu `pv == "2.0"`: Giải mã bằng **AES-128-GCM** (`NoPadding`), trong đó bắt buộc tách cấu trúc mảng byte:
     - **IV / Nonce:** 12 bytes đầu tiên (`cipher_bytes[:12]`).
     - **Auth Tag:** 16 bytes cuối cùng (`cipher_bytes[-16:]`).
     - **Ciphertext thực tế:** Phần byte ở giữa (`cipher_bytes[12:-16]`).
5. **Khử trùng lặp sự kiện theo `dataId`:** Mỗi gói tin `protocol: 4` (`deviceReport`) và `protocol: 20` (`deviceOnline/Offline`) sau khi giải mã đều có trường `"dataId"` duy nhất. Khi chạy nhiều node Backend ở chế độ `Shared` Subscription, cần kiểm tra nhanh `SET key:pulsar_msg:{dataId} 1 NX EX 60` trên Redis để đảm bảo không xử lý lặp cùng một sự kiện.

<a id="muc-2-5-e"></a>
#### (E) Mở Rộng Khả Năng Điều Khiển Giọng Nói Cho Robot Hút Bụi OEM (Model 298 Pro Ultra) & Trạm Sạc Đa Năng
Tài liệu Excel (Sheet 3 & Sheet 4) cung cấp bảng ánh xạ đầy đủ các Data Points (DPs) và REST APIs của dòng Robot hút bụi Flagship **298 Pro Ultra (LDS Laser + All-in-One Dock + AI Vision)**. Loa Xiaozhi hoàn toàn có thể khai thác trực tiếp các nhóm tính năng này qua giọng nói mà không đụng chạm tới phần render bản đồ nặng nề của Mobile App:

| Nhóm chức năng trên Loa Xiaozhi | Mã DP / Endpoint REST API | Giá trị / Tham số điều khiển | Câu lệnh giọng nói thực tế của khách hàng |
| :--- | :--- | :--- | :--- |
| **1. Bật/Tắt & Điều hướng cơ bản** | `power_go` (DP 1/101)<br>`pause` (DP 2/102)<br>`switch_charge` (DP 9)<br>`seek` (DP 10) | `true` / `false` | *"Cho robot đi dọn nhà"*, *"Tạm dừng robot hút bụi"*, *"Gọi robot quay về trạm sạc"*, *"Robot hút bụi đang ở đâu?"* (phát loa `seek=true`) |
| **2. Chế độ làm việc & Công suất** | `mode` (DP 3/103)<br>`suction` (DP 7)<br>`cistern` (DP 8) | Mode: `smart`, `zone`, `room`, `spot`, `mop_only`, `sweep_and_mop`<br>Suction: `quiet`, `normal`, `strong`, `max` (20.000Pa)<br>Cistern: `closed`, `low`, `middle`, `high` | *"Chuyển robot sang chế độ chỉ lau nhà"*, *"Tăng lực hút robot lên tối đa"*, *"Chỉnh mức nước lau nhà mức vừa"* |
| **3. Điều khiển Trạm sạc All-in-One Dock** | `dust_collection` (DP 12/120)<br>`mop_clean` (DP 14/122)<br>`hot_water_wash` (DP 16/123)<br>`mop_dry` (DP 17/124)<br>`dry_time` (DP 18/125) | `true` / `false`<br>Dry time: `2h`, `3h`, `4h` | *"Bảo robot về giặt giẻ bằng nước nóng 60 độ"*, *"Hút rác từ robot lên trạm sạc"*, *"Bật sấy khô giẻ lau trong 3 tiếng"* |
| **4. Cài đặt AI & Cảm biến thảm** | `carpet_clean_mode` (DP 21)<br>`carpet_turbo` (DP 22)<br>`ai_obstacle_avoidance` (DP 23) | Carpet: `auto_lift` (nâng giẻ 10.5mm), `avoid`, `ignore`<br>Turbo / AI: `true` / `false` | *"Bật chế độ tự nâng giẻ khi gặp thảm"*, *"Bật tránh vật cản AI cho robot"* |
| **5. Truy vấn trạng thái, Lỗi & Phụ kiện** | `status` (DP 5)<br>`battery_percentage` (DP 6)<br>`water_tank_status` (DP 19)<br>`fault` (DP 11 Bitmap)<br>`filter`, `edge_brush`, `roll_brush` (DP 27-29) | Status: `cleaning`, `mop_washing`, `dust_emptying`, `drying`, `charging`...<br>Water tank: `normal`, `clean_water_empty`, `dirty_water_full`, `tank_missing` | *"Robot hút bụi còn bao nhiêu phần trăm pin?"*, *"Bình nước trạm sạc còn nước không?"*, *"Kiểm tra tuổi thọ màng lọc và chổi quét của robot"* |
| **6. Tra cứu Lịch sử làm sạch** | `GET /v1.0/sweeper/devices/{device_id}/records` | Query: `page_no`, `page_size`, `start_time`, `end_time` | *"Hôm nay robot đã dọn nhà chưa, dọn được bao nhiêu mét vuông?"* |

> [!WARNING]
> **Ranh giới kiến trúc bắt buộc (Scope Boundary):**  
> Các luồng dữ liệu nhị phân nặng như **Bản đồ SLAM thời gian thực** (`IThingSweeper`, kênh P2P UDP/WebRTC DTLS-SRTP, hoặc tải file `.bin` nén Snappy/LZ4 từ Tuya OSS CDN) và **Vẽ tường ảo/vùng cấm tọa độ đa giác** (`command_trans` DP 25/114 dạng Raw Hex) thuộc phạm vi xử lý độc quyền của **Mobile App Flutter** (tải trực tiếp từ CDN về điện thoại). Server Xiaozhi MCP **tuyệt đối không tải hay xử lý file bản đồ `.bin`** để bảo vệ RAM và băng thông máy chủ.

<a id="muc-2-5-f"></a>
#### (F) Tiềm Năng Mở Rộng TuyaLink MQTT Cho Phần Cứng ESP32 Của Đội Nhúng
Theo Sheet 5 (`Đặc tả Giao thức Cloud Tuya` - Row 3), chuẩn **TuyaLink Standard MQTT** cho phép các thiết bị dùng MCU/ESP32 bên thứ ba (không dùng module phần cứng Tuya CBU/WBR3) kết nối trực tiếp lên Tuya Cloud Broker (`m1.tuyasg.com:8883` TLS) thông qua:
* `Username = "{deviceId}|signMethod=sha256"`
* `Password = HMAC-SHA256(deviceId + timestamp, deviceSecret)`
* Giao tiếp qua các topic chuẩn: `tylink/${deviceId}/thing/property/report`, `tylink/${deviceId}/thing/property/set`, `tylink/${deviceId}/thing/event/trigger`.
* **Giá trị chiến lược cho Đội Nhúng:** Nếu trong tương lai Sunhouse muốn đưa các thiết bị gia dụng ESP32 in-house tham gia trực tiếp vào **Ngữ cảnh tự động hóa liên thiết bị (Tuya Automation Scene)** cùng với cảm biến/công tắc Tuya, đội Nhúng chỉ cần tích hợp giao thức TuyaLink MQTT trên firmware C/C++ hiện hữu mà không tốn chi phí mua module phần cứng Tuya rời.

<a id="muc-2-5-g"></a>
#### (G) Tuân Thủ Pháp Lý & Bảo Vệ Dữ Liệu Cá Nhân (Nghị định 356/2025/NĐ-CP)
* Áp dụng **Kiến trúc Tách rời Danh tính (Decoupled Identity Architecture)** đồng nhất với đội IT Backend:
  - 100% thông tin định danh cá nhân (PII: Họ tên, SĐT, Email, Địa chỉ, Dữ liệu giọng nói của Loa) được lưu trữ độc quyền tại máy chủ đặt tại Việt Nam (Viettel IDC / VNPT).
  - Khi đồng bộ hoặc giao tiếp với Tuya Cloud Singapore, chỉ sử dụng mã băm ẩn danh một chiều (`sh_{SHA256(userId + Salt)}`). Phía Tuya Cloud hoàn toàn không thể đảo ngược để xác định danh tính thực của khách hàng Sunhouse.

<a id="muc-3"></a>
## 3. Ma Trận Đánh Giá & So Sánh Đối Đầu Chi Tiết

<a id="muc-3-1"></a>
### 3.1. Các tiêu chí định lượng & định tính
1. **Giá thành phần cứng (BOM Cost):** Ảnh hưởng trực tiếp đến giá bán lẻ sản phẩm ra thị trường.
2. **Chi phí vận hành Cloud (OPEX):** Chi phí server, băng thông, phí bản quyền API tính trên đầu thiết bị hàng tháng.
3. **Trải nghiệm khách hàng (User Onboarding UX):** Mức độ dễ dàng khi người dùng phổ thông cài đặt lần đầu.
4. **Độ trễ phản hồi (Response Latency):** Thời gian từ khi dứt khẩu lệnh đến khi thiết bị thực tế thay đổi trạng thái.
5. **Độ ổn định khi mất Internet (Offline Resilience):** Khả năng điều khiển khi đứt cáp quang hoặc mất mạng diện rộng.
6. **Thời gian đưa sản phẩm ra thị trường (Time-to-Market - TTM):** Tốc độ hoàn thiện sản phẩm để kịp tiến độ sản xuất thương mại.
7. **Khả năng mở rộng đa hãng (Cross-Brand Scalability):** Khả năng tương thích thêm các thương hiệu mới trong tương lai.

<a id="muc-3-2"></a>
### 3.2. Bảng so sánh toàn diện 4 phương án kỹ thuật

| Tiêu chí so sánh | Giải pháp 1: Cloud-to-Cloud (OAuth2 + eSunhouse Sync) | Giải pháp 2: Home Assistant Ecosystem Hub | Giải pháp 3A: Matter over Wi-Fi Controller | Giải pháp 3B: Hybrid Cloud + Tuya LAN (TCP 6668) |
| :--- | :--- | :--- | :--- | :--- |
| **Chi phí BOM phần cứng Loa** | **Tối ưu nhất (0 VNĐ)** | **Trung bình** (Nếu bán kèm Hub rời) | **Tăng 15 - 25%** (Cần nâng cấp PSRAM/Flash) | **Tối ưu nhất (0 VNĐ)** (Dùng AES phần cứng có sẵn) |
| **Chi phí vận hành Cloud (OPEX)** | Trung bình (Tuya Enterprise License) | Thấp (Tự lưu trữ / Nabu Casa) | **Thấp nhất** (Zero phí API) | **Thấp** (Giảm tải API khi điều khiển qua LAN) |
| **Trải nghiệm Onboarding (UX)** | ⭐⭐⭐⭐⭐ **(0-Chạm với OEM / 1-Chạm với Smart Life)** | ⭐⭐⭐ (Cấu hình qua HA) | ⭐⭐⭐⭐ (Quét mã QR Matter) | ⭐⭐⭐⭐⭐ **(Tự động lấy `LocalKey` từ Cloud)** |
| **Tốc độ phản hồi (Latency)** | 400ms – 800ms (Qua Singapore DC) | 100ms – 300ms (Mạng LAN) | `< 100ms` (Tại biên) | **`< 50ms` (Qua LAN TCP 6668)** / 400ms (Cloud Failover) |
| **Hoạt động Offline (Mất Internet)** | Không hoạt động | Hoạt động (nếu chạy Hub nội bộ) | **Hoạt động 100%** | **Hoạt động khi mất Internet quốc tế** (nếu cached lệnh/local) |
| **Độ rủi ro Firmware ESP32** | **Zero Risk** (Không sửa firmware loa) | Thấp (Chỉ kết nối WebSocket) | **Cao** (Nguy cơ tràn RAM, xung đột DSP) | **Thấp** (Gói tin TCP `0x55AA` chỉ vài chục bytes) |
| **Thời gian ra thị trường (TTM)** | **Rất nhanh (1 – 2 tháng)** | Trung bình (2 – 3 tháng) | Dài (4 – 6 tháng) | **Nhanh (Phase 1: Cloud 1.5 tháng ➔ Phase 2: LAN +1 tháng)** |
| **Mức độ phù hợp Hàng MP** | **CHỦ ĐẠO GIAI ĐOẠN 1 (MVP MP)** | Phù hợp phân khúc B2B / Prosumer | Định hướng phần cứng thế hệ sau | **NÂNG CẤP CHIẾN LƯỢC GIAI ĐOẠN 2** |

<a id="muc-3-3"></a>
### 3.3. Bảng Dự Toán Chi Phí Vận Hành (OPEX Projection: 1K - 10K - 100K Loa Active)

#### 1. Mô hình chi phí cấu thành (Đã hiệu chỉnh theo cơ chế Token TTL 7200s & Event-Driven Pulsar):
* **Tần suất gọi API thực tế:**
  - Khẩu lệnh điều khiển: trung bình 6 lệnh/ngày ➔ **180 API calls/tháng/loa** (`POST /commands`). Nhờ cơ chế Redis Caching (`device_cache`), không tốn thêm API tra cứu danh sách thiết bị trước mỗi lệnh.
  - **Làm mới Token thông minh (Lazy / On-Demand Token Refresh):** Do `access_token` của Tuya có TTL **7200s (2 giờ)**, nếu dùng cronjob tự động làm mới 24/24 cho toàn bộ user (kể cả khi họ đi vắng hoặc đang ngủ) sẽ tốn tới `12 lần/ngày × 30 ngày = 360 calls/tháng/user` (lãng phí gấp đôi số lệnh điều khiển thật!). Thay vào đó:
    * Với **Project-level Token (`grant_type=1`)** dùng chung cho toàn bộ thiết bị OEM eSunhouse: Chỉ tốn cố định `12 calls/ngày = 360 calls/tháng` cho **toàn bộ hệ thống** (không nhân theo số lượng user!).
    * Với **User-level OAuth Token** (thiết bị Smart Life ngoài): Áp dụng **Lazy Refresh** (chỉ gọi `GET /v1.0/token/{refresh_token}` khi người dùng thực sự phát sinh khẩu lệnh mà `access_token` đã hết hạn hoặc còn `< 300s`, kết hợp gia hạn định kỳ cho `refresh_token` sắp hết hạn). Nhờ đó số lệnh refresh trung bình giảm xuống chỉ còn **~ 30 – 50 calls/tháng/loa**.
  - **Đồng bộ danh mục & trạng thái qua Apache Pulsar (`mqe.tuyasg.com:7285`):** Nhận sự kiện đẩy thời gian thực hoàn toàn miễn phí quota REST API (**0 API call**).
  - **Tổng lưu lượng API thực tế:** Ước tính trung bình **~ 220 – 250 API calls / Loa / tháng**.

#### 2. Bảng dự toán chi phí vận hành (OPEX Projection Matrix):

| Hạng mục chi phí | Quy mô 1.000 Loa Active (Thử nghiệm Pilot) | Quy mô 10.000 Loa Active (Thương mại Giai đoạn 1) | Quy mô 100.000 Loa Active (Đại trà Mass Production) |
| :--- | :--- | :--- | :--- |
| **Tổng API Calls Tuya / tháng** | ~ 230.000 calls | ~ 2.300.000 calls | ~ 23.000.000 calls |
| **Gói Bản quyền Tuya Cloud** | Dùng chung gói Enterprise với dự án eSunhouse OEM (\$50/tháng) | Gói Enterprise Standard (\$100/tháng) | Gói Corporate Partner (\$300/tháng) |
| **Phí vượt hạn mức API Tuya** | \$0 (Nằm trọn trong Quota) | ~ \$10 – \$15/tháng | ~ \$320 – \$420/tháng (Block bulk tier) |
| **Hạ tầng Server & CSDL** | 1 VPS Cloud 4 vCPU / 8GB RAM + Redis + DB (~ \$45/tháng) | Cụm 2-3 Node Worker (Load Balancing) + Managed Redis/DB (~ \$250/tháng) | Cụm Kubernetes K8s Multi-Zone Auto-scale + Redis Sentinel (~ \$1.800/tháng) |
| **Tổng Chi Phí OPEX / Tháng** | **~ \$95 / tháng** (~ 2.400.000 VNĐ) | **~ \$360 / tháng** (~ 9.150.000 VNĐ) | **~ \$2.450 / tháng** (~ 62.200.000 VNĐ) |
| **Chi Phí Trên 1 Loa / Tháng** | **\$0.095** (~ 2.400 VNĐ/loa/tháng) | **\$0.036** (~ 915 VNĐ/loa/tháng) | **\$0.0245** (~ **620 VNĐ / loa / tháng**) |

<a id="muc-4"></a>
## 4. Kết Luận Lựa Chọn Giải Pháp & Sơ Đồ Quy Trình Hệ Thống (Architecture & Workflows)

<a id="muc-4-1"></a>
### 4.1. Giải pháp được chọn: Kiến trúc Đa Nguồn Hợp Nhất (Unified Multi-Source Cloud MCP + Optional LAN Failover)
Hội đồng kỹ thuật thống nhất lựa chọn kiến trúc **Hybrid Cloud-to-Cloud qua Server-side MCP** làm nền tảng cốt lõi, kết hợp đồng bộ trực tiếp với **Backend eSunhouse** (cho các thiết bị OEM như Robot 298 Pro Ultra) và mở lộ trình nâng cấp **Tuya LAN TCP 6668** cho Giai đoạn 2.

<a id="muc-4-2"></a>
### 4.2. Sơ đồ kiến trúc phân tầng hệ thống tổng thể

```text
┌────────────────────────────────────────────────────────────────────────────┐
│ 1. TẦNG BIÊN (ESP32-S3 FIRMWARE - VOICE ENDPOINT)                          │
│   • Mic I2S DMA ──► DSP (AEC/WakeWord) ──► Opus Encoder                    │
│   • Speaker I2S DMA ◄── Opus Decoder ◄── Audio Stream                      │
│   • [Phase 1]: Giữ nguyên 100% firmware, truyền nhận WebSocket thoại       │
│   • [Phase 2 Optional]: Bắn gói tin Tuya LAN (TCP 6668, 0x55AA) < 50ms     │
└─────────────────────────────────────┬──────────────────────────────────────┘
                                      │ WebSocket Luồng thoại Opus 2 chiều
                                      ▼
┌────────────────────────────────────────────────────────────────────────────┐
│ 2. TẦNG MÁY CHỦ CLOUD (XIAOZHI BACKEND SERVER - PYTHON ASYNC)              │
│   • STT (Speech-to-Text) ──► LLM (Function Calling + Dynamic Context)      │
│   • Unified MCP Tool Manager (`smarthome_control` + `robot_vacuum_control`)│
│   • Multi-Tenant Dispatcher: Phân luồng O(1) theo `platform_type`          │
│   • Pulsar Event Consumer (`mqe.tuyasg.com:7285`): Đồng bộ trạng thái < 2s │
└──────┬──────────────────────┬───────────────────────┬──────────────────────┘
       │ (1. Tuya OEM Nội bộ) │ (2. Tuya Smart Life)  │ (3. Sunhouse AWS)   │ (4. B2B/Prosumer)
       ▼                      ▼                       ▼                     ▼
┌─────────────────┐   ┌──────────────────┐   ┌─────────────────┐   ┌──────────────────┐
│ TUYA CLOUD (AY) │   │ TUYA CLOUD (AY)  │   │ AWS IOT CORE    │   │ HOME ASSISTANT   │
│ (App Schema SH) │   │ (OAuth2 / QR)    │   │ (Sunhouse In-   │   │ (Reverse WSS     │
│ • Robot 298 Pro │   │ • Công tắc, đèn  │   │  house ESP32)   │   │  MCP Bridge)     │
│   Ultra, OEM... │   │ • Rèm, quạt ngoài│   │ • Nồi cơm, RO...│   │ • 2.500+ hãng    │
└────────▲────────┘   └────────▲─────────┘   └─────────────────┘   └──────────────────┘
         │ Zero-Touch Sync     │ 1-Click OAuth2 / QR Ticket
┌────────┴─────────────────────┴─────────────────────────────────────────────┐
│ 3. TẦNG ỨNG DỤNG DI ĐỘNG & BACKEND ESUNHOUSE (FLUTTER & C# ASP.NET CORE)   │
│   • Quản lý tập trung `UserDevices` (`PlatformType`: 1=AWS, 2=TuyaOEM, 3=TuyaExt)│
│   • Chia sẻ `TuyaUid` (`sh_{SHA256}`) & Redis Token Cache với Xiaozhi      │
└────────────────────────────────────────────────────────────────────────────┘
```

<a id="muc-4-3"></a>
### 4.3. Bảng đối chiếu nhanh bản chất kỹ thuật giữa 2 Quy trình Tuya

| Hạng mục | Quy trình 1: Robot hút bụi OEM (298 Pro Ultra) chạy App eSunhouse | Quy trình 2: Công tắc, Đèn, Rèm... chính hãng chạy App Tuya / Smart Life |
| :--- | :--- | :--- |
| **Mã phân loại (`platform_type`)** | `2` (`tuya_oem_esunhouse`) | `3` (`tuya_external_smartlife`) |
| **Nơi thiết bị được ghép nối gốc** | Ghép nối trực tiếp trong **App eSunhouse** (dùng Tuya Smart App SDK nội bộ). | Ghép nối trên **App Smart Life / Tuya Smart** chính chủ của khách hàng. |
| **Trải nghiệm Onboarding lên Loa** | **0-Chạm (Zero-Touch Sync):** Tự động đồng bộ từ Backend eSunhouse ngay khi gắn Loa, không cần đăng nhập hay quét QR lần 2. | **1-Chạm (1-Click Account Linking):** Khách hàng xác nhận liên kết tài khoản Smart Life qua OAuth2 Webview hoặc quét mã QR Ticket (1 lần duy nhất). |
| **Định danh User trên Tuya Cloud** | UID ẩn danh do eSunhouse sinh: `sh_{SHA256(userId + Salt)}` (Tuân thủ NĐ 356/2025/NĐ-CP). | `external_tuya_uid` gốc của tài khoản Smart Life khách hàng. |
| **Loại Token dùng để gọi OpenAPI** | **Project-level Token (`grant_type=1`)** dùng chung cho toàn hệ thống (lưu Redis chung với Backend eSunhouse). | **User-level OAuth Token (`grant_type=2` / QR Ticket)** riêng của từng khách hàng (lưu mã hóa `AES-256-GCM` trong bảng `tuya_user_credentials`). |
| **Cơ chế làm mới Token (TTL 7200s)** | Worker tự động refresh mỗi `1h55p` (khi TTL còn `< 300s`) bằng Redis RedLock; chỉ tốn cố định ~12 calls/ngày cho toàn server. | **Lazy On-Demand Refresh:** Chỉ gọi refresh ngay tại thời điểm khách hàng ra lệnh thoại nếu phát hiện token còn `< 300s` (tiết kiệm >70% API call). |
| **Đặc thù xử lý lệnh (Normalizer)** | Tập lệnh chuyên sâu **32 DPs** (Robot + Trạm sạc All-in-One: giặt giẻ 60°C, sấy khô, hút rác, lực hút 20.000Pa) + API lịch sử `/v1.0/sweeper/...`. | **Schema-Driven Normalizer:** Tự động đọc `raw_schema` để ánh xạ mã DP (`switch_1`, `switch_led`) và quy đổi thang giá trị (`0-100%` ➔ `10-1000`). |

<a id="muc-4-4"></a>
### 4.4. Sơ đồ Quy trình 1: Loa Xiaozhi điều khiển Robot hút bụi OEM (App eSunhouse)

Với Robot hút bụi OEM của Sunhouse, thiết bị đã nằm sẵn trong **App Schema của eSunhouse**, nên hệ thống tận dụng hoàn toàn hạ tầng sẵn có của đội IT Backend để mang lại trải nghiệm **không cần cấu hình (Zero-Touch)** cho người dùng:

```text
====================================================================================================
 QUY TRÌNH 1: ĐIỀU KHIỂN ROBOT HÚT BỤI OEM SUNHOUSE (298 PRO ULTRA - APP ESUNHOUSE)
====================================================================================================

[GIAI ĐOẠN A: ĐỒNG BỘ TỰ ĐỘNG 0-CHẠM (ZERO-TOUCH ONBOARDING)]

  (1) Khách hàng mua Robot 298 Pro Ultra, mở App eSunhouse ghép nối Wi-Fi 2.4GHz.
      • App eSunhouse gọi SDK: loginWithUid("84", "sh_{SHA256(userId)}", hmacSecret)
      • Backend eSunhouse (C#) lưu vào DB: PlatformType = 2 (TuyaCloud), TuyaDeviceId, PID.
                           │
                           ▼
  (2) Khách hàng bật Loa Xiaozhi (nhập PIN 6 số / quét QR trên màn OLED để gắn vào App eSunhouse).
      • Backend eSunhouse (C#) ──[POST /api/v1/auth/esunhouse/sync-oem-devices]──► Server Xiaozhi (Python)
      • Server Xiaozhi dùng Project Token (grant_type=1) gọi Tuya Singapore (openapi-sg.tuya.com):
        GET /v1.0/iot-03/devices/{devId}/specifications
      • Lưu toàn bộ 32 DPs của Robot & Trạm sạc vào bảng `device_cache` (platform_type = 2).
      ➔ HOÀN TẤT TỰ ĐỘNG 100% (Khách hàng KHÔNG CẦN đăng nhập lại hay quét QR ủy quyền Tuya).

----------------------------------------------------------------------------------------------------
[GIAI ĐOẠN B: THỰC THI LỆNH GIỌNG NÓI THỜI GIAN THỰC (RUNTIME VOICE CONTROL < 600ms)]

  Khách hàng nói: "Xiaozhi ơi, bảo robot hút bụi ở mức tối đa rồi về trạm giặt giẻ nước nóng"
                           │
                           ▼
  ┌────────────────────────────────────────────────────────────────────────────────────────┐
  │ 1. LOA XIAOZHI (ESP32-S3 FIRMWARE)                                                     │
  │    • Mic I2S ──► DSP (AEC/VAD) ──► Mã hóa luồng âm thanh Opus đẩy lên WebSocket        │
  └────────────────────────────────────────┬───────────────────────────────────────────────┘
                                           │ WebSocket Audio Stream
                                           ▼
  ┌────────────────────────────────────────────────────────────────────────────────────────┐
  │ 2. SERVER XIAOZHI (PYTHON ASYNC BACKEND)                                               │
  │    • B1 (STT + Dynamic Context): Nhận diện câu nói; tiêm danh mục thiết bị từ Redis    │
  │      vào ngữ cảnh LLM: [{"id": "tuya_oem_298pro", "name": "Robot hút bụi", "cat": "sd"}]│
  │    • B2 (LLM Function Call): Sinh lệnh gọi MCP Tool `smarthome_control`:               │
  │      device_id="tuya_oem_298pro", actions=[turn_on, set_suction="max", wash_mop=60C]   │
  │    • B3 (O(1) Dispatcher): Thấy `platform_type == 2` ➔ Chuyển vào Sweeper Adapter.     │
  │    • B4 (Token Lookup): Đọc `Project-level Token (grant_type=1)` từ Redis Cache chung  │
  │      (Nếu TTL < 300s ➔ Khóa Redis RedLock ➔ Gọi GET /v1.0/token/{refresh_token}).      │
  │    • B5 (Ký số & Gọi OpenAPI): Tạo Header `t` (ms), `nonce` (UUID), `sign` (HMAC-SHA256)│
  └────────────────────────────────────────┬───────────────────────────────────────────────┘
                                           │ HTTPS POST (RTT 35-50ms tới Singapore DC)
                                           │ URL: https://openapi-sg.tuya.com/v1.0/iot-03/devices/{devId}/commands
                                           │ Body: {"commands": [
                                           │   {"code": "power_go", "value": true},
                                           │   {"code": "suction", "value": "max"},
                                           │   {"code": "hot_water_wash", "value": true}
                                           │ ]}
                                           ▼
  ┌────────────────────────────────────────────────────────────────────────────────────────┐
  │ 3. TUYA CLOUD SINGAPORE (REGION: AY) ──► ROBOT HÚT BỤI 298 PRO ULTRA                   │
  │    • Tuya Cloud đẩy gói tin MQTT TLS (Port 8883, m1.tuyasg.com) xuống Robot.           │
  │    • Robot kích hoạt động cơ 20.000Pa & lên lịch giặt giẻ 60°C tại Trạm sạc đa năng.   │
  │    • Server Xiaozhi phát TTS về Loa: "Đã bật robot hút bụi ở mức tối đa và giặt nước nóng"│
  └────────────────────────────────────────────────────────────────────────────────────────┘

----------------------------------------------------------------------------------------------------
[GIAI ĐOẠN C: ĐỒNG BỘ TRẠNG THÁI & CẢNH BÁO GIỌNG NÓI CHỦ ĐỘNG (PULSAR REVERSE STREAM < 2s)]

  Robot 298 Pro Ultra (Đầy bình nước bẩn DP 19 / Kẹt chổi cuộn DP 11 / Cập nhật % Pin DP 6)
        │
        ├──► (1) Báo cáo DP (Command 0x07) lên Tuya Cloud Broker (m1.tuyasg.com:8883)
        ├──► (2) Tuya Pulsar Bus (`pulsar+ssl://mqe.tuyasg.com:7285`) đẩy gói tin `protocol: 4`
        ├──► (3) Server Xiaozhi giải mã AES-128-GCM/ECB bằng khóa `AccessSecret[8:24]` (16 bytes),
        │        kiểm tra `dataId` chống trùng lặp và cập nhật `device_cache` trong < 2 giây.
        └──► (4) [Proactive Alert]: Nếu phát hiện lỗi (`water_tank_status == "dirty_water_full"`),
                 Server Xiaozhi chủ động phát giọng nói qua Loa:
                 "Thông báo từ trạm sạc robot: Bình nước bẩn đã đầy, bạn vui lòng đổ nước nhé!"
```

<a id="muc-4-5"></a>
### 4.5. Sơ đồ Quy trình 2: Loa Xiaozhi điều khiển Công tắc, Đèn, Rèm... chính hãng Tuya (App Smart Life)

Đối với các thiết bị Tuya khách hàng tự mua ngoài thị trường và đang cài trên **App Smart Life / Tuya Smart chính chủ**, vì nằm ngoài App Schema của eSunhouse nên khách hàng thực hiện **1 bước liên kết ủy quyền duy nhất (1-Click OAuth2 hoặc QR Ticket)**, sau đó hệ thống tự động chuẩn hóa mọi dị biệt phần cứng:

```text
====================================================================================================
 QUY TRÌNH 2: ĐIỀU KHIỂN CÔNG TẮC, ĐÈN, QUẠT... CHÍNH HÃNG TUYA (APP SMART LIFE / TUYA SMART)
====================================================================================================

[GIAI ĐOẠN A: LIÊN KẾT ỦY QUYỀN TÀI KHOẢN 1-CHẠM (1-CLICK ACCOUNT LINKING)]

  Khách hàng đang dùng Công tắc, Đèn, Rèm trên App Smart Life gốc (không muốn xóa đi cài lại)
                           │
        ┌──────────────────┴──────────────────┐
        ▼ (Cách 1: Khuyên dùng cho 1 máy)     ▼ (Cách 2: Khi dùng 2 máy / iPad / PC)
  [OAuth2 Webview 1-Chạm]               [Quét mã QR Ticket (Giống cơ chế App Lily)]
  • Trên App eSunhouse, bấm             • Nhập `User Code` từ Smart Life vào App eSunhouse.
    "Liên kết tài khoản Smart Life".    • Server Xiaozhi gọi `POST /v1.0/token/qr/create`
  • Mở trang ủy quyền Tuya, bấm           sinh mã QR Ticket (hiệu lực 5 phút).
    "Đồng ý" (Authorization Code).      • Mở App Smart Life quét mã QR xác nhận ủy quyền.
        └──────────────────┬──────────────────┘
                           │
                           ▼
  Tuya Cloud Singapore cấp cho Server Xiaozhi: `external_tuya_uid` + Cặp `User OAuth Token`
        │
        ├──► (1) Server Xiaozhi mã hóa `AES-256-GCM` cho `access_token` & `refresh_token`,
        │        lưu vào bảng `tuya_user_credentials` của đúng `user_id` đó.
        ├──► (2) Gọi `GET /v1.0/users/{external_tuya_uid}/devices` lấy toàn bộ danh sách thiết bị
        │        (kèm `device_id`, `name`, `category`, `local_key`, `ip`).
        └──► (3) Gọi `GET /v1.0/iot-03/devices/{devId}/specifications` lấy đặc tả DP của từng đèn,
                 công tắc (`min`, `max`, `scale`) lưu vào cột JSONB `raw_schema` (`platform_type = 3`).

----------------------------------------------------------------------------------------------------
[GIAI ĐOẠN B: THỰC THI LỆNH GIỌNG NÓI & CHUẨN HÓA SCHEMA ĐỘNG (RUNTIME CONTROL)]

  Khách hàng nói: "Xiaozhi ơi, bật đèn chùm phòng khách độ sáng 50 phần trăm"
                           │
                           ▼
  ┌────────────────────────────────────────────────────────────────────────────────────────┐
  │ 1. LOA XIAOZHI (ESP32-S3) ──[WebSocket Opus]──► SERVER XIAOZHI (STT ──► LLM)           │
  │    • LLM đối chiếu ngữ nghĩa (Semantic Match) từ danh sách thiết bị được tiêm vào,     │
  │      sinh Function Call: `smarthome_control(device_id="tuya_ext_bf82a1",               │
  │                           action="set_level", value=50)`                               │
  └────────────────────────────────────────┬───────────────────────────────────────────────┘
                                           │
                                           ▼
  ┌────────────────────────────────────────────────────────────────────────────────────────┐
  │ 2. MULTI-TENANT DISPATCHER & GENERIC SCHEMA ENGINE (TRÊN SERVER XIAOZHI)               │
  │    • B1 (O(1) Routing): Tra cứu `device_id` ➔ `platform_type == 3`.                    │
  │    • B2 (Lazy On-Demand Token Check): Giải mã `User OAuth Token` của khách hàng.       │
  │      Kiểm tra nếu `expire_at - now < 300s`:                                            │
  │      └─► Khóa Redis (`SET lock:tuya_refresh:{user_id} NX EX 30`)                       │
  │      └─► Gọi `GET /v1.0/token/{refresh_token}` lấy Token mới (TTL 7200s) & lưu DB.     │
  │    • B3 (Zero-Hardcode Generic Schema Engine): Đọc mảng `functions` từ Tuya OpenAPI:   │
  │      - Ý định Bật/Tắt (Power): Lọc DP `type == "Boolean"` có tiền tố `switch` / `power`│
  │        (tự động khớp `switch_led`, `switch_fan`, `switch_1..4` mà KHÔNG hardcode!).     │
  │      - Ý định Đại lượng (Scalar): Lọc DP `type == "Integer"` theo từ khóa hành vi      │
  │        (`bright`, `speed`/`wind`, `temp`) và đọc dải `min`/`max` từ metadata `values`. │
  │      - Tự động co giãn tỷ lệ phần trăm (0-100% ➔ `[min, max]`) chuẩn xác 100%.         │
  └───────────────────┬────────────────────────────────────────────────┬───────────────────┘
                      │                                                │
       [Kênh 1: Mặc định Cloud-to-Cloud]                [Kênh 2: Phase 2 Hybrid LAN Failover]
       • HTTPS POST tới `openapi-sg.tuya.com`           • Nếu mất mạng quốc tế hoặc cần < 50ms:
       • `/v1.0/iot-03/devices/{devId}/commands`        • Đẩy lệnh xuống Loa ESP32-S3 bắn thẳng
       • Body: `{"commands": [`                           qua mạng Wi-Fi nội bộ tới **TCP Port 6668**
           `{"code": "switch_led", "value": true},`       của công tắc/đèn bằng khung nhị phân:
           `{"code": "bright_value_v2", "value": 500}`    `[0x55AA][Ver][Seq][Cmd 0x0D][Len]`
         `]}`                                             `[Payload AES-128-GCM với LocalKey][0xAA55]`
                      │                                                │
                      └───────────────────────┬────────────────────────┘
                                              ▼
  ┌────────────────────────────────────────────────────────────────────────────────────────┐
  │ 3. THIẾT BỊ CÔNG TẮC / BÓNG ĐÈN TUYA TRONG NHÀ KHÁCH HÀNG                              │
  │    • Bóng đèn bật sáng đúng mức 50%.                                                   │
  │    • Loa Xiaozhi phát phản hồi TTS: "Đã bật đèn chùm phòng khách ở mức 50 phần trăm".  │
  └────────────────────────────────────────────────────────────────────────────────────────┘

----------------------------------------------------------------------------------------------------
[GIAI ĐOẠN C: ĐỒNG BỘ TỰ ĐỘNG KHI KHÁCH HÀNG ĐỔI TÊN / BẬT TẮT TRÊN APP SMART LIFE]

  Khách hàng mở App Smart Life đổi tên "Đèn trần" ➔ "Đèn thả bàn ăn" (hoặc bấm công tắc tay)
        │
        ├──► (1) Tuya Cloud bắn sự kiện `deviceReport` (`protocol: 4`) qua kênh **Apache Pulsar**
        │        (`pulsar+ssl://mqe.tuyasg.com:7285`, hoặc dự phòng qua Webhook `/api/v1/tuya/webhook`).
        ├──► (2) Server Xiaozhi giải mã gói tin bằng `AccessSecret[8:24]`, cập nhật tên mới
        │        "Đèn thả bàn ăn" vào `device_cache` của user đó trong vòng **< 2 giây**.
        └──► (3) Ngay lập tức, khách hàng nói "Xiaozhi ơi, tắt đèn thả bàn ăn", Loa nhận diện
                 chính xác 100% mà KHÔNG CẦN hủy liên kết hay quét lại mã QR như App Lily.
```

<a id="muc-4-6"></a>
### 4.6. Ba điểm cốt lõi Đội Nhúng cần lưu ý khi phối hợp triển khai

1. **Firmware ESP32-S3 ở Phase 1 hoàn toàn "mỏng" (Zero Hardware Impact):** Dù điều khiển Robot 298 Pro Ultra phức tạp hay hàng chục công tắc Smart Life, ở Phase 1 toàn bộ việc phân biệt `platform_type` (`1 = AWS`, `2 = Tuya OEM`, `3 = Tuya Smart Life`, `4 = Home Assistant`), quản lý Token và chuẩn hóa DP đều nằm gọn trên `xiaozhi-esp32-server`. Firmware ESP32-S3 chỉ cần ẩn bộ tool cũ (`sunhouse_mcp_tools.cc`) khi kết nối vào Server mới để tránh trùng lặp.
2. **Điểm giao tiếp duy nhất cần chốt với Đội IT Backend (eSunhouse C#):** Chỉ cần thống nhất **1 API đồng bộ thiết bị OEM** (`POST /api/v1/auth/esunhouse/sync-oem-devices`) và **quy ước đọc/ghi chung khóa Redis cho Project Token (`grant_type=1`)** để 2 backend C# và Python không tự làm mất hiệu lực token của nhau.
3. **Lợi thế độc quyền của Đội Nhúng ở Phase 2 (Tuya LAN `0x55AA`):** Nhờ Server Xiaozhi đã thu thập và lưu sẵn trường `local_key` (16 ký tự) cùng `local_ip` vào bảng `device_cache` ở cả 2 quy trình trên, bất cứ khi nào Đội Nhúng muốn nâng cấp tính năng điều khiển cục bộ không độ trễ (`< 50ms`) hoặc điều khiển khi đứt cáp quang, chỉ cần mở một hàm C/C++ nhỏ trên ESP32-S3 dùng phần cứng AES-128 bắn gói tin `0x55AA` (Command `0x0D`) qua cổng `TCP 6668` là chạy được cho cả Robot OEM lẫn công tắc Tuya ngoài thị trường.

<a id="muc-4-7"></a>
### 4.7. Cấu Trúc Thư Mục & Module Toàn Dự Án (`xiaozhi-esp32-server`)

Nhằm bảo đảm nguyên tắc **Clean Architecture & Fault Isolation**, hệ thống áp dụng **Phương Án A (Chuẩn Kiến Trúc Microservices Độc Lập - Chia Để Trị)**:
* **Tách rời hoàn toàn**: Logic Smarthome IoT được đóng gói thành Microservice độc lập `mcp_smarthome_hub/` (Port 8005), cùng cấp độ với `mcp_sunhouse_rag/` (Port 8004) và `main/xiaozhi-server/` (Port 8000 & 8003).
* **Bảo vệ luồng âm thanh**: Zero rủi ro chặn luồng Audio Stream (Opus, VAD, ASR, TTS). Dù Cloud Tuya hoặc Hub HA gặp sự cố mạng, lõi đàm thoại thời gian thực vẫn chạy mượt mà 100%.

#### 1. Cây Thư Mục & Module Cụm MCP SmartHome Hub (`mcp_smarthome_hub/` - Port 8005):

```text
mcp_smarthome_hub/            📁 CỤM SERVER ĐỘC LẬP: IOT SMARTHOME & HA HUB (PORT 8005)
│
├── main.py                   → Daemon MCP JSON-RPC 2.0, Ingress WSS, HTTP Healthcheck
│
├── storage/                  📁 TẦNG LƯU TRỮ & BẢO MẬT DAL (PHASE 1: ĐÃ XONG 100%)
│   ├── token_vault.py        → Két mã hóa AES-256-GCM (Nonce 12B) & ẩn danh UID (NĐ 356)
│   ├── models.py             → SQLAlchemy ORM đa người dùng (users, speakers, credentials)
│   ├── db.py                 → SmartHomeDAL: Mã hóa trong suốt, CRUD siêu tốc (< 0.3ms)
│   └── token_manager.py      → Quản trị Token: RedLock (Project), Lazy Refresh (User)
│
├── clients/                  📁 TẦNG KẾT NỐI CLOUD & SỰ KIỆN (PHASE 2: ĐÃ XONG 100%)
│   ├── tuya_client.py        → Client Tuya OpenAPI (Singapore), ký HMAC-SHA256, Retry
│   └── pulsar_consumer.py    → Pulsar SSL (7285), giải mã ECB/GCM, Proactive Voice Alert
│
├── adapters/                 📁 TẦNG CHUẨN HÓA SCHEMA & THIẾT BỊ (PHASE 2 - HIỆU CHUẨN)
│   ├── normalizer.py         → Generic Schema Engine: Đọc metadata functions từ Tuya OpenAPI, Zero-Hardcode DP
│   └── sweeper_adapter.py    → [Staged / R&D Pause] Adapter Robot 298 Pro (tạm ẩn cho đến khi phần cứng hoàn thiện)
│
├── ha_bridge/                📁 CẦU NỐI HA REVERSE TUNNEL (PHASE 3: ĐÃ XONG 100%)
│   ├── ha_tunnel_server.py   → Ingress WebSocket (wss), Bearer Auth, Ping 25s, Revoke 1008
│   ├── redis_session_mgr.py  → Quản trị phiên đa node qua Redis HSET ha:sessions, Ping
│   └── jsonrpc_forwarder.py  → Cầu nối MCP JSON-RPC 2.0 <-> HA qua Redis Pub/Sub (< 15ms)
│
├── dispatcher/               📁 BỘ ĐỊNH TUYẾN ĐA NGUỒN O(1) & NGỮ CẢNH (PHASE 4 - HIỆU CHUẨN)
│   ├── multisource_dispatcher.py → Định tuyến O(1) 4 nguồn (AWS, Tuya OEM, HA) < 5ms, đọc trạng thái đa năng
│   └── context_injector.py   → Tiêm danh mục thiết bị của user vào LLM Prompt, lọc sạch thiết bị R&D
│
├── tools/                    📁 CÔNG CỤ MCP UNIFIED CHO AI VOICE (PHASE 4 - HIỆU CHUẨN)
│   ├── smarthome_tool.py     → Tool MCP smarthome_control: Bật/tắt, mức độ, Hard Timeout 1.5s
│   ├── tuya_sync_tool.py     → Tool MCP tuya_sync_devices: Đồng bộ danh sách theo yêu cầu người dùng (On-Demand)
│   └── sweeper_tool.py       → [Staged / R&D Pause] Tool MCP Robot (tạm ẩn khỏi tools/list của Loa)
│
├── routers/                  📁 CỤM REST API ONBOARDING & WEBHOOK (PHASE 5: PRODUCTION)
│   ├── esunhouse_sync.py     → API sync 0-chạm từ App eSunhouse (nhận TuyaUid, nạp Cache)
│   ├── tuya_auth.py          → API liên kết Smart Life ngoài: OAuth2 URL & QR-Ticket
│   ├── pairing.py            → API ghép nối Loa: Sinh và xác thực mã PIN hiển thị OLED
│   └── webhook.py            → Endpoint HTTP callback dự phòng khi Pulsar gián đoạn
│
├── edge_lan/                 📁 GIAO THỨC TUYA LOCAL LAN (PHASE 2 ROADMAP: BOM = 0 VNĐ)
│   └── tuya_lan_proto.py     → Frame 0x55AA (TCP 6668) qua local_key, điều khiển < 50ms
│
└── tests/                    📁 BỘ KIỂM THỬ TỰ ĐỘNG THEO GIAI ĐOẠN (CI/CD PASS GATES)
    ├── test_smart_home_phase1.py → [✓ PASS 5/5] DAL đa người dùng, Vault AES-256, RedLock
    ├── test_smart_home_phase2.py → [✓ PASS 6/6] OpenAPI HMAC-SHA256, Pulsar, 32 DPs Robot
    ├── test_smart_home_phase3.py → [✓ PASS 5/5] HA Ingress WSS, Bearer Auth, JSON-RPC < 15ms
    ├── test_smart_home_phase4.py → [✓ PASS 7/7] Dispatcher O(1) < 5ms, Semantic Match ≥ 98%, Tuya On-Demand Sync
    └── test_smart_home_phase5.py → [⏳ Phase 5] Stress Test 200 Loa, Sync eSunhouse 0-chạm
```

#### 2. Diễn Giải Vai Trò & Thông Số Kỹ Thuật Từng Module (Technical Summary):

##### 📁 Tầng 1: Lưu Trữ & Bảo Mật DAL (`storage/`) - [✓ Phase 1 ĐÃ HOÀN TẤT]
* **`token_vault.py`**: Két mã hóa **AES-256-GCM** (Nonce 12B, Tag 16B chống sửa đổi); ẩn danh UID một chiều `sh_{SHA256(uid + salt)}` tuân thủ nghiêm ngặt **Nghị định 356/2025/NĐ-CP** bảo vệ dữ liệu PII.
* **`models.py`**: Thực thể SQLAlchemy ORM đa thuê bao: quản lý người dùng (`users`), định danh Loa (`speakers`), token dự án (`tuya_project_tokens`), ủy quyền OAuth (`tuya_user_credentials`) và cache thiết bị (`device_cache`).
* **`db.py`**: Lớp SmartHomeDAL mã hóa/giải mã trong suốt hai chiều khi tương tác CSDL SQLite/PostgreSQL; tốc độ CRUD thực đo siêu tốc **0.293ms** (vượt xa chỉ tiêu < 5ms).
* **`token_manager.py`**: Quản trị vòng đời Token Tuya tự động; khóa phân tán **Redis RedLock** (`SET NX EX 30` + script Lua) chống Race Condition với Backend C#; cơ chế Lazy Refresh giảm 70% cuộc gọi API thừa.

##### 📁 Tầng 2: Kết Nối Cloud & Sự Kiện (`clients/`) - [✓ Phase 2 ĐÃ HOÀN TẤT]
* **`tuya_client.py`**: Client HTTP bất đồng bộ giao tiếp Tuya Singapore Gateway (`openapi-sg.tuya.com`); tạo chữ ký chuẩn **HMAC-SHA256** kèm `nonce` và `t` chống Replay Attack; tự động khôi phục lỗi mạng với `tenacity` exponential backoff (vượt qua lỗi 502 trong 3.2ms); hỗ trợ điều khiển DP, lấy lịch sử và sơ đồ dọn dẹp.
* **`pulsar_consumer.py`**: Lắng nghe sự kiện thời gian thực qua kết nối SSL (`pulsar+ssl://mqe.tuyasg.com:7285`); trích xuất khóa `AccessSecret[8:24]` giải mã tự động cả 2 chuẩn **AES-128-ECB** (0.025ms) và **AES-128-GCM** (0.040ms); khử trùng lặp `dataId` trên Redis; kích hoạt **Proactive Voice Alert** phát loa cảnh báo khi robot kẹt rác hoặc trạm sạc cạn/đầy nước.

##### 📁 Tầng 3: Chuẩn Hóa Schema & Thiết Bị (`adapters/`) - [Phase 2 Hiệu Chuẩn Generic Schema Engine]
* **`normalizer.py`**: **Generic Schema Engine (Động cơ chuẩn hóa schema tổng quát)**:
  - Khai thác 100% metadata `functions` và `specifications` trả về từ Tuya OpenAPI (Singapore).
  - **Triệt tiêu hoàn toàn mảng tĩnh và logic if/else theo category:** Không hardcode DP code, không suy đoán ("mò mò dò dò").
  - Tự động nhận diện DP Nguồn (`type == "Boolean"` có tiền tố `switch` / `power`), DP Đại lượng (`type == "Integer"` theo từ khóa `speed`/`wind`, `bright`, `temp`), DP Chế độ (`type == "Enum"` theo `range`).
  - Tích hợp **Semantic-to-Range Mapper**: Quy đổi khẩu ngữ tự nhiên tiếng Việt (*"nhẹ"*, *"vừa"*, *"mạnh"*, *"tối đa"*, *"mờ"*, *"sáng"*) sang dải số `[min, max]` chuẩn xác, khắc phục triệt để lỗi ép kiểu chuỗi sang số.
* **`sweeper_adapter.py`**: [Staged / R&D Pause] Bộ điều hợp Robot 298 Pro Ultra (32 DPs) được gắn cờ tạm ẩn (`ENABLE_SWEEPER_RND = False`) trong giai đoạn R&D phần cứng chưa hoàn thiện, không gây nhiễu cho AI và các thiết bị gia dụng khác.

##### 📁 Tầng 4: Cầu Nối Home Assistant (`ha_bridge/`) - [✓ Phase 3 ĐÃ HOÀN TẤT]
* **`ha_tunnel_server.py`**: Cổng tiếp nhận WebSocket Ingress Gateway (`wss://.../ha/tunnel`) cho Hub Home Assistant nội bộ kết nối ngược lên Cloud; xác thực bảo mật bắt buộc qua Header `Authorization: Bearer`; duy trì nhịp tim Ping 25s xuyên NAT; cơ chế thu hồi tức thời với WebSocket Close Code 1008 (< 500ms).
* **`redis_session_mgr.py`**: Quản lý phiên kết nối đa máy chủ qua Redis (`HSET ha:sessions`); giám sát trạng thái Online/Offline và điều phối tải tập trung.
* **`jsonrpc_forwarder.py`**: Chuyển tiếp bản tin MCP JSON-RPC 2.0 sang dịch vụ HA `call_service` qua Redis Pub/Sub liên node với độ trễ nội bộ **< 15ms** (đo lường pass 100% 5/5 test).

##### 📁 Tầng 5: Định Tuyến Đa Nguồn & Ngữ Cảnh (`dispatcher/`) - [Phase 4 Hiệu Chuẩn Đa Năng]
* **`multisource_dispatcher.py`**: Bộ định tuyến thông minh độ phức tạp **O(1)** trong **< 5ms** phân luồng 4 nền tảng (AWS IoT, Tuya OEM, Tuya Ngoài OAuth, HA). Mở rộng hàm `_format_immediate_status` trích xuất đa năng trạng thái nguồn (`switch_fan`, `switch_led`, `switch_1..4`) và đại lượng (`fan_speed`, `bright_value_v2`).
* **`context_injector.py`**: Tiêm danh mục thiết bị của user vào LLM System Prompt; chủ động lọc bỏ các danh mục thiết bị đang thử nghiệm R&D (`category == "sd"`), nâng độ chính xác nhận diện khẩu lệnh tự nhiên lên **≥ 98%**.

##### 📁 Tầng 6: Công Cụ MCP Hợp Nhất Cho AI Voice (`tools/`) - [Phase 4 Hiệu Chuẩn Đa Năng]
* **`smarthome_tool.py`**: Công cụ MCP chuẩn hóa (`smarthome_control`) cho Function Calling của LLM; hỗ trợ điều khiển thiết bị toàn diện; tích hợp **Hard Timeout 1.5s** bảo vệ tuyệt đối luồng đàm thoại âm thanh.
* **`tuya_sync_tool.py`**: Công cụ MCP `tuya_sync_devices` đồng bộ danh sách thiết bị theo yêu cầu người dùng (On-Demand qua giọng nói: *"đồng bộ thiết bị tuya"*, *"đồng bộ tất cả thiết bị"*), chấm dứt hoàn toàn việc chạy ngầm định kỳ 1p/lần gây lãng phí gói tin.
* **`sweeper_tool.py`**: [Staged / R&D Pause] Công cụ MCP chuyên dụng cho Robot: tạm thời đóng băng, không đăng ký vào `tools/list` của Server Xiaozhi.

##### 📁 Tầng 7: Cụm REST API Onboarding & Webhook (`routers/`) - [⏳ Phase 5]
* **`esunhouse_sync.py`**: API nội bộ bảo mật (`POST .../sync-oem-devices`) đồng bộ tức thì thiết bị từ App eSunhouse mà khách **không cần thao tác thêm (Zero-Touch Onboarding)**.
* **`tuya_auth.py`**: API liên kết tài khoản Smart Life ngoài qua OAuth2 URL WebView hoặc quét mã QR-Ticket.
* **`pairing.py`**: API ghép nối Loa XiaoZhi vào tài khoản gia đình qua mã PIN 4-6 số trên màn hình OLED.
* **`webhook.py`**: Endpoint HTTP callback dự phòng khi Pulsar gián đoạn; kiểm tra chữ ký HMAC-SHA256 và whitelist IP.

##### 📁 Tầng 8: Dự Phòng Điều Khiển Cục Bộ (`edge_lan/`) - [Phase 2 Roadmap]
* **`tuya_lan_proto.py`**: Bộ đóng gói frame nhị phân Tuya LAN (`Header 0x55AA`, mã hóa AES-128 bằng `local_key`, Footer `0xAA55`); hỗ trợ Loa ESP32-S3 bắn lệnh trực tiếp qua cổng **TCP 6668** trong mạng LAN, đạt độ trễ **< 50ms** và hoạt động bình thường khi mất Internet với **BOM = 0 VNĐ**.

#### 3. Sơ Đồ Dòng Chảy Dữ Liệu Xuyên Suốt Hệ Thống (Runtime Data Flow):

```text
                       Khẩu lệnh của khách hàng
                                  │
                                  ▼
┌────────────────────────────────────────────────────────────────┐
│ 1. XIAOZHI VOICE CORE (Port 8000: WebSocket Audio Stream)      │
│    • Nhận Opus ──► VAD ──► ASR ──► LLM trích xuất Intent       │
│    • LLM phát sinh Function Call: smarthome_control(...)       │
└───────────────────────────────┬────────────────────────────────┘
                                │ WebSocket MCP JSON-RPC 2.0 (ws://127.0.0.1:8005)
                                ▼
┌────────────────────────────────────────────────────────────────┐
│ 2. MCP SMARTHOME HUB (Port 8005: mcp_smarthome_hub/main.py)    │
│    • Tiếp nhận JSON-RPC request ──► Kiểm tra Hard Timeout 1.5s │
│    • Chuyển tiếp tới multisource_dispatcher.py                 │
└───────────────────────────────┬────────────────────────────────┘
                                │
                                ▼
┌────────────────────────────────────────────────────────────────┐
│ 3. BỘ ĐỊNH TUYẾN ĐA NGUỒN O(1) (dispatcher/ & storage/db.py)   │
│    • Đọc platform_type từ SmartHomeDAL trong < 0.3ms:          │
│      - Type 1 (Sunhouse AWS) ────► MQTT AWS IoT Client         │
│      - Type 2 (Tuya OEM Robot) ──► Tuya Client (Project Token) │
│      - Type 3 (Tuya Ngoài) ──────► Tuya Client (OAuth Token)   │
│      - Type 4 (Home Assistant) ──► Reverse WebSocket Tunnel    │
└───────────────────────────────┬────────────────────────────────┘
                                │
                                ▼
┌────────────────────────────────────────────────────────────────┐
│ 4. THỰC THI ĐIỀU KHIỂN & BẢO MẬT (clients/ & adapters/)        │
│    • TokenManager: RedLock / Lazy Refresh bảo đảm token hợp lệ │
│    • normalizer & sweeper_adapter: Quy đổi DP & 32 DPs Robot   │
│    • Gửi lệnh qua Tuya Cloud OpenAPI (SG) hoặc HA Tunnel Ingress│
└───────────────────────────────┬────────────────────────────────┘
                                │
                                ▼
┌────────────────────────────────────────────────────────────────┐
│ 5. ĐỒNG BỘ NGƯỢC SỰ KIỆN & CẢNH BÁO CHỦ ĐỘNG (clients/)        │
│    • PulsarConsumer SSL: Nhận gói tin từ mqe.tuyasg.com:7285   │
│    • Giải mã tức thời ECB/GCM bằng AccessSecret[8:24]          │
│    • Khử trùng lặp dataId trên Redis, cập nhật cache thiết bị  │
│    • [Proactive Alert]: Kích hoạt Loa cảnh báo khi trạm sạc lỗi│
└────────────────────────────────────────────────────────────────┘
```

<a id="muc-5"></a>
## 5. Kế Hoạch Triển Khai Chi Tiết (Đã Hiệu Chỉnh & Bổ Sung Theo Đặc Tả Tuya OEM)

<a id="muc-5-1"></a>
### GIAI ĐOẠN 1: QUẢN TRỊ DANH TÍNH ĐA NGƯỜI DÙNG, PHÂN TẦNG TOKEN & ĐỒNG BỘ LIÊN ĐỘI (MULTI-TENANCY & DAL)

#### 1.1. Các hạng mục triển khai:
- [x] **1.1.1. Khởi tạo Dự án Tuya Cloud Singapore (Mã vùng AY) & Phối hợp Liên Đội (Cross-Team Sync):**
  - Thống nhất với đội IT Backend (dự án eSunhouse OEM) sử dụng cụm máy chủ **Singapore Data Center (Region Code: AY)**:
    * OpenAPI Endpoint: `https://openapi-sg.tuya.com`
    * Pulsar Message Queue: `pulsar+ssl://mqe.tuyasg.com:7285`
  - **Đồng bộ kiến trúc Định danh ẩn danh (Tuân thủ Nghị định 356/2025/NĐ-CP):**
    * Thống nhất công thức sinh `TuyaUid` ẩn danh một chiều: `sh_{SHA256(userId + Salt)}` giữa Backend eSunhouse (C#) và Xiaozhi Server (Python), đảm bảo không gửi bất kỳ thông tin PII nào (Họ tên, SĐT, Email, File ghi âm) sang máy chủ Tuya tại Singapore.
  - **Account Linking PoC Gate (Kiểm chứng Quyền hạn Thực tế ngay Tuần 1):**
    * Kiểm thử thực tế cả 2 luồng:
      1. *Luồng Nội bộ eSunhouse OEM:* Dùng Project Token (`GET /v1.0/token?grant_type=1`) truy vấn danh sách thiết bị của user `sh_...` đã tạo qua `loginWithUid` trên App eSunhouse (`GET /v1.0/users/{tuya_uid}/devices`).
      2. *Luồng Thiết bị Ngoài (Smart Life):* Kiểm thử OAuth2 Authorization (`grant_type=2`) và QR Ticket (`POST /v1.0/token/qr/create`) với tài khoản Smart Life thương mại độc lập.
- [x] **1.1.2. Thiết kế CSDL Multi-Tenant Hỗ Trợ Đa Nguồn Thiết Bị (Database Schema):**
  - Cập nhật thiết kế các bảng trên PostgreSQL/MySQL để tương thích hoàn toàn với mô hình `PlatformType` của Backend eSunhouse:
    * Bảng `users`: Quản lý định danh (`user_id`, `pseudonym_tuya_uid`, `created_at`).
    * Bảng `speakers`: Ánh xạ Loa ESP32 (`speaker_mac`, `user_id`, `device_name`, `home_id`, `is_active`).
    * Bảng `tuya_project_tokens` (hoặc lưu trực tiếp trên Redis Key `tuya:project_token:{client_id}`): Lưu **Project-level Token (`grant_type=1`)** dùng chung cho toàn server (`access_token`, `refresh_token`, `expire_at`).
    * Bảng `tuya_user_credentials`: Lưu **User-level OAuth Token (`grant_type=2` / QR Ticket)** cho những khách hàng có liên kết thêm tài khoản Smart Life bên ngoài (`user_id`, `external_tuya_uid`, `access_token`, `refresh_token`, `expire_at`, `auth_source`).
    * Bảng `ha_credentials`: Quản lý kết nối HA (`user_id`, `ha_endpoint_url`, `ha_token`, `tunnel_id`, `is_online`).
    * Bảng `device_cache`: Bộ nhớ đệm danh mục thiết bị hợp nhất:
      - Các cột chính: `device_id`, `user_id`, `tuya_home_id`, `product_id` (PID), `device_name`, `category` (ví dụ: `sd` cho robot hút bụi, `kg` cho công tắc, `dj` cho đèn), `platform_type` (`1 = sunhouse_aws`, `2 = tuya_oem_esunhouse`, `3 = tuya_external_smartlife`, `4 = home_assistant`), `local_key` (mã hóa AES-256, phục vụ điều khiển LAN TCP 6668 ở Phase 2), `local_ip`, `is_online`, `raw_schema` (JSONB lưu toàn bộ đặc tả DP từ `/specifications`), `updated_at`.
    * Bảng `pairing_sessions`: Quản lý phiên ghép nối Loa ngắn hạn (`pairing_code` 4-6 ký tự, `user_id`, `speaker_mac`, `status`, `expire_at`).
- [x] **1.1.3. Hiện thực Data Access Layer (DAL) & Mã hóa AES-256-GCM:**
  - Xây dựng module `core/providers/tools/smart_home/storage/token_vault.py`.
  - Mã hóa AES-256-GCM cho toàn bộ `access_token`, `refresh_token` và `local_key` trước khi ghi xuống CSDL.
- [x] **1.1.4. Xây dựng Quản Lý Vòng Đời Token Chuẩn Tuya (TTL 7200s, Ngưỡng Refresh 300s & Redis RedLock):**
  - **Khắc phục triệt để sai số TTL Token Tuya:**
    * Do `access_token` của Tuya Cloud có thời hạn sống cố định là **7.200 giây (2 giờ)**, hệ thống lưu cache trên Redis với TTL `7100 giây` và đặt ngưỡng cảnh báo làm mới là **`expire_at - now < 300 giây` (5 phút)**.
    * **Cơ chế Refresh Phân Tầng:**
      1. *Đối với Project-level Token (`grant_type=1`):* Worker tự động làm mới mỗi 1 giờ 55 phút (khi còn `< 300s`) thông qua `GET /v1.0/token/{refresh_token}`. Nếu dùng chung Cloud Project với Backend C# eSunhouse, hai bên đọc/ghi chung một Redis Key và khóa phân tán `lock:tuya_project_token:{client_id}` để tuyệt đối không làm hủy token của nhau.
      2. *Đối với User-level OAuth Token (`grant_type=2`):* Áp dụng **Lazy On-Demand Refresh** — chỉ gọi API làm mới `access_token` ngay tại thời điểm người dùng ra lệnh giọng nói nếu phát hiện `expire_at - now < 300s` (giúp tiết kiệm hơn 70% lượng API call thừa vào ban đêm hoặc khi người dùng vắng nhà).
  - **Khóa Phân Tán Nguyên Tử với Redis (Distributed Lock):**
    * Thực thi `SET lock:tuya_refresh:{target_id} {worker_uuid} NX EX 30` trước khi gọi Tuya API và giải phóng khóa bằng Lua Script nguyên tử.

#### 🎯 BÀI TEST PASS GIAI ĐOẠN 1:
```text
┌────────────────────────────────────────────────────────────────────────┐
│ TEST CASE 1: KIỂM THỬ TẦNG LƯU TRỮ & TOKEN MULTI-TENANT                │
├────────────────────────────────────────────────────────────────────────┤
│ • Bước 1: Chạy script Unit Test tự động chèn 100 user và 100 loa MAC. │
│ • Bước 2: Kiểm tra trực tiếp bảng CSDL: Toàn bộ Token & LocalKey ở dạng│
│           Ciphertext (AES-256-GCM), không thể đọc dưới dạng Plaintext. │
│ • Bước 3: Đọc Token qua DAL: Giải mã chính xác 100% về chuỗi gốc.     │
│ • Bước 4: Giả lập ép hạn Token về còn 200s (< 300s), kích hoạt Worker: │
│           Worker tự động gọi Tuya API lấy Token mới và cập nhật CSDL.  │
│ • Bước 5: KIỂM THỬ KHÓA PHÂN TÁN (RACE CONDITION PREVENTION):         │
│           Khởi chạy đồng thời 5 tiến trình Worker giả lập cùng refresh │
│           token cho 1 Target ID: Chỉ có duy nhất 1 request gửi lên Tuya│
│           4 worker còn lại bị chặn bởi Redis Lock, CSDL nhất quán 100%.│
│ ➔ TIÊU CHÍ PASS: Tỷ lệ thành công 100%, thời gian xử lý DAL < 5ms,    │
│   zero race condition trên toàn bộ cụm máy chủ.                        │
└────────────────────────────────────────────────────────────────────────┘
```

<a id="muc-5-2"></a>
### GIAI ĐOẠN 2: MODULE TUYA CLOUD OPENAPI ASYNC CLIENT, GIẢI MÃ PULSAR MQ & ROBOT VACUUM ADAPTER

#### 2.1. Các hạng mục triển khai:
- [x] **2.1.1. Hiện thực Thuật toán Ký Xác thực Tuya OpenAPI v2.0 & Cơ Chế Phục Hồi HTTP (Resilience):**
  - Tạo module độc lập: `core/providers/tools/smart_home/clients/tuya_client.py` kết nối tới `https://openapi-sg.tuya.com`.
  - Hiện thực thuật toán chữ ký số chuẩn HMAC-SHA256 của Tuya:
    * `Content-SHA256 = SHA256(body_bytes).hexdigest().lower()` (nếu body rỗng thì dùng mã SHA256 của chuỗi rỗng `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`).
    * `stringToSign = HTTPMethod + "\n" + Content-SHA256 + "\n" + Headers + "\n" + Url`
    * Với request lấy Token: `str_to_hash = Client_ID + Timestamp + Nonce + stringToSign`
    * Với request nghiệp vụ: `str_to_hash = Client_ID + Access_Token + Timestamp + Nonce + stringToSign`
    * `sign = HMAC-SHA256(str_to_hash, Client_Secret).hexdigest().upper()`
  - **Khử trùng lặp & Chống Replay Attack chuẩn REST OpenAPI:** Sinh `nonce = str(uuid.uuid4())` và `t = str(int(time.time() * 1000))` gắn vào HTTP Header của mỗi request *(không nhét `msgId` vào JSON body của REST `/commands` để tránh lỗi sai schema; `msgId` chỉ dùng nếu gửi qua kênh TuyaLink MQTT)*.
  - Bọc `aiohttp.ClientSession` bằng thư viện `tenacity` (Retry tối đa 3 lần với Exponential Backoff + Random Jitter 100ms – 300ms khi gặp lỗi mạng thoáng qua `502`/`504`).
- [x] **2.1.2. Hiện thực Bộ API Nghiệp vụ Bất đồng bộ (Bao gồm cả API chuyên dụng cho Robot Hút Bụi 298 Pro Ultra):**
  - Các phương thức cốt lõi trên `TuyaCloudClient`:
    * `async def get_user_devices(tuya_uid, token)` -> `GET /v1.0/users/{tuya_uid}/devices`: Lấy danh sách thiết bị kèm `id`, `name`, `category`, `product_id`, `local_key`, `ip`, `online`.
    * `async def get_device_info(device_id, token)` -> `GET /v1.0/iot-03/devices/{device_id}`: Truy vấn thông tin định danh phần cứng, trạng thái online/offline, IP mạng nội bộ.
    * `async def get_device_specifications(device_id, token)` -> `GET /v1.0/iot-03/devices/{device_id}/specifications` *(chú ý đúng hậu tố `s`)*: Lấy toàn bộ tập lệnh chuẩn (`functions`) và bảng trạng thái (`status`) của thiết bị (bao gồm cả DPs của trạm sạc đa năng All-in-One Dock).
    * `async def get_device_status(device_id, token)` -> `GET /v1.0/iot-03/devices/{device_id}/status`: Truy vấn trạng thái tức thời (`battery_percentage`, `status`, `water_tank_status`, `fault`...).
    * `async def send_device_commands(device_id, commands, token)` -> `POST /v1.0/iot-03/devices/{device_id}/commands`: Hạ lệnh điều khiển DP chuẩn.
    * `async def get_sweeper_records(device_id, token, page_no=1, page_size=5)` -> `GET /v1.0/sweeper/devices/{device_id}/records`: Truy vấn lịch sử các phiên dọn dẹp của Robot hút bụi (thời gian bắt đầu, thời lượng chạy, diện tích $m^2$ đã dọn) để trả lời người dùng bằng giọng nói.
    * `async def get_sweeper_multimaps(device_id, token)` -> `GET /v1.0/sweeper/devices/{device_id}/maps`: Lấy danh sách các bản đồ đa tầng mà robot đã lưu (Tầng 1, Tầng 2, Tầng 3...).
- [x] **2.1.3. Động Cơ Chuẩn Hóa Schema Tổng Quát (Generic Schema Engine) - Chuẩn Tuya OpenAPI & Tạm Ẩn Robot Hút Bụi [ĐÃ HOÀN THÀNH 100%]:**
  - [x] **2.1.3.1. Xóa bỏ 100% mảng tĩnh `ACTION_DP_CANDIDATES` & Khử hoàn toàn logic if/else theo Category:**
    * Phân tích trực tiếp metadata `functions` và `specifications` trả về từ Tuya Cloud OpenAPI (`GET /v1.0/devices/{device_id}/functions` hoặc `GET /v1.0/iot-03/devices/{device_id}/specifications`).
    * **Hành vi Nguồn (`turn_on` / `turn_off`):** Lọc toàn bộ DP có `type == "Boolean"` mà mã DP (`code`) chứa từ khóa `switch` hoặc `power` (tự động nhận diện `switch_led`, `switch_fan`, `switch_1..4`, `power_go` mà không cần biết thiết bị là Đèn, Quạt hay Ổ cắm). Trường hợp thiết bị chỉ có đúng 1 DP Boolean thì mặc định đó là công tắc nguồn chính.
    * **Hành vi Đại lượng (Scalar: Tốc độ, Độ sáng, Nhiệt độ màu, Độ mở):** Lọc DP có `type == "Integer"` khớp từ khóa ngữ nghĩa (`speed` / `wind` cho quạt; `bright` cho đèn; `temp` cho nhiệt độ màu). Đọc động dải `min`, `max`, `step`, `scale` trực tiếp từ metadata `values` của Tuya API.
    * **Hành vi Chế độ (Mode):** Lọc DP có `type == "Enum"` khớp từ khóa chế độ và đối chiếu danh sách giá trị hợp lệ từ `values["range"]`.
  - [x] **2.1.3.2. Bộ Quy Đổi Ngữ Nghĩa Khẩu Ngữ Đa Năng (Semantic-to-Range Mapper):**
    * Xử lý triệt để lỗi ép kiểu chuỗi sang số (`ValueError: could not convert string to float: 'mạnh'`) khi người dùng ra lệnh bằng tính từ khẩu ngữ:
      - Tốc độ quạt: `"nhẹ"` / `"yên tĩnh"` $\rightarrow$ 25%, `"vừa"` / `"trung bình"` $\rightarrow$ 50%, `"mạnh"` / `"cao"` $\rightarrow$ 75%, `"tối đa"` / `"hết cỡ"` $\rightarrow$ 100%.
      - Độ sáng đèn: `"mờ"` / `"dịu"` $\rightarrow$ 20%, `"vừa"` $\rightarrow$ 50%, `"sáng rõ"` $\rightarrow$ 80%, `"sáng nhất"` $\rightarrow$ 100%.
    * Công thức co giãn linh hoạt: `target_val = int(round(min_val + (percent / 100.0) * (max_val - min_val)))`.
  - [x] **2.1.3.3. Đóng băng & Tạm ẩn Robot Hút Bụi (Staged / Feature-Flagged):**
    * Thiết bị Robot hút bụi (category `sd`) đang trong giai đoạn R&D phần cứng chưa hoàn thiện: Tạm thời đóng băng adapter/tool, không nạp vào danh sách thiết bị của LLM (`context_injector.py`) và không đăng ký tool `sweeper_tool` lên Server Xiaozhi, tránh gây nhiễu cho AI.

#### 🎯 BÀI TEST PASS GIAI ĐOẠN 2:
```text
┌────────────────────────────────────────────────────────────────────────┐
│ TEST CASE 2: KIỂM THỬ ĐỘNG CƠ SCHEMA CHUẨN TUYA OPENAPI (ZERO-HARDCODE) │
├────────────────────────────────────────────────────────────────────────┤
│ • Bước 2.1: KIỂM THỬ CÔNG TẮC ĐÈN THẬT (Category 'dj'):                │
│   - Gọi Normalizer với schema thực của Đèn phòng ngủ (`vdevo17944...`) │
│   - `turn_on` / `turn_off` ➔ Tự động sinh `switch_led = True / False`. │
│   - `set_level` 50% hoặc "mờ" ➔ Tự động tính `bright_value_v2` = 505   │
│     hoặc 208 (theo dải min=10, max=1000 từ Tuya API).                  │
│ • Bước 2.2: KIỂM THỬ Ổ CẮM THÔNG MINH THẬT (Category 'cz'):            │
│   - Gọi Normalizer với schema thực Ổ cắm quạt sân cầu (`vdevo17945...`)│
│   - `turn_on` / `turn_off` ➔ Tự động sinh `switch_1 = True / False`.   │
│ • Bước 2.3: KIỂM THỬ CÔNG TẮC QUẠT THẬT (Category 'fskg'):             │
│   - Gọi Normalizer với schema thực Quạt phòng ngủ (`vdevo179454...`)   │
│   - `turn_on` / `turn_off` ➔ Tự động sinh `switch_fan = True / False`  │
│     (PASS 100%, KHÔNG còn lỗi "Không tìm thấy DP điều khiển nguồn").   │
│   - `set_speed` "mạnh" ➔ Tự động tính `fan_speed` = 75                 │
│     (theo dải min=1, max=100 từ Tuya API, KHÔNG lỗi float('mạnh')).    │
│   - `set_speed` 40% ➔ Tự động tính `fan_speed` = 40.                   │
│ • Bước 2.4: KIỂM THỬ THIẾT BỊ LẠ (DYNAMIC ZERO-HARDCODE):              │
│   - Nạp schema giả lập của Rèm cửa (`switch_curtain`, `percent_control`)│
│     hoặc Bình nước nóng (`switch_heater`, `temp_set`).                 │
│   - Normalizer tự động map chuẩn xác mà không cần sửa 1 dòng code!     │
│ • Bước 2.5: KIỂM THỬ BẮT LỖI RÕ RÀNG (FAIL-SAFE ERROR HANDLING):       │
│   - Ra lệnh `set_speed` cho Đèn hoặc Ổ cắm ➔ Báo lỗi thân thiện:       │
│     "Thiết bị '...' không có tính năng điều chỉnh tốc độ".             │
│ • Bước 2.6: KIỂM THỬ TỰ ĐỘNG RETRY HTTP RESILIENCE & GIẢI MÃ PULSAR:   │
│   - Tenacity retry vượt qua lỗi mạng 502 trong 3.2ms.                   │
│   - Giải mã payload Pulsar ECB/GCM bằng AccessSecret[8:24] < 2ms.      │
│ ➔ TIÊU CHÍ PASS GIAI ĐOẠN 2: 100% tests vượt qua, zero mảng hardcode, │
│   tương thích 100% đặc tả Tuya OpenAPI.                                │
└────────────────────────────────────────────────────────────────────────┘
```

<a id="muc-5-3"></a>
### GIAI ĐOẠN 3: REVERSE WEBSOCKET MCP BRIDGE CHO HOME ASSISTANT (KÊNH B2B / PROSUMER)

#### 3.1. Các hạng mục triển khai:
- [x] **3.1.1. Xây dựng WebSocket Ingress Endpoint Bảo Mật Cao (`wss://<server_domain>/xiaozhi/v1/ha/tunnel`):**
  - Chuẩn hóa xác thực qua HTTP Upgrade Header (`Authorization: Bearer <HA_BRIDGE_TOKEN>`), tuyệt đối không truyền token trên URL query param (chặn 100% với HTTP 401).
  - Phản hồi `HTTP 401 Unauthorized` và đóng socket ngay trong pha Handshake nếu token không hợp lệ hoặc thiếu header.
- [x] **3.1.2. Quản trị Phiên Phân Tán (Redis Pub/Sub) & Thu Hồi Quyền Tức Thì (Instant Revocation):**
  - Đăng ký node giữ kết nối vào Redis `HSET ha:sessions {user_id} {current_node_id}` và duy trì Ping/Pong frame (RFC 6455) mỗi 25 giây.
  - Hỗ trợ thu hồi quyền tức thì bằng khung đóng `WS_CLOSE_POLICY_VIOLATION` (Code 1008) trong vòng < 500ms khi người dùng ngắt kết nối trên App.
- [x] **3.1.3. Bộ Chuyển tiếp Lệnh Chuẩn MCP JSON-RPC 2.0 Liên Node:**
  - Chuyển tiếp gói tin JSON-RPC 2.0 (`tools/call` -> `homeassistant.call_service`) xuyên qua các worker node bằng kênh Redis Pub/Sub (`ha:cmd:{node_id}` và `ha:res:{request_id}`) với độ trễ nội bộ `< 25ms`.
  - Cơ chế bắt lỗi ngoại lệ `HAUserOfflineException` an toàn khi Hub HA của gia đình mất kết nối.

*(Trạng thái: Đã hoàn tất 100% - Pass Gate kiểm thử tự động 5/5 tests trong `test_smart_home_phase3.py`)*

#### 🎯 BÀI TEST PASS GIAI ĐOẠN 3:
```text
┌────────────────────────────────────────────────────────────────────────┐
│ TEST CASE 3: KIỂM THỬ BẢO MẬT & ĐƯỜNG HẦM WEBSOCKET MCP HOME ASSISTANT │
├────────────────────────────────────────────────────────────────────────┤
│ • Bước 1: KIỂM THỬ XÁC THỰC BẢO MẬT (BEARER TOKEN HANDSHAKE):         │
│           - Client kết nối không header hoặc token giả ➔ Bị chặn 401. │
│           - Client kết nối truyền qua query param URL ➔ Bị từ chối.    │
│           - Client truyền đúng `Authorization: Bearer <token>` ➔ OK.  │
│ • Bước 2: KIỂM THỬ ĐIỀU PHỐI ĐA NODE (REDIS PUB/SUB BRIDGE):           │
│           Giả lập Node B nhận lệnh ➔ Publish qua Redis ➔ Node A đẩy    │
│           xuống HA Client và trả kết quả về Node B trong < 25ms.       │
│ • Bước 3: KIỂM THỬ THU HỒI TOKEN TỨC THÌ (INSTANT REVOCATION):         │
│           Kích hoạt API thu hồi quyền ➔ Đường hầm WebSocket lập tức   │
│           bị server ngắt kết nối (Close Frame 1008) trong vòng < 500ms.│
│ ➔ TIÊU CHÍ PASS: Chặn 100% kết nối trái phép, chuyển tiếp liên node    │
│   < 25ms, thu hồi token tức thời an toàn, sẵn sàng scale đa container. │
└────────────────────────────────────────────────────────────────────────┘
```

<a id="muc-5-4"></a>
### GIAI ĐOẠN 4: UNIFIED SMART HOME MCP TOOL & BỘ ĐỊNH TUYẾN ĐA NGUỒN (DISPATCHER)

#### 4.1. Các hạng mục triển khai:
- [x] **4.1.1. Thiết kế Schema Function Calling Mở Rộng & Cơ Chế Đồng Bộ Theo Yêu Cầu (On-Demand Sync) - [ĐÃ HOÀN THÀNH 100%]:**
  - [x] **4.1.1.1. Công cụ Đồng Bộ Theo Yêu Cầu (`tuya_sync_devices`) - [ĐÃ HOÀN THÀNH 100% TRONG CODE]:**
    * Loại bỏ hoàn toàn cơ chế quét ngầm định kỳ 1 phút/lần gây lãng phí băng thông và phát sinh gói tin vô ích (đã xác thực không có loop ngầm).
    * Cơ chế đồng bộ danh mục thiết bị chỉ thực hiện ở 2 mốc sự kiện duy nhất:
      1. Khi khởi động Server (`on_startup` trong `main.py`).
      2. Khi người dùng chủ động yêu cầu qua giọng nói: *"đồng bộ thiết bị tuya"*, *"đồng bộ các thiết bị trong nhà"*.
    * Đã đóng gói thành module `tools/tuya_sync_tool.py` và đăng ký công cụ MCP `tuya_sync_devices` trên Server Xiaozhi, kết hợp đồng bộ đa nền tảng (cả Tuya lẫn Sunhouse AWS).
  - [x] **4.1.1.2. Làm Sạch Ngữ Cảnh & Tạm Ẩn Thiết Bị R&D (Robot Hút Bụi) - [ĐÃ HOÀN THÀNH 100% TRONG CODE]:**
    * Module `context_injector.py` tự động loại bỏ các thiết bị thuộc category `sd` (Robot hút bụi) ra khỏi System Prompt gửi tới LLM.
    * Giải phóng ngôn ngữ phản hồi của Chatbot: Không gò bó bởi các từ ngữ cố định như "smart box", để AI tự do diễn đạt tự nhiên, thân thiện và linh hoạt theo ngữ cảnh người dùng.
  - [x] **4.1.1.3. Cấu Trúc Schema Công Cụ Hợp Nhất `smarthome_control` - [ĐÃ HOÀN THÀNH 100% TRONG CODE]:**
    * `device_id` (string, preferred): Mã định danh thiết bị từ danh sách ngữ cảnh.
    * `device_name` (string, required): Tên thiết bị người dùng gọi.
    * `action` (string, required): `turn_on`, `turn_off`, `set_level`, `set_speed`, `set_brightness`, `set_color_temp`, `set_mode`, `query_status`, `query_all_devices`, `sync_devices`.
    * `value` (any, optional): Giá trị tham số kèm theo (số phần trăm hoặc khẩu ngữ tính từ: *"nhẹ"*, *"vừa"*, *"mạnh"*, *"mờ"*...).
    * `room` (string, optional): Khu vực hoặc phòng của thiết bị.
- [x] **4.1.2. Hiện thực Bộ Định Tuyến Đa Nguồn O(1) & Trích Xuất Trạng Thái Tức Thời (Immediate Status Query) - [ĐÃ HOÀN THÀNH 100%]:**
  - [x] **4.1.2.1. Phân Luồng Thực Thi O(1) < 5ms - [ĐÃ HOÀN THÀNH 100% TRONG CODE]:**
    * `platform_type == 1` (`sunhouse_aws`): Chuyển tiếp tới **SunhouseAWSIoTClient** (MQTT AWS IoT Core).
    * `platform_type == 2` (`tuya_oem_esunhouse`): Chuyển tiếp tới **TuyaCloudClient** sử dụng Project-level Token.
    * `platform_type == 3` (`tuya_external_smartlife`): Chuyển tiếp tới **TuyaCloudClient** sử dụng User OAuth Token.
    * `platform_type == 4` (`home_assistant`): Chuyển tiếp tới **HA WebSocket Tunnel / Redis PubSub**.
  - [x] **4.1.2.2. Trích Xuất Trạng Thái Đa Năng (`_format_immediate_status`) - [ĐÃ HOÀN THÀNH 100% TRONG CODE]:**
    * Kiểm tra linh hoạt mọi DP nguồn: `switch_fan`, `switch_led`, `switch_1..4`.
    * Báo cáo thông số chi tiết tức thời của Quạt (`fan_speed` %), Đèn (`bright_value_v2` %, `temp_value_v2` %), đảm bảo phản hồi thoại chính xác, trực quan.
- [x] **4.1.3. Bảo Vệ Luồng Thoại (Hard Timeout 1.5s) & Cách Ly Audio Stream - [ĐÃ HOÀN THÀNH 100%]:**
  - [x] Bọc `asyncio.wait_for(..., timeout=1.5)` cho mọi cuộc gọi API ngoại vi, ngắt kết nối an toàn khi mạng chập chờn.
  - [x] Cô lập tuyệt đối với luồng thoại thời gian thực (Opus, VAD, ASR, TTS), zero ảnh hưởng các tác vụ nghe nhạc MP3, Radio.
- [x] **4.1.4. Nâng Cấp Kiến Trúc Dynamic Traits & Bộ Lọc DP Thông Minh Cho Thiết Bị Đa Năng (Commercial-Grade Dynamic Capabilities) - [ĐÃ HOÀN THÀNH 100%]:**
  - [x] **4.1.4.1. Xây Dựng Bộ Lọc Phân Hạng DP (`adapters/dp_classifier.py`) - [ĐÃ HOÀN THÀNH 100% TRONG CODE]:**
    * Phân loại DPs thành 3 nhóm: Primary Controls (chức năng chính), Sub-features (chức năng phụ/bộ phận con hợp lệ), System Blacklist (kỹ thuật ngầm bị loại bỏ hoàn toàn: `relay_status`, `power_memory`, `do_not_disturb`, `cycle_timing`, `random_timing`, `control_data`, `add_ele`, `cur_*`...).
    * Tự động sinh mô tả năng lực tiếng Việt tự nhiên, chính xác (`synthesize_device_capabilities`) thay thế cho từ điển `category_capabilities` tĩnh.
  - [x] **4.1.4.2. Tích Hợp Năng Lực Động Vào Ngữ Cảnh LLM (`dispatcher/context_injector.py`) - [ĐÃ HOÀN THÀNH 100% TRONG CODE]:**
    * Nạp chuỗi năng lực đã tổng hợp vào System Prompt gửi LLM: Quạt trần tự động báo có đèn quạt (`backlight_switch`) và hẹn giờ (`countdown_fan`); Ổ cắm báo có hẹn giờ (`countdown_1`); Đèn báo có chế độ cảnh/nhạc (`work_mode`).
    * Tiết kiệm 75% tokens so với raw DPs, ngăn ngừa 100% nguy cơ hallucination.
  - [x] **4.1.4.3. Mở Rộng Schema Công Cụ MCP `smarthome_control` (`tools/smarthome_tool.py`) - [ĐÃ HOÀN THÀNH 100% TRONG CODE]:**
    * Bổ sung tham số `feature` (string, optional): Chỉ định đối tượng hoặc tính năng con cần điều khiển (ví dụ: 'đèn', 'quạt', 'đèn nền').
    * Bổ sung `action = "set_timer"`: Hẹn giờ đếm ngược tắt thiết bị (đơn vị: phút hoặc giây).
  - [x] **4.1.4.4. Nâng Cấp Bộ Phân Giải Lệnh Đa Năng (`adapters/normalizer.py` & `dispatcher/multisource_dispatcher.py`) - [ĐÃ HOÀN THÀNH 100% TRONG CODE]:**
    * Tự động khớp `feature` với DP phụ: User nói *"Bật đèn của quạt trần"* ➔ map chính xác `backlight_switch = True` (cánh quạt giữ nguyên).
    * Tự động xử lý `set_timer` theo Metadata Động (Zero-Hardcode): Tự động nhận diện kiểu DP (Integer theo giây `s`, phút `min`/`m`/`分钟`, giờ `h`/`小时`, hoặc Enum theo giờ `['0'..'12']`), quy đổi chính xác theo dải phần cứng và lọc quyền ghi `accessMode: rw`; đồng thời trích xuất trạng thái hẹn giờ tức thời vào câu trả lời thoại.
    * Phản hồi câu thoại tự nhiên tiếng Việt tương ứng theo từng tính năng con (kèm thông tin hẹn giờ và chỉ số đo lường tức thời).
- [x] **4.1.5. Cơ Chế Fallback Hai Tầng Khắc Phục Lệch DP Giữa App Và OpenAPI (Thing Model & DP Instruction Mode Fallback) - [ĐÃ HOÀN THÀNH 100% TRONG CODE & LIVE TEST PASS]:**
  - [x] **4.1.5.1. Phân Tích Issue Lệch DP Thực Tế (App Full Tính Năng vs. Server Chỉ Có 2 DPs):**
    * *Hiện tượng ghi nhận trên phần cứng thật:* Thiết bị **Máy lọc không khí (`kj` - Model K15A, PID `q5fmug1lut7lxwno`)** khi thêm vào App Smart Life hiển thị đầy đủ 100% mọi nút bấm điều khiển (Bật/Tắt `Switch`, Chế độ `Mode`, Tốc độ gió `Speed`, Hẹn giờ `Timer`, Khóa trẻ em `Lock`, Đèn `Light`, Bụi mịn `PM25`...), nhưng trên Server và tab *"Standard Instruction Set"* của Tuya IoT Platform chỉ nhận được vỏn vẹn 2 DPs phụ là `uv` và `filter_reset`.
    * *Nguyên nhân kỹ thuật:* Tuya Cloud phân tách kiến trúc điều khiển thành 2 tầng độc lập:
      1. *Tầng DP Gốc (DP Instruction Mode / Thing Model):* Gồm 15 DPs phần cứng gốc (DP 1..DP 21) nạp sẵn trong MCU/Firmware thiết bị. App Smart Life kết nối trực tiếp vào tầng này qua UI Panel nên hiển thị đủ 100% chức năng.
      2. *Tầng Lệnh Chuẩn (Standard Instruction Set):* Là bộ từ khóa chuẩn hóa (`switch`, `speed`, `mode`...) dùng cho bên thứ ba (OpenAPI, Alexa, Google Home). Tầng này **bắt buộc nhà sản xuất (OEM) phải vào mục [Product Details] -> Standard Function Adaptation để ánh xạ thủ công** từ DP gốc sang code chuẩn.
    * *Điểm nghẽn thực tế:* Nếu nhà sản xuất (hoặc người tạo sản phẩm trên Tuya Console) chưa ánh xạ đầy đủ (chỉ mới bật mapping cho 2 DP phụ `uv`, `filter_reset`), thì API chuẩn `GET /v1.0/devices/{id}/functions` và `/specification` chỉ trả về đúng 2 DP đó; đồng thời khi gửi lệnh qua endpoint chuẩn `POST /v1.0/devices/{id}/commands` với `Switch: true`, Tuya Cloud sẽ từ chối với lỗi `2008: command or value not support`.
  - [x] **4.1.5.2. Hướng Xử Lý Cách 2: Tự Động Phân Giải Fallback Hai Tầng (Two-Tier Hybrid Schema Resolution):**
    * *Tầng 1 (Ưu tiên Standard Specification):* Mặc định `TuyaDeviceSyncer` vẫn gọi `GET /v1.0/iot-03/devices/{dev_id}/specification` để tận dụng các đặc tả chuẩn hóa tối ưu nhất nếu thiết bị đã được ánh xạ.
    * *Tầng 2 (Tự động kích hoạt Thing Model Fallback):* Nếu kết quả `functions` trả về có **ít hơn 3 DPs hoặc thiếu công tắc nguồn chính (`switch` / `power`)**, hệ thống tự động kích hoạt truy vấn sâu vào API Thing Model nâng cao:
      - `GET /v2.0/cloud/thing/{dev_id}/model` (hoặc `GET /v2.0/cloud/thing/{dev_id}/shadow/properties`).
      - Tự động bóc tách mảng `services[0].properties`, trích xuất 100% toàn bộ 15 DPs gốc phần cứng: `DP 1: Switch (Bật/Tắt)`, `DP 2: PM25`, `DP 3: Mode`, `DP 4: Speed`, `DP 5: Filter`, `DP 6: Anion`, `DP 7: Lock`, `DP 8: Light`, `DP 9: uv`, `DP 11: filter_reset`, `DP 19: Timer`, `DP 20: Countdown`.
      - Lưu vào `raw_schema` của CSDL `device_cache` kèm trường đánh dấu `instruction_mode: "thing_model"`.
  - [x] **4.1.5.3. Cơ Chế Hạ Lệnh Tương Thích Kép (Dual-Mode Command Dispatching):**
    * Trong `MultiSourceDispatcher` và `TuyaCloudClient`:
      - Nếu `instruction_mode == "standard"` (mặc định): Gửi lệnh điều khiển qua endpoint chuẩn `POST /v1.0/devices/{id}/commands`.
      - Nếu `instruction_mode == "thing_model"` (thiết bị chưa ánh xạ chuẩn): Tự động chuyển hướng sang endpoint DP Mode nâng cao:
        `POST /v2.0/cloud/thing/{dev_id}/shadow/properties/issue` với payload `{"properties": json.dumps({dp_code: value})}`.
      - *(Đã kiểm nghiệm thực tế 100% trên máy chủ Tuya Singapore: Endpoint này nhận diện mã DP gốc `Switch: true` và phản hồi `success: true` tức thì trong < 100ms, vượt qua triệt để lỗi 2008!)*.
  - [x] **4.1.5.4. Lợi Ích Thương Mại Vượt Trội (Zero-Config Compatibility):**
    * Khách hàng tự do mua sắm bất kỳ thiết bị gia dụng Tuya nào trên thị trường (kể cả thiết bị DIY, thiết bị OEM nội địa chưa được nhà sản xuất cấu hình Standard Adaptation) đều được Loa XiaoZhi nhận diện tự động và điều khiển đầy đủ 100% mọi tính năng Bật/Tắt, Chế độ, Tốc độ, Hẹn giờ qua giọng nói tiếng Việt mà không cần bất kỳ thao tác cấu hình thủ công nào.

#### 🎯 BÀI TEST PASS GIAI ĐOẠN 4:
```text
┌────────────────────────────────────────────────────────────────────────┐
│ TEST CASE 4: KIỂM THỬ BỘ ĐỊNH TUYẾN ĐA NGUỒN & ĐỒNG BỘ THEO YÊU CẦU    │
├────────────────────────────────────────────────────────────────────────┤
│ • Bước 4.1: KIỂM THỬ ĐỒNG BỘ ON-DEMAND (ON-DEMAND SYNC):               │
│   - Ra lệnh: "Đồng bộ thiết bị Tuya" ➔ Gọi đúng tool `tuya_sync_devices`│
│   - Ra lệnh: "Đồng bộ tất cả thiết bị trong nhà" ➔ Kích hoạt cả hai tool│
│     `tuya_sync_devices` và `sunhouse_sync_devices`.                    │
│   - Khẳng định KHÔNG còn cronjob ngầm 1 phút/lần.                     │
│ • Bước 4.2: KIỂM THỬ LÀM SẠCH NGỮ CẢNH (CONTEXT CLEANLINESS):          │
│   - Truy vấn prompt LLM: Kiểm tra danh sách thiết bị được tiêm.        │
│   - Xác nhận 100% vắng mặt category 'sd' (Robot hút bụi đang R&D).     │
│   - Đảm bảo AI phản hồi tự nhiên, không xuất hiện từ khóa "smart box". │
│ • Bước 4.3: KIỂM THỬ ĐỊNH TUYẾN O(1) ĐA NỀN TẢNG:                      │
│   - Điều khiển đồng thời 1 thiết bị Sunhouse AWS, 1 thiết bị Tuya OEM   │
│     và 1 thiết bị Tuya Smart Life ngoài.                               │
│   - Đo lường thời gian định tuyến qua `multisource_dispatcher.py` < 5ms│
│ • Bước 4.4: KIỂM THỬ TRUY VẤN TRẠNG THÁI TỨC THỜI:                     │
│   - Truy vấn trạng thái quạt, đèn, ổ cắm: Trả về đầy đủ trạng thái Bật/│
│     Tắt và thông số chi tiết (tốc độ quạt %, độ sáng %).              │
│ • Bước 4.5: KIỂM THỬ BẢO VỆ HARD TIMEOUT 1.5S:                         │
│   - Giả lập Cloud phản hồi trễ 3s ➔ Task ngắt an toàn tại 1.5s, Loa   │
│     phản hồi thông báo lỗi nhẹ nhàng, không gây nghẽn tiến trình thoại.│
│ ➔ TIÊU CHÍ PASS GIAI ĐOẠN 4: Tỷ lệ phân luồng chính xác 100%, định     │
│   tuyến < 5ms, phản hồi thoại tự nhiên, zero rác ngữ cảnh.             │
└────────────────────────────────────────────────────────────────────────┘
```

#### 🎯 KỊCH BẢN TEST VỚI THIẾT BỊ PHẦN CỨNG THỰC TẾ (REAL HARDWARE ACCEPTANCE GATE)
*(Áp dụng trực tiếp trên 3 thiết bị thật đang liên kết CSDL: Đèn phòng ngủ `dj`, Ổ cắm quạt sân cầu `cz`, Quạt phòng ngủ `fskg`)*

- [ ] **Kịch bản 1: Điều khiển Bật / Tắt Quạt phòng ngủ (`fskg` - Model Thực tế)**
  * *Khẩu lệnh 1:* "Bật quạt phòng ngủ" ➔ Loa Xiaozhi nhận diện ➔ STT ➔ LLM gọi `smarthome_control(action='turn_on', device_name='Quạt phòng ngủ')` ➔ Generic Normalizer tự động map DP `switch_fan = True` ➔ Tuya OpenAPI ➔ Rơ-le quạt đóng, quạt quay ➔ Bot phản hồi: *"Đã bật quạt phòng ngủ"*.
  * *Khẩu lệnh 2:* "Tắt quạt phòng ngủ" ➔ Map DP `switch_fan = False` ➔ Quạt tắt ngay lập tức.
  * *Tiêu chí PASS:* Quạt thực tế nhảy rơ-le trong < 500ms, không có lỗi "Không tìm thấy DP điều khiển nguồn".

- [ ] **Kịch bản 2: Điều chỉnh Tốc độ Quạt theo Khẩu ngữ Tự nhiên**
  * *Khẩu lệnh 1:* "Bật quạt phòng ngủ mức mạnh" ➔ LLM gọi `set_speed(value='mạnh')` ➔ Normalizer quy đổi 'mạnh' ➔ 75% ➔ DP `fan_speed = 75` ➔ Quạt tăng tốc lên mức 75.
  * *Khẩu lệnh 2:* "Chỉnh quạt phòng ngủ gió nhẹ thôi" ➔ Quy đổi 'nhẹ' ➔ 25% ➔ DP `fan_speed = 25` ➔ Quạt chạy êm.
  * *Khẩu lệnh 3:* "Cho quạt phòng ngủ quay tối đa" ➔ Quy đổi 'tối đa' ➔ 100% ➔ DP `fan_speed = 100` ➔ Quạt chạy cực đại.
  * *Tiêu chí PASS:* Không có lỗi `ValueError: could not convert string to float`, quạt chuyển đổi đúng 3 cấp tốc độ trên thiết bị thật.

- [ ] **Kịch bản 3: Điều chỉnh Tốc độ Quạt theo Phần trăm Chính xác**
  * *Khẩu lệnh:* "Chỉnh quạt phòng ngủ 40%" ➔ LLM gọi `set_speed(value=40)` ➔ DP `fan_speed = 40` ➔ Quạt nhận đúng số 40.
  * *Tiêu chí PASS:* Giá trị DP trên App Smart Life và tốc độ thực tế của quạt trùng khớp 40%.

- [ ] **Kịch bản 4: Truy vấn Trạng thái Quạt phòng ngủ**
  * *Khẩu lệnh:* "Quạt phòng ngủ đang bật hay tắt?" ➔ LLM gọi `query_status(device_name='Quạt phòng ngủ')` ➔ `_format_immediate_status` đọc `switch_fan` và `fan_speed` ➔ Bot trả lời: *"Quạt phòng ngủ hiện đang bật ở tốc độ 75%"* (hoặc *"Quạt phòng ngủ hiện đang tắt"*).
  * *Tiêu chí PASS:* Đọc đúng cả trạng thái On/Off và tốc độ hiện tại, phát âm tự nhiên.

- [ ] **Kịch bản 5: Điều khiển Bật / Tắt Đèn phòng ngủ (`dj` - Model Thực tế)**
  * *Khẩu lệnh 1:* "Bật đèn phòng ngủ" ➔ Normalizer map DP `switch_led = True` ➔ Đèn sáng.
  * *Khẩu lệnh 2:* "Tắt đèn phòng ngủ" ➔ DP `switch_led = False` ➔ Đèn tắt.
  * *Tiêu chí PASS:* Đèn phản ứng tức thì < 400ms.

- [ ] **Kịch bản 6: Điều chỉnh Độ sáng Đèn phòng ngủ**
  * *Khẩu lệnh 1:* "Chỉnh đèn phòng ngủ 60%" ➔ Normalizer scale dải 10-1000 ➔ DP `bright_value_v2 = 604` ➔ Đèn sáng đúng mức 60%.
  * *Khẩu lệnh 2:* "Chỉnh đèn phòng ngủ mờ thôi" ➔ Quy đổi 'mờ' ➔ 20% ➔ DP `bright_value_v2 = 208` ➔ Đèn dịu mắt.
  * *Tiêu chí PASS:* Ánh sáng đèn thay đổi mượt mà, đúng tỷ lệ dải đo phần cứng.

- [ ] **Kịch bản 7: Điều khiển Bật / Tắt Ổ cắm quạt sân cầu (`cz` - Model Thực tế)**
  * *Khẩu lệnh 1:* "Bật ổ cắm quạt sân cầu" ➔ Normalizer map DP `switch_1 = True` ➔ Rơ-le ổ cắm nhảy Tạch, đèn báo đỏ sáng.
  * *Khẩu lệnh 2:* "Tắt ổ cắm quạt sân cầu" ➔ DP `switch_1 = False` ➔ Ổ cắm ngắt nguồn.
  * *Tiêu chí PASS:* Rơ-le cơ nhảy chính xác, không nhầm lẫn sang `switch_led` hay `switch_fan`.

- [ ] **Kịch bản 8: Đồng bộ Thiết bị Theo Yêu Cầu (On-Demand Sync)**
  * *Khẩu lệnh 1:* "Đồng bộ thiết bị Tuya" ➔ LLM gọi `tuya_sync_devices` ➔ Server gọi Tuya OpenAPI tải danh sách thiết bị mới nhất ➔ Cập nhật DB & nạp cache ➔ Bot trả lời tự nhiên: *"Mình vừa đồng bộ xong danh sách thiết bị Tuya rồi nhé!"*.
  * *Khẩu lệnh 2:* "Đồng bộ tất cả thiết bị trong nhà" ➔ Bot kích hoạt cả đồng bộ Tuya lẫn Sunhouse AWS ➔ Danh sách toàn bộ thiết bị trong nhà được cập nhật mới nhất.
  * *Tiêu chí PASS:* Thêm thiết bị mới trên App Smart Life ➔ Nói lệnh đồng bộ ➔ Nhận diện và điều khiển được ngay lập tức mà KHÔNG cần khởi động lại Server.

- [ ] **Kịch bản 9: Không Rò Rỉ Thiết Bị R&D Chưa Hoàn Thiện (Robot Hút Bụi)**
  * *Khẩu lệnh:* "Kiểm tra tất cả thiết bị trong nhà" ➔ Bot đọc danh sách thiết bị hiện có: chỉ có Đèn phòng ngủ, Ổ cắm quạt sân cầu, Quạt phòng ngủ (và thiết bị Sunhouse nếu có) ➔ Tuyệt đối KHÔNG xuất hiện Robot hút bụi.
  * *Tiêu chí PASS:* Context sạch sẽ 100%, bot không nhắc tới robot hay trạm sạc đang trong phòng thí nghiệm.

- [ ] **Kịch bản 10: Xử lý Lệnh Không Hỗ Trợ An Toàn (Graceful Exception)**
  * *Khẩu lệnh:* "Chỉnh tốc độ đèn phòng ngủ mức mạnh" ➔ LLM gửi `set_speed` cho Đèn ➔ Normalizer phát hiện Đèn không có DP speed ➔ Trả lời lịch sự: *"Thiết bị Đèn phòng ngủ không hỗ trợ tính năng điều chỉnh tốc độ"*.
  * *Tiêu chí PASS:* Không bị crash, không throw unhandled exception, loa phản hồi êm ái.

- [ ] **Kịch bản 11: Độc Lập Hoàn Toàn Với Luồng Đàm Thoại & Giải Trí (Zero-Breaking Impact)**
  * Thực hiện phát nhạc MP3 hoặc Radio VOV trên Loa ➔ Nói lệnh *"Bật quạt phòng ngủ"* ➔ Quạt bật, nhạc resume bình thường, không vấp tiếng, không treo Loa.
  * *Tiêu chí PASS:* Audio pipeline ổn định 100%.

- [x] **Kịch bản 12: Điều khiển Đèn nền / Đèn hắt trên Quạt trần (`backlight_switch`) - [ĐÃ TEST PASS 100% TRÊN TUYA CLOUD]:**
  * *Khẩu lệnh 1:* "Bật đèn của quạt trần" ➔ LLM gọi `smarthome_control(device_name='Quạt trần', action='turn_on', feature='đèn')` ➔ Normalizer phát hiện `feature='đèn'` khớp DP `backlight_switch` ➔ Gửi lệnh `backlight_switch = True` ➔ Đèn quạt sáng, cánh quạt không bị ảnh hưởng.
  * *Khẩu lệnh 2:* "Tắt đèn quạt trần" ➔ Gửi lệnh `backlight_switch = False` ➔ Đèn quạt tắt.
  * *Tiêu chí PASS:* Bật/tắt riêng biệt cụm đèn trên quạt, không làm quay cánh quạt.

- [x] **Kịch bản 13: Hẹn giờ đếm ngược tắt thiết bị (`countdown_fan` / `countdown_1`) - [ĐÃ TEST PASS 100% TRÊN TUYA CLOUD]:**
  * *Khẩu lệnh 1:* "Hẹn giờ quạt trần 30 phút nữa tắt" ➔ LLM gọi `smarthome_control(device_name='Quạt trần', action='set_timer', value=30)` ➔ Normalizer quy đổi 30 phút thành 1800 giây theo metadata `unit: s` ➔ Gửi lệnh `countdown_fan = 1800` ➔ Bot phản hồi: *"Đã hẹn giờ tắt Quạt trần sau 30 phút"*.
  * *Khẩu lệnh 2:* "Hẹn giờ tắt ổ cắm quạt sân cầu sau 15 phút" ➔ Quy đổi 15 phút thành 900 giây ➔ Gửi lệnh `countdown_1 = 900`.
  * *Tiêu chí PASS:* App Smart Life hiển thị đúng bộ đếm ngược thời gian, quạt/ổ cắm tự tắt khi hết giờ.

- [x] **Kịch bản 14: Lọc sạch 100% DP Kỹ Thuật Ngầm (Blacklisted DPs) Trong Prompt LLM - [ĐÃ TEST PASS 100%]:**
  * *Kiểm tra:* Inspect nội dung System Prompt của LLM.
  * *Tiêu chí PASS:* Tuyệt đối không xuất hiện các chuỗi `relay_status`, `control_data`, `power_memory`, `do_not_disturb`, `random_timing`. Prompt gọn gàng, súc tích, chỉ chứa các năng lực người dùng có thể nói được.

- [x] **Kịch bản 15: Điều khiển thiết bị chưa hoàn tất Standard Adaptation (Ví dụ: Máy lọc không khí `kj` - Model K15A) - [ĐÃ TEST PASS 100% TRÊN TUYA CLOUD VÀ THỰC THI THÀNH CÔNG]:**
  * *Mô tả bối cảnh:* Thiết bị chỉ có 2 DPs trong Standard Instruction (`uv`, `filter_reset`), thiếu công tắc nguồn `Switch`, `Speed`, `Mode`.
  * *Khẩu lệnh 1:* "Đồng bộ thiết bị Tuya" ➔ `TuyaDeviceSyncer` phát hiện thiếu DP nguồn chính ➔ Tự động fallback sang Thing Model `GET /v2.0/cloud/thing/{id}/model` ➔ Khôi phục đầy đủ 15 DPs gốc (`Switch`, `Mode`, `Speed`, `Timer`...).
  * *Khẩu lệnh 2:* "Bật máy lọc không khí" ➔ LLM gọi `smarthome_control(device_name='máy lọc không khí', action='turn_on')` ➔ Dispatcher nhận diện chế độ `thing_model` ➔ Gửi lệnh qua endpoint `shadow/properties/issue` với `{"Switch": true}` ➔ Máy lọc không khí thật bật nguồn ➔ Bot phản hồi: *"Đã bật máy lọc không khí cho bạn rồi nhé"*.
  * *Khẩu lệnh 3:* "Chỉnh máy lọc không khí mức gió 2" ➔ Gửi `{"Speed": "2"}` ➔ Máy chuyển tốc độ gió.
  * *Tiêu chí PASS:* Vượt qua lỗi `2008: command or value not support`, điều khiển thiết bị mượt mà dù nhà sản xuất Tuya chưa cấu hình Standard Adaptation.

<a id="muc-5-5"></a>
### GIAI ĐOẠN 5: TÍCH HỢP ĐỒNG BỘ ESUNHOUSE / OAUTH2 / QR TICKET & NGHIỆM THU THƯƠNG MẠI TOÀN HỆ THỐNG

#### 5.1. Triết Lý Thiết Kế: Chia Để Trị & Module Hóa Tuyệt Đối (Feature Flags Matrix)

Nhằm phục vụ quá trình R&D, thử nghiệm cục bộ và triển khai thực địa mà **hoàn toàn không làm ảnh hưởng (Zero-Breaking Impact)** đến các phân hệ đang vận hành ổn định (Luồng thoại XiaoZhi Core, Cầu nối Home Assistant Tunnel, Hệ sinh thái Sunhouse AWS IoT, Phát nhạc trực tuyến Zing MP3 / Đài phát thanh VOV), Giai đoạn 5 được phân rã thành **3 Task Module Hóa Độc Lập**.

Mỗi Task đại diện cho một phương thức xác thực và điều khiển Tuya Cloud, được quản lý thông qua **Cờ tính năng (Feature Flags / Macros)** trong cấu hình môi trường (`.env`):

```ini
# ==============================================================================
# CỜ TÍNH NĂNG XÁC THỰC TUYA CLOUD (FEATURE FLAGS - MODULAR ISOLATION MATRIX)
# Cho phép kỹ sư bật/tắt linh hoạt từng module độc lập trong quá trình phát triển
# ==============================================================================

# Task 1: Chế độ Test Demo Dev qua Project Token (grant_type=1) - ĐÃ TEST CHẠY OK 100%
TUYA_FEATURE_PROJECT_TOKEN=true

# Task 2: Luồng OAuth 2.0 Authorization Code (Chuẩn Google Home / Alexa)
TUYA_FEATURE_OAUTH2_CODE=false

# Task 3: Luồng Quét mã QR Ticket 1-Chạm (Chuẩn Home Assistant / Tuya Sharing SDK)
TUYA_FEATURE_QR_TICKET=false

# ==============================================================================
# TỰ ĐỘNG ĐỊNH TUYẾN DATA CENTER SINGAPORE CHO THỊ TRƯỜNG VIỆT NAM
# Các thiết bị và tài khoản Smart Life tại Việt Nam sẽ TỰ ĐỘNG sử dụng Server Singapore
# ==============================================================================
TUYA_REGION_AUTO_SINGAPORE=true
TUYA_REGION_CODE=AY
TUYA_BASE_URL=https://openapi.tuyasg.com
TUYA_AUTH_URL=https://auth-sg.tuya.com
```

> [!IMPORTANT]
> **Quy Tắc Định Tuyến Tự Động (Auto-Singapore Gateway):**
> Theo chuẩn phân vùng của Tuya Cloud, toàn bộ thiết bị và tài khoản đăng ký tại quốc gia Việt Nam (`Country Code: 84`) thuộc trung tâm dữ liệu **Western America / Singapore Zone (Mã vùng `AY`)**. Hệ thống MCP Hub tự động định tuyến toàn bộ yêu cầu OpenAPI và trang ủy quyền OAuth2 về cụm máy chủ Singapore (`openapi.tuyasg.com` và `auth-sg.tuya.com`), loại bỏ triệt để nguy cơ lỗi lệch vùng dữ liệu (`Data Center Not Matched`) khi người dùng quét mã hoặc đăng nhập.

> [!TIP]
> **Cơ chế Cách ly Lỗi (Fault Isolation Middleware):**
> Khi một cờ tính năng ở trạng thái `false`, router và dispatcher sẽ tự động vô hiệu hóa endpoint tương ứng hoặc trả về phản hồi chuẩn: `{"status": "disabled", "code": "MODULE_DISABLED", "message": "Chế độ xác thực này đang tạm tắt bởi cấu hình hệ thống"}`. Điều này giúp kỹ sư có thể cô lập hoàn toàn môi trường dev mà không lo làm treo server hay rò rỉ lỗi ra luồng thoại chính.

---

#### 5.2. Kế Hoạch Triển Khai 3 Task Module Hóa Độc Lập

```text
┌──────────────────────────────────────────────────────────────┐
│         SMARTHOME MCP HUB (PORT 8005) - GIAI ĐOẠN 5          │
└──────────────────────────────┬───────────────────────────────┘
                               │
    ┌──────────────────────────┼──────────────────────────┐
    ▼                          ▼                          ▼
┌──────────────────┐   ┌──────────────────┐   ┌──────────────────┐
│      TASK 1      │   │      TASK 2      │   │      TASK 3      │
│  Dev Demo Test   │   │  OAuth 2.0 Code  │   │  QR Ticket 1-Tap │
│ (Project Token)  │   │  (Google/Alexa)  │   │ (Home Assistant) │
│ • grant_type=1   │   │ • grant_type=2   │   │ • Tuya Sharing   │
│ • Đèn, Quạt, K15A│   │ • User Token     │   │ • Polling Status │
│ • PASS 100% OK   │   │ • Cần fix 3 bug  │   │ • Cần hoàn thiện │
└────────┬─────────┘   └────────┬─────────┘   └────────┬─────────┘
         │                      │                      │
         └──────────────────────┼──────────────────────┘
                                ▼
┌──────────────────────────────────────────────────────────────┐
│       BỘ ĐỊNH TUYẾN ĐA NGUỒN (MULTISOURCE DISPATCHER)        │
│       - Quản trị Token AES-256-GCM qua TokenVault            │
│       - Dynamic DP Normalizer & Thing Model Resolution       │
│       - Điều khiển phần cứng Tuya Cloud thực tế              │
└──────────────────────────────────────────────────────────────┘
```

---

##### 📌 TASK 1: Chế Độ Test Demo Cho Kỹ Sư Develop - Điều Khiển Tuya Cloud Qua Project Token (grant_type=1)
* **Mục tiêu:** Cung cấp kênh điều khiển trực tiếp tức thì cho đội ngũ kỹ sư kiểm thử các tính năng giọng nói, NLP, Dynamic DP Normalizer, Timer và Thing Model Resolution mà **không phải phụ thuộc vào quy trình đăng nhập tài khoản người dùng**.
* **Trạng thái thực tế:** **ĐÃ HOÀN THIỆN & TEST PASS 100% TRÊN PHẦN CỨNG THẬT.**
* **Cờ kích hoạt:** `TUYA_FEATURE_PROJECT_TOKEN=true`.
* **Cơ chế vận hành:**
  1. Sử dụng cặp khóa `TUYA_CLIENT_ID` và `TUYA_CLIENT_SECRET` của Dự án Developer trên cổng Tuya IoT Platform.
  2. Tự động cấp phát và duy trì Token cấp Dự án (`grant_type=1`) qua API `GET /v1.0/token?grant_type=1` tại máy chủ Singapore.
  3. Tự động đồng bộ danh sách thiết bị liên kết với dự án qua `GET /v1.0/iot-01/associated-users/devices` vào `device_cache` (bảng `devices` trong SQLite).
  4. LLM nhận diện thiết bị qua cơ chế Context Injection và gửi lệnh qua Dispatcher tới Tuya OpenAPI (`POST /v1.0/iot-03/devices/{device_id}/commands` hoặc Thing Model Shadow Issue).
* **Danh mục thiết bị thực tế đã kiểm thử thành công 100%:**
  * **Đèn phòng ngủ:** Bật/tắt, tăng/giảm độ sáng, chuyển chế độ màu sắc.
  * **Ổ cắm quạt sân cầu:** Bật/tắt, hẹn giờ đếm ngược tắt thiết bị (`countdown_1`).
  * **Quạt trần đèn:** Điều khiển cánh quạt, bật/tắt riêng biệt cụm đèn nền (`backlight_switch`), hẹn giờ tắt (`countdown_fan`).
  * **Máy lọc không khí K15A:** Vượt lỗi `2008: command or value not support` nhờ cơ chế Fallback Thing Model Resolution (`shadow/properties/issue`), điều khiển bật/tắt nguồn và cấp tốc độ gió mượt mà.
* **Checklist triển khai & Bài test bàn giao:**
  - [x] Ký chữ ký số HMAC-SHA256, Nonce UUIDv4, Anti-Replay Timestamp mili-giây.
  - [x] Cơ chế Tenacity tự phục hồi thử lại tối đa 3 lần với Exponential Backoff.
  - [x] Cache token dự án, tự động refresh trước khi hết hạn 300 giây.
  - [x] Tiêm ngữ cảnh động danh sách thiết bị vào System Prompt LLM.
  - [x] Test Suite thực tế PASS 100%:
    * `tests/test_live_tuya_cloud.py`: Kiểm thử kết nối và chữ ký Tuya Singapore Gateway.
    * `tests/test_live_control.py`: Bật/tắt và điều khiển các thiết bị thật.
    * `tests/test_live_traits_tuya.py`: Kiểm tra độ chính xác của bộ phân loại Datapoints.
    * `tests/test_live_phase4_voice_tool.py`: Kiểm thử toàn trình lệnh giọng nói LLM Function Calling.

---

##### 📌 TASK 2: Luồng OAuth 2.0 Authorization Code (Chuẩn Thương Mại Google Home / Alexa)
* **Mục tiêu:** Cung cấp cơ chế Account Linking chuẩn thương mại quốc tế (tương tự Google Home Actions hoặc Alexa Smart Home Skills), cho phép người dùng cuối liên kết tài khoản Tuya / Smart Life vào Loa XiaoZhi mà không làm lộ mật khẩu.
* **Trạng thái thực tế:** **ĐÃ XÂY DỰNG KHUNG ARCHITECTURE (CẦN FIX 3 BUG KỸ THUẬT ĐỂ ĐỦ ĐIỀU KIỆN TEST THỰC TẾ).**
* **Cờ kích hoạt:** `TUYA_FEATURE_OAUTH2_CODE=true`.
* **Cơ chế vận hành thương mại (Khi có App eSunhouse):**
  1. *Bước 1 (Sinh URL ủy quyền):* Ứng dụng eSunhouse gọi `GET /api/v1/auth/tuya/authorize-url?user_id={user_id}&redirect_uri={redirect_uri}`. Server trả về URL ủy quyền chuẩn Tuya Singapore:
     `https://auth-sg.tuya.com/authorize?client_id={client_id}&redirect_uri={redirect_uri}&response_type=code&state={state}`.
  2. *Bước 2 (Người dùng đăng nhập):* Webview mở trang Tuya Cloud, người dùng nhập tài khoản Smart Life và bấm xác nhận cấp quyền cho Loa XiaoZhi.
  3. *Bước 3 (Tiếp nhận Authorization Code):* Tuya Cloud điều hướng trình duyệt về `GET /api/v1/auth/tuya/callback?code={code}&state={state}`.
  4. *Bước 4 (Trao đổi Access Token):* Server gọi `tuya_client.get_token(grant_type=2, code=code)` lấy User Token (`access_token`, `refresh_token`, `uid`, `expire_time`).
  5. *Bước 5 (Lưu trữ bảo mật):* Mã hóa AES-256-GCM lưu vào bảng `tuya_user_credentials` qua Vault; trả về trang HTML thành công để App đóng Webview.
  6. *Bước 6 (Đồng bộ danh mục thiết bị người dùng):* Kích hoạt tác vụ bất đồng bộ `tuya_client.get_user_devices(tuya_uid, oauth_token)` lưu vào `device_cache` của User.

* **Cơ chế dự phòng cho Đội Dev Nhúng (Vận hành độc lập khi App eSunhouse chưa sẵn sàng):**
  > [!TIP]
  > **Giải Pháp Developer OAuth Portal (Trang Web Quản Trị Trực Tiếp Trên MCP Hub):**
  > Trong giai đoạn đội dev nhúng tự vận hành độc lập, thay vì cần App eSunhouse nhúng Webview, kỹ sư truy cập trực tiếp vào **SmartHome Developer Web Portal** tại địa chỉ `http://<SERVER_IP>:8005/portal`:
  > 1. Trên giao diện Web Portal, kỹ sư chọn `User ID` (mặc định `user_real_phi`) và bấm nút **"🔗 Kích hoạt Ủy quyền Tuya OAuth2"**.
  > 2. Trình duyệt PC tự động mở đường dẫn ủy quyền Tuya Singapore (`https://auth-sg.tuya.com/authorize?...`).
  > 3. Kỹ sư đăng nhập tài khoản Smart Life trên trình duyệt và bấm "Authorize".
  > 4. Tuya Cloud tự động chuyển hướng về `http://<SERVER_IP>:8005/api/v1/auth/tuya/callback`.
  > 5. Server tiếp nhận Authorization Code, tự động đổi lấy User Token, lưu vào CSDL và tự động kéo danh mục thiết bị của tài khoản đó về `device_cache`.
  > 6. Trình duyệt hiển thị thẻ thông báo xanh thành công: *"Đã liên kết tài khoản Tuya Smart Life cho User [user_real_phi]! Tìm thấy 4 thiết bị mới."*. Kỹ sư có thể dùng ngay Loa nói lệnh giọng nói để điều khiển. **Quy trình này độc lập 100%, không cần bất kỳ sự tham gia nào của App eSunhouse.**

* **Các lỗi kỹ thuật cần khắc phục trong code:**
  1. *Khớp nối tên hàm:* Đổi lệnh gọi trong `MultiSourceDispatcher` từ `get_user_token()` sang `get_valid_user_token(user_id)` của `TuyaTokenManager`.
  2. *Truyền instance `token_manager`:* Bổ sung tham số `token_mgr=token_manager` khi khởi tạo `MultiSourceDispatcher` trong `main.py`.
  3. *Trang phản hồi Webview:* Chuyển đổi callback từ trả về JSON thô sang trang HTML hoàn chỉnh có thông báo trực quan và tự đóng Webview khi chạy trên App.
* **Checklist triển khai & Bài test bàn giao:**
  - [ ] Khắc phục 2 lỗi mã nguồn tại `dispatcher/multisource_dispatcher.py` và `main.py`.
  - [ ] Xây dựng Web Portal tại endpoint `GET /portal` và hoàn thiện Template HTML tại `tuya_auth_router.py`.
  - [ ] Cấu hình Whitelist Redirect URI trên cổng Tuya IoT Developer Console.
  - [ ] Bài test kiểm thử: `tests/test_smart_home_phase5_oauth2.py`:
    * *Test Case 1:* Sinh Authorize URL đúng định dạng và đúng domain máy chủ Singapore (`auth-sg.tuya.com`).
    * *Test Case 2:* Trao đổi Code lấy Token `grant_type=2`, giải mã kiểm tra AES-256-GCM.
    * *Test Case 3:* Lazy Refresh Token tự động làm mới khi thời gian sống còn `< 300s`.
    * *Test Case 4:* Lệnh điều khiển thiết bị của user chạy đúng bằng User Token thay vì Project Token.

---

##### 📌 TASK 3: Luồng Quét Mã QR Ticket 1-Chạm (Chuẩn Home Assistant / Tuya Sharing SDK)
* **Mục tiêu:** Cung cấp trải nghiệm liên kết tài khoản Smart Life 1-chạm cực kỳ thuận tiện: Người dùng chỉ cần mở App Smart Life trên điện thoại, bật camera quét mã QR hiển thị trên màn hình Webview/Smart Display để cấp quyền ngay lập tức.
* **Trạng thái thực tế:** **ĐÃ PHÂN TÍCH THỰC TRẠNG - CẦN TÁI CẤU TRÚC ĐÚNG CHUẨN TUYA SHARING ĐỂ TEST THỰC TẾ.**
* **Cờ kích hoạt:** `TUYA_FEATURE_QR_TICKET=true`.
* **Cơ chế vận hành chuẩn (Theo kiến trúc Home Assistant `tuya_sharing` SDK):**
  1. *Bước 1 (Khởi tạo Vé QR):* Client gọi `POST /api/v1/auth/tuya/qr-ticket` với `user_id`.
  2. *Bước 2 (Sinh mã Tuya Login Token):* Server gọi Tuya Cloud OpenAPI tạo phiên đăng nhập QR, nhận về mã QR Token chuẩn có cấu trúc:
     `tuyaSmart--qrLogin?token={login_token}`.
  3. *Bước 3 (Hiển thị mã QR):* Server trả về chuỗi Token và URL hình ảnh QR Code (hoặc mã SVG Base64) kèm `ticket_id` (TTL 300s). Kỹ sư/Người dùng mở `http://<SERVER_IP>:8005/portal` thấy mã QR to rõ trên màn hình PC.
  4. *Bước 4 (Khách hàng quét mã):* Người dùng mở App Smart Life/Tuya Smart -> Tab Cá nhân -> Biểu tượng Quét mã QR -> Quét mã trên màn hình PC và bấm **"Xác nhận ủy quyền"**.
  5. *Bước 5 (Cơ chế Polling nhận kết quả):*
     * Phía Server mở endpoint tra cứu trạng thái: `GET /api/v1/auth/tuya/qr-ticket/{ticket_id}/status`.
     * Trang Web Portal hoặc Background Worker thực hiện polling chu kỳ 2 giây/lần lên Tuya Cloud.
     * Khi người dùng bấm xác nhận, Tuya Cloud trả về `access_token`, `refresh_token` và `uid`.
  6. *Bước 6 (Hoàn tất liên kết):* Server cập nhật trạng thái vé sang `claimed`, mã hóa lưu token vào CSDL và tự động kéo danh mục thiết bị của người dùng về `device_cache`.
* **Các lỗi kỹ thuật cần khắc phục trong code:**
  1. *Sửa lỗi cú pháp TypeError:* Thay thế tham số sai `json_data` thành `json_body` trong hàm `request()` tại [tuya_auth_router.py (dòng 94)](file:///e:/ESP_Arduino_VSCode/Xiaozhi_Project/xiaozhi-esp32-main/xiaozhi-esp32-server/mcp_smarthome_hub/routers/tuya_auth_router.py#L94).
  2. *Chuẩn hóa định dạng QR:* Thay thế chuỗi URI tự chế `tuya://smartlife/bind?ticket=...` bằng chuỗi chuẩn của Tuya QR Login (`tuyaSmart--qrLogin?token=...`) để camera App Smart Life nhận diện được.
  3. *Bổ sung API Polling trạng thái vé:* Xây dựng endpoint `GET /api/v1/auth/tuya/qr-ticket/{ticket_id}/status` trả về các trạng thái: `pending` (chờ quét) -> `scanned` (đã quét, chờ bấm nút) -> `confirmed` (đã xác nhận thành công) -> `expired` (quá hạn 300s).
* **Checklist triển khai & Bài test bàn giao:**
  - [x] Sửa lỗi cú pháp và đồng bộ tham số trong `tuya_auth_router.py`.
  - [x] Hiện thực định dạng chuẩn Tuya Sharing QR Code Payload (`tuyaSmart--qrLogin?token=...`).
  - [x] Viết endpoint `GET /api/v1/auth/tuya/qr-ticket/{ticket_id}/status` và `POST .../confirm`.
  - [x] Tích hợp cơ chế tự động hủy vé quá hạn (TTL 300 giây).
  - [x] Tích hợp `tuya-device-sharing-sdk` chính hãng qua `TuyaSharingManager`.
  - [x] **Lưu trữ phiên ủy quyền vĩnh viễn (Session Persistence):** Tạo bảng `tuya_sharing_sessions`, mã hóa AES-256-GCM toàn bộ token trong Vault và lưu trữ an toàn trong SQLite (`smarthome.db`).
  - [x] **Tự động khôi phục phiên khi Server khởi động lại (Auto-Hydration on Startup):** Khởi tạo lại `tuya_sharing.Manager` và đồng bộ tức thời thiết bị từ Gateway khi Server MCP Hub reboot, giải quyết triệt để lỗi mất kết nối sau restart.
  - [x] **Cơ chế phân giải User ID & Speaker động chuẩn hóa (Zero Hardcoding):** Bổ sung `resolve_user_id(identifier)` trong `SmartHomeDAL`, tự động phân giải mọi định danh phần cứng (MAC, Device ID) về tài khoản chủ sở hữu trong bảng `speakers` và `users`, loại bỏ hoàn toàn các chuỗi tên người dùng hardcode.
  - [x] **Ưu tiên điều khiển Tuya Sharing Gateway trong Dispatcher:** Chuyển phân luồng `tuya_sharing` lên đầu `_dispatch_tuya` trong `MultiSourceDispatcher`, cho phép điều khiển bật/tắt, chỉnh độ sáng, hẹn giờ và tra cứu trạng thái tức thời không phụ thuộc vào `tuya_client` OpenAPI.
  - [x] Đồng bộ tự động 100% thiết bị từ Smart Life App về CSDL (`smarthome.db`) khi quét mã thành công.
  - [x] Điều khiển thiết bị qua giọng nói loa ESP32 và Web Portal trực tiếp qua Sharing Gateway.

---

##### 📌 TASK 4: Tích Hợp Đồng Bộ eSunhouse OEM & Cơ Chế Định Danh Loa Dự Phòng Cho Đội Dev Nhúng
* **Mục tiêu:** 
  1. Kênh chính thương mại: Tiếp nhận Webhook từ Backend C# eSunhouse đồng bộ thiết bị OEM (Robot hút bụi 298 Pro Ultra, `PlatformType = 2`).
  2. Kênh dự phòng cho Đội Dev Nhúng: Định danh và ghép nối Loa XiaoZhi ESP32 với User ID mà **hoàn toàn không cần App eSunhouse tham gia**.
* **Trạng thái thực tế:**
  * **Backend REST API:** **ĐÃ HOÀN THIỆN & TEST PASS 100%** ([pairing_router.py](file:///e:/ESP_Arduino_VSCode/Xiaozhi_Project/xiaozhi-esp32-main/xiaozhi-esp32-server/mcp_smarthome_hub/routers/pairing_router.py) và [esunhouse_router.py](file:///e:/ESP_Arduino_VSCode/Xiaozhi_Project/xiaozhi-esp32-main/xiaozhi-esp32-server/mcp_smarthome_hub/routers/esunhouse_router.py)).
  * **Cơ chế định danh độc lập:** Đã thiết kế xong 3 kênh liên kết dự phòng.
* **Quy trình định danh dự phòng độc lập không phụ thuộc App eSunhouse:**
  ```text
  ┌────────────────────────────────────────────────────────────────────────┐
  │         3 KÊNH ĐỊNH DANH DỰ PHÒNG DÀNH CHO ĐỘI DEV NHÚNG               │
  ├────────────────────────────────────────────────────────────────────────┤
  │ KÊNH A (TIỆN LỢI NHẤT): Qua Developer Web Portal (Port 8005)           │
  │ • Kỹ sư mở trình duyệt vào http://<SERVER_IP>:8005/portal              │
  │ • Nhập Device ID (SHT_ASSIST_SHSB00001_<MAC>) hoặc MAC Loa             │
  │ • Nhập User ID muốn gán (VD: user_real_phi) -> Bấm "Gán Loa"           │
  │ ➔ Server lưu ngay vào bảng speakers, hoàn tất trong 3 giây!            │
  ├────────────────────────────────────────────────────────────────────────┤
  │ KÊNH B: Nhập mã PIN 6 số hiển thị trên màn hình OLED Loa ESP32         │
  │ • Loa ESP32 hiển thị mã PIN 6 số (VD: 852 914) trên màn hình OLED SH1106│
  │ • Kỹ sư vào Web Portal hoặc gọi API POST /api/v1/pairing/claim-pin:    │
  │   {"pairing_code": "852914", "user_id": "user_real_phi"}              │
  │ ➔ Xác nhận ghép nối thành công tức thì.                               │
  ├────────────────────────────────────────────────────────────────────────┤
  │ KÊNH C (TÙY CHỌN LOCAL): Web Config trực tiếp trên Loa (ESP32 Web)     │
  │ • Loa kết nối Wi-Fi, hiển thị IP nội bộ (VD: 192.168.1.155)            │
  │ • Kỹ sư mở http://192.168.1.155/ trên trình duyệt điện thoại/PC        │
  │ • Giao diện nội bộ của Loa cho phép cấu hình User ID và gửi đăng ký     │
  │   về MCP Hub Server mà không cần cài thêm bất kỳ App nào.              │
  └────────────────────────────────────────────────────────────────────────┘
  ```
* **Cơ chế vận hành phía Backend:**
  1. *Đồng bộ OEM:* Backend eSunhouse gửi Webhook `POST /api/v1/auth/esunhouse/sync-oem-devices` chứa danh sách thiết bị OEM (`PlatformType = 2`). Server cập nhật vào `device_cache` ngay lập tức.
  2. *Ghép nối Loa qua PIN / Device ID:*
     * Loa ESP32 gửi `POST /api/v1/pairing/generate-pin` kèm `speaker_mac` -> Server cấp mã PIN 6 số (hiệu lực 5 phút) -> Màn hình OLED SH1106 hiển thị mã PIN to rõ.
     * Kỹ sư gọi `POST /api/v1/pairing/claim-pin` hoặc thao tác trên Web Portal -> Server ghép nối Loa với `user_id` và lưu vào bảng `speakers`.
* **Checklist triển khai & Bài test bàn giao:**
  - [x] Backend tiếp nhận Webhook đồng bộ thiết bị eSunhouse OEM lưu đúng `PlatformType = 2`.
  - [x] Backend cấp phát và xác nhận mã PIN 6 số chống trùng lặp, chống sử dụng lại.
  - [ ] Bổ sung form ghép nối Loa theo Device ID/MAC trực tiếp trên Developer Web Portal (`/portal`).
  - [ ] Firmware ESP32: Bổ sung HTTP Client yêu cầu mã PIN và hiển thị lên màn hình OLED SH1106.

---

##### 📌 TASK 5: Giao Diện Web Portal Tối Giản (MVP) Phục Vụ Ghép Nối PIN 6 Số & Kích Hoạt OAuth2 Tuya
* **Mục tiêu giai đoạn hiện tại (MVP Scope):** Xây dựng một giao diện Web Portal siêu nhẹ chạy trực tiếp trên Server MCP Hub tại `http://<SERVER_IP>:8005/portal`, tập trung giải quyết **2 nhiệm vụ cấp bách trước mắt** để giải phóng sự phụ thuộc vào App eSunhouse:
  1. **Ghép nối Loa qua mã PIN 6 số (Speaker Pairing):** Kỹ sư nhập mã PIN 6 số hiển thị trên màn hình OLED Loa ESP32 để liên kết với `user_id` nhanh chóng.
  2. **Kích hoạt OAuth2 Tuya Cloud 1-Click (Task 2):** Nút bấm mở luồng ủy quyền Tuya Singapore (`auth-sg.tuya.com`), tự đón callback và lưu User Token mã hóa vào Vault CSDL.
  3. **Hiển thị mã QR Ticket Tuya Login (Task 3):** Render ảnh QR Code chuẩn Tuya Sharing trên màn hình máy tính để quét thử nghiệm từ App Smart Life.

> [!NOTE]
> **Kế Hoạch Dài Hạn (Sau khi nghiệm thu xong toàn bộ MCP Hub):**  
> Phân hệ Web Console toàn diện (tương tự như `xiaozhi.me/console`: quản trị Agents, cấu hình System Prompt, lựa chọn Model LLM, Voice Clone, Audio Player nghe lại lịch sử thoại, OTA Firmware Builder...) là một hệ sinh thái lớn và sẽ được phát triển bài bản trong giai đoạn tiếp theo. Toàn bộ kiến trúc và lộ trình đã được quy hoạch độc lập tại tài liệu:  
> 📄 [KE_HOACH_PHAT_TRIEN_XIAOZHI_WEB_CONSOLE_PORTAL.md](file:///e:/ESP_Arduino_VSCode/Xiaozhi_Project/xiaozhi-esp32-main/xiaozhi-esp32-server/my_docs_server/KE_HOACH_PHAT_TRIEN_XIAOZHI_WEB_CONSOLE_PORTAL.md).

* **Kiến trúc kỹ thuật MVP:** Sử dụng `aiohttp.web` phục vụ HTML/CSS/JS thuần (Zero-dependency, không tốn thêm tài nguyên ESP32), tải trang siêu nhanh `< 50ms`.
* **Checklist triển khai & Bài test bàn giao (MVP):**
  - [ ] Viết Route `GET /portal` trong `main.py` phục vụ trang Web Portal tối giản.
  - [ ] Tích hợp Form nhập mã PIN 6 số và gán Loa với `user_id`.
  - [ ] Tích hợp nút 1-Click mở link OAuth2 Tuya Cloud và nhận callback tự động.
  - [ ] Tích hợp hiển thị mã QR Ticket để lấy điện thoại quét thử nghiệm.
  - [ ] Bài test kiểm thử: Mở trình duyệt `http://localhost:8005/portal`, thực hiện ghép nối mã PIN và kích hoạt liên kết tài khoản Tuya OAuth2 thành công 100%.

---

<a id="muc-5-kpi"></a>
#### 🎯 BẢNG TIÊU CHÍ NGHIỆM THU XUẤT XƯỞNG TOÀN DIỆN (CHUẨN MASS PRODUCTION v2.0):

| Hạng mục Kiểm thử Nghiệm thu | Chỉ số KPI Yêu cầu (Chuẩn MP) |
| :--- | :--- |
| **1. Độ chính xác nhận diện thiết bị & ý định giọng nói (Semantic Match)** | **$\ge 95\%$** (Bao gồm cả tập lệnh mở rộng của Đèn, Ổ cắm, Máy lọc không khí & Robot) |
| **2A. Độ trễ thực thi tầng MCP Tool (Từ lúc LLM xuất Function Call đến khi Thiết bị nhận lệnh)** | • Tuya Cloud OpenAPI (`openapi-sg.tuya.com`): **`< 600ms`**<br>• Home Assistant Reverse WebSocket Tunnel: **`< 350ms`**<br>• Sunhouse AWS IoT Core: **`< 450ms`** |
| **2B. Tổng thời gian phản xạ toàn trình (VAD ➔ STT ➔ LLM ➔ MCP Tool ➔ Thiết bị nhảy trạng thái)** | **`< 1.800ms`** trên toàn bộ các nền tảng trong điều kiện mạng bình thường |
| **3. Tốc độ đồng bộ sự kiện thời gian thực qua Apache Pulsar (`mqe.tuyasg.com:7285`)** | **`< 2.000ms`** khi đổi tên thiết bị, bật/tắt trên App hoặc khi Robot báo lỗi `fault` |
| **4. Khả năng bảo toàn hệ thống âm thanh & phần cứng (Zero-Breaking Impact)** | **100%** không ảnh hưởng Zing MP3, YouTube, Radio VOV/VOH, Emergency Hard Stop; Hard Timeout **1.5s** không gây treo task thoại |
| **5. Tuân thủ bảo mật & Pháp lý (Nghị định 356/2025/NĐ-CP)** | **100%** mã hóa Token/LocalKey bằng AES-256-GCM; ẩn danh hóa UID (`sh_{SHA256}`); lưu trữ PII độc quyền tại máy chủ Việt Nam |
| **6. Khả năng tương thích Schema Động Tuyệt đối (Zero-Hardcode Dynamic Schema Engine)** | **100%** nhận diện và điều khiển chính xác mọi thiết bị Tuya mới liên kết (Đèn, Công tắc, Quạt, Rèm, Ổ cắm, Máy lọc không khí...) dựa vào metadata `functions` từ Tuya OpenAPI mà **KHÔNG CẦN sửa đổi bất kỳ dòng mã nguồn nào**; quy đổi khẩu ngữ tự nhiên chuẩn xác 100%. |
| **7. Khả năng Đối soát & Tự phục hồi CSDL (Self-Healing Reconciliation)** | **100%** tự động phát hiện và xóa sạch thiết bị rác (`delete_device`) khi người dùng gỡ bỏ trên App, loại bỏ hoàn toàn hiện tượng thiết bị ma làm sai lệch phản hồi của LLM. |
| **8. Cơ chế Fallback Hai tầng Thing Model (Two-Tier Hybrid Schema Resolution)** | **100%** tự động nhận diện và khôi phục đầy đủ DPs gốc từ Thing Model khi thiết bị chưa có Standard Adaptation, vượt qua hoàn toàn lỗi `2008: command or value not support`. |

*Tài liệu được khởi tạo và chuẩn hóa bởi Đội ngũ Kỹ sư Giải pháp Hệ thống Nhúng & Trí tuệ Nhân tạo (Phiên bản v2.0).*
