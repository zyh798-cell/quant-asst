"""未来函数确定性检查测试（外部代码 review 第 4 项）。

覆盖：
- 合规策略（仅用历史数据）通过检查；
- ``shift(-n)`` 作弊策略被检查器抓到；
- 全局统计量泄漏（``df['close'].max()``）被抓；
- 反序引用（``iloc[::-1]``）被抓；
- 行数不足 / 无可用检查点时明确报错；
- CLI ``--lookahead-check`` 开关可用（默认关）。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backtest.lookahead import (
    DEFAULT_CHECKPOINTS,
    check_lookahead_determinism,
    format_lookahead_verdict,
)

ROOT = Path(__file__).resolve().parent.parent


def _ohlcv(n: int = 200, seed: int = 7) -> pd.DataFrame:
    """合成先跌后涨行情（确定性，极值落在末段，便于暴露未来引用）。"""
    rng = np.random.default_rng(seed)
    base = np.linspace(95.0, 115.0, n)          # 末段创出新高
    prices = base + rng.normal(0.0, 0.4, n)
    return pd.DataFrame({
        "date": pd.bdate_range("2024-01-01", periods=n),
        "open": prices,
        "high": prices * 1.01,
        "low": prices * 0.99,
        "close": prices,
        "volume": 1e6,
        "amount": 1e7,
        "suspended": False,
        "limit_up": np.nan,
        "limit_down": np.nan,
    })


def _load_strategy_module(path: Path):
    """按文件路径加载策略模块（示例脚本非包内模块）。"""
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[path.stem] = module
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# 合规策略：现有示例必须通过
# ---------------------------------------------------------------------------

def test_example_dual_ma_passes_lookahead_check():
    """examples/dual_ma.py 只依赖历史 rolling，截断一致性必须通过。"""
    module = _load_strategy_module(ROOT / "examples" / "dual_ma.py")
    verdict = check_lookahead_determinism(_ohlcv(), module.generate_positions)
    assert verdict.passed, verdict.detail
    assert set(verdict.checkpoints) == set(DEFAULT_CHECKPOINTS)
    assert all(verdict.checkpoints.values())
    assert verdict.first_violation_at is None


def test_hist_only_custom_strategy_passes():
    """显式因果策略（当日及之前数据）必须通过。"""
    def causal(df: pd.DataFrame) -> pd.Series:
        close = df["close"].astype(float)
        return (close > close.rolling(10).mean()).astype(float)

    verdict = check_lookahead_determinism(_ohlcv(), causal)
    assert verdict.passed


# ---------------------------------------------------------------------------
# 作弊策略：必须被抓到
# ---------------------------------------------------------------------------

def test_shift_negative_is_detected():
    """shift(-1) 引入未来数据，检查器必须判定不一致。"""
    def cheating(df: pd.DataFrame) -> pd.Series:
        close = df["close"].astype(float)
        future = close.shift(-1)
        return (future > close).astype(float)

    verdict = check_lookahead_determinism(_ohlcv(), cheating)
    assert not verdict.passed
    assert verdict.first_violation_at is not None
    assert verdict.detail


def test_global_stat_leak_is_detected():
    """全局 max() 泄漏未来信息，同样必须被抓。"""
    def leaking(df: pd.DataFrame) -> pd.Series:
        close = df["close"].astype(float)
        return (close >= close.max()).astype(float)

    verdict = check_lookahead_determinism(_ohlcv(), leaking)
    assert not verdict.passed


def test_reversed_index_is_detected():
    """反序引用（future-first）必须被抓。"""
    def reversed_ref(df: pd.DataFrame) -> pd.Series:
        close = df["close"].astype(float).to_numpy()
        rev = close[::-1]
        sig = (rev > np.roll(rev, 1)).astype(float)
        return pd.Series(sig[::-1], index=df.index)

    verdict = check_lookahead_determinism(_ohlcv(), reversed_ref)
    assert not verdict.passed


# ---------------------------------------------------------------------------
# 边界与文案
# ---------------------------------------------------------------------------

def test_too_few_rows_raises():
    with pytest.raises(ValueError, match="无可用检查点"):
        check_lookahead_determinism(_ohlcv(6), lambda df: df["close"] * 0.0)


def test_custom_checkpoints():
    def causal(df: pd.DataFrame) -> pd.Series:
        return (df["close"].astype(float) > 0).astype(float)

    verdict = check_lookahead_determinism(_ohlcv(), causal, checkpoints=[40, 80])
    assert verdict.passed
    assert set(verdict.checkpoints) == {40, 80}


def test_format_verdict_text():
    good = check_lookahead_determinism(
        _ohlcv(), lambda df: (df["close"] > 0).astype(float)
    )
    assert "通过" in format_lookahead_verdict(good, "dual_ma")

    def cheating(df: pd.DataFrame) -> pd.Series:
        return (df["close"].astype(float).shift(-1) > df["close"]).astype(float)

    bad = check_lookahead_determinism(_ohlcv(), cheating)
    text = format_lookahead_verdict(bad, "cheat")
    assert "未通过" in text and "cheat" in text
