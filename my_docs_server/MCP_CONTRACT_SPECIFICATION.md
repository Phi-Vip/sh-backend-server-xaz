# HỢP ĐỒNG GIAO DIỆN MCP & ĐẶC TẢ BIÊN GIỚI MODULE (MCP CONTRACT SPECIFICATION)

> **Mã tài liệu:** MCP-SPEC-2026-V1.0  
> **Trạng thái:** KHÓA CHẶT (FROZEN)  
> **Phạm vi áp dụng:** Giao tiếp giữa `xiaozhi-server` (Voice Core) $\leftrightarrow$ `mcp_smarthome_hub` (Port 8005) & `mcp_sunhouse_rag` (Port 8004)  
> **Nguyên tắc cốt lõi:** *Chia để trị — Module hóa — Không phá vỡ (Decoupled & Zero-Breaking).*

---

## 1. NGUYÊN TẮC BIÊN GIỚI & GIAO THỨC CHUẨN

1. **Giao thức vận chuyển:** WebSocket Full-Duplex (`ws://...` hoặc `wss://...`).
2. **Định dạng dữ liệu:** JSON-RPC 2.0 (`"jsonrpc": "2.0"`).
3. **Cổng kết nối mặc định:**
   * `mcp_sunhouse_rag`: `ws://127.0.0.1:8004/mcp_endpoint/mcp/?token=<mcp_token>`
   * `mcp_smarthome_hub`: `ws://127.0.0.1:8005/mcp_endpoint/mcp/?token=<mcp_token>`
4. **Cô lập mã nguồn:** Voice Core (`xiaozhi-server`) giao tiếp với các MCP Hub hoàn toàn qua giao thức mạng mạng nội bộ (LAN/Docker Network). Tuyệt đối **không** import chéo mã nguồn nội bộ giữa các module.

---

## 2. QUY TRÌNH BẮT TAY MCP (MCP HANDSHAKE LIFECYCLE)

```text
[ XiaoZhi Voice Core ]                                   [ MCP Hub Server ]
         │                                                        │
         │  1. WebSocket Connect (?token=...)                     │
         ├───────────────────────────────────────────────────────>│
         │                                                        │
         │  2. request: "initialize" (protocolVersion, clientInfo)│
         ├───────────────────────────────────────────────────────>│
         │  response: serverInfo, capabilities                    │
         │<───────────────────────────────────────────────────────┤
         │                                                        │
         │  3. notification: "notifications/initialized"          │
         ├───────────────────────────────────────────────────────>│
         │                                                        │
         │  4. request: "tools/list"                              │
         ├───────────────────────────────────────────────────────>│
         │  response: tools: [ {name, description, inputSchema} ] │
         │<───────────────────────────────────────────────────────┤
         │                                                        │
         │  5. request: "tools/call" (name, arguments)            │
         ├───────────────────────────────────────────────────────>│
         │  response: content: [ {type: "text", text: "..."} ]    │
         │<───────────────────────────────────────────────────────┤
```

### Bước 1: Khởi tạo (`initialize`)
* **Request:**
  ```json
  {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
      "protocolVersion": "2024-11-05",
      "clientInfo": {
        "name": "xiaozhi-voice-core",
        "version": "2.1.0"
      }
    }
  }
  ```
* **Response:**
  ```json
  {
    "jsonrpc": "2.0",
    "id": 1,
    "result": {
      "protocolVersion": "2024-11-05",
      "serverInfo": {
        "name": "mcp_smarthome_hub",
        "version": "1.0.0"
      },
      "capabilities": {
        "tools": {}
      }
    }
  }
  ```

### Bước 2: Thông báo sẵn sàng (`notifications/initialized`)
* **Notification:**
  ```json
  {
    "jsonrpc": "2.0",
    "method": "notifications/initialized",
    "params": {}
  }
  ```

### Bước 3: Đọc danh sách công cụ (`tools/list`)
* **Request:**
  ```json
  {
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/list",
    "params": {}
  }
  ```

### Bước 4: Thực thi công cụ (`tools/call`)
* **Request:**
  ```json
  {
    "jsonrpc": "2.0",
    "id": 3,
    "method": "tools/call",
    "params": {
      "name": "<tool_name>",
      "arguments": { ... }
    }
  }
  ```
* **Response thành công:**
  ```json
  {
    "jsonrpc": "2.0",
    "id": 3,
    "result": {
      "content": [
        {
          "type": "text",
          "text": "<ket_qua_tra_ve_dang_chuoi>"
        }
      ]
    }
  }
  ```

---

## 3. DANH MỤC CÔNG CỤ MCP SMARTHOME HUB (PORT 8005)

