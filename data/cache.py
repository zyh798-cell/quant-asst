"""本地行情缓存层：Parquet 存储 + DuckDB 查询。

- 缓存文件：var/market/<market>/<code>__<start>__<end>[__<adjust>].parquet
  例：``600519__20240101__20261128__qfq.parquet``（A 股前复权）、
  ``AAPL__20240101__20261128.parquet``（美股实际成交价，无口径段）。
- 口径隔离：复权口径由适配器的 ``ADJUST`` 声明并写入文件名，不同口径永不混入
  同一文件；旧版本的无口径缓存文件不再命中，自动失效重建。
- 命中策略：同 symbol + 同区间 + 同口径的完整缓存文件存在即直接读（研究批处理友好）；
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


def _cache_path(
    settings: Settings,
    symbol: Symbol,
    start: str,
    end: str,
    adjust: str = "",
) -> Path:
    """构造缓存文件路径（start/end 统一为 YYYYMMDD 便于跨格式命中）。

    Args:
        adjust: 复权口径标识（适配器 ``ADJUST``）。非空时追加为文件名尾段，
            使 qfq / 不复权数据各自独立成文件，杜绝串味。
    """
    s = start.replace("-", "")
    e = end.replace("-", "")
    suffix = f"__{adjust}" if adjust else ""
    return (
        settings.market_cache_dir
        / symbol.market.value
        / f"{symbol.code}__{s}__{e}{suffix}.parquet"
    )


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
    adapter = get_adapter(symbol.market, crypto_exchange=crypto_exchange)
    path = _cache_path(settings, symbol, start, end, getattr(adapter, "ADJUST", ""))
    if not force_refresh and path.exists():
        return pd.read_parquet(path)

    df = adapter.fetch_daily(symbol, start, end)
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
