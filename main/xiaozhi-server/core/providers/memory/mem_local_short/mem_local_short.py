from ..base import MemoryProviderBase, logger
import time
import json
import os
import yaml
from config.config_loader import get_project_dir
from config.manage_api_client import generate_and_save_chat_summary
import asyncio
from core.utils.util import check_model_key


short_term_memory_prompt = """
# HỆ THỐNG TRÍ NHỚ HỒ SƠ NGƯỜI DÙNG (USER PROFILE & MEMORY)

## NHIỆM VỤ
Dựa vào lịch sử hội thoại giữa Người dùng (User) và Trợ lý AI (Assistant), hãy cập nhật và duy trì hồ sơ thông tin người dùng để trợ lý có thể phục vụ cá nhân hóa, tự nhiên và thân thiện hơn.

## NGUYÊN TẮC CẬP NHẬT TRÍ NHỚ
1. Chỉ trích xuất thông tin thực tế từ hội thoại, không bịa đặt hoặc suy diễn quá mức.
2. Tất cả nội dung văn bản (giá trị trong JSON) BẮT BUỘC viết bằng TIẾNG VIỆT tự nhiên, súc tích.
3. Các khóa JSON (key) sử dụng tiếng Anh chuẩn (ASCII) để tối ưu token và tương thích cao.
4. Tên gọi: Nếu người dùng xưng tên (ví dụ: "mình là Phi", "gọi tôi là Nam"), hãy lưu vào trường "name".
5. Sự kiện gần đây: Chỉ lưu tối đa 5 sự kiện/yêu cầu nổi bật gần nhất, tóm tắt súc tích trong 1 câu ngắn gọn.
6. TUYỆT ĐỐI KHÔNG lưu các câu văn dài dòng, câu chào sướt mướt hay trích dẫn lan man.

## CẤU TRÚC JSON ĐẦU RA
Đầu ra BẮT BUỘC là chuỗi JSON hợp lệ, không kèm lời giải thích hay ký tự thừa nào ngoài khối ```json ... ```:
```json
{
  "user_profile": {
    "name": "Tên người dùng nếu biết (ví dụ: Phi)",
    "traits": ["Đặc điểm nhận diện, ví dụ: Người dùng tiếng Việt, Thích phản hồi ngắn gọn"]
  },
  "recent_events": [
    {
      "event": "Tóm tắt sự kiện hoặc yêu cầu vừa diễn ra",
      "timestamp": "YYYY-MM-DD HH:MM",
      "topic": "Chủ đề (ví dụ: IoT, Âm nhạc, Lịch sử...)"
    }
  ],
  "preferences": {
    "favorite_topics": ["Chủ đề người dùng hay tương tác"],
    "interaction_style": "Ngắn gọn, súc tích, tự nhiên, thân thiện"
  }
}
```
"""


def extract_json_data(json_code):
    start = json_code.find("```json")
    # 从start开始找到下一个```结束
    end = json_code.find("```", start + 1)
    # print("start:", start, "end:", end)
    if start == -1 or end == -1:
        try:
            jsonData = json.loads(json_code)
            return json_code
        except Exception as e:
            print("Error:", e)
        return ""
    jsonData = json_code[start + 7 : end]
    return jsonData


TAG = __name__


class MemoryProvider(MemoryProviderBase):
    def __init__(self, config, summary_memory):
        super().__init__(config)
        self.short_memory = ""
        self.save_to_file = True
        self.memory_path = get_project_dir() + "data/.memory.yaml"
        self.load_memory(summary_memory)

    def init_memory(
        self, role_id, llm, summary_memory=None, save_to_file=True, **kwargs
    ):
        super().init_memory(role_id, llm, **kwargs)
        self.save_to_file = save_to_file
        self.load_memory(summary_memory)

    def load_memory(self, summary_memory):
        # api获取到总结记忆后直接返回
        if summary_memory or not self.save_to_file:
            self.short_memory = summary_memory
            return

        all_memory = {}
        if os.path.exists(self.memory_path):
            with open(self.memory_path, "r", encoding="utf-8") as f:
                all_memory = yaml.safe_load(f) or {}
        if self.role_id in all_memory:
            self.short_memory = all_memory[self.role_id]

    def save_memory_to_file(self):
        all_memory = {}
        if os.path.exists(self.memory_path):
            with open(self.memory_path, "r", encoding="utf-8") as f:
                all_memory = yaml.safe_load(f) or {}
        all_memory[self.role_id] = self.short_memory
        with open(self.memory_path, "w", encoding="utf-8") as f:
            yaml.dump(all_memory, f, allow_unicode=True)

    async def save_memory(self, msgs, session_id=None):
        # 打印使用的模型信息
        model_info = getattr(self.llm, "model_name", str(self.llm.__class__.__name__))
        logger.bind(tag=TAG).debug(f"使用记忆保存模型: {model_info}")
        api_key = getattr(self.llm, "api_key", None)
        memory_key_msg = check_model_key("记忆总结专用LLM", api_key)
        if memory_key_msg:
            logger.bind(tag=TAG).error(memory_key_msg)
        if self.llm is None:
            logger.bind(tag=TAG).error("LLM is not set for memory provider")
            return None

        if len(msgs) < 2:
            return None

        msgStr = ""
        for msg in msgs:
            content = msg.content

            # Extract content from JSON format if present (for ASR with emotion/language tags)
            try:
                if content and content.strip().startswith("{") and content.strip().endswith("}"):
                    data = json.loads(content)
                    if "content" in data:
                        content = data["content"]
            except (json.JSONDecodeError, KeyError, TypeError):
                # If parsing fails, use original content
                pass

            if msg.role == "user":
                msgStr += f"User: {content}\n"
            elif msg.role == "assistant":
                msgStr += f"Assistant: {content}\n"
        if self.short_memory and len(self.short_memory) > 0:
            msgStr += "\n[Trí nhớ trước đó]:\n"
            msgStr += self.short_memory

        # Thời gian hiện tại
        time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        msgStr += f"\n[Thời gian hiện tại]: {time_str}\n"

        if self.save_to_file:
            try:
                result = self.llm.response_no_stream(
                    short_term_memory_prompt,
                    msgStr,
                    max_tokens=2000,
                    temperature=0.2,
                )
                json_str = extract_json_data(result)
                json.loads(json_str)  # 检查json格式是否正确
                self.short_memory = json_str
                self.save_memory_to_file()
            except Exception as e:
                logger.bind(tag=TAG).error(f"Error in saving memory: {e}")
        else:
            # 当save_to_file为False时，调用Java端的聊天记录总结接口
            summary_id = session_id if session_id else self.role_id
            await generate_and_save_chat_summary(summary_id)
        logger.bind(tag=TAG).info(
            f"Save memory successful - Role: {self.role_id}, Session: {session_id}"
        )

        return self.short_memory

    async def query_memory(self, query: str) -> str:
        return self.short_memory
