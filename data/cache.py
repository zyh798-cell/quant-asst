"""本地行情缓存层：Parquet 存储 + DuckDB 查询。

- 缓存文件：var/market/<market>/<code>__<start>__<end>.parquet
- 命中策略：同 symbol + 同区间的完整缓存文件存在即直接读（研究批处理友好）；
  force_refresh=True 强制重新抓取。
- DuckDB：为 Parquet 提供本地 SQL 查询入口（技术栈要求的落地形式）。
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from core.config import Settings
from core.markets import Market, Symbol
from data.adapters import get_adapter


def _cache_path(settings: Settings, symbol: Symbol, start: str, end: str) -> Path:
    """构造缓存文件路径（start/end 统一为 YYYYMMDD 便于跨格式命中）。"""
    s = start.replace("-", "")
    e = end.replace("-", "")
    return settings.market_cache_dir / symbol.market.value / f"{symbol.code}__{s}__{e}.parquet"


def get_daily(
    symbol: Symbol,
    start: str,
    end: str,
    settings: Settings,
    force_refresh: bool = False,
    crypto_exchange: str = "binance",
) -> pd.DataFrame:
    """取日线数据：优先读缓存，未命中则经适配器抓取并写缓存。

    Args:
        symbol: 统一 symbol。
        start / end: 日期（YYYY-MM-DD 或 YYYYMMDD 均可）。
        settings: 全局配置。
        force_refresh: True 时忽略缓存强制抓取。
        crypto_exchange: 加密货币交易所 id。

    Returns:
        标准 OHLCV DataFrame（见 data.adapters.base schema）。
    """
    path = _cache_path(settings, symbol, start, end)
    if not force_refresh and path.exists():
        return pd.read_parquet(path)

    df = get_adapter(symbol.market, crypto_exchange=crypto_exchange).fetch_daily(
        symbol, start, end
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    return df


def query_parquet(sql: str, settings: Settings, parquet_path: Path | None = None) -> pd.DataFrame:
    """用 DuckDB 查询 Parquet 文件（或缓存目录下全部 Parquet）。

    Args:
        sql: SQL 语句，表名占位为 ``ohlcv``（自动绑定 read_parquet）。
        settings: 全局配置。
        parquet_path: 目标 Parquet 路径；None 时扫描整个缓存目录。

    Returns:
        查询结果 DataFrame。
    """
    target = parquet_path or (settings.market_cache_dir / "**" / "*.parquet")
    bound = f"read_parquet('{target.as_posix()}')"
    con = duckdb.connect()
    try:
        return con.execute(sql.replace("ohlcv", bound)).fetchdf()
    finally:
        con.close()
