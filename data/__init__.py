"""data 子包：多市场数据源适配器、本地缓存（DuckDB/Parquet）、股票池。

随 Step 2 交付；适配器按市场划分（adapters/），
统一输出 OHLCV Parquet schema（见 backtest/market_rules.py 模块注释）。
"""

__version__ = "0.2.0"
