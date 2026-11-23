"""pytest 全局夹具与环境隔离。"""

from __future__ import annotations

import os

import pytest

from core.config import Settings

# 固定测试环境变量，避免依赖本机 .env 内容
os.environ.setdefault("QUANTSENTINEL_LLM_MODEL", "deepseek/deepseek-chat")
os.environ.setdefault("QUANTSENTINEL_QDRANT_MODE", "local")

# 单元测试（test_graph / test_hypothesis_agent 等）通过 monkeypatch 替换
# ``litellm.completion`` 注入确定性响应，必须走真实 LiteLLM 后端路径。
# 若外部（CI / 本机 .env / shell）注入 QUANT_ASST_LLM_MOCK，get_completion_backend
# 会切换到 MockCompletionBackend，导致这些测试收不到注入响应而失败。
# 此处强制清除（新旧名都清），保证本地与 CI 行为一致；示例测试在子进程内自设 mock，不受影响。
os.environ.pop("QUANT_ASST_LLM_MOCK", None)
os.environ.pop("QUANTSENTINEL_LLM_MOCK", None)


@pytest.fixture()
def test_settings(tmp_path) -> Settings:
    """指向临时目录的配置实例（不读 .env，不污染真实 var/）。"""
    s = Settings(_env_file=None, var_dir=tmp_path / "var")
    s.ensure_dirs()
    return s
