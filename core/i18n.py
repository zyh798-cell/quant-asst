"""报告层双语字符串目录（Step K）。

设计约束：

- **集中式**：所有报告渲染可见文案集中在 :data:`MESSAGES_ZH` / :data:`MESSAGES_EN`
  两个扁平 dict，渲染代码禁止散落三元表达式或内联硬编码文案；
- **键集合一致**：两个 dict 的键必须完全相同，由 ``tests/test_report_i18n.py`` 守护；
- **fail-closed**：无法识别的语言值一律报错，绝不静默回落到某种语言之外的猜测；
- **只动文案**：本模块不参与风控/辩论/审计的判定逻辑，门控结论语言由
  ``core.risk_gate`` 在产出文案时按同一目录选择。

数字与日期格式不随语言变化（由 ``report.markdown._pct`` 等既有格式化函数负责），
本目录只做「文案」不做「数值」。
"""

from __future__ import annotations

from typing import Literal, Mapping

#: 报告语言取值
ReportLanguage = Literal["zh", "en"]

#: 默认报告语言（默认行为不变：中文）
DEFAULT_REPORT_LANGUAGE: ReportLanguage = "zh"

#: 支持的语言（顺序即文档展示顺序）
SUPPORTED_REPORT_LANGUAGES: tuple[str, ...] = ("zh", "en")

#: 英文免责声明固定用 Release notes 原句，任何英文报告都须包含该句
EN_DISCLAIMER = (
    "Research and education use only; not investment advice; "
    "backtest results do not represent future returns."
)


def normalize_report_language(value: str | None) -> ReportLanguage:
    """把外部输入归一化为受支持的报告语言。

    - ``None`` / 空串 -> ``zh``（默认行为不变）；
    - ``zh`` / ``en``（大小写不敏感、去空白）-> 对应语言；
    - 其余取值一律 ``ValueError``（fail-closed，不静默猜测）。
    """
    if value is None:
        return DEFAULT_REPORT_LANGUAGE
    key = str(value).strip().lower()
    if not key:
        return DEFAULT_REPORT_LANGUAGE
    if key in SUPPORTED_REPORT_LANGUAGES:
        return key  # type: ignore[return-value]
    raise ValueError(
        f"不支持的报告语言：{value!r}（可选：{' / '.join(SUPPORTED_REPORT_LANGUAGES)}）"
    )


# ---------------------------------------------------------------------------
# 中文目录（默认；与历史产物逐字一致，避免回归）
# ---------------------------------------------------------------------------

