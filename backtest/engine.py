"""自研事件驱动日频回测引擎（仅依赖 pandas/numpy，可在沙箱内独立运行）。

硬约束 5 的落地清单：
1. **滑点**：成交价按不利方向偏移（买价 ×(1+s)、卖价 ×(1-s)）；
2. **手续费**：佣金（费率 + 最低佣金）+ 印花税（买/卖分开计）；
3. **涨跌停**：成交开盘价触及涨停（买入）或跌停（卖出）时视为无法成交；
4. **停牌**：``suspended=True`` 的交易日禁止一切成交，净值照常记账；
5. **T+1**：显式记录最近买入日，当日买入当日禁止卖出（日频「信号次日执行」
   结构本身即满足 T+1，此处为防御性双保险）；
6. **样本外区间**：按 ``train_ratio`` 切分，样本内/外指标分别输出，供过拟合审计。

信号-执行分离（防未来函数的结构性保障）：
    策略函数在 t 日收盘后输出目标仓位 ``target[t]``，引擎在 t+1 日开盘执行 ——
    策略代码在结构上不可能用到未来数据成交（残留的越权取数由 Step 5 红队审计）。

记账模型（现金账户简化口径）：
- 多头：``NAV = cash + shares × close``；
- 空头（``allow_short`` 市场）：``shares < 0``，``NAV = cash + shares × close``（负市值），
  目标仓位幅值上限 = ``1 / margin_rate``（名义杠杆上限）；
- 期货逐日保证金追缴/强平暂未实现（Step 2 后增强），当前以杠杆上限近似。
"""

from __future__ import annotations

import math
from typing import Callable

import numpy as np
import pandas as pd

from backtest.market_rules import MarketRules
from backtest.metrics import compute_metrics

#: 策略函数签名：输入标准 OHLCV 全量 DataFrame，输出逐日目标仓位序列（index 与 df 对齐）
PositionFn = Callable[[pd.DataFrame], pd.Series]


#: 再平衡容差：目标占比与当前占比差异低于该阈值时不交易（贴近实盘的 rebalance band）
REBALANCE_TOL = 0.01


def _align_target(raw: object, df: pd.DataFrame) -> pd.Series:
    """把策略输出按**行序**对齐到 ``df.date``（返回索引类型无关）。

    历史 bug（2026-11 零成交事故）：策略返回以 ``df.index``（RangeIndex）为索引的
    ``Series`` 时，旧实现 ``target.reindex(df["date"])`` 会因索引类型不匹配而**全量
    落空**，再经 ``ffill().fillna(0.0)`` 变成全程零仓位 —— 回测「成功」但零成交、
    净值恒等于初始资金，且无任何报错。

    因此这里统一按位置取值、再挂 ``df.date`` 索引，并强制长度一致：
    - 兼容 ``RangeIndex`` / ``df.date`` / 任意索引的 ``Series``；
    - 兼容 ``numpy`` 数组（便于策略简化返回）；
    - 长度不符直接报错，杜绝静默错位。
    """
    if isinstance(raw, pd.Series):
        values = raw.to_numpy(dtype=float)
    else:
        values = np.asarray(raw, dtype=float)
    if values.ndim != 1 or len(values) != len(df):
        raise ValueError(
            f"策略输出 shape={values.shape} 与 K 线数 {len(df)} 不一致，无法对齐"
        )
    target = pd.Series(values, index=pd.Index(df["date"]), dtype=float)
    return target.ffill().fillna(0.0)


