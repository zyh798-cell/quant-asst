# -*- coding: utf-8 -*-
"""硬编码双均线策略直跑校验（不依赖 LLM、不依赖网络）。

用途：验证 ``examples/dual_ma.py`` 模板 + 回测引擎在「有趋势」行情下
必然产生成交信号与非零收益 —— 即 2026-11「零成交」事故的回归校验。

运行：``uv run python examples/run_dual_ma_check.py``
退出码：全部断言通过为 0，否则非 0。
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

# 允许直接以脚本方式运行（把项目根加入 import 路径）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backtest.engine import run_event_backtest  # noqa: E402
from backtest.market_rules import CN_STOCK_RULES  # noqa: E402
from examples.dual_ma import generate_positions  # noqa: E402

INITIAL_CAPITAL = 1_000_000.0


def make_ohlcv(close: np.ndarray) -> pd.DataFrame:
    """由收盘价构造标准 OHLCV（open=close，无涨跌停/停牌）。"""
    arr = np.asarray(close, dtype=float)
    n = len(arr)
    return pd.DataFrame({
        "date": pd.bdate_range("2024-01-01", periods=n),
        "open": arr,
        "high": arr * 1.01,
        "low": arr * 0.99,
        "close": arr,
        "volume": 1e6,
        "amount": 1e7,
        "suspended": False,
        "limit_up": np.nan,
        "limit_down": np.nan,
    })


def _report(name: str, result: dict) -> None:
    m = result["metrics"]["overall"]
    print(f"[{name}]")
    print(f"  区间            : {result['period_start']} ~ {result['period_end']}"
          f"（{result['metrics']['overall']['n_days']} 个净值日）")
    print(f"  信号非零交易日  : {result['signal_nonzero_days']}")
    print(f"  成交笔数        : {m['n_trades']}（买 {sum(1 for t in result['trades'] if t['side']=='buy')}"
          f" / 卖 {sum(1 for t in result['trades'] if t['side']=='sell')}）")
    print(f"  累计成本        : {result['total_cost']:.2f}")
    print(f"  期末净值        : {result['final_equity']:.2f}")
    print(f"  总收益率        : {m['total_return'] * 100:.2f}%")
    print(f"  最大回撤        : {m['max_drawdown'] * 100:.2f}%")
    for t in result["trades"][:6]:
        print(f"    - {t['date']} {t['side']:>4} {t['shares']:>8.0f} 股"
              f" @ {t['price']:.2f}  金额 {t['amount']:.2f}")


def check_synthetic() -> None:
    """场景 A：先涨后跌（必产生金叉买入 + 死叉卖出，总收益非零）。"""
    n = 160
    half = n // 2
    prices = np.concatenate([
        np.linspace(100.0, 160.0, half),
        np.linspace(160.0, 90.0, n - half),
    ])
    result = run_event_backtest(
        make_ohlcv(prices), generate_positions, CN_STOCK_RULES,
        initial_capital=INITIAL_CAPITAL,
    )
    _report("合成-先涨后跌", result)

    buys = [t for t in result["trades"] if t["side"] == "buy"]
    sells = [t for t in result["trades"] if t["side"] == "sell"]
    assert result["signal_nonzero_days"] > 0, "双均线应产生非零目标仓位"
    assert len(buys) >= 1, "应至少出现一次金叉买入"
    assert len(sells) >= 1, "应至少出现一次死叉卖出"
    assert result["metrics"]["overall"]["total_return"] != 0.0, "总收益不应为 0"
    print("  ✔ 有买入、有卖出、总收益非零\n")

    # 场景 B：单边上涨（金叉后持有一段，总收益应为正）
    prices_up = np.linspace(100.0, 220.0, n)
    result_up = run_event_backtest(
        make_ohlcv(prices_up), generate_positions, CN_STOCK_RULES,
        initial_capital=INITIAL_CAPITAL,
    )
    _report("合成-单边上涨", result_up)
    assert result_up["metrics"]["overall"]["n_trades"] >= 1, "单边上涨应产生买入"
    assert result_up["metrics"]["overall"]["total_return"] > 0.0, "单边上涨总收益应为正"
    print("  ✔ 有成交且总收益为正\n")


def check_cached_real() -> None:
    """场景 C：若本地有真实行情缓存，用真实数据再跑一遍（无缓存则跳过）。"""
    cache_dir = Path(__file__).resolve().parent.parent / "var" / "market" / "cn_stock"
    files = sorted(cache_dir.glob("*.parquet")) if cache_dir.is_dir() else []
    if not files:
        print("[真实缓存] 未找到 var/market/cn_stock/*.parquet，跳过\n")
        return
    for f in files:
        df = pd.read_parquet(f)
        result = run_event_backtest(
            df, generate_positions, CN_STOCK_RULES, initial_capital=INITIAL_CAPITAL,
        )
        _report(f"真实缓存-{f.stem}", result)
        assert result["metrics"]["overall"]["n_trades"] >= 1, \
            f"{f.name} 上双均线应产生成交（这是零成交事故的回归校验）"
        assert result["metrics"]["overall"]["total_return"] != 0.0, "真实数据总收益不应为 0"
        print("  ✔ 真实数据有成交、总收益非零\n")


def main() -> int:
    print("=" * 78)
    print("QuantSentinel 硬编码双均线（5/20）直跑校验")
    print("=" * 78)
    check_synthetic()
    check_cached_real()
    print("全部校验通过 ✔")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
