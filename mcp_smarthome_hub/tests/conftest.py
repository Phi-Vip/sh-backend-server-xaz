# -*- coding: utf-8 -*-
import os
import pytest

@pytest.fixture(autouse=True)
def default_test_environment(monkeypatch):
    """Cấu hình môi trường mặc định cho toàn bộ test suite.
    
    Đảm bảo các test case cũ (Phase 2, Phase 3, Phase 4, Fallback Thing Model)
    chạy độc lập, không bị ảnh hưởng bởi biến môi trường .env cục bộ của server.
    Các test kiểm thử Task 2 Phase 5 sẽ dùng monkeypatch.setenv để kiểm tra cờ tắt mở.
    """
    # Mặc định cho phép Project Token trong các bài test thuật toán / mock cũ
    monkeypatch.setenv("TUYA_FEATURE_PROJECT_TOKEN", "true")