### Tool 1: `smarthome_control`
* **Mục đích:** Điều khiển bật/tắt, tăng giảm độ sáng, đổi màu, chỉnh nhiệt độ, tốc độ hoặc tra cứu trạng thái thiết bị trong nhà thông minh Tuya / Smart Life.
* **Input Schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "action": {
        "type": "string",
        "enum": ["turn_on", "turn_off", "set_brightness", "set_color", "set_temperature", "set_speed", "query_status"],
        "description": "Hành động điều khiển"
      },
      "device_name": {
        "type": "string",
        "description": "Tên thiết bị thân thiện (ví dụ: 'đèn phòng khách', 'quạt cây')"
      },
      "device_id": {
        "type": "string",
        "description": "Mã định danh thiết bị Tuya (nếu biết)"
      },
      "value": {
        "type": "number",
        "description": "Giá trị số (độ sáng 1-100, nhiệt độ 16-30, tốc độ quạt)"
      },
      "color": {
        "type": "string",
        "description": "Tên màu sắc (ví dụ: 'đỏ', 'xanh dương', 'vàng ấm')"
      }
    },
    "required": ["action"]
  }
  ```

### Tool 2: `tuya_sync_devices`
* **Mục đích:** Đồng bộ danh sách thiết bị và trạng thái mới nhất từ Tuya IoT Cloud Platform về cơ sở dữ liệu cục bộ.
* **Input Schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "force_refresh": {
        "type": "boolean",
        "default": true,
        "description": "Bắt buộc kéo mới từ Cloud bỏ qua cache"
      }
    }
  }
  ```

---

## 4. DANH MỤC CÔNG CỤ MCP SUNHOUSE RAG (PORT 8004)

### Tool 1: `tra_cuu_thong_tin_sunhouse`
* **Mục đích:** Tra cứu thông tin chính hãng về tập đoàn Sunhouse, Shark Nguyễn Xuân Phú, chính sách bảo hành, danh sách nhà máy và tổng đài miễn cước 1800 6680.
* **Input Schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "chu_de": {
        "type": "string",
        "description": "Chủ đề cần tra cứu (ví dụ: 'bao_hanh', 'shark_phu', 'hotline', 'tong_quan', 'nha_may')"
      },
      "cau_hoi_chi_tiet": {
        "type": "string",
        "description": "Nội dung câu hỏi của khách hàng"
      }
    },
    "required": ["chu_de"]
  }
  ```

### Tool 2: `tra_cuu_ma_loi_sunhouse`
* **Mục đích:** Tra cứu nguyên nhân kỹ thuật và giải pháp xử lý mã lỗi từ sổ tay dịch vụ (E0, E1, E2, E3, E4, tiếng kêu bíp cảnh báo, đèn nháy) trên bếp từ, quạt điều hòa, nồi cơm, máy lọc nước RO.
* **Input Schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "loai_thiet_bi": {
        "type": "string",
        "description": "Tên loại thiết bị (ví dụ: 'bep_tu', 'quat_dieu_hoa', 'noi_com', 'may_loc_nuoc')"
      },
      "ma_loi": {
        "type": "string",
        "description": "Ký tự mã lỗi hiển thị (ví dụ: 'E0', 'E1', 'E2', 'E3', 'E4')"
      },
      "device_id": {
        "type": "string",
        "description": "Mã định danh loa gọi (nếu có)"
      }
    },
    "required": ["loai_thiet_bi", "ma_loi"]
  }
  ```

### Tool 3: `tim_kiem_truc_tuyen_sunhouse`
* **Mục đích:** Tra cứu thông số model mới, công suất, kích thước, sách HDSD và tin tức sản phẩm Sunhouse theo thời gian thực.
* **Input Schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "tu_khoa": {
        "type": "string",
        "description": "Tên model sản phẩm hoặc từ khóa tra cứu"
      }
    },
    "required": ["tu_khoa"]
  }
  ```

---

## 5. MÃ LỖI JSON-RPC TIÊU CHUẨN

| Mã lỗi | Tên lỗi | Mô tả nguyên nhân |
| :---: | :--- | :--- |
| **`-32700`** | Parse error | Gói tin JSON gửi lên bị sai cú pháp, không thể parse. |
| **`-32600`** | Invalid Request | Gói tin JSON-RPC không đúng chuẩn (thiếu `jsonrpc` hoặc `method`). |
| **`-32601`** | Method not found | Lệnh yêu cầu không tồn tại (chỉ hỗ trợ `initialize`, `notifications/initialized`, `tools/list`, `tools/call`). |
| **`-32602`** | Invalid params | Tham số truyền vào công cụ thiếu trường bắt buộc hoặc sai kiểu dữ liệu. |
| **`-32603`** | Internal error | Lỗi nội bộ trong quá trình xử lý công cụ (ghi log chi tiết trên server). |
| **`4001`** | Unauthorized | Token kết nối WebSocket không hợp lệ hoặc thiếu `?token=...`. |
| **`4003`** | Device Unbound | Thiết bị đã bị thu hồi quyền hoặc hủy liên kết khỏi hệ thống. |
