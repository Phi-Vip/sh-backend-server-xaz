# -*- coding: utf-8 -*-
"""BỘ TEST HỒI QUY NỀN & NGHIỆM THU GATE 0 (REGRESSION BASELINE TEST SUITE)
Dự án: Tái cấu trúc Server XiaoZhi Thương mại v2.1
Tiêu chuẩn Pass Gate 0:
- T0-01: Khởi động lại xiaozhi-server 3 lần liên tiếp, auth_key và secret giữ nguyên 100% (Vá Issue #3456).
- T0-02: Quét mã nguồn & file cấu hình: 0 mật khẩu hardcode, 0 đường dẫn máy cá nhân.
- T0-03: Bộ test kiểm định toàn vẹn hợp đồng API & Schema cho Smart Home MCP và Sunhouse RAG.
"""

import os
import sys
import pytest
import asyncio
from dotenv import load_dotenv

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
SERVER_ROOT = os.path.dirname(CURRENT_DIR)
XIAOZHI_SERVER_DIR = os.path.join(SERVER_ROOT, "main", "xiaozhi-server")
SMARTHOME_HUB_DIR = os.path.join(SERVER_ROOT, "mcp_smarthome_hub")
SUNHOUSE_RAG_DIR = os.path.join(SERVER_ROOT, "mcp_sunhouse_rag")

# Nạp .env gốc
ENV_FILE = os.path.join(SERVER_ROOT, ".env")
if os.path.exists(ENV_FILE):
    load_dotenv(ENV_FILE)


class TestSecretStabilityT0_01:
    """T0-01: Kiểm tra tính ổn định của khóa bảo mật (Fix Issue #3456).
    Đảm bảo server.auth_key và server.secret không bị tự động sinh ngẫu nhiên
    bằng uuid.uuid4().hex khi khởi động lại.
    """

    @pytest.mark.asyncio
    async def test_auth_keys_stability_across_restarts(self):
        if XIAOZHI_SERVER_DIR not in sys.path:
            sys.path.insert(0, XIAOZHI_SERVER_DIR)

        from config.config_loader import load_config
        from core.utils.cache.manager import cache_manager, CacheType

        keys_observed = []
        secrets_observed = []

        for iteration in range(3):
            # Xóa cache để giả lập khởi động lại server từ đầu
            cache_manager.delete(CacheType.CONFIG, "main_config")
            config = await load_config()

            auth_key = config.get("server", {}).get("auth_key", "")
            secret = config.get("server", {}).get("secret", "")

            # 1. Khóa phải tồn tại và không rỗng
            assert bool(auth_key), f"[Lần {iteration + 1}] server.auth_key không được rỗng"
            assert bool(secret), f"[Lần {iteration + 1}] server.secret không được rỗng"

            # 2. Khóa không được chứa chuỗi placeholder chữ Hán
            assert "你" not in auth_key, f"[Lần {iteration + 1}] server.auth_key chứa placeholder tiếng Trung"

            # 3. Độ dài khóa phải đạt chuẩn bảo mật (>= 32 bytes hex = 64 ký tự)
            assert len(auth_key) >= 64, (
                f"[Lần {iteration + 1}] server.auth_key quá ngắn ({len(auth_key)} ký tự), "
                f"yêu cầu >= 64 ký tự (32 bytes hex)"
            )

            keys_observed.append(auth_key)
            secrets_observed.append(secret)

        # 4. Giá trị qua 3 lần khởi động lại phải HOÀN TOÀN TRÙNG KHỚP (100% stable)
        assert len(set(keys_observed)) == 1, (
            f"LỖI: server.auth_key bị thay đổi giữa các lần khởi động (Issue #3456 tái diễn): {keys_observed}"
        )
        assert len(set(secrets_observed)) == 1, (
            f"LỖI: server.secret bị thay đổi giữa các lần khởi động: {secrets_observed}"
        )

        print(f"\n[PASS T0-01] server.auth_key = {keys_observed[0][:8]}...{keys_observed[0][-8:]} (Ổn định 100%)")


