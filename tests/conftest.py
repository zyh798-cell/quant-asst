"""pytest 全局夹具与环境隔离。"""

from __future__ import annotations

import os

import pytest

from core.config import Settings

# 固定测试环境变量，避免依赖本机 .env 内容
os.environ.setdefault("QUANTSENTINEL_LLM_MODEL", "deepseek/deepseek-chat")
os.environ.setdefault("QUANTSENTINEL_QDRANT_MODE", "local")


@pytest.fixture()
def test_settings(tmp_path) -> Settings:
    """指向临时目录的配置实例（不读 .env，不污染真实 var/）。"""
    s = Settings(_env_file=None, var_dir=tmp_path / "var")
    s.ensure_dirs()
    return s
