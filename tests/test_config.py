"""
配置模块测试 — 验证 Settings 加载、默认值、环境变量覆盖。
"""

import os
import pytest
from lingyi.config import Settings, get_settings


class TestSettings:
    """Settings 测试套件。"""

    def test_default_values(self):
        """默认值应正确（使用 _env_file=None 避免 .env 文件干扰）。"""
        s = Settings(_env_file=None)
        assert s.environment == "development"
        assert s.rag_mode == "mock"
        assert s.model_name == "qwen-max"
        assert s.rag_recall_k == 15
        assert s.safety_max_retries == 3

    def test_env_override(self, monkeypatch):
        """环境变量应覆盖默认值。"""
        monkeypatch.setenv("MODEL_NAME", "qwen-plus")
        monkeypatch.setenv("RAG_MODE", "chroma")
        s = Settings()
        assert s.model_name == "qwen-plus"
        assert s.rag_mode == "chroma"

    def test_effective_api_key(self):
        """effective_api_key 应优先返回 dashscope_api_key。"""
        s = Settings(dashscope_api_key="test-key", openai_api_key="fallback")
        assert s.effective_api_key == "test-key"

    def test_effective_api_key_fallback(self):
        """dashscope_api_key 为空时应回退到 openai_api_key。"""
        s = Settings(dashscope_api_key="", openai_api_key="fallback")
        assert s.effective_api_key == "fallback"

    def test_db_path_property(self):
        """db_path 应返回正确的路径。"""
        s = Settings(storage_dir="/tmp/test")
        # 使用 os.path.join 处理 Windows/Unix 路径差异
        expected = os.path.join("/tmp/test", "patient_profiles.db")
        assert s.db_path == expected

    def test_get_settings_cached(self):
        """get_settings() 应返回缓存的实例。"""
        get_settings.cache_clear()
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2
