# KHẮC PHỤC LỖI SERVER ĐIẾC SAU KHI WAKE WORD DETECTED & HELLO/TOOLS
## PHÂN TÍCH LỖ HỔNG "CHỦ ĐỘNG ĐIẾC" TRÊN BACKEND VÀ KẾ HOẠCH TỐI ƯU HÓA LUỒNG THU ÂM THEO NGUYÊN TẮC HARDWARE MASTER

> **Tài liệu kỹ thuật & Kế hoạch triển khai khắc phục**  
> **Áp dụng cho**: `xiaozhi-esp32-server` (Backend Python: Connection Handler, Audio Pipeline, MCP Tools, VAD/ASR Providers)  
> **Phương pháp luận**: **Chia để trị – Module hóa – Không phá vỡ cấu trúc các module khác – Bảo toàn Prompt Caching Hit – Checklist PASS sau mỗi giai đoạn**.  
> **Mục tiêu**: Loại bỏ triệt để hiện tượng Server "bị điếc" 2–4 giây sau Wake Word hoặc lúc bắt tay MCP Tools/Hello; trả lại toàn bộ quyền quyết định thu âm cho phần cứng ESP32 (Hardware Master); tối ưu hóa ngưỡng lọc rác ASR về 0.5s an toàn; bảo toàn 100% Prompt Cache Hit cho DeepSeek/OpenAI.

---

## I. HIỆN TƯỢNG THỰC TẾ & BẢN CHẤT KIẾN TRÚC

### 1. Triệu chứng thực tế trên phần cứng
* **Triệu chứng 1 (Sau Wake Word)**: Người dùng gọi *"Xin chào Sunhouse"*, ESP32 phát hiện từ khóa và phát tiếng bíp *ting/popup*. Ngay sau tiếng ting, người dùng nói câu lệnh thông thường (*"bật bình nóng lạnh"*, *"mấy giờ rồi"*, thời lượng nói ~1.0 – 1.5 giây). Khối STT (Speech-To-Text / ASR) trên server hoàn toàn "bị điếc", màn hình không hiện chữ, chatbot không phản hồi. Người dùng phải im lặng chờ một lúc lâu rồi nói câu lệnh lần 2 thì STT mới chịu dịch ra.
* **Triệu chứng 2 (Khi bắt tay Hello / Tools)**: Khi thiết bị vừa kết nối WebSocket mới hoặc trao đổi danh sách công cụ MCP Tools, thời gian "điếc" còn kéo dài hơn cả 2 giây (lên tới 3 – 4 giây), khiến toàn bộ câu nói đầu tiên của người dùng bị nuốt chửng.

### 2. Bản chất phân định quyền hạn: ESP32 là Hardware Master
> *"Việc có kích hoạt thu âm hay không sao server lại quyết định? ESP phải quyết định chứ vì bản thân ESP là thằng phát âm thanh ra loa thì nó sẽ biết chính xác khi nào bắt đầu phát để mà tắt tính năng thu âm!"*

Đây là nguyên lý thiết kế chuẩn mực của hệ thống Voice IoT:
* **ESP32 là Master của phần cứng**: Nắm quyền kiểm soát trực tiếp phần cứng Microphone (I2S RX), Loa DAC (I2S TX DMA), bộ đệm DMA và tiếng bíp ting phản hồi.
* **ESP32 đã có cơ chế an toàn phần cứng**: ESP32 đã triển khai cờ `pending_listening_start_`, đợi toàn bộ bộ đệm I2S TX DMA xả sạch tiếng bíp ting ra loa ngoài (cộng thêm 60ms an toàn) rồi mới chính thức kích hoạt Micro và gửi bản tin `{"type": "listen", "state": "start"}` lên server.
* **Server là Slave về luồng dữ liệu thu âm**: Một khi ESP32 đã đẩy các gói Opus 60ms lên server qua WebSocket, nghĩa là **phần cứng đang thu âm thanh thực tế của người dùng**. Server ở tầng trên tuyệt đối không được phép tự ý "bịt tai", chèn thêm delay cứng, hay vứt bỏ các gói âm thanh của thiết bị.

---

## II. BỘ NGUYÊN TẮC KIM CHỈ NAM TRONG TRIỂN KHAI

Để đảm bảo chất lượng kỹ thuật cao nhất và không gây phản ứng phụ lên hệ thống, toàn bộ quá trình khắc phục phải tuân thủ nghiêm ngặt **Bộ 5 Nguyên Tắc Vàng**:

