"""QuantAsst 全局配置。

- 基于 pydantic-settings，所有配置从环境变量读取（前缀 ``QUANT_ASST_``）。
- LLM 密钥（DEEPSEEK_API_KEY / OPENAI_API_KEY 等）**不进入**本对象：
  由 LiteLLM 按其官方约定直接从进程环境变量读取，
  避免密钥随 trajectory 落盘或出现在日志中。
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from core.markets import Market


class Settings(BaseSettings):
    """全局配置对象（进程级单例见 :func:`get_settings`）。"""

    model_config = SettingsConfigDict(
        env_prefix="QUANT_ASST_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # .env 中的无关变量直接忽略
    )

    # ---- LLM ----
    llm_model: str = "deepseek/deepseek-chat"  # LiteLLM 格式：provider/model
    llm_temperature: float = 0.2
    llm_max_retries: int = 1  # 硬约束 2：结构化输出格式错误自动重试 1 次

    # ---- 市场 ----
    default_market: Market = Market.CN_STOCK

    # ---- 回测成本（硬约束 5；各市场完整规则见 backtest/market_rules.py）----
    trade_cost_rate: float = 0.0015  # 双边各 0.15%（含佣金/税费总口径）
    slippage_rate: float = 0.001     # 滑点 0.1%
    train_test_split: float = 0.7    # 样本内/外切分（样本外 30%，硬约束 5）

    # ---- Docker 沙箱（硬约束 3）----
    sandbox_image: str = "quant-asst-sandbox:latest"
    sandbox_timeout_seconds: int = 120
    sandbox_memory_limit: str = "1g"
    sandbox_network_disabled: bool = True  # 沙箱容器禁网
    sandbox_cpu_quota: float = 1.0

    # ---- Qdrant 向量库 ----
    qdrant_mode: str = "local"  # local：进程内模式，零外部依赖
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "quant_asst_mem"
    embedding_model: str = "BAAI/bge-small-zh-v1.5"  # fastembed 中文向量化模型

    # ---- 运行时根目录（var/ 不入库、不打包；子目录由 var_dir 派生）----
    var_dir: Path = Path("var")

    @property
    def trajectory_dir(self) -> Path:
        """JSONL 运行轨迹目录（硬约束 4）。"""
        return self.var_dir / "trajectories"

    @property
    def market_cache_dir(self) -> Path:
        """行情 Parquet/DuckDB 缓存目录。"""
        return self.var_dir / "market"

    @property
    def report_dir(self) -> Path:
        """报告输出目录。"""
        return self.var_dir / "reports"

    @property
    def sandbox_workdir(self) -> Path:
        """沙箱临时工作区目录。"""
        return self.var_dir / "sandbox"

    @property
    def output_dir(self) -> Path:
        """交付物输出根目录（辩论 Markdown 报告等 Demo 产物）。"""
        return Path("output")

    @property
    def debate_report_dir(self) -> Path:
        """辩论 Markdown 报告目录：``./output/debate_reports/``（自动创建）。"""
        d = self.output_dir / "debate_reports"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def audit_dir(self) -> Path:
        """红队审计/最终分析报告目录：``./output/audit/``（自动创建，Step 5）。"""
        d = self.output_dir / "audit"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def ensure_dirs(self) -> None:
        """确保全部运行时目录存在（幂等）。"""
        for d in (
            self.var_dir,
            self.trajectory_dir,
            self.market_cache_dir,
            self.report_dir,
            self.sandbox_workdir,
        ):
            d.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """进程级单例配置；首次调用时创建运行时目录。"""
    settings = Settings()
    settings.ensure_dirs()
    return settings
