"""Agent 结构化输出 Pydantic schema —— 硬约束 1/2 的载体。

- 硬约束 1：所有 LLM 输出的数字必须来自工具返回。携带财务数字的 schema
  （如 BacktestResult）由回测工具生成并序列化进 State，Agent 只能引用，
  不允许在自由文本中编造数字。
- 硬约束 2：每个 Agent 输出必须通过 schema 校验，格式错误自动重试 1 次。
- 各角色专属 schema（HypothesisSpec / DebatePosition / RiskReport /
  RedTeamReport 等）随 Step 3-6 对应 Agent 一并完善。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

#: 规范风险级别（Pydantic Literal 约束；原始值在 validator 中先归一化）
RiskLevel = Literal["low", "medium", "high", "critical"]


class StrictModel(BaseModel):
    """全部 Agent 输出 schema 的基类：禁止额外字段，保证 trajectory 可回放。"""

    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# 风险定级归一化（fail-closed）
# ---------------------------------------------------------------------------

#: 风险定级（低 -> 致命，单调递增）
RISK_LEVELS: tuple[str, ...] = ("low", "medium", "high", "critical")

#: 风险级别 -> 中文标签
RISK_LABELS_ZH: dict[str, str] = {
    "low": "低", "medium": "中", "high": "高", "critical": "致命",
}

#: 风险级别排序（用于取最高级别）
RISK_RANK: dict[str, int] = {lvl: i for i, lvl in enumerate(RISK_LEVELS, start=1)}

#: LLM 原始输出 -> 规范级别 的白名单别名表（含常见英文/中文写法）。
#: 白名单外或缺失一律按最高级 critical 处理（fail-closed），绝不回落 low。
RISK_LEVEL_ALIASES: dict[str, str] = {
    # 英文别名
    "critical": "critical", "fatal": "critical", "severe": "critical",
    "catastrophic": "critical", "blocker": "critical",
    "high": "high",
    "medium": "medium", "moderate": "medium", "mid": "medium",
    "low": "low", "minor": "low", "trivial": "low", "negligible": "low",
    # 中文别名
    "致命": "critical", "严重": "critical", "极高": "critical", "危急": "critical",
    "高": "high", "较高": "high",
    "中": "medium", "中等": "medium", "适中": "medium",
    "低": "low", "较低": "low", "轻微": "low",
}


def normalize_risk_level(raw: object) -> str:
    """把任意 LLM 输出的风险等级归一化为 ``RISK_LEVELS`` 之一（fail-closed）。

    规则（外部代码 review 要求）：
    - 白名单别名命中 -> 对应级别；
    - **白名单外、缺失、空串、非字符串** 一律返回最高级 ``"critical"``，
      并记录告警日志，绝不回落为 ``low``。

    Args:
        raw: 原始值（可能是 None / 中文 / 英文别名 / 已规范化的级别）。

    Returns:
        ``"low" | "medium" | "high" | "critical"``。
    """
    import logging

    logger = logging.getLogger("quant_asst.risk")
    if not isinstance(raw, str) or not raw.strip():
        logger.warning(
            "风险定级缺失或非法（raw=%r），按 fail-closed 处理为 critical", raw
        )
        return "critical"
    key = raw.strip().lower()
    normalized = RISK_LEVEL_ALIASES.get(key)
    if normalized is None:
        logger.warning(
            "风险定级 %r 不在白名单内，按 fail-closed 处理为 critical", raw
        )
        return "critical"
    return normalized



# ---------------------------------------------------------------------------
# 结构化策略假设（HypothesisAgent 产出，Step 3）
# ---------------------------------------------------------------------------


class HypothesisSpec(StrictModel):
    """从自然语言解析出的结构化量化假设（不含任何预测数字，硬约束 1）。"""

    strategy_name: str = Field(description="策略简短名称")
    market: str = Field(description="市场枚举值：cn_stock | us_stock | hk_stock | futures | crypto")
    symbols: list[str] = Field(
        description="标的列表，统一 <market>:<code> 格式（如 cn:600519）；Step 3 仅支持单标的"
    )
    period_start: str = Field(description="回测起始日 YYYY-MM-DD")
    period_end: str = Field(description="回测结束日 YYYY-MM-DD")
    logic_summary: str = Field(description="策略逻辑一段话")
    entry_rule: str = Field(description="开仓规则（可执行的自然语言描述）")
    exit_rule: str = Field(description="平仓规则（可执行的自然语言描述）")
    params: dict[str, float | int] = Field(
        default_factory=dict, description="策略参数（窗口/阈值等），不含任何预测结果"
    )
    risk_notes: str = Field(default="", description="策略主要风险点")
    assumptions: list[str] = Field(
        default_factory=list, description="默认假设清单（标的/区间为推测时必须注明）"
    )


# ---------------------------------------------------------------------------
# 回测结果（由回测工具产出，Agent 只读）
# ---------------------------------------------------------------------------


class BacktestMetrics(StrictModel):
    """单一区间的绩效指标（由 backtest.metrics 计算并落盘，禁止 Agent 自造）。"""

    total_return: float = Field(description="区间总收益率，如 0.1234 表示 +12.34%")
    annual_return: float | None = Field(default=None, description="年化收益率（按自然日推算）")
    max_drawdown: float = Field(description="最大回撤（负值，如 -0.25 表示最大回撤 25%）")
    sharpe: float | None = Field(default=None, description="夏普比率（无风险利率 0）")
    win_rate: float | None = Field(default=None, description="按笔胜率（盈利笔数/总笔数）")
    n_trades: int = Field(default=0, description="区间内成交笔数")
    n_days: int = Field(default=0, description="区间交易日数")


class BacktestResult(StrictModel):
    """完整回测结果：回测引擎产出，多空辩论/风控/红队仅引用其字段。"""

    symbol: str = Field(description="统一 symbol，如 cn:600519")
    market: str = Field(description="市场枚举值（core.markets.Market）")
    period_start: str = Field(description="回测起始日 YYYY-MM-DD")
    period_end: str = Field(description="回测结束日 YYYY-MM-DD")
    initial_capital: float = Field(description="初始资金")
    final_equity: float = Field(description="期末净值（现金+持仓市值）")
    total_cost: float = Field(description="累计交易成本（佣金+印花税+滑点）")
    out_sample_start: str = Field(description="样本外区间起始日（硬约束 5）")
    overall: BacktestMetrics = Field(description="全区间指标")
    in_sample: BacktestMetrics = Field(description="样本内指标")
    out_sample: BacktestMetrics = Field(description="样本外指标（与样本内对比审过拟合）")
    engine: str = Field(default="event_engine", description="回测引擎标识")
    rules: dict = Field(description="生效的 MarketRules dump（成本参数透明可审计）")
    signal_nonzero_days: int = Field(
        default=0,
        description="策略目标仓位非零的交易日数（诊断用：为 0 说明信号全空，回测必然零成交）",
    )
    # ---- 以下两个字段为 Step 6 可视化 HTML 报告提供数据（可选，缺省为空）----
    equity_curve: dict = Field(
        default_factory=dict,
        description="净值曲线明细：dates 日期列表 + nav 净值列表，由回测引擎产出（可选）",
    )
    trades: list[dict] = Field(
        default_factory=list,
        description="成交明细：date/side/price/shares/amount/pnl，由回测引擎产出（可选）",
    )


# ---------------------------------------------------------------------------
# 多空辩论（Step 4：Bull / Bear / Risk / Reviewer）
# ---------------------------------------------------------------------------


class ArgumentPoint(StrictModel):
    """单条论点：可核验论据 + 证据类型。

    硬约束 1 的口径：``evidence`` 只能引用**工具已返回的数据字段**或公开可查事实，
    不得写「预计收益 X%」这类由模型自造的预测数字（预测数字统一进 scenario_*）。
    """

    claim: str = Field(description="论点一句话")
    evidence: str = Field(description="支撑证据（须可核验：回测指标字段 / 公开数据 / 逻辑推导）")
    evidence_type: str = Field(
        description="证据类型：backtest_metric | public_data | logic"
    )


class BullArgument(StrictModel):
    """多头分析师输出（仅看多维度）。"""

    stance: str = Field(default="", description="观点摘要（看多，一段话）")
    points: list[ArgumentPoint] = Field(
        min_length=1, max_length=5, description="看多论点清单（1~5 条；缺省空列表供裁决兜底）"
    )
    assumptions: list[str] = Field(
        default_factory=list, description="多头假设前提（必须显式写明，供风控核验是否脱离现实）"
    )
    scenario_gain_pct: float = Field(
        default=0.0,
        description="乐观情景收益预估（%，相对区间起点；区间 -50~200）",
    )
    strategy_profit_source: str = Field(default="", description="策略收益来源分析")


class BearArgument(StrictModel):
    """空头分析师输出（仅看空维度）。"""

    stance: str = Field(default="", description="观点摘要（看空，一段话）")
    points: list[ArgumentPoint] = Field(
        min_length=1, max_length=5, description="看空论点清单（1~5 条；缺省空列表供裁决兜底）"
    )
    failure_scenarios: list[str] = Field(
        default_factory=list, description="策略失效场景 / 尾部风险清单"
    )
    scenario_drawdown_pct: float = Field(
        default=0.0,
        description="悲观情景回撤预估（正数表示回撤幅度；区间 0~80）",
    )
    historical_failure_cases: list[str] = Field(
        default_factory=list, description="历史失效案例（同类策略在何行情下失效）"
    )


class RiskFinding(StrictModel):
    """风控核验发现的问题。"""

    target_side: str = Field(description="指向方：bull | bear | both | none")
    issue: str = Field(description="问题描述")
    severity: str = Field(description="严重级别：low | medium | high")
    falsifiable: bool = Field(description="是否可证伪（不可证伪的主观猜想应被剔除）")

    @field_validator("severity", mode="before")
    @classmethod
    def _normalize_severity(cls, v: object) -> str:
        """严重级别白名单外一律按 critical 处理（fail-closed，不回落 low）。"""
        return normalize_risk_level(v)


class RiskCheckReport(StrictModel):
    """风控核验 Agent 输出（中立，不站队）。

    每个辩论轮次对「本轮多空草稿 + 此前留存论据」做一次独立校验。
    """

    stance: str = Field(default="neutral", description="固定为 neutral（风控不站队）")
    round_no: int = Field(ge=1, le=3, description="所校验的轮次号")
    data_validity: str = Field(description="数据有效性核查结论（样本量/幸存者偏差/复权口径等）")
    findings: list[RiskFinding] = Field(
        min_length=1, max_length=6, description="核验发现清单（含被剔除的无效论据）"
    )
    kept_bull_points: list[int] = Field(
        default_factory=list, description="通过校验的多头论点索引（对应 BullArgument.points 下标）"
    )
    kept_bear_points: list[int] = Field(
        default_factory=list, description="通过校验的空头论点索引（对应 BearArgument.points 下标）"
    )
    recommendation: str = Field(description="给裁决方的独立核验建议")


class StrategyRevision(StrictModel):
    """可直接送入回测引擎的策略修改建议（裁决的可执行产物）。"""

    revised_strategy_text: str = Field(
        description="修订后的策略自然语言描述（可直接作为 cli.py run 的输入）"
    )
    entry_rule: str = Field(description="修订后开仓规则")
    exit_rule: str = Field(description="修订后平仓规则")
    params: dict[str, float | int] = Field(
        default_factory=dict, description="修订后参数（窗口/阈值等）"
    )
    expected_effect: str = Field(description="预期改进效果（供回测对照验证）")


class DebateVerdict(StrictModel):
    """最终裁决 Agent 输出（汇总三方材料）。"""

    credibility_score: int = Field(
        ge=0, le=100, description="策略可信度打分（0~100）"
    )
    consensus: list[str] = Field(description="多空共识清单")
    disagreements: list[str] = Field(description="多空主要分歧清单")
    decision: str = Field(description="裁决结论：adopt | reject | revise")
    rationale: str = Field(description="裁决理由（一段话）")
    revision: StrategyRevision | None = Field(
        default=None,
        description="decision 为 revise 时必填；adopt 时可给出可选优化建议",
    )


class DebateOutcome(StrictModel):
    """辩论完整纪要（CLI ``debate`` 的结构化输出载体）。"""

    run_id: str = Field(description="本次辩论 run_id")
    symbol: str = Field(description="标的（如 cn:300750）")
    market: str = Field(description="市场枚举值")
    user_input: str = Field(description="用户原始策略描述")
    rounds: int = Field(description="实际进行的辩论轮次")
    round_transcripts: list[dict] = Field(
        default_factory=list,
        description="逐轮原文纪要：[{round, bull, bear, risk_check}]，供 Markdown 报告完整呈现",
    )
    bull_final: BullArgument = Field(description="多头最终观点（最后一轮经风控校验）")
    bear_final: BearArgument = Field(description="空头最终观点（最后一轮经风控校验）")
    risk_checks: list[RiskCheckReport] = Field(description="各轮风控核验报告")
    verdict: DebateVerdict = Field(description="最终裁决")
    revised_strategy_text: str = Field(
        description="修订后策略文本（decision=revise 时来自 revision.revised_strategy_text，否则为空串）"
    )


# ---------------------------------------------------------------------------
# 红队审计 + 风控门控（Step 5：RedTeam / RiskOfficer）
# ---------------------------------------------------------------------------

class AuditFinding(StrictModel):
    """红队审计单条发现（按风险类别 + 定级）。"""

    category: str = Field(
        description=(
            "风险类别：logic_flaw（逻辑漏洞）| overfitting（过拟合）| "
            "lookahead（未来函数）| survivorship（幸存者偏差）| "
            "liquidity_trap（流动性陷阱）| data_integrity（数据完整性）| other"
        )
    )
    title: str = Field(description="问题一句话标题")
    description: str = Field(description="问题详细描述")
    severity: RiskLevel = Field(description="风险定级：low | medium | high | critical")
    evidence: str = Field(description="支撑证据（引用回测指标字段 / 公开数据 / 逻辑推导）")
    recommendation: str = Field(description="修复或缓解建议")

    @field_validator("severity", mode="before")
    @classmethod
    def _normalize_severity(cls, v: object) -> str:
        """LLM 原始严重级别先归一化（白名单外 -> critical，fail-closed）。"""
        return normalize_risk_level(v)


class AuditReport(StrictModel):
    """红队审计意见书（独立于多空辩论，只做风险定级，不下交易结论）。"""

    symbol: str = Field(description="标的（如 cn:300750）")
    market: str = Field(description="市场枚举值")
    strategy_name: str = Field(default="", description="被审计的策略名称")
    audit_run_id: str = Field(description="本次审计 run_id")
    source_run_id: str = Field(default="", description="被审计的辩论 run_id")
    overall_risk_level: RiskLevel = Field(
        default="critical",
        description=(
            "综合风险定级：取全部发现中的最高级别（low|medium|high|critical）；"
            "LLM 缺失或给出白名单外写法时按 fail-closed 处理为 critical"
        ),
    )
    risk_grade_label: str = Field(
        default="致命",
        description="综合风险定级中文标签：低|中|高|致命（缺失时按级别自动回填）",
    )
    findings: list[AuditFinding] = Field(
        default_factory=list, description="审计发现清单（按严重级别排序）"
    )
    summary: str = Field(description="审计结论一段话")
    tradability: str = Field(
        description="据此生成交易建议的可行性：allowed | restricted | prohibited"
    )

    @field_validator("overall_risk_level", mode="before")
    @classmethod
    def _normalize_overall_level(cls, v: object) -> str:
        """LLM 原始综合定级先归一化（缺失/白名单外 -> critical，绝不回落 low）。"""
        return normalize_risk_level(v)

    @field_validator("risk_grade_label", mode="before")
    @classmethod
    def _fill_risk_grade_label(cls, v: object, info) -> str:
        """未给出中文标签时按已归一化的级别自动回填，保证报告文案一致。"""
        if isinstance(v, str) and v.strip():
            return v
        level = info.data.get("overall_risk_level")
        return RISK_LABELS_ZH.get(level, "致命") if level else "致命"


class RiskGate(StrictModel):
    """风控门控结论（确定性规则产出，不由 LLM 决定，保证拦截可复现）。"""

    risk_level: RiskLevel = Field(description="采用的综合风险定级（来自审计 overall_risk_level）")
    trade_suggestion_allowed: bool = Field(
        description="是否允许生成交易建议（致命风险恒为 False）"
    )
    risk_banner: str = Field(
        default="",
        description="报告顶部的显著风险提示文本（高风险及以上非空；否则空串）",
    )
    constraint_boundaries: list[str] = Field(
        default_factory=list,
        description="强制写明的约束边界清单（高风险及以上非空）",
    )


class FinalAnalysisDraft(StrictModel):
    """RiskOfficerAgent 的 LLM 输出（分析部分；门控与最终决策由流水线确定性填充）。"""

    @field_validator("overall_risk_level", mode="before")
    @classmethod
    def _normalize_overall_level(cls, v: object) -> str:
        return normalize_risk_level(v)

    symbol: str = Field(description="标的")
    market: str = Field(description="市场枚举值")
    strategy_name: str = Field(default="", description="策略名称")
    debate_run_id: str = Field(default="", description="被综合的辩论 run_id")
    audit_run_id: str = Field(default="", description="被综合的审计 run_id")
    credibility_score: int = Field(ge=0, le=100, description="策略可信度打分（0~100）")
    overall_risk_level: RiskLevel = Field(description="综合风险定级（low|medium|high|critical）")
    executive_summary: str = Field(description="执行摘要（一段话）")
    key_findings: list[str] = Field(
        default_factory=list, description="关键风险发现（引用审计高定级条目）"
    )
    recommendations: list[str] = Field(
        default_factory=list, description="改进建议清单"
    )
    trade_advisory: str = Field(
        default="",
        description="可执行交易建议；若审计为致命风险，此项应留空（由门控强制拦截）",
    )


class FinalAnalysisReport(StrictModel):
    """最终量化分析报告（RiskOfficerAgent 分析草稿 + 确定性风控门控）。"""

    @field_validator("overall_risk_level", mode="before")
    @classmethod
    def _normalize_overall_level(cls, v: object) -> str:
        return normalize_risk_level(v)

    symbol: str = Field(description="标的")
    market: str = Field(description="市场枚举值")
    strategy_name: str = Field(default="", description="策略名称")
    debate_run_id: str = Field(default="", description="辩论 run_id")
    audit_run_id: str = Field(default="", description="审计 run_id")
    final_decision: str = Field(
        description="最终决策：adopt | revise | reject | blocked（致命风险恒为 blocked）"
    )
    credibility_score: int = Field(ge=0, le=100, description="策略可信度打分（0~100）")
    overall_risk_level: RiskLevel = Field(description="综合风险定级")
    risk_gate: RiskGate = Field(description="风控门控结论")
    executive_summary: str = Field(description="执行摘要")
    key_findings: list[str] = Field(default_factory=list, description="关键风险发现")
    recommendations: list[str] = Field(default_factory=list, description="改进建议")
    trade_advisory: str = Field(default="", description="可执行交易建议（被拦截时为空）")
