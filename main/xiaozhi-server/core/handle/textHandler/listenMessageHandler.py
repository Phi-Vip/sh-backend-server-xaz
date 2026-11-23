import time
import uuid
import asyncio
from typing import Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from core.connection import ConnectionHandler

from core.utils.dialogue import Message
from core.providers.asr.dto.dto import InterfaceType
from core.handle.receiveAudioHandle import startToChat
from core.handle.reportHandle import enqueue_asr_report
from core.handle.sendAudioHandle import send_stt_message, send_tts_message, send_display_message
from core.handle.textMessageHandler import TextMessageHandler
from core.handle.textMessageType import TextMessageType
from core.utils.util import remove_punctuation_and_length
from core.providers.tts.dto.dto import ContentType, TTSMessageDTO, SentenceType


TAG = __name__

class ListenTextMessageHandler(TextMessageHandler):
    """Listen消息处理器"""

    @property
    def message_type(self) -> TextMessageType:
        return TextMessageType.LISTEN

    async def handle(self, conn: "ConnectionHandler", msg_json: Dict[str, Any]) -> None:
        if "mode" in msg_json:
            conn.client_listen_mode = msg_json["mode"]
            conn.logger.bind(tag=TAG).debug(
                f"客户端拾音模式：{conn.client_listen_mode}"
            )
        if msg_json["state"] == "start":
            # Khi client bắt đầu lắng nghe (nhấn nút BOOT hoặc Wake word detected), hủy đóng băng phát nhạc/đài
            if getattr(conn, "is_playing_music", False):
                conn.is_playing_music = False
                conn.logger.bind(tag=TAG).info("[MEDIA EMERGENCY STOP] ⏹️ Nhận listen start -> Hủy đóng băng phát nhạc/đài, kích hoạt lại silence timeout để nghe người dùng")

            # Bật cờ nhận âm thanh cho ASR, ghi nhận thời điểm bắt đầu nghe
            conn.client_is_listening = True
            conn.listen_start_time = time.monotonic()
            conn.last_activity_time = time.time() * 1000

            # Xóa sạch hàng đợi ASR để đảm bảo không còn gói tin rác nào trước thời điểm start
            while not conn.asr_audio_queue.empty():
                try:
                    conn.asr_audio_queue.get_nowait()
                except Exception:
                    break

            # Thiết bị từ phát chuyển sang thu âm, xóa sạch trạng thái âm thanh và bộ đệm
            conn.reset_audio_states()
            conn.just_woken_up = False
            conn.client_is_speaking = False
            if hasattr(conn, "dialogue_sniff_packets"):
                conn.dialogue_sniff_packets.clear()
            if hasattr(conn, "recent_opus_packets"):
                conn.recent_opus_packets.clear()
        elif msg_json["state"] == "stop":
            # Dừng lắng nghe âm thanh
            conn.client_is_listening = False
            if hasattr(conn, "recent_opus_packets"):
                conn.recent_opus_packets.clear()

            # 收到stop但asr未初始化，跳过处理
            if conn.asr is None:
                return

            conn.client_voice_stop = True
            if conn.asr.interface_type == InterfaceType.STREAM:
                # 流式模式下，发送结束请求
                asyncio.create_task(conn.asr._send_stop_request())
            else:
                # 非流式模式：直接触发ASR识别
                if len(conn.asr_audio) > 0:
                    asr_audio_task = conn.asr_audio.copy()
                    conn.reset_audio_states()

                    if len(asr_audio_task) > 0:
                        await conn.asr.handle_voice_stop(conn, asr_audio_task)
                else:
                    # [HOOK SNIFFER]: ESP32 đã gửi stop nhưng asr_audio rỗng (do VAD drop hoàn toàn âm thanh)
                    if hasattr(conn, "dialogue_sniff_packets") and conn.dialogue_sniff_packets:
                        from core.utils.dialogue_recorder import get_dialogue_recorder
                        rec = get_dialogue_recorder(conn.config)
                        if rec.is_enabled():
                            pkts = list(conn.dialogue_sniff_packets)
                            conn.dialogue_sniff_packets.clear()
                            asyncio.get_running_loop().run_in_executor(
                                None, rec.record_session, pkts, conn.device_id, conn.session_id, "", "STT_NO_RESPONSE"
                            )
        elif msg_json.get("state") == "detect" or msg_json.get("type") == "wake_word_debug":
            # Xử lý riêng nhánh instant_spike / triplet_spike / wake_word_debug (chỉ lưu dataset, không đánh thức Bot)
            meta_data = msg_json.get("meta") or {}
            is_instant_spike = (
                msg_json.get("type") == "wake_word_debug"
                or msg_json.get("trigger_type") in ("instant_spike", "triplet_spike")
                or (isinstance(meta_data, dict) and meta_data.get("trigger_type") in ("instant_spike", "triplet_spike"))
            )

            if is_instant_spike:
                if hasattr(conn, "recent_opus_packets") and conn.recent_opus_packets:
                    packets_to_save = list(conn.recent_opus_packets)
                    conn.recent_opus_packets.clear()
                    if isinstance(meta_data, dict):
                        meta_data.setdefault("trigger_type", "instant_spike")
                    from core.utils.dataset_recorder import get_dataset_recorder

                    recorder = get_dataset_recorder(conn.config)
                    if recorder.is_enabled():
                        asyncio.get_running_loop().run_in_executor(
                            None,
                            recorder.record,
                            packets_to_save,
                            meta_data,
                            conn.device_id,
                        )
                conn.logger.bind(tag=TAG).info("🎯 Dataset Pipeline: Đã nhận gói debug instant_spike, bỏ qua đàm thoại")
                return

            # Khi phát hiện Wake Word chính thức (smoothed), ngắt cờ nghe ASR để loại bỏ âm thanh kèm theo
            conn.client_is_listening = False
            if hasattr(conn, "dialogue_sniff_packets"):
                conn.dialogue_sniff_packets.clear()

            # 1. Dataset Pipeline: Lưu gói âm thanh kích hoạt Wake Word chính thức nếu được bật
            if hasattr(conn, "recent_opus_packets") and conn.recent_opus_packets:
                packets_to_save = list(conn.recent_opus_packets)
                conn.recent_opus_packets.clear()
                from core.utils.dataset_recorder import get_dataset_recorder

                recorder = get_dataset_recorder(conn.config)
                if recorder.is_enabled():
                    asyncio.get_running_loop().run_in_executor(
                        None,
                        recorder.record,
                        packets_to_save,
                        meta_data,
                        conn.device_id,
                    )

            # 2. Xóa sạch hàng đợi ASR để tránh các gói Opus kích hoạt bị ASR nhận diện nhầm
            while not conn.asr_audio_queue.empty():
                try:
                    conn.asr_audio_queue.get_nowait()
                except Exception:
                    break

            conn.client_have_voice = False
            conn.reset_audio_states()
            if getattr(conn, "is_playing_music", False):
                conn.is_playing_music = False
                conn.logger.bind(tag=TAG).info("[MEDIA EMERGENCY STOP] ⏹️ Nhận listen detect -> Hủy đóng băng phát nhạc/đài")
            conn.last_activity_time = time.time() * 1000
            if "text" in msg_json:
                original_text = msg_json["text"]  # 保留原始文本
                filtered_len, filtered_text = remove_punctuation_and_length(
                    original_text
                )

                # 检查是否是设备呼叫指令 [device_call]
                if original_text.startswith("[device_call]"):
                    # 提取 tag 后的文本
                    call_text = original_text[len("[device_call]"):].strip()
                    conn.logger.bind(tag=TAG).info(f"收到设备呼叫指令: {call_text}")

                    # 标记为来电接听模式
                    conn.incoming_call = True

                    # 准备开始新会话
                    conn.sentence_id = uuid.uuid4().hex

                    await send_stt_message(conn, call_text)

                    # 等待tts初始化，最多等待3秒
                    start_time = time.time()
                    while time.time() - start_time < 3:
                        if conn.tts:
                            break
                        await asyncio.sleep(0.1)

                    if conn.tts:
                        conn.tts.store_tts_text(conn.sentence_id, call_text)
                        conn.tts.tts_text_queue.put(TTSMessageDTO(sentence_id=conn.sentence_id, sentence_type=SentenceType.FIRST, content_type=ContentType.ACTION))
                        conn.tts.tts_one_sentence(conn, ContentType.TEXT, content_detail=call_text)
                        conn.tts.tts_text_queue.put(TTSMessageDTO(sentence_id=conn.sentence_id, sentence_type=SentenceType.LAST, content_type=ContentType.ACTION))

                    # 添加到对话历史，让模型理解上下文
                    conn.dialogue.put(Message(role="assistant", content=call_text))
                    return

                # Xử lý wake word:
                # ESP32 đã phát âm thanh popup/ting ngay trên phần cứng và chuyển sang chế độ listening.
                # Không gọi startToChat để tránh LLM sinh lời chào không cần thiết ("Chào bạn, mình là trợ lý Sunhouse đây").
                # Thiết bị duy trì trạng thái im lặng và sẵn sàng lắng nghe câu lệnh tiếp theo của người dùng.
                enable_greeting = conn.config.get("enable_greeting", False)
                
                # Hiển thị text wake word lên màn hình ESP32 (Role: user) mà không kích hoạt speaking
                await send_display_message(conn, original_text)
                conn.client_is_speaking = False
                conn.just_woken_up = False

                if enable_greeting and not msg_json.get("meta"):
                    # Chỉ chào nếu người dùng cấu hình enable_greeting: true VÀ không phải từ Edge Impulse pipeline
                    conn.logger.bind(tag=TAG).info("Kích hoạt lời chào theo cấu hình enable_greeting")
                    enqueue_asr_report(conn, "嘿，你好呀", [])
                    await startToChat(conn, "嘿，你好呀")