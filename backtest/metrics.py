"""绩效指标计算：收益、年化、最大回撤、夏普、胜率。

全部函数输入为净值/收益序列，输出为纯数值 —— 结果由引擎打包进
BacktestResult（Pydantic），Agent 只能引用不得自造（硬约束 1）。
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def total_return(nav: pd.Series) -> float:
    """区间总收益率。"""
    if len(nav) < 2 or nav.iloc[0] == 0:
        return 0.0
    return float(nav.iloc[-1] / nav.iloc[0] - 1)


def annual_return(nav: pd.Series) -> float | None:
    """年化收益率：按首尾日期的自然日数几何外推（不依赖交易日历）。"""
    if len(nav) < 2 or nav.iloc[0] <= 0:
        return None
    days = (nav.index[-1] - nav.index[0]).days
    if days <= 0:
        return None
    return float((nav.iloc[-1] / nav.iloc[0]) ** (365.25 / days) - 1)


def max_drawdown(nav: pd.Series) -> float:
    """最大回撤（负值）：min(nav / 累计峰值 - 1)。"""
    if len(nav) < 2:
        return 0.0
    peak = nav.cummax()
    dd = nav / peak - 1
    return float(dd.min())


def sharpe(nav: pd.Series, periods_per_year: int = 252) -> float | None:
    """夏普比率（无风险利率 0）：日收益均值 / 日收益标准差 × 年化开方。

    periods_per_year：常规市场 252；加密货币 7x24 传 365。
    """
    ret = nav.pct_change().dropna()
    if len(ret) < 2 or float(ret.std(ddof=1)) == 0.0:
        return None
    return float(ret.mean() / ret.std(ddof=1) * np.sqrt(periods_per_year))


def win_rate(pnl_list: list[float]) -> float | None:
    """按笔胜率：盈利笔数 / 总笔数（0 笔成交返回 None）。"""
    if not pnl_list:
        return None
    wins = sum(1 for p in pnl_list if p > 0)
    return wins / len(pnl_list)


def compute_metrics(
    nav: pd.Series,
    trades_pnl: list[float],
    periods_per_year: int = 252,
    n_trades: int | None = None,
) -> dict[str, float | int | None]:
    """一次性计算全组指标，输出与 core.schemas.BacktestMetrics 字段对齐。

    Args:
        nav: 净值序列。
        trades_pnl: **平仓（卖出）笔**的已实现盈亏，用于胜率统计。
        periods_per_year: 年化因子。
        n_trades: 成交总笔数（买+卖）；缺省回退为 ``len(trades_pnl)``。
            显式传入是为了让 ``n_trades`` 表示「成交笔数」而非「平仓笔数」——
            买入后持有到区间结束的策略不应被误报为零成交。
    """
    return {
        "total_return": total_return(nav),
        "annual_return": annual_return(nav),
        "max_drawdown": max_drawdown(nav),
        "sharpe": sharpe(nav, periods_per_year),
        "win_rate": win_rate(trades_pnl),
        "n_trades": len(trades_pnl) if n_trades is None else int(n_trades),
        "n_days": len(nav),
    }