MESSAGES_ZH: Mapping[str, str] = {
    # ---- 通用 ----
    "common.item": "项目",
    "common.value": "内容",
    "common.none_paren": "（无）",
    "common.na": "N/A",
    "punct.colon": "：",
    "disclaimer.research_only": "仅用于研究与教育，不构成投资建议。",

    # ---- 风险级别 ----
    "risk.low": "低",
    "risk.medium": "中",
    "risk.high": "高",
    "risk.critical": "致命",
    "risk.level_display": "{label}（{code}）",

    # ---- 风控门控（core.risk_gate 使用，结论文案随语言）----
    "gate.constraint.base.0": "本报告仅为研究与教育用途，不构成投资建议，禁止直接用于实盘下单",
    "gate.constraint.base.1": "策略信号须经样本外与滚动窗口复验后方可评估落地",
    "gate.constraint.base.2": "仓位与止损须按标的流动性单独核定，不得套用默认满仓假设",
    "gate.constraint.critical": "存在致命缺陷：在缺陷修复并重新审计前，禁止生成交易建议",
    "gate.banner.critical": (
        "风险提示：本策略经红队审计判定为致命风险，已拦截交易建议生成。"
        "在缺陷修复并重新通过审计前，请勿将本报告用于任何实盘决策。"
    ),
    "gate.banner.high": "风险提示：本策略存在高风险，须严格遵守下列约束边界后方可评估使用。",
    "gate.blocked_advisory": (
        "（交易建议已被风控门控拦截：本策略存在致命缺陷或明确禁止交易，"
        "禁止生成任何实盘买卖建议）"
    ),

    # ---- 辩论纪要 ----
    "debate.title": "# 多空辩论报告：{symbol}",
    "debate.meta.symbol": "标的",
    "debate.meta.market": "市场",
    "debate.meta.strategy_desc": "策略描述",
    "debate.meta.rounds": "辩论轮次",
    "debate.meta.run_id": "run_id",
    "debate.disclaimer": "本报告由 Quant Asst 多智能体辩论流程自动生成，仅用于研究与教育，不构成投资建议。",
    "debate.transcripts_title": "## 逐轮辩论原文",
    "debate.no_transcripts": "（无逐轮记录）",
    "debate.round_heading": "### 第 {round_no} 轮",
    "debate.bull_stance": "**多头观点**",
    "debate.bear_stance": "**空头观点**",
    "debate.point_line": "{i}. **{claim}** — 证据类型 `{evidence_type}`：{evidence}",
    "debate.assumptions_prefix": "假设前提：",
    "debate.failure_scenarios_prefix": "失效场景：",
    "debate.risk_check_title": "**风控核验意见**",
    "debate.data_validity_label": "数据有效性",
    "debate.findings_label": "核验发现",
    "debate.finding_line": "  - [{severity}] {target_side}：{issue}（可证伪={falsifiable}）",
    "debate.kept_points_line": "- 留存多头论点索引：{bull}；留存空头论点索引：{bear}",
    "debate.recommendation_label": "独立建议",
    "debate.verdict_title": "## 裁决结论",
    "debate.credibility_label": "可信度打分",
    "debate.decision_label": "最终结论",
    "debate.rationale_label": "**裁决理由**：",
    "debate.consensus_label": "**共识**",
    "debate.disagreements_label": "**分歧**",
    "debate.revision_title": "## 策略修订建议",
    "debate.revised_strategy_label": "**修订后策略**：",
    "debate.entry_rule_label": "开仓规则",
    "debate.exit_rule_label": "平仓规则",
    "debate.params_label": "参数",
    "debate.expected_effect_label": "预期效果",
    "debate.usage_hint": "该修订文本可直接作为 `cli.py run` 的输入执行回测验证：",
    "debate.no_revision": "裁决未给出修订建议（decision 非 revise，或 adopt/reject 情形）。",

    # ---- 红队审计意见书 ----
    "audit.title": "# 红队审计意见书：{symbol}",
    "audit.meta.strategy": "被审计策略",
    "audit.meta.audit_run_id": "审计 run_id",
    "audit.meta.source_run_id": "辩论来源 run_id",
    "audit.meta.overall_risk": "综合风险定级",
    "audit.meta.tradability": "交易建议可行性",
    "audit.disclaimer": (
        "本意见书由 Quant Asst 红队审计 Agent 独立产出，不参与多空辩论，仅做风险定级；"
        "仅用于研究与教育，不构成投资建议。"
    ),
    "audit.banner": "> **风险提示：本策略综合风险定级为「{label}」。以下审计发现须在后续决策中逐项处置。**",
    "audit.conclusion_title": "## 审计结论",
    "audit.findings_title": "## 审计发现（{n} 条）",
    "audit.no_findings": "未发现需登记的风险条目。",
    "audit.finding_heading": "### {i}. [{sev}] {title}",
    "audit.risk_category": "风险类别",
    "audit.severity": "严重级别",
    "audit.description": "问题描述",
    "audit.evidence": "支撑证据",
    "audit.recommendation": "处置建议",
    "audit.scale_title": "## 风险定级说明",
    "audit.scale_col_level": "级别",
    "audit.scale_col_meaning": "含义",
    "audit.scale.low": "常规可控风险，按既定流程处置",
    "audit.scale.medium": "存在明确缺陷，须修复后复验",
    "audit.scale.high": "关键风险，触发约束边界与报告顶部显著标注",
    "audit.scale.critical": "阻断性缺陷，禁止生成交易建议",

    # ---- 最终量化分析报告 ----
    "final.title": "# 最终量化分析报告：{symbol}",
    "final.constraints_title": "**约束边界（强制）**",
    "final.blocked_note": (
        "> **本报告已拦截交易建议生成**：{trigger}，"
        "在缺陷修复并重新通过红队审计前，不输出任何可执行交易建议。"
    ),
    "final.trigger_critical": "综合风险定级为致命（critical）",
    "final.trigger_prohibited": "交易可行性被判定为禁止（prohibited）",
    "final.meta.symbol": "标的",
    "final.meta.market": "市场",
    "final.meta.strategy": "策略",
    "final.meta.debate_run_id": "辩论 run_id",
    "final.meta.audit_run_id": "审计 run_id",
    "final.meta.overall_risk": "综合风险定级",
    "final.meta.decision": "最终决策",
    "final.meta.credibility": "策略可信度",
    "final.disclaimer": (
        "本报告由 Quant Asst 风控综合官在「多空辩论 + 红队审计」之后产出，"
        "仅用于研究与教育，不构成投资建议。"
    ),
    "final.executive_summary_title": "## 执行摘要",
    "final.key_findings_title": "## 关键风险发现（{n} 条）",
    "final.recommendations_title": "## 改进建议（{n} 条）",
    "final.advisory_title": "## 交易建议",
    "final.no_advisory": "（无：致命风险已拦截交易建议生成，或当前风险级别未给出可执行建议。）",

    # ---- 参数网格寻优报告 ----
    "opt.title": "# 参数网格寻优报告：{symbol}",
    "opt.meta.period": "回测区间",
    "opt.meta.train_ratio": "样本内占比",
    "opt.meta.out_sample_start": "（样本外起点 {start}）",
    "opt.meta.grid": "参数网格",
    "opt.meta.combinations": "组合数",
    "opt.meta.selection_metric": "选优指标",
    "opt.meta.selection_metric_value": "样本内 {metric}（固定主指标）；对照指标：样本内 {comparison}",
    "opt.meta.threshold": "准入门槛",
    "opt.meta.threshold_value": "样本内成交笔数 ≥ {n} 笔，不足者不参与选优",
    "opt.meta.initial_capital": "初始资金",
    "opt.meta.sandbox": "沙箱模式",
    "opt.disclaimer": (
        "本报告由 Quant Asst 参数网格寻优流程自动生成，仅用于研究与教育，不构成投资建议。"
        "寻优过程为纯确定性网格遍历，不调用任何 LLM。"
    ),
    "opt.compare_title": "## 全组合样本内 / 样本外指标对比（{n} 组）",
    "opt.col.eligible": "资格",
    "opt.col.return_rank": "总收益排名",
    "opt.col.in_total": "样本内总收益",
    "opt.col.out_total": "样本外总收益",
    "opt.col.in_annual": "样本内年化",
    "opt.col.out_annual": "样本外年化",
    "opt.col.in_drawdown": "样本内最大回撤",
    "opt.col.out_drawdown": "样本外最大回撤",
    "opt.col.in_sharpe": "样本内夏普",
    "opt.col.out_sharpe": "样本外夏普",
    "opt.col.in_trades": "样本内笔数",
    "opt.col.out_trades": "样本外笔数",
    "opt.cell.eligible": "合格",
    "opt.cell.ineligible": "不合格",
    "opt.ineligible_title": "## 不参与选优的组合（样本内成交笔数不足）",
    "opt.ineligible_none": "全部组合均满足准入门槛。",
    "opt.ineligible_col.params": "参数",
    "opt.ineligible_col.in_trades": "样本内笔数",
    "opt.ineligible_col.reason": "原因",
    "opt.best_title": "## 最优组合（按样本内 {metric} 选定）",
    "opt.no_valid": "（无有效组合）",
    "opt.param_col": "参数",
    "opt.value_col": "取值",
    "opt.best_metrics_title": "### 最优组合指标",
    "opt.metric_col": "指标",
    "opt.overall_col": "全区间",
    "opt.in_col": "样本内",
    "opt.out_col": "样本外",
    "opt.metric.total_return": "总收益",
    "opt.metric.annual_return": "年化收益",
    "opt.metric.max_drawdown": "最大回撤",
    "opt.metric.sharpe": "夏普比率",
    "opt.metric.win_rate": "按笔胜率",
    "opt.metric.n_trades": "成交笔数",
    "opt.compare_metric_title": "### 选优指标对照（并列呈现，不做加权综合）",
    "opt.primary_selected": "- 主指标（样本内 {metric}）选定：组合 #{index}",
    "opt.return_first": "- 按样本内 {metric} 排序首位：组合 #{index}",
    "opt.agree": "- 结论：两个指标指向同一组合，结论一致。",
    "opt.conflict": (
        "- 结论：两个指标**指向不同组合，结论冲突**；上表已并列呈现，"
        "本流程不做加权综合，请结合样本外表现与红队审计人工判断。"
    ),
    "opt.leak_title": "## 防泄漏声明",
    "opt.leak.split": (
        "- 切分点在寻优开始前一次性固定：样本内占比 {ratio}，样本外起点 {start}；"
        "全部分组合共用同一切分点，执行时已校验各组合样本外起点一致。"
    ),
    "opt.leak.selection": (
        "- 网格遍历与选优仅使用样本内指标；样本外指标仅在选出最优组合后的最终验证中"
        "使用一次（劣化判定），不参与任何筛选或排序。"
    ),
    "opt.leak.deterministic": "- 寻优过程为纯确定性网格遍历，不调用任何 LLM，不使用随机数。",
    "opt.oos_title": "## 样本外验证结论",
    "opt.degraded": "> **判定：degraded（样本外表现显著劣于样本内）**",
    "opt.not_degraded": "> **判定：未触发劣化阈值**（样本外未显著劣于样本内）",
    "opt.degraded_reason": "- 触发原因：{reason}",
    "opt.no_threshold_hit": "- 本次最优组合的样本外指标未跌破下述任一阈值。",
    "opt.threshold_title": "### 劣化判定口径（确定性阈值）",
    "opt.threshold.sharpe": "- 样本内夏普为正且样本外夏普低于样本内的 {ratio}；",
    "opt.threshold.sign": "- 样本内总收益为正而样本外总收益非正（符号翻转）；",
    "opt.threshold.drawdown": "- 样本外最大回撤比样本内更深超过 {extra}。",
    "opt.overfit_title": "### 过拟合提示",
    "opt.overfit": (
        "网格寻优按**样本内**指标挑出最优组合，本质是对同一批数据反复试参，"
        "样本内指标天然被高估；样本外未显著劣化只能说明该组合在既有切分下尚未暴露问题，"
        "**不能排除过拟合**。任何进入实盘讨论的参数仍须使用完全独立的样本外区间复验，"
        "并通过红队审计（未来函数 / 幸存者偏差 / 成本敏感性）确认。"
    ),

    # ---- Plotly HTML 报告 ----
    "html.lang_attr": "zh-CN",
    "html.title": "Quant Asst 最终量化分析报告：{symbol}",
    "html.meta": "数据源：{note} | 回测约束边界见文末注释 | 仅用于研究与教育，不构成投资建议",
    "html.decision_label": "最终决策",
    "html.risk_label": "综合风险定级",
    "html.constraints_title": "约束边界（强制）",
    "html.metrics_title": "风险指标汇总",
    "html.charts_title": "图表",
    "html.summary_title": "分析摘要",
    "html.summary.verdict": "裁决",
    "html.summary.consensus_prefix": "共识：",
    "html.panel.debate": "辩论摘要",
    "html.panel.audit": "红队审计风险结论",
    "html.panel.officer": "风控综合结论",
    "html.panel.advisory": "交易建议",
    "html.empty.debate": "（无辩论纪要）",
    "html.empty.audit": "（未执行红队审计）",
    "html.empty.officer": "（无最终分析）",
    "html.empty.advisory": "（致命风险已拦截交易建议生成，或未给出可执行建议。）",
    "html.empty.backtest": "（无回测数据）",
    "html.empty.charts": "（无可视化数据：缺净值曲线或K线明细）",
    "html.metrics_col.name": "指标",
    "html.metrics_col.value": "数值",
    "html.metric.total_return": "区间总收益",
    "html.metric.annual_return": "年化收益",
    "html.metric.max_drawdown": "最大回撤",
    "html.metric.sharpe": "夏普比率",
    "html.metric.win_rate": "按笔胜率",
    "html.metric.n_trades": "成交笔数",
    "html.metric.initial_capital": "初始资金",
    "html.metric.final_equity": "期末净值",
    "html.metric.total_cost": "累计成本",
    "html.metric.out_sample_start": "样本外起点",
    "html.footer": (
        "数据来源：{note}（AkShare/DuckDB 本地缓存 + 事件驱动回测引擎）。\n"
        "回测约束边界：样本内/外按 70/30 切分；成交按次开盘价撮合并含双边成本与滑点；\n"
        "本报告为历史回测研究产物，不预示未来收益，禁止直接用于实盘下单。"
    ),
    "html.chart.candle_title": "标的K线行情与策略信号标记",
    "html.chart.date": "日期",
    "html.chart.price": "价格",
    "html.chart.kline": "K线",
    "html.chart.buy": "买入信号",
    "html.chart.sell": "卖出信号",
    "html.chart.buy_hover": "买入 {shares}",
    "html.chart.sell_hover": "卖出 {shares}",
    "html.chart.equity_title": "回测净值曲线",
    "html.chart.nav": "策略净值",
    "html.chart.benchmark": "初始资金基准",
    "html.chart.oos_mark": "样本外起点",
    "html.chart.nav_axis": "净值",
    "html.chart.dd_title": "最大回撤曲线",
    "html.chart.dd": "回撤",
    "html.chart.dd_axis": "回撤",
}


