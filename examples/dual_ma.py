# -*- coding: utf-8 -*-
"""示例策略 01：双均线趋势跟踪（QuantAsst 策略契约合规模板）。

本文件同时是 **LLM 生成代码的对照模板**：HypothesisAgent 的代码契约
（``agents/hypothesis.py`` 的 ``CODE_CONTRACT_SYSTEM``）要求生成结果遵守同一约定。

策略接口契约（生成代码必须遵守）：
- 函数名固定 ``generate_positions(df, params=None)``；
- 策略参数集中为模块级字典 ``PARAMS``（键为参数名，值为默认取值）；
  ``params`` 给出时按 key 覆盖 ``PARAMS``，缺失键回落默认值 —— 同一份代码
  因此被 ``cli.py optimize`` 的参数网格反复调用时无需改动任何代码；
- 输入：标准 OHLCV DataFrame（``date/open/high/low/close/volume/amount/
  suspended/limit_up/limit_down`` 列，``date`` 升序）；
- 输出：**逐行对应 df 每一行**的目标仓位 ``pd.Series``（1=满仓多，0=空仓）；
  - 返回索引可以是 ``df.index``（RangeIndex）或 ``df.date``，引擎按**行序**对齐；
  - 长度必须等于 ``len(df)``，否则引擎报错；
  - **不要**再 ``shift(1)``：信号在 t 日收盘后生成，引擎已统一在 t+1 日开盘执行。
- 红线：只允许使用截至当日的数据（t 日信号 t+1 开盘执行），引用未来数据会被
  Step 5 红队审计（未来函数检查）捕获。

历史事故（2026-11）：生成代码返回 ``df.index`` 索引的 Series，而旧引擎用
``reindex(df["date"])`` 对齐 —— 索引类型不匹配导致全量落空、被 ``fillna(0)``
吞成全程零仓位，回测「成功」但零成交、净值恒等于初始资金。现行引擎已改为
按行序对齐（``backtest.engine._align_target``），并在 ``n_trades == 0`` 时告警。
"""

import pandas as pd

# 策略参数（集中定义，便于 HypothesisAgent 生成后参数化）
PARAMS = {
    "short_window": 5,   # 短期均线窗口
    "long_window": 20,   # 长期均线窗口
}

#: 兼容旧引用（历史常量语义不变，由 PARAMS 派生）
SHORT_WINDOW = PARAMS["short_window"]
LONG_WINDOW = PARAMS["long_window"]


def generate_positions(df: pd.DataFrame, params: dict | None = None) -> pd.Series:
    """双均线：短均线在长均线上方时满仓，否则空仓（仅用历史数据，无未来函数）。

    ``close.rolling(...)`` 天然只包含当日及以前数据；显式按行序返回，
    不依赖索引类型，避免与引擎对齐方式耦合。

    Args:
        df: 标准 OHLCV DataFrame。
        params: 可选参数覆盖（``cli.py optimize`` 的网格寻优会逐组合传入）；
            缺省或缺失键一律回落模块级 ``PARAMS``。
    """
    p = {**PARAMS, **(params or {})}
    short_window = int(p["short_window"])
    long_window = int(p["long_window"])

    close = df["close"].astype(float)
    ma_short = close.rolling(short_window).mean()
    ma_long = close.rolling(long_window).mean()
    pos = (ma_short > ma_long).astype(float)
    # 逐行对齐：显式按 df 行序返回（不依赖索引类型）
    return pd.Series(pos.to_numpy(), index=df.index, dtype=float)
