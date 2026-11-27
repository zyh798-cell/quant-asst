"""A股日线适配器（AkShare / 东财源）。

- 价格：前复权 qfq（回测口径，避免除权跳空导致的假金叉/死叉）。美股无复权概念，
  不使用该口径；两市场口径差异通过 ``ADJUST`` 声明，缓存层据此隔离。
- 停牌：以交易日历补齐缺失日并标记 suspended=True；
- 涨跌停：前收 × 板块系数（主板 10%、创业板 300/301 与科创板 688 为 20%、
  北交所 8 开头/4 开头为 30%）；ST 股 5% 需名称数据，暂不区分（研究口径近似）。
  边界取保守方向（涨停上取整、跌停下取整），避免 qfq 舍入误差把涨停误判为可买。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from core.markets import Symbol
from data.adapters.base import ADJUST_QFQ, MarketDataAdapter


def _limit_pct(code: str) -> float:
    """按 A 股板块推断涨跌停幅度（近似口径，见模块 docstring）。"""
    if code.startswith(("300", "301", "688")):
        return 0.20  # 创业板 / 科创板
    if code.startswith(("43", "83", "87", "88", "92")):
        return 0.30  # 北交所
    return 0.10      # 沪深主板


class CnStockAdapter(MarketDataAdapter):
    """A 股日线适配器：ak.stock_zh_a_hist（东财源，前复权）。"""

    #: A 股回测统一使用前复权；该值同时是缓存文件名中的口径段。
    ADJUST = ADJUST_QFQ

    def fetch_daily(self, symbol: Symbol, start: str, end: str) -> pd.DataFrame:
        """抓取 A 股日线并归一为标准 OHLCV schema（东财主源，限流时自动回退新浪源）。"""
        import akshare as ak  # 延迟导入：加快包加载、隔离可选依赖

        code = symbol.code
        # A 股代码为 6 位数字，忽略用户传入的交易所前缀（如 sh600519）
        code = code.replace("SH", "").replace("SZ", "").replace("BJ", "")
        start = start.replace("-", "")
        end = end.replace("-", "")

        # ---- 抓取：东财主源 -> 新浪源回退（东财 push2 有 IP 限流）----
        try:
            df = self._fetch_em(ak, code, start, end)
        except Exception as exc:  # noqa: BLE001 —— 限流/网络异常统一回退新浪
            if type(exc).__name__ in ("Push2RateLimitError", "ConnectionError",
                                      "ReadTimeout", "HTTPError"):
                df = self._fetch_sina(ak, code, start, end)
            else:
                raise
        if df is None or df.empty:
            raise ValueError(f"A 股 {code} 在 {start}-{end} 无数据（检查代码/区间）")

        # ---- 交易日历补停牌 ----
        cal = ak.calendar_trade_date_hist_sina()
        trading_dates = pd.to_datetime(pd.DataFrame(cal)["trade_date"])
        trading_dates = trading_dates[
            (trading_dates >= df["date"].min()) & (trading_dates <= df["date"].max())
        ]
        df = self._fill_missing_trading_days(df, pd.DatetimeIndex(trading_dates))

        # ---- 涨跌停价：前收 × 板块系数，按 A 股报价精度取保守边界 ----
        # 用前复权价推算的涨停/跌停价只是近似值；若做四舍五入，可能比真实边界高出
        # 一个最小报价单位，导致回测把「一字涨停」误判为可买入（假成交）。
        # 因此向上/向下取整到 0.01，使拦截偏保守：宁可漏拦，不可误放。
        pct = _limit_pct(code)
        prev_close = df["close"].shift(1)
        tick = 0.01
        df["limit_up"] = np.ceil(prev_close * (1 + pct) / tick) * tick
        df["limit_down"] = np.floor(prev_close * (1 - pct) / tick) * tick
        df.loc[df["suspended"], "limit_up"] = df["limit_up"].ffill()
        df.loc[df["suspended"], "limit_down"] = df["limit_down"].ffill()
        df.loc[0, ["limit_up", "limit_down"]] = float("nan")  # 首日无前收
        return self._normalize(df)

    # ---- 数据源实现 ----

    def _fetch_em(self, ak, code: str, start: str, end: str) -> pd.DataFrame:
        """东方财富源（前复权，列名为中文）。"""
        raw = ak.stock_zh_a_hist_em(
            symbol=code, period="daily",
            start_date=start, end_date=end, adjust=self.ADJUST,
        )
        return pd.DataFrame({
            "date": pd.to_datetime(raw["日期"]),
            "open": raw["开盘"].astype(float),
            "high": raw["最高"].astype(float),
            "low": raw["最低"].astype(float),
            "close": raw["收盘"].astype(float),
            "volume": raw["成交量"].astype(float),
            "amount": raw["成交额"].astype(float),
            "suspended": False,
        })

    def _fetch_sina(self, ak, code: str, start: str, end: str) -> pd.DataFrame:
        """新浪源回退（全量返回后本地过滤日期区间）。"""
        if code.startswith("6"):
            sina_code = f"sh{code}"
        elif code.startswith(("0", "3")):
            sina_code = f"sz{code}"
        else:
            raise ValueError(f"新浪源暂不支持代码 {code}（北交所请稍后重试东财源）")
        raw = ak.stock_zh_a_daily_sina(symbol=sina_code, adjust=self.ADJUST)
        df = pd.DataFrame({
            "date": pd.to_datetime(raw["date"]),
            "open": raw["open"].astype(float),
            "high": raw["high"].astype(float),
            "low": raw["low"].astype(float),
            "close": raw["close"].astype(float),
            "volume": raw["volume"].astype(float),
            "amount": raw["amount"].astype(float) if "amount" in raw else float("nan"),
            "suspended": False,
        })
        start_ts = pd.Timestamp(start)
        end_ts = pd.Timestamp(end)
        return df[(df["date"] >= start_ts) & (df["date"] <= end_ts)].reset_index(drop=True)