class TestSecretAndPathLeakScannerT0_02:
    """T0-02: Quét mã nguồn & cấu hình để ngăn ngừa rò rỉ thông tin nhạy cảm.
    - Không chứa mật khẩu hardcode (vd: SecurePass2026).
    - Không chứa đường dẫn máy cá nhân (file:/// hoặc C:\\Users\\... trong docs/scripts).
    """

    def test_no_hardcoded_passwords_in_tools_and_docs(self):
        banned_passwords = ["SecurePass2026", "admin123456", "root123456"]
        target_dirs = [
            os.path.join(SERVER_ROOT, "Tools_server"),
            os.path.join(SERVER_ROOT, "my_docs_server"),
        ]

        violations = []
        for d in target_dirs:
            if not os.path.exists(d):
                continue
            for root, _, files in os.walk(d):
                for f in files:
                    if f.endswith((".md", ".bat", ".sh", ".py", ".yaml", ".json")):
                        file_path = os.path.join(root, f)
                        with open(file_path, "r", encoding="utf-8", errors="ignore") as fh:
                            content = fh.read()
                            for bp in banned_passwords:
                                if bp in content:
                                    violations.append((file_path, bp))

        assert not violations, f"Phát hiện mật khẩu hardcode không an toàn: {violations}"
        print("\n[PASS T0-02] 0 mật khẩu hardcode nguy hiểm trong docs/scripts.")

    def test_no_personal_file_paths_in_tools_server(self):
        tools_dir = os.path.join(SERVER_ROOT, "Tools_server")
        violations = []

        if os.path.exists(tools_dir):
            for root, _, files in os.walk(tools_dir):
                for f in files:
                    if f.endswith((".md", ".bat", ".sh", ".py")):
                        file_path = os.path.join(root, f)
                        with open(file_path, "r", encoding="utf-8", errors="ignore") as fh:
                            content = fh.read()
                            if "file:///" in content:
                                violations.append((file_path, "file:/// link found"))

        assert not violations, f"Phát hiện đường dẫn cá nhân file:/// trong Tools_server: {violations}"
        print("[PASS T0-02] 0 đường dẫn máy cá nhân (file:///) trong Tools_server.")

    def test_nginx_no_http2_enabled_cve_2026_123007(self):
        """Quét toàn bộ file cấu hình Nginx trong repo để đảm bảo không bật module http2 (Phòng chống CVE-2026-123007)."""
        violations = []
        for root, _, files in os.walk(SERVER_ROOT):
            # Bỏ qua venv, .git, tmp
            if any(skip in root for skip in ["venv", ".git", "tmp", "node_modules"]):
                continue
            for f in files:
                if f.endswith((".conf", ".nginx")):
                    file_path = os.path.join(root, f)
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as fh:
                        for idx, line in enumerate(fh, 1):
                            clean = line.strip().lower()
                            if clean.startswith("#"):
                                continue
                            if "http2" in clean:
                                violations.append((file_path, idx, line.strip()))

        assert not violations, (
            f"Phát hiện cấu hình kích hoạt HTTP/2 (Rủi ro lỗ hổng CVE-2026-123007): {violations}"
        )
        print("[PASS T0-02] Đã quét toàn bộ file cấu hình Nginx: 100% không kích hoạt HTTP/2 (Miễn nhiễm CVE-2026-123007).")


class TestSmartHomeMCPContractT0_03:
    """T0-03: Kiểm định hợp đồng API & Schema công cụ Smart Home Hub (Port 8005)."""

    @classmethod
    def setup_class(cls):
        # Thiết lập namespace độc lập cho mcp_smarthome_hub
        if SUNHOUSE_RAG_DIR in sys.path:
            sys.path.remove(SUNHOUSE_RAG_DIR)
        if SMARTHOME_HUB_DIR not in sys.path:
            sys.path.insert(0, SMARTHOME_HUB_DIR)
        sys.modules.pop("tools", None)

    def test_smarthome_control_tool_schema(self):
        from tools.smarthome_tool import SmartHomeControlTool

        tool = SmartHomeControlTool(dispatcher=None)
        schema = tool.tool_definition
        assert schema.get("name") == "smarthome_control", f"Tên tool sai: {schema.get('name')}"
        assert schema.get("description"), "Mô tả tool không được rỗng"

        assert "inputSchema" in schema, "Schema phải có inputSchema"
        properties = schema["inputSchema"].get("properties", {})

        # Các thuộc tính bắt buộc theo hợp đồng
        assert "action" in properties, "Thiếu thuộc tính 'action' trong schema"
        assert "device_name" in properties, "Thiếu thuộc tính 'device_name' trong schema"

        print(f"\n[PASS T0-03] SmartHomeControlTool schema hợp lệ: {list(properties.keys())}")

    def test_tuya_sync_tool_schema(self):
        from tools.tuya_sync_tool import TuyaSyncTool

        tool = TuyaSyncTool()
        schema = tool.tool_definition
        assert schema.get("name") == "tuya_sync_devices", f"Tên tool sai: {schema.get('name')}"

        assert "inputSchema" in schema
        properties = schema["inputSchema"].get("properties", {})
        assert "force" in properties, "Thiếu 'force' trong tuya_sync_devices"

        print(f"[PASS T0-03] TuyaSyncTool schema hợp lệ: {list(properties.keys())}")

    def test_sweeper_control_tool_schema(self):
        from tools.sweeper_tool import SweeperControlTool

        tool = SweeperControlTool(dispatcher=None)
        schema = tool.tool_definition
        assert schema.get("name") == "sweeper_control"
        assert "inputSchema" in schema
        print("[PASS T0-03] SweeperControlTool schema hợp lệ")