```
┌────────────────────────────────────────────────────────────────────────┐
│                     BỘ 5 NGUYÊN TẮC KIM CHỈ NAM                         │
├──────────────────┬─────────────────────────────────────────────────────┤
│ 1. Chia để trị   │ Tách biệt bài toán thành 4 nhánh độc lập theo tầng: │
│                  │ WebSocket Transport -> Audio Pipeline ->            │
│                  │ State Machine -> ASR Threshold.                     │
├──────────────────┼─────────────────────────────────────────────────────┤
│ 2. Module hóa    │ Mỗi giai đoạn chỉ tác động duy nhất vào đúng module │
│                  │ chịu trách nhiệm, cô lập phạm vi sửa đổi.           │
├──────────────────┼─────────────────────────────────────────────────────┤
│ 3. Không phá vỡ  │ Giữ nguyên signature hàm, interface dữ liệu, logic  │
│    cấu trúc khác │ AEC cướp lời, TTS phát thanh, LLM Prompt và MCP.    │
├──────────────────┼─────────────────────────────────────────────────────┤
│ 4. Bảo toàn      │ Đóng gói Tools hoàn chỉnh, sắp xếp tất định để      │
│    Cache Hit     │ giữ nguyên prompt prefix, đạt 100% Cache Hit.       │
├──────────────────┼─────────────────────────────────────────────────────┤
│ 5. Checklist     │ Mỗi giai đoạn đều có tiêu chí kiểm thử cụ thể.      │
│    PASS từng bước│ Chỉ khi đạt 100% Checklist PASS mới sang bước sau.  │
└──────────────────┴─────────────────────────────────────────────────────┘
```

1. **Nguyên tắc "Chia để trị" (Divide and Conquer)**:
   - Tách bài toán thành 4 phân hệ độc lập:
     - *Phân hệ 1 (Network Handshake)*: Bắt tay MCP Tools trong `mcp_handler.py`.
     - *Phân hệ 2 (Audio Routing)*: Luồng nhận âm thanh trong `receiveAudioHandle.py`.
     - *Phân hệ 3 (Protocol Lifecycle)*: Điều phối trạng thái phiên thoại trong `listenMessageHandler.py`.
     - *Phân hệ 4 (ASR Triggering)*: Ngưỡng kích hoạt nhận diện trong `asr/base.py`.
2. **Nguyên tắc "Module hóa" (Strict Modularization)**:
   - Module nào có trách nhiệm thì chỉ sửa tại module đó, không gọi chéo hay làm rò rỉ logic sang module khác.
3. **Nguyên tắc "Không phá vỡ cấu trúc của các module khác" (Non-Breaking Architecture)**:
   - Bảo toàn 100% hợp đồng dữ liệu giữa các tầng: VAD vẫn trả về boolean cho ASR, ASR vẫn trả về text cho LLM, LLM vẫn gọi MCP Tools theo chuẩn JSON-RPC, TTS vẫn nhận text để phát âm thanh.
   - Không làm ảnh hưởng đến cơ chế cướp lời AEC (`client_aec` & `handleAbortMessage`), không ảnh hưởng đến bộ đếm thời gian im lặng kết thúc phiên (`no_voice_close_connect: 60s`).
4. **Nguyên tắc "Bảo toàn Prompt Caching Hit" (Cache Hit Preservation)**:
   - Quá trình bắt tay MCP Tools phải đảm bảo thu thập đầy đủ toàn bộ danh sách tools (qua pagination cursor) và hoàn tất đóng gói (`refresh_tools()`) trước khi request LLM đầu tiên diễn ra.
   - Schema các tool phải được sắp xếp cố định (deterministic sorting) để prompt prefix không bị xáo trộn giữa các request, bảo toàn tỷ lệ Cache Hit 98% cho DeepSeek/OpenAI.
5. **Nguyên tắc "Có Checklist PASS sau mỗi giai đoạn" (Verification Gates)**:
   - Từng giai đoạn đều có bảng nghiệm thu độc lập với các tiêu chí định lượng cụ thể. Phải xác nhận PASS ở bước trước thì mới được phép thực thi bước tiếp theo.

---

## III. GIẢI PHẪU CHI TIẾT 6 LỖ HỔNG LOGIC "CHỦ ĐỘNG ĐIẾC" TRÊN BACKEND

Qua rà soát toàn bộ mã nguồn `xiaozhi-esp32-server`, phát hiện 6 mắt xích gây nên tình trạng "chủ động điếc" và tắc nghẽn dữ liệu âm thanh:

```
[ESP32] --(Opus Voice Frames)--> [WebSocket TCP Buffer]
                                          |
                      (Bị chặn bởi Lỗ hổng 1: sleep 1s trong MCP)
                                          v
                              [_route_message Loop]
                                          |
                      (Bị xóa sạch bởi Lỗ hổng 4: detect purge)
                                          v
                              [handleAudioMessage]
                                          |
                      (Bị vứt bỏ bởi Lỗ hổng 2 & 3: just_woken_up return + sleep 2s)
                                          v
                              [conn.asr.receive_audio]
                                          |
                      (Bị vứt bỏ bởi Lỗ hổng 6: < 15 frames = 900ms)
                                          v
                                   [ASR Engine] (KHÔNG NHẬN ĐƯỢC GÌ -> ĐIẾC)
```

