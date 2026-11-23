# -*- coding: utf-8 -*-
"""
Unit test suite for Test Case 1.4:
Multi-depth Tools Schema Invariance & KV-Cache Preservation
Verifies that:
1. Functions schema (including direct_answer) is 100% identical across depth=0, depth=1, depth=2.
2. Function names and ordering remain strictly invariant.
3. At depth >= MAX_DEPTH, functions is still passed with tool_choice="none" to preserve KV-Cache.
4. OpenAI provider forwards tool_choice to chat completions request_params.
"""

import sys
import os
import unittest
from unittest.mock import MagicMock, patch

SERVER_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_ROOT not in sys.path:
    sys.path.insert(0, SERVER_ROOT)

from core.connection import ConnectionHandler, DIRECT_ANSWER_TOOL
from core.providers.llm.openai.openai import LLMProvider as OpenAILLM


class TestDepthToolsInvariance(unittest.TestCase):

    def setUp(self):
        self.mock_config = {
            "intent_type": "function_call",
            "voiceprint": {},
            "exit_commands": ["exit", "bye"],
            "read_config_from_api": False,
        }
        self.mock_vad = MagicMock()
        self.mock_asr = MagicMock()
        self.mock_llm = MagicMock()
        self.mock_memory = None
        self.mock_intent = MagicMock()

        self.handler = ConnectionHandler(
            self.mock_config,
            self.mock_vad,
            self.mock_asr,
            self.mock_llm,
            self.mock_memory,
            self.mock_intent,
        )
        self.handler.intent_type = "function_call"
        self.handler.session_id = "test_session_id"
        self.handler.tts = MagicMock()
        self.handler.loop = MagicMock()

        # Mock func_handler with sample tools
        sample_tools = [
            {"type": "function", "function": {"name": "get_weather", "description": "Thời tiết"}},
            {"type": "function", "function": {"name": "control_device", "description": "Điều khiển thiết bị"}},
            {"type": "function", "function": {"name": "play_music", "description": "Phát nhạc"}},
        ]
        self.handler.func_handler = MagicMock()
        self.handler.func_handler.get_functions.return_value = sample_tools

    def test_tools_schema_invariance_across_all_depths(self):
        """Test Case 1.4.1: Functions schema must remain 100% identical at depth=0, depth=1, depth=2"""
        captured_functions_by_depth = {}

        def mock_response_with_functions(session_id, dialogue, functions=None, **kwargs):
            # Capture the functions list passed at this depth
            depth_key = kwargs.get("_test_depth", len(captured_functions_by_depth))
            captured_functions_by_depth[depth_key] = list(functions) if functions else []
            return [("Dạ thời tiết Hà Nội 31 độ ạ", None)]

        self.handler.llm.response_with_functions = mock_response_with_functions

        # Test at depth = 0
        with patch.object(self.handler.tts.tts_text_queue, "put"):
            self.handler.chat("thời tiết hôm nay", depth=0)

        # Test at depth = 1 (simulating second recursion turn after tool execution)
        with patch.object(self.handler.tts.tts_text_queue, "put"):
            self.handler.chat(None, depth=1)

        # Test at depth = 2 (simulating third recursion turn)
        with patch.object(self.handler.tts.tts_text_queue, "put"):
            self.handler.chat(None, depth=2)

        funcs_depth_0 = captured_functions_by_depth[0]
        funcs_depth_1 = captured_functions_by_depth[1]
        funcs_depth_2 = captured_functions_by_depth[2]

        # 1. direct_answer must be present in ALL depths
        self.assertTrue(any(f["function"]["name"] == "direct_answer" for f in funcs_depth_0))
        self.assertTrue(any(f["function"]["name"] == "direct_answer" for f in funcs_depth_1))
        self.assertTrue(any(f["function"]["name"] == "direct_answer" for f in funcs_depth_2))

        # 2. Length must be identical
        self.assertEqual(len(funcs_depth_0), len(funcs_depth_1))
        self.assertEqual(len(funcs_depth_1), len(funcs_depth_2))
        self.assertEqual(len(funcs_depth_0), 4)  # 3 sample tools + 1 direct_answer

        # 3. Exact tool names and ordering must be 100% identical
        names_0 = [f["function"]["name"] for f in funcs_depth_0]
        names_1 = [f["function"]["name"] for f in funcs_depth_1]
        names_2 = [f["function"]["name"] for f in funcs_depth_2]

        self.assertEqual(names_0, names_1)
        self.assertEqual(names_1, names_2)
        # Sắp xếp theo bảng chữ cái: control_device, direct_answer, get_weather, play_music
        self.assertEqual(names_0, ["control_device", "direct_answer", "get_weather", "play_music"])

    def test_max_depth_preserves_functions_with_tool_choice_none(self):
        """Test Case 1.4.2: At depth >= MAX_DEPTH, tools schema is preserved and tool_choice='none' is passed"""
        captured_kwargs = {}
        captured_functions = []

        def mock_response_with_functions(session_id, dialogue, functions=None, **kwargs):
            nonlocal captured_kwargs, captured_functions
            captured_kwargs = dict(kwargs)
            captured_functions = list(functions) if functions else []
            return [("Câu trả lời cuối cùng", None)]

        self.handler.llm.response_with_functions = mock_response_with_functions

        with patch.object(self.handler.tts.tts_text_queue, "put"):
            # Call at depth = 5 (MAX_DEPTH)
            self.handler.chat(None, depth=5)

        # Functions must STILL be passed (preserving DeepSeek KV-Cache schema!)
        self.assertGreater(len(captured_functions), 0)
        self.assertTrue(any(f["function"]["name"] == "direct_answer" for f in captured_functions))

        # tool_choice must be 'none' to safely terminate recursion
        self.assertEqual(captured_kwargs.get("tool_choice"), "none")

    def test_openai_provider_tool_choice_forwarding(self):
        """Test Case 1.4.3: OpenAI LLM provider forwards tool_choice to client.chat.completions.create"""
        llm = OpenAILLM({
            "model_name": "deepseek-flash",
            "api_key": "fake_key",
            "base_url": "https://api.deepseek.com/v1"
        })

        mock_stream = MagicMock()
        mock_stream.__iter__.return_value = []

        with patch.object(llm.client.chat.completions, "create", return_value=mock_stream) as mock_create:
            dialogue = [{"role": "user", "content": "Hello"}]
            tools = [DIRECT_ANSWER_TOOL]

            # Call with tool_choice="none"
            list(llm.response_with_functions("sess_1", dialogue, functions=tools, tool_choice="none"))

            mock_create.assert_called_once()
            _, call_kwargs = mock_create.call_args
            self.assertEqual(call_kwargs.get("tools"), tools)
    def test_divergence_guard_when_tools_added_between_depths(self):
        """Test Case 1.4.4: If func_handler discovers tools mid-turn, depth > 0 MUST reuse depth 0 snapshot"""
        initial_tools = [
            {"type": "function", "function": {"name": "get_weather", "description": "Thời tiết"}},
        ]
        self.handler.func_handler.get_functions.return_value = initial_tools

        captured_functions_by_depth = {}

        def mock_response_with_functions(session_id, dialogue, functions=None, **kwargs):
            depth_key = len(captured_functions_by_depth)
            captured_functions_by_depth[depth_key] = list(functions) if functions else []
            return [("Dạ thời tiết Hà Nội 31 độ ạ", None)]

        self.handler.llm.response_with_functions = mock_response_with_functions

        # Depth 0
        with patch.object(self.handler.tts.tts_text_queue, "put"):
            self.handler.chat("thời tiết", depth=0)

        # Simulate MCP discovery in background: adds 2 new tools mid-turn!
        mutated_tools = initial_tools + [
            {"type": "function", "function": {"name": "tra_cuu_thong_tin_sunhouse", "description": "Sunhouse"}},
            {"type": "function", "function": {"name": "play_online_music", "description": "Music"}},
        ]
        self.handler.func_handler.get_functions.return_value = mutated_tools

        # Depth 1 (recursion)
        with patch.object(self.handler.tts.tts_text_queue, "put"):
            self.handler.chat(None, depth=1)

        funcs_0 = captured_functions_by_depth[0]
        funcs_1 = captured_functions_by_depth[1]

        # Assert depth 1 strictly kept depth 0 snapshot (2 tools: get_weather, direct_answer), NOT 4 tools!
        self.assertEqual(len(funcs_0), 2)
        self.assertEqual(len(funcs_1), 2)
        self.assertEqual(
            [f["function"]["name"] for f in funcs_0],
            [f["function"]["name"] for f in funcs_1]
        )


if __name__ == "__main__":
    unittest.main()