# ---------------------------------------------------------------------------
# English catalog (same keys as MESSAGES_ZH; guarded by tests)
# ---------------------------------------------------------------------------

MESSAGES_EN: Mapping[str, str] = {
    # ---- common ----
    "common.item": "Item",
    "common.value": "Value",
    "common.none_paren": "(none)",
    "common.na": "N/A",
    "punct.colon": ": ",
    "disclaimer.research_only": EN_DISCLAIMER,

    # ---- risk levels ----
    "risk.low": "Low",
    "risk.medium": "Medium",
    "risk.high": "High",
    "risk.critical": "Critical",
    "risk.level_display": "{label} ({code})",

    # ---- risk gate ----
    "gate.constraint.base.0": (
        "This report is for research and education only, does not constitute investment "
        "advice, and must not be used directly for live order placement."
    ),
    "gate.constraint.base.1": (
        "Strategy signals must be revalidated out-of-sample and over rolling windows "
        "before any deployment assessment."
    ),
    "gate.constraint.base.2": (
        "Position sizing and stop-loss must be set per underlying liquidity; the default "
        "full-position assumption must not be reused."
    ),
    "gate.constraint.critical": (
        "Fatal defect present: no trade suggestion may be generated until the defect is "
        "fixed and re-audited."
    ),
    "gate.banner.critical": (
        "Risk notice: the red-team audit classified this strategy as critical risk and "
        "trade suggestion generation has been blocked. Do not use this report for any live "
        "decision until the defect is fixed and the audit is passed again."
    ),
    "gate.banner.high": (
        "Risk notice: this strategy carries high risk; the mandatory constraint boundaries "
        "below must be strictly observed before any evaluation."
    ),
    "gate.blocked_advisory": (
        "(Trade suggestion blocked by the risk gate: this strategy has a fatal defect or "
        "trading is explicitly prohibited; no live buy/sell suggestion may be generated.)"
    ),

    # ---- debate minutes ----
    "debate.title": "# Bull/Bear Debate Report: {symbol}",
    "debate.meta.symbol": "Symbol",
    "debate.meta.market": "Market",
    "debate.meta.strategy_desc": "Strategy description",
    "debate.meta.rounds": "Debate rounds",
    "debate.meta.run_id": "run_id",
    "debate.disclaimer": (
        "Generated automatically by the Quant Asst multi-agent debate pipeline. "
        f"{EN_DISCLAIMER}"
    ),
    "debate.transcripts_title": "## Round-by-Round Debate Transcript",
    "debate.no_transcripts": "(no round transcript)",
    "debate.round_heading": "### Round {round_no}",
    "debate.bull_stance": "**Bull stance**",
    "debate.bear_stance": "**Bear stance**",
    "debate.point_line": "{i}. **{claim}** - evidence type `{evidence_type}`: {evidence}",
    "debate.assumptions_prefix": "Assumptions: ",
    "debate.failure_scenarios_prefix": "Failure scenarios: ",
    "debate.risk_check_title": "**Risk check opinion**",
    "debate.data_validity_label": "Data validity",
    "debate.findings_label": "Findings",
    "debate.finding_line": "  - [{severity}] {target_side}: {issue} (falsifiable={falsifiable})",
    "debate.kept_points_line": (
        "- Retained bull point indexes: {bull}; retained bear point indexes: {bear}"
    ),
    "debate.recommendation_label": "Independent recommendation",
    "debate.verdict_title": "## Verdict",
    "debate.credibility_label": "Credibility score",
    "debate.decision_label": "Final decision",
    "debate.rationale_label": "**Verdict rationale**: ",
    "debate.consensus_label": "**Consensus**",
    "debate.disagreements_label": "**Disagreements**",
    "debate.revision_title": "## Strategy Revision Proposal",
    "debate.revised_strategy_label": "**Revised strategy**: ",
    "debate.entry_rule_label": "Entry rule",
    "debate.exit_rule_label": "Exit rule",
    "debate.params_label": "Parameters",
    "debate.expected_effect_label": "Expected effect",
    "debate.usage_hint": (
        "The revised text can be fed directly to `cli.py run` for backtest validation:"
    ),
    "debate.no_revision": (
        "No revision proposed by the verdict (decision is not revise, or an adopt/reject case)."
    ),

    # ---- red-team audit ----
    "audit.title": "# Red-Team Audit Opinion: {symbol}",
    "audit.meta.strategy": "Audited strategy",
    "audit.meta.audit_run_id": "Audit run_id",
    "audit.meta.source_run_id": "Source debate run_id",
    "audit.meta.overall_risk": "Overall risk level",
    "audit.meta.tradability": "Tradability",
    "audit.disclaimer": (
        "Produced independently by the Quant Asst red-team audit agent; it does not take part "
        "in the bull/bear debate and only assigns a risk level. "
        f"{EN_DISCLAIMER}"
    ),
    "audit.banner": (
        "> **Risk notice: the overall risk level of this strategy is \"{label}\". "
        "Every audit finding below must be dispositioned in subsequent decisions.**"
    ),
    "audit.conclusion_title": "## Audit Conclusion",
    "audit.findings_title": "## Audit Findings ({n})",
    "audit.no_findings": "No risk items were registered.",
    "audit.finding_heading": "### {i}. [{sev}] {title}",
    "audit.risk_category": "Risk category",
    "audit.severity": "Severity",
    "audit.description": "Description",
    "audit.evidence": "Evidence",
    "audit.recommendation": "Recommendation",
    "audit.scale_title": "## Risk Level Reference",
    "audit.scale_col_level": "Level",
    "audit.scale_col_meaning": "Meaning",
    "audit.scale.low": "Routine controllable risk; handle through the established process.",
    "audit.scale.medium": "Clear defect exists; fix and revalidate before use.",
    "audit.scale.high": (
        "Key risk; triggers constraint boundaries and a prominent banner at the top of the report."
    ),
    "audit.scale.critical": "Blocking defect; generating trade suggestions is forbidden.",

    # ---- final analysis report ----
    "final.title": "# Final Quantitative Analysis Report: {symbol}",
    "final.constraints_title": "**Mandatory Constraint Boundaries**",
    "final.blocked_note": (
        "> **Trade suggestion generation has been blocked in this report**: {trigger}. "
        "No executable trade suggestion will be output until the defect is fixed and the "
        "red-team audit is passed again."
    ),
    "final.trigger_critical": "the overall risk level is critical",
    "final.trigger_prohibited": "tradability was judged prohibited",
    "final.meta.symbol": "Symbol",
    "final.meta.market": "Market",
    "final.meta.strategy": "Strategy",
    "final.meta.debate_run_id": "Debate run_id",
    "final.meta.audit_run_id": "Audit run_id",
    "final.meta.overall_risk": "Overall risk level",
    "final.meta.decision": "Final decision",
    "final.meta.credibility": "Strategy credibility",
    "final.disclaimer": (
        "Produced by the Quant Asst risk officer after the bull/bear debate and the red-team "
        f"audit. {EN_DISCLAIMER}"
    ),
    "final.executive_summary_title": "## Executive Summary",
    "final.key_findings_title": "## Key Risk Findings ({n})",
    "final.recommendations_title": "## Recommendations ({n})",
    "final.advisory_title": "## Trade Suggestion",
    "final.no_advisory": (
        "(none: a critical risk blocked trade suggestion generation, or the current risk level "
        "yielded no executable suggestion.)"
    ),

    # ---- parameter grid optimization ----
    "opt.title": "# Parameter Grid Optimization Report: {symbol}",
    "opt.meta.period": "Backtest period",
    "opt.meta.train_ratio": "In-sample ratio",
    "opt.meta.out_sample_start": " (out-of-sample start {start})",
    "opt.meta.grid": "Parameter grid",
    "opt.meta.combinations": "Combinations",
    "opt.meta.selection_metric": "Selection metric",
    "opt.meta.selection_metric_value": (
        "in-sample {metric} (primary); comparison metric: in-sample {comparison}"
    ),
    "opt.meta.threshold": "Eligibility threshold",
    "opt.meta.threshold_value": (
        "in-sample trades >= {n}; combinations below the threshold are excluded from selection"
    ),
    "opt.meta.initial_capital": "Initial capital",
    "opt.meta.sandbox": "Sandbox mode",
    "opt.disclaimer": (
        "Generated automatically by the Quant Asst parameter grid optimization pipeline. "
        "Optimization is a deterministic grid sweep and calls no LLM. "
        f"{EN_DISCLAIMER}"
    ),
    "opt.compare_title": "## All Combinations: In-Sample vs Out-of-Sample ({n})",
    "opt.col.eligible": "Eligibility",
    "opt.col.return_rank": "Total return rank",
    "opt.col.in_total": "In-sample total return",
    "opt.col.out_total": "Out-of-sample total return",
    "opt.col.in_annual": "In-sample annualized",
    "opt.col.out_annual": "Out-of-sample annualized",
    "opt.col.in_drawdown": "In-sample max drawdown",
    "opt.col.out_drawdown": "Out-of-sample max drawdown",
    "opt.col.in_sharpe": "In-sample Sharpe",
    "opt.col.out_sharpe": "Out-of-sample Sharpe",
    "opt.col.in_trades": "In-sample trades",
    "opt.col.out_trades": "Out-of-sample trades",
    "opt.cell.eligible": "Eligible",
    "opt.cell.ineligible": "Ineligible",
    "opt.ineligible_title": "## Combinations Excluded From Selection (too few in-sample trades)",
    "opt.ineligible_none": "All combinations meet the eligibility threshold.",
    "opt.ineligible_col.params": "Parameters",
    "opt.ineligible_col.in_trades": "In-sample trades",
    "opt.ineligible_col.reason": "Reason",
    "opt.best_title": "## Best Combination (selected by in-sample {metric})",
    "opt.no_valid": "(no valid combination)",
    "opt.param_col": "Parameter",
    "opt.value_col": "Value",
    "opt.best_metrics_title": "### Best Combination Metrics",
    "opt.metric_col": "Metric",
    "opt.overall_col": "Full period",
    "opt.in_col": "In-sample",
    "opt.out_col": "Out-of-sample",
    "opt.metric.total_return": "Total return",
    "opt.metric.annual_return": "Annualized return",
    "opt.metric.max_drawdown": "Max drawdown",
    "opt.metric.sharpe": "Sharpe ratio",
    "opt.metric.win_rate": "Win rate",
    "opt.metric.n_trades": "Trades",
    "opt.compare_metric_title": (
        "### Selection Metric Comparison (presented side by side; no weighted aggregation)"
    ),
    "opt.primary_selected": "- Primary metric (in-sample {metric}) selected: combination #{index}",
    "opt.return_first": "- Top-ranked by in-sample {metric}: combination #{index}",
    "opt.agree": "- Conclusion: both metrics point to the same combination; they agree.",
    "opt.conflict": (
        "- Conclusion: the two metrics point to different combinations (conflict). Both are "
        "presented above; this pipeline performs no weighted aggregation. Judge manually using "
        "out-of-sample behaviour and the red-team audit."
    ),
    "opt.leak_title": "## Leakage Statement",
    "opt.leak.split": (
        "- The split point is fixed once before optimization starts: in-sample ratio {ratio}, "
        "out-of-sample start {start}. All combinations share the same split point, and the run "
        "verified that every combination's out-of-sample start is identical."
    ),
    "opt.leak.selection": (
        "- Grid traversal and selection use in-sample metrics only; out-of-sample metrics are "
        "used exactly once, in the final validation after the best combination is chosen "
        "(degradation check), and never participate in filtering or ranking."
    ),
    "opt.leak.deterministic": (
        "- Optimization is a deterministic grid sweep: no LLM call, no random numbers."
    ),
    "opt.oos_title": "## Out-of-Sample Validation",
    "opt.degraded": (
        "> **Verdict: degraded (out-of-sample performance is materially worse than in-sample)**"
    ),
    "opt.not_degraded": (
        "> **Verdict: degradation thresholds not triggered** (out-of-sample not materially worse "
        "than in-sample)"
    ),
    "opt.degraded_reason": "- Trigger: {reason}",
    "opt.no_threshold_hit": (
        "- The best combination's out-of-sample metrics did not breach any threshold below."
    ),
    "opt.threshold_title": "### Degradation Criteria (deterministic thresholds)",
    "opt.threshold.sharpe": (
        "- In-sample Sharpe positive and out-of-sample Sharpe below {ratio} of the in-sample value;"
    ),
    "opt.threshold.sign": (
        "- In-sample total return positive while out-of-sample total return is non-positive "
        "(sign flip);"
    ),
    "opt.threshold.drawdown": (
        "- Out-of-sample max drawdown deeper than in-sample by more than {extra}."
    ),
    "opt.overfit_title": "### Overfitting Warning",
    "opt.overfit": (
        "Grid optimization picks the best combination by in-sample metrics, which is repeated "
        "parameter search on the same data; in-sample metrics are inherently inflated. Failing "
        "to degrade out-of-sample only means the combination has not yet exposed problems under "
        "this split; it **does not rule out overfitting**. Any parameter considered for live use "
        "must be revalidated on a fully independent out-of-sample window and confirmed by the "
        "red-team audit (look-ahead, survivorship bias, cost sensitivity)."
    ),

    # ---- Plotly HTML report ----
    "html.lang_attr": "en",
    "html.title": "Quant Asst Final Quantitative Analysis Report: {symbol}",
    "html.meta": (
        "Data source: {note} | Backtest constraint boundaries in the footer | "
        "Research and education use only, not investment advice"
    ),
    "html.decision_label": "Final decision",
    "html.risk_label": "Overall risk level",
    "html.constraints_title": "Mandatory Constraint Boundaries",
    "html.metrics_title": "Risk Metrics",
    "html.charts_title": "Charts",
    "html.summary_title": "Analysis Summary",
    "html.summary.verdict": "Verdict",
    "html.summary.consensus_prefix": "Consensus: ",
    "html.panel.debate": "Debate Summary",
    "html.panel.audit": "Red-Team Audit Risk Conclusion",
    "html.panel.officer": "Risk Officer Conclusion",
    "html.panel.advisory": "Trade Suggestion",
    "html.empty.debate": "(no debate minutes)",
    "html.empty.audit": "(red-team audit not run)",
    "html.empty.officer": "(no final analysis)",
    "html.empty.advisory": (
        "(a critical risk blocked trade suggestion generation, or no executable suggestion given.)"
    ),
    "html.empty.backtest": "(no backtest data)",
    "html.empty.charts": "(no chart data: equity curve or kline detail missing)",
    "html.metrics_col.name": "Metric",
    "html.metrics_col.value": "Value",
    "html.metric.total_return": "Period total return",
    "html.metric.annual_return": "Annualized return",
    "html.metric.max_drawdown": "Max drawdown",
    "html.metric.sharpe": "Sharpe ratio",
    "html.metric.win_rate": "Win rate",
    "html.metric.n_trades": "Trades",
    "html.metric.initial_capital": "Initial capital",
    "html.metric.final_equity": "Ending equity",
    "html.metric.total_cost": "Cumulative cost",
    "html.metric.out_sample_start": "Out-of-sample start",
    "html.footer": (
        "Data source: {note} (AkShare/DuckDB local cache + event-driven backtest engine).\n"
        "Backtest constraint boundaries: 70/30 in-sample/out-of-sample split; fills at next-open "
        "prices with two-sided costs and slippage.\n"
        "This report is a historical backtest research artifact; it does not predict future "
        "returns and must not be used directly for live order placement."
    ),
    "html.chart.candle_title": "Underlying K-Line and Strategy Signal Markers",
    "html.chart.date": "Date",
    "html.chart.price": "Price",
    "html.chart.kline": "K-Line",
    "html.chart.buy": "Buy signal",
    "html.chart.sell": "Sell signal",
    "html.chart.buy_hover": "Buy {shares}",
    "html.chart.sell_hover": "Sell {shares}",
    "html.chart.equity_title": "Backtest Equity Curve",
    "html.chart.nav": "Strategy NAV",
    "html.chart.benchmark": "Initial capital baseline",
    "html.chart.oos_mark": "Out-of-sample start",
    "html.chart.nav_axis": "NAV",
    "html.chart.dd_title": "Max Drawdown Curve",
    "html.chart.dd": "Drawdown",
    "html.chart.dd_axis": "Drawdown",
}

