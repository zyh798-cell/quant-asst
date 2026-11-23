"""密钥读取与隐私展示、mock 离线开关的单元测试。"""

from __future__ import annotations

import os

import pytest

from core import llm
from core.secrets import (
    KNOWN_LLM_KEYS,
    describe_keys,
    load_env_file,
    mask_secret,
    present_keys,
    secret_exists,
)

_SECRET_VALUE = "sk-should-never-be-printed"


@pytest.fixture(autouse=True)
def _clean_key_env(monkeypatch):
    """清空全部已知密钥环境变量，保证测试可重复（不受本机 .env 影响）。"""
    for name in KNOWN_LLM_KEYS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("QUANT_ASST_LLM_MOCK", raising=False)
    monkeypatch.delenv("QUANTSENTINEL_LLM_MOCK", raising=False)
    monkeypatch.delenv("LITELLM_OFFLINE_MODE", raising=False)


def test_secret_exists_true(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", _SECRET_VALUE)
    assert secret_exists("DEEPSEEK_API_KEY") is True


def test_secret_exists_false_when_missing():
    assert secret_exists("DEEPSEEK_API_KEY") is False


def test_secret_exists_false_when_blank(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "   ")
    assert secret_exists("DEEPSEEK_API_KEY") is False


def test_present_keys_only_returns_configured(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    assert present_keys() == ["OPENAI_API_KEY"]


def test_mask_secret_never_leaks_value(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", _SECRET_VALUE)
    text = mask_secret("DEEPSEEK_API_KEY")
    assert text == "DEEPSEEK_API_KEY: 存在"
    assert _SECRET_VALUE not in text


def test_describe_keys_format():
    lines = describe_keys()
    assert len(lines) == len(KNOWN_LLM_KEYS)
    assert all(line.endswith("不存在") for line in lines)
    assert all(_SECRET_VALUE not in line for line in lines)


def test_load_env_file_loads_and_does_not_override(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("QUANTSENTINEL_TEST_VAR=from_file\n", encoding="utf-8")
    monkeypatch.setenv("QUANTSENTINEL_TEST_VAR", "from_env")

    assert load_env_file(env_file) is True
    # 已存在的环境变量不被 .env 覆盖
    assert os.environ["QUANTSENTINEL_TEST_VAR"] == "from_env"

    env_file.write_text("QUANTSENTINEL_TEST_VAR2=from_file\n", encoding="utf-8")
    load_env_file(env_file)
    assert os.environ["QUANTSENTINEL_TEST_VAR2"] == "from_file"


def test_load_env_file_missing_returns_false(tmp_path):
    assert load_env_file(tmp_path / "nope.env") is False


def test_mock_mode_enables_litellm_offline(monkeypatch):
    """mock 模式必须开启 LiteLLM 离线开关，避免远端 cost map 拉取告警。"""
    monkeypatch.setenv("QUANTSENTINEL_LLM_MOCK", "1")
    assert llm.is_mock_mode() is True

    backend = llm.get_completion_backend()
    assert isinstance(backend, llm.MockCompletionBackend)
    assert os.environ["LITELLM_OFFLINE_MODE"] == "true"


def test_real_mode_does_not_force_offline(monkeypatch):
    monkeypatch.delenv("QUANT_ASST_LLM_MOCK", raising=False)
    monkeypatch.delenv("QUANTSENTINEL_LLM_MOCK", raising=False)
    assert llm.is_mock_mode() is False

    backend = llm.get_completion_backend()
    assert not isinstance(backend, llm.MockCompletionBackend)
    assert os.environ.get("LITELLM_OFFLINE_MODE") is None


# ---------------------------------------------------------------------------
# mock 开关命名兼容（外部代码 review 第 5 项）
# ---------------------------------------------------------------------------

def test_new_mock_env_var_is_primary(monkeypatch):
    """新名 QUANT_ASST_LLM_MOCK 生效。"""
    monkeypatch.setenv("QUANT_ASST_LLM_MOCK", "1")
    monkeypatch.delenv("QUANTSENTINEL_LLM_MOCK", raising=False)
    assert llm.is_mock_mode() is True
    assert isinstance(llm.get_completion_backend(), llm.MockCompletionBackend)


def test_legacy_mock_env_var_still_supported(monkeypatch):
    """旧名 QUANTSENTINEL_LLM_MOCK 仍向后兼容生效。"""
    monkeypatch.delenv("QUANT_ASST_LLM_MOCK", raising=False)
    monkeypatch.setenv("QUANTSENTINEL_LLM_MOCK", "true")
    assert llm.is_mock_mode() is True
    assert isinstance(llm.get_completion_backend(), llm.MockCompletionBackend)


def test_new_name_wins_when_both_set(monkeypatch):
    """两个都设时以新名为准（避免旧值意外关闭 mock）。"""
    monkeypatch.setenv("QUANT_ASST_LLM_MOCK", "0")
    monkeypatch.setenv("QUANTSENTINEL_LLM_MOCK", "1")
    assert llm.is_mock_mode() is False


@pytest.mark.parametrize("value", ["1", "true", "YES", "On"])
def test_mock_true_values_case_insensitive(monkeypatch, value):
    monkeypatch.setenv("QUANT_ASST_LLM_MOCK", value)
    assert llm.is_mock_mode() is True


def test_cli_startup_prints_key_status_without_value(monkeypatch):
    """CLI 启动日志只报告存在性，绝不泄漏密钥明文。"""
    from typer.testing import CliRunner

    from cli import app

    monkeypatch.setenv("DEEPSEEK_API_KEY", _SECRET_VALUE)
    result = CliRunner().invoke(app, ["settings"])
    assert result.exit_code == 0
    assert "DEEPSEEK_API_KEY: 存在" in result.output
    assert _SECRET_VALUE not in result.output


def test_cli_startup_reports_missing_key(monkeypatch, tmp_path):
    from typer.testing import CliRunner

    from cli import app

    # 指向不存在的 .env，避免本机真实 .env 干扰断言
    monkeypatch.setattr("core.secrets.ENV_FILE", str(tmp_path / "missing.env"))
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    result = CliRunner().invoke(app, ["settings"])
    assert result.exit_code == 0
    assert "DEEPSEEK_API_KEY: 不存在" in result.output
