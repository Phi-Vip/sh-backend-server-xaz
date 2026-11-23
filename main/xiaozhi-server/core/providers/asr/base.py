import os
import io
import wave
import uuid
import json
import time
import queue
import shutil
import asyncio
import tempfile
import traceback
import threading

from abc import ABC, abstractmethod
from config.logger import setup_logging
from core.providers.asr.dto.dto import InterfaceType
from core.handle.receiveAudioHandle import startToChat
from core.handle.reportHandle import enqueue_asr_report
from core.utils.util import remove_punctuation_and_length
from core.utils.asr_filter import check_asr_text_validity
from core.handle.receiveAudioHandle import handleAudioMessage
from typing import Optional, Tuple, List, NamedTuple, TYPE_CHECKING


if TYPE_CHECKING:
    from core.connection import ConnectionHandler

TAG = __name__
logger = setup_logging()


class ASRProviderBase(ABC):
    def __init__(self):
        pass

    # 打开音频通道
    async def open_audio_channels(self, conn: "ConnectionHandler"):
        conn.asr_priority_thread = threading.Thread(
            target=self.asr_text_priority_thread, args=(conn,), daemon=True
        )
        conn.asr_priority_thread.start()

    # 有序处理ASR音频
    def asr_text_priority_thread(self, conn: "ConnectionHandler"):
        while not conn.stop_event.is_set():
            try:
                message = conn.asr_audio_queue.get(timeout=1)
                future = asyncio.run_coroutine_threadsafe(
                    handleAudioMessage(conn, message),
                    conn.loop,
                )
                future.result()
            except queue.Empty:
                continue
            except Exception as e:
                logger.bind(tag=TAG).error(
                    f"处理ASR文本失败: {str(e)}, 类型: {type(e).__name__}, 堆栈: {traceback.format_exc()}"
                )
                continue

    # 接收音频
    async def receive_audio(self, conn: "ConnectionHandler", pcm_frame, audio_have_voice):
        if conn.client_listen_mode == "manual":
            # 手动模式：缓存音频用于ASR识别
            conn.asr_audio.append(pcm_frame)
        else:
            # 自动/实时模式：使用VAD检测
            conn.asr_audio.append(pcm_frame)

            # 如果没有语音，且之前也没有声音，缓存部分音频
            if not audio_have_voice and not conn.client_have_voice:
                conn.asr_audio = conn.asr_audio[-10:]
                return

            # 自动模式下通过VAD检测到语音停止时触发识别
            if conn.asr.interface_type != InterfaceType.STREAM and conn.client_voice_stop:
                listen_elapsed = time.monotonic() - getattr(conn, "listen_start_time", 0.0)
                pcm_bytes = b"".join(conn.asr_audio)
                duration_sec = len(pcm_bytes) / 32000.0
                speech_frames = getattr(conn, "speech_frames_count", 0)
                silence_threshold_sec = getattr(conn.vad, "silence_threshold_ms", 800) / 1000.0
                real_speech_sec = max(0.0, duration_sec - silence_threshold_sec)

                logger.bind(tag=TAG).info(
                    f"[ASR TRIGGER] ⚡ VAD báo dứt câu! Buffer: {duration_sec:.2f}s ({len(pcm_bytes)} bytes) | Nói thực: {real_speech_sec:.2f}s ({speech_frames} frames) | Sau start: {listen_elapsed:.2f}s"
                )

                # Ngưỡng bảo vệ chống xung cơ học / dội loa / tiếng tặc lưỡi, chép miệng:
                # Phải có ít nhất 8 frames tiếng nói (~256ms) VÀ thời lượng nói thực >= 0.25s
                # Bảo đảm các câu ngắn "OK", "Đúng", "Có", "Bật" (>=10-16 frames, >=0.35s) luôn vượt qua, loại bỏ 100% tiếng tặc lưỡi/chép miệng rác (<8 frames)
                if speech_frames < 8 or real_speech_sec < 0.25:
                    logger.bind(tag=TAG).info(
                        f"[ASR GUARD] 🛡️ Bỏ qua âm thanh quá ngắn (Nói thực: {real_speech_sec:.2f}s, {speech_frames} frames) - nghi vấn tặc lưỡi/chép miệng/xung cơ học"
                    )
                    conn.reset_audio_states()
                    return

                # Ngưỡng an toàn co hẹp lại 0.5s (8 frames ~ 480ms = 15360 bytes):
                # Vừa lọc sạch tiếng click/thở ngắn (<0.3s), vừa bắt trọn các câu lệnh ngắn ("Bật đèn", "Mấy giờ")
                if len(pcm_bytes) >= 1920 * 8:
                    logger.bind(tag=TAG).info(
                        f"[ASR CALL] 🚀 Gửi {duration_sec:.2f}s âm thanh lên {conn.asr.__class__.__name__} nhận diện..."
                    )
                    await self.handle_voice_stop(conn, [pcm_bytes])
                else:
                    logger.bind(tag=TAG).warning(
                        f"[ASR DROP] ⚠️ Buffer quá ngắn ({duration_sec:.2f}s < 0.48s), bỏ qua không gọi ASR"
                    )
                conn.reset_audio_states()

    # 处理语音停止
    async def handle_voice_stop(self, conn: "ConnectionHandler", asr_audio_task: List[bytes]):
        """并行处理ASR和声纹识别"""
        try:
            total_start_time = time.monotonic()

            # 数据已经是PCM直接使用
            pcm_data = asr_audio_task
            combined_pcm_data = b"".join(pcm_data)

            # 预先准备WAV数据
            wav_data = None
            if conn.voiceprint_provider and combined_pcm_data:
                wav_data = self._pcm_to_wav(combined_pcm_data)

            # 定义ASR任务
            asr_task = self.speech_to_text_wrapper(
                asr_audio_task, conn.session_id
            )

            if conn.voiceprint_provider and wav_data:
                voiceprint_task = conn.voiceprint_provider.identify_speaker(
                    wav_data, conn.session_id
                )
                # 并发等待两个结果
                asr_result, voiceprint_result = await asyncio.gather(
                    asr_task, voiceprint_task, return_exceptions=True
                )
            else:
                asr_result = await asr_task
                voiceprint_result = None

            # 记录识别结果 - 检查是否为异常
            if isinstance(asr_result, Exception):
                logger.bind(tag=TAG).error(f"ASR识别失败: {asr_result}")
                raw_text = ""
            else:
                raw_text, _ = asr_result

            if isinstance(voiceprint_result, Exception):
                logger.bind(tag=TAG).error(f"声纹识别失败: {voiceprint_result}")
                speaker_name = ""
            else:
                speaker_name = voiceprint_result

            # 判断 ASR 结果类型
            if isinstance(raw_text, dict):
                # FunASR 返回的 dict 格式
                if speaker_name:
                    raw_text["speaker"] = speaker_name

                # 记录识别结果
                if raw_text.get("language"):
                    logger.bind(tag=TAG).info(f"识别语言: {raw_text['language']}")
                if raw_text.get("emotion"):
                    logger.bind(tag=TAG).info(f"识别情绪: {raw_text['emotion']}")
                if raw_text.get("content"):
                    logger.bind(tag=TAG).info(f"识别文本: {raw_text['content']}")
                if speaker_name:
                    logger.bind(tag=TAG).info(f"识别说话人: {speaker_name}")

                # 转换为 JSON 字符串用于下游
                enhanced_text = json.dumps(raw_text, ensure_ascii=False)
                content_for_length_check = raw_text.get("content", "")
            else:
                # 其他 ASR 返回的纯文本
                if raw_text:
                    logger.bind(tag=TAG).info(f"识别文本: {raw_text}")
                if speaker_name:
                    logger.bind(tag=TAG).info(f"识别说话人: {speaker_name}")

                # 构建包含说话人信息的JSON字符串
                enhanced_text = self._build_enhanced_text(raw_text, speaker_name)
                content_for_length_check = raw_text

            # 性能监控
            total_time = time.monotonic() - total_start_time
            logger.bind(tag=TAG).debug(f"总处理耗时: {total_time:.3f}s")

            # 检查文本长度
            text_len, _ = remove_punctuation_and_length(content_for_length_check)
            self.stop_ws_connection()

            # Lọc ảo giác Whisper: Whitelist từ đơn (chống tặc lưỡi/chép miệng 'Tr', 'Tch') + Blacklist cụm từ rác ('subscribe', 'La La School'...)
            is_valid, filter_reason = check_asr_text_validity(content_for_length_check)

            if text_len > 0 and is_valid:
                logger.bind(tag=TAG).info(f"[ASR TO LLM] 🤖 Chuyển văn bản hợp lệ sang LLM: '{enhanced_text}' ({filter_reason})")
                # [HOOK SNIFFER]: Lưu phiên nhận diện STT thành công
                if hasattr(conn, "dialogue_sniff_packets") and conn.dialogue_sniff_packets:
                    from core.utils.dialogue_recorder import get_dialogue_recorder
                    rec = get_dialogue_recorder(conn.config)
                    if rec.is_enabled():
                        pkts = list(conn.dialogue_sniff_packets)
                        conn.dialogue_sniff_packets.clear()
                        asyncio.get_running_loop().run_in_executor(
                            None, rec.record_session, pkts, conn.device_id, conn.session_id, enhanced_text, "STT_SUCCESS"
                        )
                audio_snapshot = asr_audio_task.copy()
                enqueue_asr_report(conn, enhanced_text, audio_snapshot)
                # 使用自定义模块进行上报
                await startToChat(conn, enhanced_text)
            else:
                drop_reason = filter_reason if not is_valid else "Văn bản rỗng hoặc chỉ có dấu câu"
                logger.bind(tag=TAG).warning(
                    f"[ASR FILTER] 🗑️ Bỏ qua văn bản không hợp lệ: '{content_for_length_check}' (Lý do: {drop_reason}), không gửi LLM"
                )
                # [HOOK SNIFFER]: Lưu phiên nhận dạng trả về rỗng hoặc bị lọc
                if hasattr(conn, "dialogue_sniff_packets") and conn.dialogue_sniff_packets:
                    from core.utils.dialogue_recorder import get_dialogue_recorder
                    rec = get_dialogue_recorder(conn.config)
                    if rec.is_enabled():
                        pkts = list(conn.dialogue_sniff_packets)
                        conn.dialogue_sniff_packets.clear()
                        tag_reason = "STT_FILTER_HALLUCINATION" if not is_valid else "STT_EMPTY_TEXT"
                        asyncio.get_running_loop().run_in_executor(
                            None, rec.record_session, pkts, conn.device_id, conn.session_id, content_for_length_check, tag_reason
                        )
        except Exception as e:
            logger.bind(tag=TAG).error(f"处理语音停止失败: {e}")
            import traceback

            logger.bind(tag=TAG).debug(f"异常详情: {traceback.format_exc()}")

    def _build_enhanced_text(self, text: str, speaker_name: Optional[str]) -> str:
        """构建包含说话人信息的文本（仅用于纯文本ASR）"""
        if speaker_name and speaker_name.strip():
            return json.dumps(
                {"speaker": speaker_name, "content": text}, ensure_ascii=False
            )
        else:
            return text

    def _pcm_to_wav(self, pcm_data: bytes) -> bytes:
        """将PCM数据转换为WAV格式"""
        if len(pcm_data) == 0:
            logger.bind(tag=TAG).warning("PCM数据为空，无法转换WAV")
            return b""

        # 确保数据长度是偶数（16位音频）
        if len(pcm_data) % 2 != 0:
            pcm_data = pcm_data[:-1]

        # 创建WAV文件头
        wav_buffer = io.BytesIO()
        try:
            with wave.open(wav_buffer, "wb") as wav_file:
                wav_file.setnchannels(1)  # 单声道
                wav_file.setsampwidth(2)  # 16位
                wav_file.setframerate(16000)  # 16kHz采样率
                wav_file.writeframes(pcm_data)

            wav_buffer.seek(0)
            wav_data = wav_buffer.read()

            return wav_data
        except Exception as e:
            logger.bind(tag=TAG).error(f"WAV转换失败: {e}")
            return b""

    def stop_ws_connection(self):
        pass

    async def close(self):
        pass

    class AudioArtifacts(NamedTuple):
        pcm_frames: List[bytes]
        """PCM音频帧列表"""
        pcm_bytes: bytes
        """合并后的PCM音频字节数据"""
        file_path: Optional[str]
        """WAV文件路径"""
        temp_path: Optional[str]
        """临时WAV文件路径"""

    def get_current_artifacts(self) -> Optional["ASRProviderBase.AudioArtifacts"]:
        return self._current_artifacts

    def requires_file(self) -> bool:
        """是否需要文件输入"""
        return False

    def prefers_temp_file(self) -> bool:
        """是否优先使用临时文件"""
        return False

    def build_temp_file(self, pcm_bytes: bytes) -> Optional[str]:
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
                temp_path = temp_file.name
            with wave.open(temp_path, "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(16000)
                wav_file.writeframes(pcm_bytes)
            return temp_path
        except Exception as e:
            logger.bind(tag=TAG).error(f"临时音频文件生成失败: {e}")
            return None

    def save_audio_to_file(self, pcm_data: List[bytes], session_id: str) -> str:
        """PCM数据保存为WAV文件"""
        module_name = __name__.split(".")[-1]
        file_name = f"asr_{module_name}_{session_id}_{uuid.uuid4()}.wav"
        file_path = os.path.join(self.output_dir, file_name)

        with wave.open(file_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 2 bytes = 16-bit
            wf.setframerate(16000)
            wf.writeframes(b"".join(pcm_data))

        return file_path

    async def speech_to_text_wrapper(
        self, pcm_data: List[bytes], session_id: str
    ) -> Tuple[Optional[str], Optional[str]]:
        file_path = None
        temp_path = None
        try:
            combined_pcm_data = b"".join(pcm_data)

            free_space = shutil.disk_usage(self.output_dir).free
            if free_space < len(combined_pcm_data) * 2:
                raise OSError("磁盘空间不足")

            if self.requires_file() and self.prefers_temp_file():
                temp_path = self.build_temp_file(combined_pcm_data)

            if (hasattr(self, "delete_audio_file") and not self.delete_audio_file) or (
                self.requires_file() and not self.prefers_temp_file()
            ):
                file_path = self.save_audio_to_file(pcm_data, session_id)

            if len(combined_pcm_data) == 0:
                artifacts = None
            else:
                artifacts = ASRProviderBase.AudioArtifacts(
                    pcm_frames=pcm_data,
                    pcm_bytes=combined_pcm_data,
                    file_path=file_path,
                    temp_path=temp_path,
                )

            text, _ = await self.speech_to_text(
                pcm_data, session_id, artifacts
            )
            return text, file_path
        except OSError as e:
            logger.bind(tag=TAG).error(f"文件操作错误: {e}")
            return None, None
        except Exception as e:
            logger.bind(tag=TAG).error(f"语音识别失败: {e}")
            return None, None
        finally:
            try:
                if temp_path and os.path.exists(temp_path):
                    os.unlink(temp_path)
                if (
                    hasattr(self, "delete_audio_file")
                    and self.delete_audio_file
                    and file_path
                    and os.path.exists(file_path)
                ):
                    os.remove(file_path)
            except Exception as e:
                logger.bind(tag=TAG).error(f"文件清理失败: {e}")

    @abstractmethod
    async def speech_to_text(
        self,
        opus_data: List[bytes],
        session_id: str,
        artifacts: Optional[AudioArtifacts] = None,
    ) -> Tuple[Optional[str], Optional[str]]:
        """将语音数据转换为文本

        :param opus_data: 输入的Opus音频数据
        :param session_id: 会话ID
        :param artifacts: 音频工件，包含PCM数据、文件路径等
        :return: 识别结果文本和文件路径（如果有）
        """
        pass