def run_event_backtest(
    df: pd.DataFrame,
    position_fn: PositionFn,
    rules: MarketRules,
    initial_capital: float = 1_000_000.0,
    train_ratio: float = 0.7,
    periods_per_year: int = 252,
) -> dict:
    """执行事件驱动日频回测。

    Args:
        df: 标准 OHLCV 数据（data.adapters.base schema，按 date 升序）。
        position_fn: 策略函数，输出与 ``df.date`` 对齐的目标仓位（1=满仓多头，
            0=空仓，-1=满仓空头；幅值受 1/margin_rate 限幅）。
        rules: 市场交易规则（frozen MarketRules）。
        initial_capital: 初始资金。
        train_ratio: 样本内占比（样本外 = 1 - train_ratio，硬约束 5）。
        periods_per_year: 年化因子（常规市场 252，加密货币 365）。

    Returns:
        含 equity_curve / trades / metrics / out_sample_start / signal_nonzero_days
        的字典（纯 JSON 可序列化，宿主侧再经 BacktestResult schema 校验）。

    Raises:
        ValueError: 数据行数不足或策略输出与日历不对齐。
    """
    if len(df) < 5:
        raise ValueError(f"回测至少需要 5 根 K 线，收到 {len(df)} 根")
    if not isinstance(df.get("date"), pd.Series):
        raise ValueError("输入 df 必须包含标准列 date（见 data.adapters.base schema）")

    # ---- 策略信号：t 日收盘后确定，t+1 执行 ----
    target = _align_target(position_fn(df), df)
    max_leverage = 1.0 / rules.margin_rate if rules.margin_rate > 0 else 1.0
    target = target.clip(-max_leverage, max_leverage)
    if not rules.allow_short:
        target = target.clip(lower=0.0)  # 不允许做空的市场：负目标仓位一律压平为 0

    # 诊断：策略目标仓位非零的交易日数（0 说明信号全空，便于定位「零成交」类问题）
    n_signal_days = int((target != 0).sum())

    dates = df["date"].tolist()
    opens = df["open"].to_numpy(dtype=float)
    closes = df["close"].to_numpy(dtype=float)
    suspended = df["suspended"].to_numpy(dtype=bool)
    limit_up = df["limit_up"].to_numpy(dtype=float)
    limit_down = df["limit_down"].to_numpy(dtype=float)

    # ---- 逐日事件循环 ----
    cash = float(initial_capital)
    shares = 0.0            # 净持仓（负值为空头）
    avg_cost = 0.0          # 持仓平均成本（按当前方向维护）
    last_buy_date: str | None = None  # T+1 防御检查用
    nav_list: list[float] = []
    trades: list[dict] = []
    total_cost = 0.0

    def _execute(delta: float, i: int) -> None:
        """按方向执行一笔成交（含成本/滑点/涨跌停/T+1 检查）。"""
        nonlocal cash, shares, avg_cost, last_buy_date, total_cost
        o = opens[i]
        date_str = dates[i].strftime("%Y-%m-%d")
        unit = float(rules.min_trade_unit)

        if delta > 0:
            # 买入（多头加仓或空头平仓）：滑点统一按不利方向（买价上偏）
            price_eff = o * (1 + rules.slippage_rate)
            qty = delta if unit == 0 else math.floor(delta / unit) * unit
            if qty <= 0:
                return
            # 现金约束：含成本预留的可负担数量（防止因手续费/滑点导致现金穿仓）
            affordable = cash / (price_eff * (1 + rules.commission_rate + rules.stamp_duty_buy))
            qty = min(qty, affordable if unit == 0 else math.floor(affordable / unit) * unit)
            if qty <= 0:
                return
            amount = qty * price_eff
            cost = max(amount * rules.commission_rate, rules.commission_min) \
                + amount * rules.stamp_duty_buy
            cash -= amount + cost
            total_cost += cost
            if shares < 0:  # 平空：已实现盈亏 = (开空均价 - 平空价) × 数量
                pnl = (avg_cost - price_eff) * qty
                new_shares = shares + qty
                avg_cost = 0.0 if new_shares == 0 else avg_cost
            else:           # 加多
                pnl = 0.0
                avg_cost = (avg_cost * shares + amount) / (shares + qty)
                last_buy_date = date_str  # T+1：记录买入日
            shares += qty
            trades.append({
                "date": date_str, "side": "buy", "shares": qty,
                "price": round(price_eff, 6), "amount": round(amount, 2),
                "cost": round(cost, 2), "pnl": round(pnl, 2),
                "position_after": shares,
            })
        else:
            # 卖出（多头减仓或空头开仓）：滑点统一按不利方向（卖价下偏）
            if rules.t_plus_1 and last_buy_date == date_str:
                return  # T+1：当日买入当日禁止卖出（防御性检查）
            price_eff = o * (1 - rules.slippage_rate)
            qty = -delta if unit == 0 else math.floor(-delta / unit) * unit
            if qty <= 0:
                return
            # 做空权限防御：不允许做空的市场，卖出数量不得超过当前多头持仓
            if not rules.allow_short:
                qty = min(qty, max(shares, 0.0))
                if qty <= 0:
                    return
            amount = qty * price_eff
            cost = max(amount * rules.commission_rate, rules.commission_min) \
                + amount * rules.stamp_duty_sell
            cash += amount - cost
            total_cost += cost
            if shares > 0:  # 卖出多头：已实现盈亏 = (卖价 - 持仓均价) × 数量
                pnl = (price_eff - avg_cost) * qty
                new_shares = shares - qty
                avg_cost = 0.0 if new_shares == 0 else avg_cost
            else:           # 开空/加空
                pnl = 0.0
                avg_cost = (avg_cost * (-shares) + amount) / ((-shares) + qty)
            shares -= qty
            trades.append({
                "date": date_str, "side": "sell", "shares": qty,
                "price": round(price_eff, 6), "amount": round(amount, 2),
                "cost": round(cost, 2), "pnl": round(pnl, 2),
                "position_after": shares,
            })

    for i in range(1, len(df)):
        date = dates[i]
        o = opens[i]
        tgt = float(target.iloc[i - 1])  # 用 t-1 日信号（即 t 日收盘后产出）

        # 停牌禁止成交；开盘价缺失同样跳过
        tradable = (not suspended[i]) and not math.isnan(o)
        if tradable:
            equity_now = cash + shares * o
            raw_shares = tgt * equity_now / o
            unit = float(rules.min_trade_unit)
            if unit > 0:
                # 按可执行粒度逼近目标：买入方向 floor、卖出方向 ceil。
                # 防止「高股价 + 大一手」场景（如茅台一手 15 万 >> 1% 容差）中
                # 取整粒度远超容差，导致目标永远未达成而每日过度调仓。
                desired_shares = (
                    math.floor(raw_shares / unit) * unit if raw_shares >= shares
                    else math.ceil(raw_shares / unit) * unit
                )
            else:
                desired_shares = raw_shares

            # 涨跌停约束：触及涨停买不进 / 触及跌停卖不出
            buy_blocked = sell_blocked = False
            if rules.has_price_limit:
                lu, ld = limit_up[i], limit_down[i]
                if not math.isnan(lu) and o >= lu:
                    buy_blocked = True
                if not math.isnan(ld) and o <= ld:
                    sell_blocked = True

            delta = desired_shares - shares
            # 再平衡容差：目标占比变化过小不交易（防满仓持有被价格微动触发无意义调仓）
            rebalance_needed = abs(delta * o) > equity_now * REBALANCE_TOL
            # 仓位方向翻转时拆两笔：先清仓到 0，再反向建仓。
            # 注意：first 的金额必须用「执行前的旧持仓」计算，且第二笔 = delta - first，
            # 否则第一笔执行会更新 nonlocal shares，导致第二笔金额翻倍（历史 bug）。
            if rebalance_needed:
                if delta > 0 and buy_blocked:
                    pass
                elif delta < 0 and sell_blocked:
                    pass
                elif delta > 0 and shares < 0:
                    old = shares                              # 旧持仓（负值）
                    first = min(-old, delta)                  # 平空部分（正数）
                    _execute(first, i)
                    _execute(delta - first, i)                # 剩余建多部分
                elif delta < 0 and shares > 0:
                    old = shares                              # 旧持仓（正值）
                    first = max(-old, delta)                  # 平多部分（负数）
                    _execute(first, i)
                    _execute(delta - first, i)                # 剩余开空部分
                else:
                    _execute(delta, i)

        # 逐日记账：停牌/未交易日净值照常记录（持仓以收盘价估值）
        nav_list.append(cash + shares * closes[i])

    # ---- 样本内/外切分与指标 ----
    nav = pd.Series(nav_list, index=pd.DatetimeIndex(dates[1:]), name="nav")
    split_idx = max(1, int(len(nav) * train_ratio))
    out_sample_start = nav.index[split_idx].strftime("%Y-%m-%d")

    # 胜率以「卖出/平仓」笔为样本（买入开仓笔的 pnl 恒为 0，不参与统计）；
    # n_trades 则统计全部成交（买+卖），避免买入持有到末期被误报为零成交。
    sell_trades = [t for t in trades if t["side"] == "sell"]
    pnl_in = [t["pnl"] for t in sell_trades if t["date"] < out_sample_start]
    pnl_out = [t["pnl"] for t in sell_trades if t["date"] >= out_sample_start]
    n_trades_in = sum(1 for t in trades if t["date"] < out_sample_start)
    n_trades_out = len(trades) - n_trades_in

    metrics = {
        "overall": compute_metrics(
            nav, [t["pnl"] for t in sell_trades], periods_per_year, n_trades=len(trades)
        ),
        "in_sample": compute_metrics(
            nav.iloc[:split_idx], pnl_in, periods_per_year, n_trades=n_trades_in
        ),
        "out_sample": compute_metrics(
            nav.iloc[split_idx:], pnl_out, periods_per_year, n_trades=n_trades_out
        ),
    }

    return {
        "period_start": dates[0].strftime("%Y-%m-%d"),
        "period_end": dates[-1].strftime("%Y-%m-%d"),
        "initial_capital": float(initial_capital),
        "final_equity": float(nav.iloc[-1]),
        "total_cost": round(total_cost, 2),
        "out_sample_start": out_sample_start,
        "signal_nonzero_days": n_signal_days,
        "equity_curve": {
            "dates": [d.strftime("%Y-%m-%d") for d in nav.index],
            "nav": [round(float(v), 6) for v in nav.to_numpy()],
        },
        "trades": trades,
        "metrics": metrics,
        "rules": rules.dump(),
    }