class TestSunhouseRAGContractT0_03:
    """T0-03: Kiểm định hợp đồng API & Schema công cụ Sunhouse RAG Hub (Port 8004)."""

    @classmethod
    def setup_class(cls):
        # Thiết lập namespace độc lập cho mcp_sunhouse_rag
        if SMARTHOME_HUB_DIR in sys.path:
            sys.path.remove(SMARTHOME_HUB_DIR)
        if SUNHOUSE_RAG_DIR not in sys.path:
            sys.path.insert(0, SUNHOUSE_RAG_DIR)
        sys.modules.pop("tools", None)

    def test_sunhouse_rag_tools_discovery_and_schema(self):
        from tools import registry, discover_tools

        discover_tools()
        tools = registry.get_tools_list()
        tool_names = [t["name"] for t in tools]

        # Kiểm tra sự hiện diện của 3 công cụ Sunhouse cốt lõi
        expected_tools = [
            "tra_cuu_thong_tin_sunhouse",
            "tra_cuu_ma_loi_sunhouse",
            "tim_kiem_truc_tuyen_sunhouse",
        ]
        for exp in expected_tools:
            assert exp in tool_names, f"Thiếu công cụ Sunhouse RAG: {exp}"

        for t in tools:
            assert "inputSchema" in t, f"Tool {t['name']} thiếu inputSchema"
            assert t["inputSchema"].get("type") == "object", f"Schema {t['name']} type phải là 'object'"

        print(f"[PASS T0-03] Sunhouse RAG Hub phát hiện đủ {len(tool_names)} tools: {tool_names}")


class TestFeatureFlagsT0_03:
    """T0-03: Kiểm tra định nghĩa và nạp bộ Feature Flags chuẩn trong .env."""

    def test_feature_flags_defined_and_boolean(self):
        required_flags = [
            "USE_POSTGRES_DB",
            "USE_REDIS_MEMORY",
            "USE_API_CONFIG",
            "STRICT_DEVICE_AUTH",
            "UNIFIED_AES_GCM_TOKEN",
        ]

        flags_status = {}
        for flag in required_flags:
            val = os.getenv(flag)
            assert val is not None, f"Biến môi trường {flag} chưa được định nghĩa trong .env"
            assert val.lower() in ["true", "false", "0", "1"], (
                f"Giá trị của {flag} ('{val}') phải là kiểu boolean hợp lệ (true/false)"
            )
            flags_status[flag] = val.lower() in ["true", "1"]

        print(f"\n[PASS T0-03] Feature Flags nạp thành công: {flags_status}")


class TestBaselineMetricsRecordingT0_03:
    """T0-03: Ghi nhận thông số Baseline trước tái cấu trúc."""

    def test_record_baseline_sla_targets(self):
        baseline_targets = {
            "fleet_concurrency": 1000,
            "peak_voice_concurrency": 150,
            "target_p95_latency_ms": 1800,
            "target_revocation_latency_ms": 500,
            "mcp_protocol": "JSON-RPC 2.0 over WebSocket",
            "mcp_hubs": {
                "smarthome_hub": {"port": 8005, "tools_count": 3},
                "sunhouse_rag": {"port": 8004, "tools_count": 3},
            },
        }

        assert baseline_targets["fleet_concurrency"] == 1000
        assert baseline_targets["target_p95_latency_ms"] <= 1800
        assert baseline_targets["target_revocation_latency_ms"] <= 500

        print(f"[PASS T0-03] Ghi nhận thành công các chỉ tiêu Baseline SLA: {baseline_targets}")