_MESSAGES: dict[str, Mapping[str, str]] = {
    "zh": MESSAGES_ZH,
    "en": MESSAGES_EN,
}

#: 键集合（供一致性测试与外部自检）
MESSAGE_KEYS: frozenset[str] = frozenset(MESSAGES_ZH)


def t(key: str, lang: str | None = None) -> str:
    """按语言取模板原文（不做插值）。

    缺键直接 ``KeyError``：文案缺失属于实现缺陷，必须显式失败而不是静默兜底。
    """
    resolved = normalize_report_language(lang)
    table = _MESSAGES[resolved]
    try:
        return table[key]
    except KeyError as exc:  # pragma: no cover - 由键集合测试提前拦截
        raise KeyError(f"缺少报告 i18n 键 {key!r}（lang={resolved}）") from exc


def format_message(key: str, lang: str | None = None, **kwargs: object) -> str:
    """取模板并做 ``str.format`` 插值。"""
    return t(key, lang).format(**kwargs)


def risk_label(level: str, lang: str | None = None) -> str:
    """风险级别展示标签（未知级别原样返回，仅影响展示不影响定级）。"""
    key = f"risk.{level}"
    if key in MESSAGE_KEYS:
        return t(key, lang)
    return str(level)


def risk_level_display(level: str, lang: str | None = None) -> str:
    """风险级别展示：``低（low）`` / ``Low (low)``。"""
    return format_message("risk.level_display", lang, label=risk_label(level, lang), code=level)