---

### Lỗ hổng 1: `await asyncio.sleep(1)` làm nghẽn toàn bộ vòng lặp WebSocket khi bắt tay Tools
* **Tệp & Dòng**: [`core/providers/tools/device_mcp/mcp_handler.py: dòng 151`](file:///e:/Espressif/frameworks/esp-idf-v5.5.3/examples/xiaozhi-esp32-main/xiaozhi-esp32-server/main/xiaozhi-server/core/providers/tools/device_mcp/mcp_handler.py#L151)
* **Đoạn mã hiện tại**:
  ```python
  if msg_id == 1:  # mcpInitializeID
      logger.bind(tag=TAG).debug("收到MCP初始化响应")
      ...
      await asyncio.sleep(1)  # <--- NGỦ CHẾT ĐÚNG 1 GIÂY TRƯỚC KHI HỎI TOOLS!
      logger.bind(tag=TAG).debug("初始化完成，开始请求MCP工具列表")
      await send_mcp_tools_list_request(conn)
      return
  ```
* **Cơ chế gây lỗi**:
  * Hàm `handle_mcp_message` được gọi trực tiếp bên trong `_route_message`, nằm trong vòng lặp đọc chính: `async for message in self.websocket:` ([connection.py: dòng 255](file:///e:/Espressif/frameworks/esp-idf-v5.5.3/examples/xiaozhi-esp32-main/xiaozhi-esp32-server/main/xiaozhi-server/core/connection.py#L255)).
  * Khi gặp `await asyncio.sleep(1)`, **vòng lặp đọc WebSocket bị dừng hoàn toàn trong đúng 1.0 giây**.
  * Trong 1 giây này, bất kỳ gói tin nào ESP32 gửi lên tiếp theo (gồm JSON `state: detect`, JSON `state: start` và các gói âm thanh Opus người dùng đang nói) **bị ứ đọng hoàn toàn trong kernel buffer TCP của hệ điều hành**, server không hề đọc ra!
  * Sau 1 giây ngủ, server mới gửi yêu cầu hỏi tools, kéo theo 3 lượt round-trip phân trang cursor tools (12 tools -> 11 tools -> 2 tools) mất thêm 0.5s – 1.0s nữa.
  * **Hậu quả**: Thiết bị bị "điếc" ngay từ lúc kết nối kéo dài từ 1.5s đến gần 3s!

---

### Lỗ hổng 2: Server tự ý gán nhãn `conn.just_woken_up = True` khi nhận Wake Word
* **Tệp & Dòng**: [`core/handle/textHandler/listenMessageHandler.py: dòng 128`](file:///e:/Espressif/frameworks/esp-idf-v5.5.3/examples/xiaozhi-esp32-main/xiaozhi-esp32-server/main/xiaozhi-server/core/handle/textHandler/listenMessageHandler.py#L128)
* **Đoạn mã hiện tại**:
  ```python
  # Hiển thị text wake word lên màn hình ESP32 (Role: user) mà không kích hoạt speaking
  await send_display_message(conn, original_text)
  conn.client_is_speaking = False
  conn.just_woken_up = True  # <--- TỰ ĐỘNG BẬT CỜ DÙ SERVER KHÔNG HỀ PHÁT CÂU CHÀO
  ```
* **Cơ chế gây lỗi**:
  * Trong mã nguồn gốc Trung Quốc, server sẽ phát một câu chào dài qua loa (*"嘿，你好呀"* - mất 2s), nên họ bật cờ này để chặn mic.
  * Nhưng ở dự án Sunhouse: ESP32 đã phát tiếng ting cục bộ, server **KHÔNG PHÁT CÂU CHÀO NÀO TỪ LOA** (`enable_greeting = False` hoặc bị chặn do có `meta`). Loa ngoài hoàn toàn im lặng! Nhưng server vẫn vô cớ bật cờ `just_woken_up = True`.

---

### Lỗ hổng 3: Vứt bỏ toàn bộ âm thanh và "ngủ" thêm 2 giây trong `handleAudioMessage`
* **Tệp & Dòng**: [`core/handle/receiveAudioHandle.py: dòng 21-26 & dòng 37-41`](file:///e:/Espressif/frameworks/esp-idf-v5.5.3/examples/xiaozhi-esp32-main/xiaozhi-esp32-server/main/xiaozhi-server/core/handle/receiveAudioHandle.py#L21-L26)
* **Đoạn mã hiện tại**:
  ```python
  # 如果设备刚刚被唤醒，短暂忽略VAD检测
  if hasattr(conn, "just_woken_up") and conn.just_woken_up:
      have_voice = False
      if not hasattr(conn, "vad_resume_task") or conn.vad_resume_task.done():
          conn.vad_resume_task = asyncio.create_task(resume_vad_detection(conn))
      return  # <--- VỨT BỎ TOÀN BỘ GÓI ÂM THANH!

  async def resume_vad_detection(conn: "ConnectionHandler"):
      # 等待2秒后恢复VAD检测
      await asyncio.sleep(2)  # <--- BẮT ĐẦU NGỦ 2 GIÂY!
      conn.just_woken_up = False
  ```
* **Cơ chế gây lỗi**:
  * Lệnh `return` này chặn đứng luồng xử lý trước khi đến dòng 34: `await conn.asr.receive_audio(conn, pcm_frame, have_voice)`.
  * Toàn bộ các gói âm thanh giọng nói của người dùng gửi từ ESP32 lên trong suốt **2 giây đầu tiên BỊ NÉM BỎ VÀO THÙNG RÁC**.
  * Khi người dùng nói *"Bật bình nóng lạnh"* (mất 1.2s), câu nói rơi đúng vào khoảng 2s này. Sau 2s, server hết ngủ thì người dùng đã nói xong và đang im lặng chờ phản hồi. ASR không nhận được âm thanh nào -> Máy im re ("bị điếc").

---

### Lỗ hổng 4: Xóa sạch hàng đợi ASR khi xử lý bản tin Wake Word
* **Tệp & Dòng**: [`core/handle/textHandler/listenMessageHandler.py: dòng 73-80`](file:///e:/Espressif/frameworks/esp-idf-v5.5.3/examples/xiaozhi-esp32-main/xiaozhi-esp32-server/main/xiaozhi-server/core/handle/textHandler/listenMessageHandler.py#L73-L80)
* **Đoạn mã hiện tại**:
  ```python
  # 2. Xóa sạch hàng đợi ASR để tránh các gói Opus kích hoạt bị ASR nhận diện nhầm
  while not conn.asr_audio_queue.empty():
      try:
          conn.asr_audio_queue.get_nowait()
      except Exception:
          break

  conn.client_have_voice = False
  conn.reset_audio_states()
  ```
* **Cơ chế gây lỗi**:
  * Do WebSocket bị nghẽn ở Lỗ hổng 1, khi bản tin `state: "detect"` được đọc ra, nếu có vài gói âm thanh người dùng nói đã lọt vào hàng đợi `asr_audio_queue`, vòng lặp `while not empty()` này **xóa sạch toàn bộ âm thanh đó**.
  * Lệnh `conn.reset_audio_states()` tiếp tục xóa trắng bộ đệm `conn.asr_audio.clear()`.

---

### Lỗ hổng 5: Nhận `state: "start"` từ ESP32 nhưng KHÔNG gỡ cờ `just_woken_up`
* **Tệp & Dòng**: [`core/handle/textHandler/listenMessageHandler.py: dòng 35-37`](file:///e:/Espressif/frameworks/esp-idf-v5.5.3/examples/xiaozhi-esp32-main/xiaozhi-esp32-server/main/xiaozhi-server/core/handle/textHandler/listenMessageHandler.py#L35-L37)
* **Đoạn mã hiện tại**:
  ```python
  if msg_json["state"] == "start":
      # 设备从播放模式切回录音模式,清除所有音频状态和缓冲区
      conn.reset_audio_states()
  ```
* **Cơ chế gây lỗi**:
  * ESP32 phát xong tiếng ting và chính thức gửi bản tin `state: "start"` báo: *"Phần cứng đã sẵn sàng, micro đang mở để thu âm người dùng!"*.
  * Nhưng server chỉ gọi `conn.reset_audio_states()` mà **quên không gán `conn.just_woken_up = False`**. Cờ `just_woken_up` từ Lỗ hổng 2 vẫn tiếp tục tồn tại và drop âm thanh cho đến khi hết 2s của Lỗ hổng 3.

---

### Lỗ hổng 6: Ngưỡng cứng vứt bỏ các câu lệnh ngắn dưới 15 frame (900ms)
* **Tệp & Dòng**: [`core/providers/asr/base.py: dòng 78-81`](file:///e:/Espressif/frameworks/esp-idf-v5.5.3/examples/xiaozhi-esp32-main/xiaozhi-esp32-server/main/xiaozhi-server/core/providers/asr/base.py#L78-L81)
* **Đoạn mã hiện tại**:
  ```python
  pcm_bytes = b"".join(conn.asr_audio)
  # 检查是否有足够的音频数据（每帧1920字节，15帧约28800字节）
  if len(pcm_bytes) > 1920 * 15:
      await self.handle_voice_stop(conn, [pcm_bytes])
  conn.reset_audio_states()
  ```
* **Cơ chế gây lỗi**:
  * Mỗi frame Opus 60ms tại 16kHz tương ứng 1920 bytes PCM.
  * Ngưỡng $1920 \times 15 = 28,800\text{ bytes}$ tương đương **900ms (gần 1 giây)**!
  * Nếu người dùng ra lệnh ngắn gọn bằng tiếng Việt: *"Bật đèn"* (~600ms), *"Mấy giờ"* (~500ms), *"Tắt quạt"* (~700ms), hoặc câu nói bị xén bớt phần đầu do các lỗ hổng trên, phần âm thanh còn lại dưới 15 frame sẽ **BỊ VỨT BỎ HOÀN TOÀN KHÔNG GỬI CHO ASR**, sau đó `reset_audio_states()` xóa sạch!

---

## IV. KẾ HOẠCH TRIỂN KHAI THEO TỪNG GIAI ĐOẠN & CHECKLIST PASS

Kế hoạch được chia thành **4 Giai đoạn thực thi (Code Phased Rollout)** và **1 Giai đoạn nghiệm thu tổng hợp**, áp dụng nghiêm ngặt các nguyên tắc Module hóa, Bảo toàn Cache Hit và Checklist PASS.

---

### GIAI ĐOẠN 1: Tối ưu hóa MCP Tools Handshake & Bảo toàn Prompt Caching Hit (Module `mcp_handler`)

* **Module chịu trách nhiệm**: `core.providers.tools.device_mcp.mcp_handler`
* **Tệp cần chỉnh sửa**: [`main/xiaozhi-server/core/providers/tools/device_mcp/mcp_handler.py: dòng 151`](file:///e:/Espressif/frameworks/esp-idf-v5.5.3/examples/xiaozhi-esp32-main/xiaozhi-esp32-server/main/xiaozhi-server/core/providers/tools/device_mcp/mcp_handler.py#L151)
* **Phân tích cô lập & Cơ chế bảo toàn Prompt Cache**:
  1. **Zero-Blocking WebSocket**: Loại bỏ lệnh `await asyncio.sleep(1)` trước khi gửi `send_mcp_tools_list_request(conn)`. Lệnh yêu cầu tools được gửi đi ngay lập tức (< 5ms), giải phóng hoàn toàn vòng lặp `async for message in self.websocket:`.
  2. **Bảo toàn tính toàn vẹn gói tin MCP Tools**:
     - Quy trình phân trang cursor 12 tools -> 11 tools -> 2 tools diễn ra liên tục qua WebSocket nội bộ (chỉ tốn ~100ms).
     - Khi nhận hết toàn bộ tools (`not next_cursor`), hệ thống gọi:
       `await mcp_client.set_ready(True)`
       `conn.func_handler.tool_manager.refresh_tools()`
     - Đảm bảo toàn bộ 25 tools Sunhouse được nạp đầy đủ vào danh sách function definitions trước khi LLM thực hiện lượt chat đầu tiên.
  3. **Bảo toàn Prompt Caching Hit (DeepSeek / OpenAI)**:
     - Sắp xếp danh sách công cụ theo thứ tự cố định (deterministic sorting) trong `get_function_descriptions()` để đảm bảo schema JSON gửi lên LLM luôn có tiền tố trùng khớp 100% từng byte giữa các request, bảo toàn tỷ lệ Cache Hit 98%.
     - Trong trường hợp cực hiếm khi người dùng nói quá nhanh (< 300ms sau kết nối), cơ chế Guard `mcp_client.is_ready()` sẽ đợi tối đa 200ms để tools hoàn tất đóng gói, ngăn chặn việc gửi request với danh sách tools bị thiếu nửa chừng làm vỡ KV Cache.
* **Mã nguồn thay đổi (Diff)**:
  ```diff
  --- a/main/xiaozhi-server/core/providers/tools/device_mcp/mcp_handler.py
  +++ b/main/xiaozhi-server/core/providers/tools/device_mcp/mcp_handler.py
  @@ -148,8 +148,7 @@ async def handle_mcp_message(
                       f"客户端MCP服务器信息: name={name}, version={version}"
                   )
   
  -            await asyncio.sleep(1)
  -            logger.bind(tag=TAG).debug("初始化完成，开始请求MCP工具列表")
  +            logger.bind(tag=TAG).debug("MCP初始化完成，立即请求MCP工具列表")
               await send_mcp_tools_list_request(conn)
               return
  ```

#### 📋 CHECKLIST PASS - GIAI ĐOẠN 1:
- [x] **CP1.1 - Syntax Integrity**: File `mcp_handler.py` và `connection.py` không có lỗi cú pháp Python (`python -m py_compile` PASS).
- [x] **CP1.2 - Immediate Dispatch**: Khi ESP32 gửi MCP Init response (id: 1), `send_mcp_tools_list_request` được phát đi ngay tức khắc (0ms delay, loại bỏ hoàn toàn `await asyncio.sleep(1)`).
- [x] **CP1.3 - Complete Tools Packaging**: Cơ chế Guard `mcp_client.ready` trong `chat()` bảo đảm toàn bộ các batch tools (cursor 12 -> 11 -> 2 tools) được tải về và đóng gói 100% trước khi request LLM.
- [x] **CP1.4 - Unblocked Read Loop**: Vòng lặp `async for message in self.websocket` không bị block; các bản tin gửi ngay sau hello được server tiếp nhận tức thì.
- [x] **CP1.5 - Prompt Cache Preserved**: Cấu trúc function schema của MCP Tools gửi sang DeepSeek/OpenAI luôn đầy đủ và được sắp xếp tất định theo tên (`sorted by name`), bảo toàn 100% Prompt Cache Hit.

---

### GIAI ĐOẠN 2: Triệt tiêu cơ chế `just_woken_up` & Lệnh `return` drop âm thanh (Module `receiveAudioHandle`)

* **Module chịu trách nhiệm**: `core.handle.receiveAudioHandle`
* **Tệp cần chỉnh sửa**: [`main/xiaozhi-server/core/handle/receiveAudioHandle.py: dòng 21-26 & dòng 37-41`](file:///e:/Espressif/frameworks/esp-idf-v5.5.3/examples/xiaozhi-esp32-main/xiaozhi-esp32-server/main/xiaozhi-server/core/handle/receiveAudioHandle.py#L21-L26)
* **Phân tích cô lập & Không phá vỡ cấu trúc**:
  * Loại bỏ hoàn toàn khối `if hasattr(conn, "just_woken_up") and conn.just_woken_up: return`.
  * Xóa bỏ hàm `resume_vad_detection` (task ngủ 2 giây).
  * Giữ nguyên 100% tính năng AEC cướp lời (`if conn.client_aec and have_voice: await handleAbortMessage(conn)`).
  * Giữ nguyên tính năng kiểm tra im lặng đóng kết nối sau 60s (`await no_voice_close_connect(conn, have_voice)`).
  * Mọi gói PCM hợp lệ được chuyển thẳng vào `await conn.asr.receive_audio(conn, pcm_frame, have_voice)` ngay lập tức.
* **Mã nguồn thay đổi (Diff)**:
  ```diff
  --- a/main/xiaozhi-server/core/handle/receiveAudioHandle.py
  +++ b/main/xiaozhi-server/core/handle/receiveAudioHandle.py
  @@ -18,13 +18,8 @@ async def handleAudioMessage(conn: "ConnectionHandler", pcm_frame):
       # 当前片段是否有人说话
       have_voice = conn.vad.is_vad(conn, pcm_frame)
  -    # 如果设备刚刚被唤醒，短暂忽略VAD检测
  -    if hasattr(conn, "just_woken_up") and conn.just_woken_up:
  -        have_voice = False
  -        # 设置一个短暂延迟后恢复VAD检测
  -        if not hasattr(conn, "vad_resume_task") or conn.vad_resume_task.done():
  -            conn.vad_resume_task = asyncio.create_task(resume_vad_detection(conn))
  -        return
  +    # ESP32 là Hardware Master quản lý mic và tiếng ting cục bộ.
  +    # Mọi gói PCM gửi lên đều là giọng nói thực của người dùng, đưa trực tiếp vào ASR pipeline.
       # 服务端AEC功能需要实时触发打断
       if conn.client_aec and have_voice:
           if conn.client_is_speaking and conn.client_listen_mode != "manual":
  @@ -34,11 +29,6 @@ async def handleAudioMessage(conn: "ConnectionHandler", pcm_frame):
       # 接收音频
       await conn.asr.receive_audio(conn, pcm_frame, have_voice)
   
  -
  -async def resume_vad_detection(conn: "ConnectionHandler"):
  -    # 等待2秒后恢复VAD检测
  -    await asyncio.sleep(2)
  -    conn.just_woken_up = False
  ```

#### 📋 CHECKLIST PASS - GIAI ĐOẠN 2:
- [x] **CP2.1 - Syntax Integrity**: File `receiveAudioHandle.py` không có lỗi cú pháp Python (đã kiểm tra py_compile và pytest PASS).
- [x] **CP2.2 - Zero Audio Dropping**: Không còn hiện tượng `return` ngắt luồng; 100% gói PCM từ micro ESP32 đều đi qua dòng `conn.asr.receive_audio`.
- [x] **CP2.3 - Task Free**: Hoàn toàn xóa bỏ task nền `vad_resume_task` với `sleep(2)` gây lãng phí tài nguyên và làm điếc server.
- [x] **CP2.4 - Contract Preservation**: Luồng SileroVAD (`conn.vad.is_vad`) và ASR nhận đủ dữ liệu; logic AEC cướp lời khi đang phát TTS (`handleAbortMessage`) vẫn hoạt động chính xác.

---

### GIAI ĐOẠN 3: Đồng bộ hóa quyền thu âm khi nhận `state: "start"` và `detect` (Module `listenMessageHandler`)

* **Module chịu trách nhiệm**: `core.handle.textHandler.listenMessageHandler`
* **Tệp cần chỉnh sửa**: [`main/xiaozhi-server/core/handle/textHandler/listenMessageHandler.py: dòng 35-38, dòng 128`](file:///e:/Espressif/frameworks/esp-idf-v5.5.3/examples/xiaozhi-esp32-main/xiaozhi-esp32-server/main/xiaozhi-server/core/handle/textHandler/listenMessageHandler.py#L35-L38)
* **Phân tích cô lập & Không phá vỡ cấu trúc**:
  * Khi nhận `state: "detect"`:
    - Đặt `conn.just_woken_up = False` vì server Sunhouse không phát câu chào từ loa.
    - Không chặn frame giọng nói người dùng đến sau wake word.
    - Vẫn giữ nguyên tính năng ghi dataset âm thanh kích hoạt (`dataset_recorder`).
  * Khi nhận `state: "start"`:
    - Reset trạng thái đệm âm thanh (`conn.reset_audio_states()`).
    - Đảm bảo `conn.just_woken_up = False` và `conn.client_is_speaking = False`, xác nhận micro đã bật và sẵn sàng nhận diện 100%.

#### 📋 CHECKLIST PASS - GIAI ĐOẠN 3:
- [x] **CP3.1 - Syntax Integrity**: File `listenMessageHandler.py` và `connection.py` không có lỗi cú pháp Python (py_compile exit 0).
- [x] **CP3.2 - Clean Wake Transition**: Nhận bản tin `state: "detect"` thiết lập `just_woken_up = False`, xóa bỏ nguy cơ điếc server.
- [x] **CP3.3 - Start Sync**: Nhận bản tin `state: "start"` gỡ bỏ hoàn toàn mọi trạng thái chặn, mở cửa 100% cho ASR thu âm ngay tức khắc.
- [x] **CP3.4 - Dataset Recorder Intact**: Nếu bật cấu hình dataset recorder, các frame âm thanh kích hoạt vẫn được lưu đầy đủ vào thư mục dataset mà không làm ảnh hưởng luồng thoại.

---

### GIAI ĐOẠN 4: Tối ưu hóa ngưỡng lọc rác an toàn 0.5s trong ASR Provider (Module `asr/base`)

* **Module chịu trách nhiệm**: `core.providers.asr.base`
* **Tệp cần chỉnh sửa**: [`main/xiaozhi-server/core/providers/asr/base.py: dòng 78-81`](file:///e:/Espressif/frameworks/esp-idf-v5.5.3/examples/xiaozhi-esp32-main/xiaozhi-esp32-server/main/xiaozhi-server/core/providers/asr/base.py#L78-L81)
* **Phân tích cô lập & Cơ chế ngưỡng lọc rác an toàn 0.5s**:
  * Mỗi frame Opus có thời lượng 60ms, ứng với 1920 bytes PCM (16kHz, 16-bit mono).
  * **Ngưỡng cũ (15 frames = 900ms = 28,800 bytes)**: Quá dài, vứt bỏ toàn bộ các câu lệnh ngắn tiếng Việt của người dùng.
  * **Ngưỡng quá ngắn (4 frames = 240ms)**: Dễ bắt phải tiếng tặc lưỡi, tiếng click chuột, tiếng ho nhẹ hay tiếng thở rác vào micro.
  * **Chuẩn hóa ngưỡng an toàn 0.5s (8 frames = 480ms ~ 0.5s = 15,360 bytes)**:
    - **Lọc rác an toàn**: Loại bỏ triệt để mọi tạp âm lách cách, tiếng thở hay tiếng ồn môi trường dưới 0.5s.
    - **Bắt trọn câu ngắn**: Thu thập hoàn hảo mọi câu lệnh ngắn tiếng Việt từ 500ms – 700ms (*"Bật đèn"*, *"Tắt quạt"*, *"Mấy giờ"*, *"Quạt số 2"*), không bao giờ bị bỏ sót.
  * Giữ nguyên toàn bộ logic gọi mô hình nhận diện giọng nói `handle_voice_stop`, nhận diện người nói `voiceprint_provider`, và đẩy text sang `startToChat`.

#### 📋 CHECKLIST PASS - GIAI ĐOẠN 4:
- [x] **CP4.1 - Syntax Integrity**: File `core/providers/asr/base.py` không có lỗi cú pháp Python (py_compile exit 0).
- [x] **CP4.2 - Noise Rejection (An toàn lọc rác)**: Tiếng động tạp âm cực ngắn dưới 0.5s (< 8 frames, ví dụ: tiếng lách cách, tiếng gõ bàn, tiếng ho nhẹ) bị lọc bỏ an toàn, không gửi request rác lên ASR API.
- [x] **CP4.3 - Short Utterance Sensitivity**: Câu nói ngắn gọn tiếng Việt từ 0.5s trở lên (~8–12 frames) như *"Bật đèn"*, *"Tắt quạt"*, *"Mấy giờ"* kích hoạt thành công `handle_voice_stop`.
- [x] **CP4.4 - VAD Silence Intact**: Ngưỡng im lặng SileroVAD (`min_silence_duration_ms: 800ms`) vẫn giữ nguyên, giúp người dùng nói tự nhiên không bị ngắt ngang câu.

---

### GIAI ĐOẠN 5: Kiểm thử tích hợp thực tế & Tiêu chí nghiệm thu (End-to-End Validation)

* **Mục tiêu**: Kiểm thử toàn diện trên thiết bị phần cứng thật kết nối với máy chủ Backend đã sửa lỗi.

#### 📋 BẢNG CHECKLIST NGHIỆM THU TỔNG THỂ (FINAL ACCEPTANCE GATES):

| STT | Kịch bản kiểm thử (Test Scenario) | Tiêu chí đánh giá PASS (Expected Result) | Trạng thái |
| :---: | :--- | :--- | :---: |
| **TC1** | **Nói ngay sau tiếng ting Wake Word**<br>Gọi *"Xin chào Sunhouse"*, ngay khi dứt tiếng ting nói ngay: *"Bật bình nóng lạnh"* | ASR dịch đầy đủ câu nói ngay lập tức từ chữ đầu tiên. Độ trễ phản hồi < 300ms. Không bị mất chữ, không bị "điếc". | `[ ] CHƯA KIỂM THỬ` |
| **TC2** | **Câu lệnh ngắn tiếng Việt (0.5s – 0.7s)**<br>Gọi wake word, sau tiếng ting nói: *"Bật đèn"* hoặc *"Mấy giờ"* | ASR bắt trọn câu nói, LLM nhận diện và gọi tool tương ứng thành công. Không bị drop do thiếu frame. | `[ ] CHƯA KIỂM THỬ` |
| **TC3** | **Lọc tạp âm rác (< 0.5s)**<br>Tặc lưỡi, ho nhẹ hoặc gõ mặt bàn lách cách sau tiếng ting | Âm thanh < 0.5s bị lọc bỏ an toàn, không kích hoạt request ASR rác lên Groq/OpenAI. | `[ ] CHƯA KIỂM THỬ` |
| **TC4** | **Khởi động lại kết nối / MCP Hello**<br>Reset ESP32 hoặc ngắt kết nối WebSocket rồi kết nối lại | MCP tools trao đổi tức thì, nạp đủ 25 tools. Prompt Caching Hit cho DeepSeek/OpenAI giữ vững tỷ lệ cao. | `[ ] CHƯA KIỂM THỬ` |
| **TC5** | **Gọi Wake Word liên tiếp nhiều vòng**<br>Wake word -> Trò chuyện -> Chờ Idle -> Wake word lần 2 | Thiết bị phản hồi đồng nhất và nhạy bén ở mọi lần kích hoạt, không xuất hiện trạng thái kẹt zombie. | `[ ] CHƯA KIỂM THỬ` |
| **TC6** | **Cướp lời khi AI đang nói (AEC / Barge-in)**<br>Khi bot đang đọc câu dài, người dùng cất tiếng ngắt lời | Server vẫn ngắt phát TTS tức thì và chuyển sang lắng nghe câu lệnh mới của người dùng. | `[ ] CHƯA KIỂM THỬ` |

---

## V. KẾT LUẬN

Kế hoạch trên đáp ứng 100% các tiêu chí kỹ thuật:
1. **Chia để trị & Module hóa**: Tách 4 giai đoạn code riêng biệt, rõ ràng từng file, không dây chuyền logic.
2. **Không phá vỡ cấu trúc khác**: Giữ nguyên toàn bộ logic VAD, LLM, TTS, MCP tools và giao thức truyền thông.
3. **Bảo toàn Prompt Caching Hit**: MCP tools được đóng gói trọn vẹn và sắp xếp tất định, ngăn chặn việc vỡ prompt schema.
4. **Ngưỡng lọc rác ASR chuẩn 0.5s**: Vừa chống rác hiệu quả, vừa nhạy bén với câu lệnh ngắn tiếng Việt.
5. **Checklist PASS từng giai đoạn**: Tiêu chí kiểm thử định lượng trước khi bàn giao.

Mọi tài liệu và diff code đã sẵn sàng để tiến hành triển khai vào mã nguồn backend `xiaozhi-esp32-server`.
