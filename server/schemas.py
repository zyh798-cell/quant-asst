"""接口层 DTO：请求 / 响应 / 阶段产物结构。

字段与 ``core/schemas.py`` 的业务 schema 对齐，但只做**传输层裁剪**：

- 不携带任何密钥（密钥由 LiteLLM 从进程环境变量读取，绝不进响应）；
- 阶段产物直接承载各业务 schema 的 ``model_dump()``；
- 任务状态机：``pending -> running -> stage_done -> completed``，异常为 ``failed``。
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ---------------------------------------------------------------------------
# 字面量类型（与前端 src/types/api.ts 一一对应）
# ---------------------------------------------------------------------------

#: 阶段标识
StageId = Literal["parse", "backtest", "debate", "audit", "risk", "report"]

#: 任务级状态机
AnalysisStatus = Literal["pending", "running", "stage_done", "failed", "completed"]

#: 阶段级状态
StageStatus = Literal["pending", "running", "done", "failed", "skipped"]

#: 运行模式
RunMode = Literal["mock", "real"]

#: 沙箱模式
SandboxMode = Literal["local", "docker"]

#: 报告格式
ReportFormat = Literal["md", "html"]

#: 市场别名 -> 枚举值（口径与 ``core.markets._MARKET_ALIASES`` 保持一致）
_MARKET_ALIASES: dict[str, str] = {
    "cn": "cn_stock",
    "a": "cn_stock",
    "cn_stock": "cn_stock",
    "us": "us_stock",
    "us_stock": "us_stock",
    "hk": "hk_stock",
    "hk_stock": "hk_stock",
    "futures": "futures",
    "fu": "futures",
    "crypto": "crypto",
    "cc": "crypto",
}


# ---------------------------------------------------------------------------
# 请求
# ---------------------------------------------------------------------------


class AnalysisCreateRequest(BaseModel):
    """创建分析任务的请求体。"""

    model_config = ConfigDict(extra="forbid")

    strategy: str = Field(
        min_length=1,
        max_length=4000,
        description="自然语言策略描述（必填）",
    )
    symbol: str = Field(
        default="",
        max_length=64,
        description="标的（如 cn:600519）；留空由解析阶段推断",
    )
    market: str = Field(
        default="cn_stock",
        description="市场：cn_stock | us_stock | hk_stock | futures | crypto（接受 cn 等别名）",
    )
    period_start: str = Field(default="", description="回测起始日 YYYY-MM-DD；留空由解析阶段推断")
    period_end: str = Field(default="", description="回测结束日 YYYY-MM-DD")
    mode: RunMode = Field(default="mock", description="运行模式：mock 离线 | real 真实 LLM")
    sandbox: SandboxMode = Field(default="local", description="回测沙箱：local | docker")
    debate_rounds: int = Field(default=3, ge=1, le=3, description="最大辩论轮次（1~3）")
    risk_threshold: str = Field(
        default="high", description="风险门控阈值：high（默认）| medium（收紧）"
    )
    initial_capital: float = Field(default=1_000_000.0, gt=0, description="初始资金")

    @field_validator("market")
    @classmethod
    def _norm_market(cls, v: str) -> str:
        key = (v or "").strip().lower()
        if key not in _MARKET_ALIASES:
            raise ValueError(f"不支持的市场：{v!r}（可选：cn_stock/us_stock/hk_stock/futures/crypto）")
        return _MARKET_ALIASES[key]

    @field_validator("symbol")
    @classmethod
    def _check_symbol(cls, v: str) -> str:
        v = (v or "").strip()
        if v and ":" not in v:
            raise ValueError(f"symbol 须为 <market>:<code> 格式（如 cn:600519），收到：{v!r}")
        return v

    @field_validator("period_start", "period_end")
    @classmethod
    def _check_date(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            return ""
        try:
            date.fromisoformat(v)
        except ValueError as exc:
            raise ValueError(f"日期须为 YYYY-MM-DD 格式，收到：{v!r}") from exc
        return v

    @field_validator("risk_threshold")
    @classmethod
    def _check_threshold(cls, v: str) -> str:
        v = (v or "").strip().lower()
        if v not in ("high", "medium"):
            raise ValueError(f"risk_threshold 仅支持 high | medium，收到：{v!r}")
        return v


# ---------------------------------------------------------------------------
# 响应
# ---------------------------------------------------------------------------


class StageArtifact(BaseModel):
    """单阶段产物：结构化输出 + 进度元数据。

    ``data`` 的键随阶段而异，与 ``core/schemas.py`` 对应：

    - ``parse``   -> ``HypothesisSpec.model_dump()``
    - ``backtest``-> ``BacktestResult.model_dump()`` + ``sandbox_warnings``
    - ``debate``  -> ``DebateOutcome.model_dump()``
    - ``audit``   -> ``AuditReport.model_dump()``
    - ``risk``    -> ``{"risk_gate": RiskGate, "final_report": FinalAnalysisReport}``
    - ``report``  -> ``{"report": ReportRef}``
    """

    model_config = ConfigDict(extra="forbid")

    stage: StageId
    status: StageStatus
    started_at: datetime | None = None
    finished_at: datetime | None = None
    summary: str = ""
    data: dict[str, Any] = Field(default_factory=dict)


class ReportRef(BaseModel):
    """报告引用：落盘位置与可用格式。"""

    model_config = ConfigDict(extra="forbid")

    markdown_path: str | None = None
    html_path: str | None = None
    json_path: str | None = None
    available_formats: list[ReportFormat] = Field(default_factory=list)


class AnalysisRequestEcho(BaseModel):
    """请求回显（不含任何密钥）。"""

    model_config = ConfigDict(extra="forbid")

    strategy: str
    symbol: str
    market: str
    period_start: str
    period_end: str
    mode: RunMode
    sandbox: SandboxMode
    debate_rounds: int
    risk_threshold: str
    initial_capital: float


class AnalysisStatusResponse(BaseModel):
    """任务状态与已完成阶段的产物（前端轮询载体）。"""

    model_config = ConfigDict(extra="forbid")

    id: str
    status: AnalysisStatus
    mode: RunMode
    sandbox: SandboxMode
    created_at: datetime
    updated_at: datetime
    current_stage: StageId | None = None
    stages: list[StageArtifact] = Field(default_factory=list)
    error: str | None = None
    notice: str | None = None
    report: ReportRef | None = None
    request: AnalysisRequestEcho | None = None
