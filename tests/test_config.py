"""配置加载测试：环境变量前缀覆盖、默认值、运行时目录创建。"""

from __future__ import annotations

from core.config import Settings, get_settings
from core.markets import Market


def test_env_prefix_override(monkeypatch) -> None:
    """QUANT_ASST_ 前缀环境变量必须覆盖默认值。"""
    monkeypatch.setenv("QUANT_ASST_LLM_MODEL", "openai/gpt-4o-mini")
    monkeypatch.setenv("QUANT_ASST_TRADE_COST_RATE", "0.002")
    s = Settings(_env_file=None)
    assert s.llm_model == "openai/gpt-4o-mini"
    assert s.trade_cost_rate == 0.002


def test_default_values(test_settings: Settings) -> None:
    """默认值符合规格：双边 0.15% 成本、0.1% 滑点、样本外 30%。"""
    assert test_settings.trade_cost_rate == 0.0015  # 用户规格：双边 0.15%
    assert test_settings.slippage_rate == 0.001
    assert test_settings.train_test_split == 0.7    # 样本外区间 30%（硬约束 5）
    assert test_settings.llm_max_retries == 1       # 硬约束 2
    assert test_settings.sandbox_network_disabled is True  # 硬约束 3


def test_default_market_cn() -> None:
    """默认市场为 A 股。"""
    s = Settings(_env_file=None)
    assert s.default_market == Market.CN_STOCK


def test_market_env_parse(monkeypatch) -> None:
    """市场枚举可从环境变量解析（大小写不敏感由 pydantic 处理为精确匹配枚举值）。"""
    monkeypatch.setenv("QUANT_ASST_DEFAULT_MARKET", "crypto")
    s = Settings(_env_file=None)
    assert s.default_market == Market.CRYPTO


def test_ensure_dirs_creates_runtime_layout(test_settings: Settings) -> None:
    """ensure_dirs 幂等创建全部运行时目录。"""
    test_settings.ensure_dirs()
    for d in (
        test_settings.var_dir,
        test_settings.trajectory_dir,
        test_settings.market_cache_dir,
        test_settings.report_dir,
        test_settings.sandbox_workdir,
    ):
        assert d.exists()


def test_get_settings_singleton() -> None:
    """get_settings 返回缓存单例。"""
    assert get_settings() is get_settings()
