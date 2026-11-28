"""Markdown 报告渲染（Step 4 辩论纪要）。

风格约定（面向 GitHub Demo）：专业工程文档风格 —— **不使用任何 emoji 或装饰符号**，
标题层级规范、表格与代码块简洁、语言严谨客观。
"""

from __future__ import annotations

from typing import Any


def _pct(v: float | None) -> str:
    """百分比展示：-0.054 -> -5.4%；None -> N/A。"""
    if v is None:
        return "N/A"
    return f"{v * 100:.1f}%"


def _signed_pct(v: float | None) -> str:
    """带符号百分比：用于回测指标（正数前加 +）。"""
    if v is None:
        return "N/A"
    return f"{v * 100:+.1f}%"


def _fmt_points(points: list[dict]) -> list[str]:
    out = []
    for i, p in enumerate(points or []):
        ev = (p.get("evidence") or "").replace("\n", " ")
        out.append(f"{i + 1}. **{p.get('claim', '')}** — 证据类型 `{p.get('evidence_type', '')}`：{ev}")
    return out or ["（无）"]


def render_debate_markdown(outcome: dict[str, Any]) -> str:
    """把 DebateOutcome 渲染为 Markdown 辩论报告。

    Args:
        outcome: ``DebateOutcome.model_dump()`` 字典。

    Returns:
        Markdown 文本（UTF-8）。
    """
    meta_lines = [
        f"# 多空辩论报告：{outcome.get('symbol', '')}",
        "",
        "| 项目 | 内容 |",
        "| --- | --- |",
        f"| 标的 | `{outcome.get('symbol', '')}` |",
        f"| 市场 | {outcome.get('market', '')} |",
        f"| 策略描述 | {outcome.get('user_input', '')} |",
        f"| 辩论轮次 | {outcome.get('rounds', 0)} |",
        f"| run_id | `{outcome.get('run_id', '')}` |",
        "",
        "本报告由 Quant Asst 多智能体辩论流程自动生成，仅用于研究与教育，不构成投资建议。",
        "",
    ]

    sections: list[str] = ["\n".join(meta_lines), "\n## 逐轮辩论原文\n"]

    transcripts = outcome.get("round_transcripts") or []
    if not transcripts:
        sections.append("（无逐轮记录）\n")
    for t in transcripts:
        round_no = t.get("round", 0)
        bull = t.get("bull") or {}
        bear = t.get("bear") or {}
        risk = t.get("risk_check") or {}

        sections.append(f"### 第 {round_no} 轮\n")
        sections.append("**多头观点**\n")
        sections.append(f"> {bull.get('stance', '')}\n")
        sections.extend(_fmt_points(bull.get("points") or []))
        if bull.get("assumptions"):
            sections.append("")
            sections.append("假设前提：" + "；".join(bull["assumptions"]))
        sections.append("")

        sections.append("**空头观点**\n")
        sections.append(f"> {bear.get('stance', '')}\n")
        sections.extend(_fmt_points(bear.get("points") or []))
        if bear.get("failure_scenarios"):
            sections.append("")
            sections.append("失效场景：" + "；".join(bear["failure_scenarios"]))
        sections.append("")

        sections.append("**风控核验意见**\n")
        sections.append(f"- 数据有效性：{risk.get('data_validity', '')}")
        findings = risk.get("findings") or []
        if findings:
            sections.append("- 核验发现：")
            for f in findings:
                sections.append(
                    f"  - [{f.get('severity', '')}] {f.get('target_side', '')}："
                    f"{f.get('issue', '')}（可证伪={f.get('falsifiable', '')}）"
                )
        sections.append(
            f"- 留存多头论点索引：{risk.get('kept_bull_points', [])}；"
            f"留存空头论点索引：{risk.get('kept_bear_points', [])}"
        )
        sections.append(f"- 独立建议：{risk.get('recommendation', '')}\n")

    verdict = outcome.get("verdict") or {}
    sections.append("## 裁决结论\n")
    sections.append("| 项目 | 内容 |")
    sections.append("| --- | --- |")
    sections.append(f"| 可信度打分 | {verdict.get('credibility_score', 'N/A')} / 100 |")
    sections.append(f"| 最终结论 | {verdict.get('decision', '')} |")
    sections.append("")
    sections.append(f"**裁决理由**：{verdict.get('rationale', '')}\n")

    consensus = verdict.get("consensus") or []
    disagreements = verdict.get("disagreements") or []
    sections.append("**共识**\n")
    sections.extend(f"- {c}" for c in consensus or ["（无）"])
    sections.append("")
    sections.append("**分歧**\n")
    sections.extend(f"- {d}" for d in disagreements or ["（无）"])
    sections.append("")

    revision = verdict.get("revision") or {}
    sections.append("## 策略修订建议\n")
    if revision:
        sections.append(f"**修订后策略**：{revision.get('revised_strategy_text', '')}\n")
        sections.append(f"- 开仓规则：{revision.get('entry_rule', '')}")
        sections.append(f"- 平仓规则：{revision.get('exit_rule', '')}")
        params = revision.get("params") or {}
        if params:
            param_str = "、".join(f"{k}={v}" for k, v in params.items())
            sections.append(f"- 参数：{param_str}")
        sections.append(f"- 预期效果：{revision.get('expected_effect', '')}\n")
        sections.append("该修订文本可直接作为 `cli.py run` 的输入执行回测验证：")
        sections.append("")
        sections.append("```bash")
        sections.append(f'uv run python cli.py run "{revision.get("revised_strategy_text", "")}"')
        sections.append("```")
    else:
        sections.append("裁决未给出修订建议（decision 非 revise，或 adopt/reject 情形）。")

    sections.append("")
    return "\n".join(sections)


def write_debate_report(outcome: dict[str, Any], out_dir) -> str:
    """渲染并落盘辩论 Markdown 报告到 ``<out_dir>/debate_reports/<run_id>.md``。"""
    from pathlib import Path

    target = Path(out_dir) / "debate_reports"
    target.mkdir(parents=True, exist_ok=True)
    path = target / f"{outcome.get('run_id', 'debate')}.md"
    path.write_text(render_debate_markdown(outcome), encoding="utf-8")
    return str(path)


# ---------------------------------------------------------------------------
# 红队审计报告 + 最终量化分析报告（Step 5）
# ---------------------------------------------------------------------------

#: 风险级别中文标签（与 core.schemas.RISK_LABELS_ZH 保持一致，避免循环导入在此本地定义）
_AUDIT_RISK_LABELS = {"low": "低", "medium": "中", "high": "高", "critical": "致命"}

#: 风险级别排序（用于在 findings 中按严重级别降序展示）
_AUDIT_RISK_RANK = {"low": 1, "medium": 2, "high": 3, "critical": 4}


def _sanitize_ticker(ticker: str) -> str:
    """把统一 symbol（如 ``cn:300750``）转为文件名安全形式（``cn_300750``）。"""
    return (ticker or "unknown").replace(":", "_").replace("/", "_")


def _sort_findings(findings: list[dict]) -> list[dict]:
    """审计发现按严重级别降序排列，同级保持稳定。"""
    return sorted(
        findings or [],
        key=lambda f: _AUDIT_RISK_RANK.get(f.get("severity", "low"), 0),
        reverse=True,
    )


def render_audit_markdown(
    audit_report: dict[str, Any], source_outcome: dict[str, Any] | None = None
) -> str:
    """把 AuditReport 渲染为红队审计意见书（Markdown，无 emoji 工程文档风）。

    Args:
        audit_report: ``AuditReport.model_dump()`` 字典。
        source_outcome: 被审计的 ``DebateOutcome`` dump（可选，用于展示审计来源）。
    """
    level = audit_report.get("overall_risk_level", "low")
    label = _AUDIT_RISK_LABELS.get(level, level)
    banner = (
        f"> **风险提示：本策略综合风险定级为「{label}」。以下审计发现须在后续决策中逐项处置。**"
        if level in ("high", "critical") else ""
    )

    lines: list[str] = [
        f"# 红队审计意见书：{audit_report.get('symbol', '')}",
        "",
        "| 项目 | 内容 |",
        "| --- | --- |",
        f"| 标的 | `{audit_report.get('symbol', '')}` |",
        f"| 市场 | {audit_report.get('market', '')} |",
        f"| 被审计策略 | {audit_report.get('strategy_name', '')} |",
        f"| 审计 run_id | `{audit_report.get('audit_run_id', '')}` |",
    ]
    src = (source_outcome or {}).get("run_id") or audit_report.get("source_run_id")
    if src:
        lines.append(f"| 辩论来源 run_id | `{src}` |")
    lines.extend([
        f"| 综合风险定级 | **{label}（{level}）** |",
        f"| 交易建议可行性 | {audit_report.get('tradability', '')} |",
        "",
        "本意见书由 Quant Asst 红队审计 Agent 独立产出，不参与多空辩论，仅做风险定级；"
        "仅用于研究与教育，不构成投资建议。",
        "",
    ])
    if banner:
        lines.extend([banner, ""])

    lines.append("## 审计结论\n")
    lines.append(f"{audit_report.get('summary', '')}\n")

    findings = _sort_findings(audit_report.get("findings") or [])
    lines.append(f"## 审计发现（{len(findings)} 条）\n")
    if not findings:
        lines.extend(["未发现需登记的风险条目。", ""])
    for i, f in enumerate(findings, start=1):
        sev = f.get("severity", "")
        lines.append(f"### {i}. [{sev.upper()}] {f.get('title', '')}\n")
        lines.extend([
            f"- 风险类别：`{f.get('category', '')}`",
            f"- 严重级别：{sev}",
            f"- 问题描述：{f.get('description', '')}",
            f"- 支撑证据：{f.get('evidence', '')}",
            f"- 处置建议：{f.get('recommendation', '')}",
            "",
        ])

    lines.append("## 风险定级说明\n")
    lines.extend([
        "| 级别 | 含义 |",
        "| --- | --- |",
        "| 低（low） | 常规可控风险，按既定流程处置 |",
        "| 中（medium） | 存在明确缺陷，须修复后复验 |",
        "| 高（high） | 关键风险，触发约束边界与报告顶部显著标注 |",
        "| 致命（critical） | 阻断性缺陷，禁止生成交易建议 |",
        "",
    ])
    return "\n".join(lines)


def write_audit_report(
    audit_report: dict[str, Any],
    out_dir,
    ticker: str,
    timestamp: str,
    source_outcome: dict[str, Any] | None = None,
) -> str:
    """渲染并落盘红队审计意见书到 ``<out_dir>/audit/audit_{ticker}_{timestamp}.md``。

    Args:
        audit_report: ``AuditReport.model_dump()`` 字典。
        out_dir: 交付物根目录（默认 ``./output``）。
        ticker: 标的统一 symbol（``cn:300750``），落盘时转为文件名安全形式。
        timestamp: 时间戳串（``YYYYMMDD_HHMMSS``）。
        source_outcome: 被审计的辩论纪要（可选）。
    """
    from pathlib import Path

    target = Path(out_dir)
    target.mkdir(parents=True, exist_ok=True)
    safe_ticker = _sanitize_ticker(ticker or audit_report.get("symbol", "unknown"))
    path = target / f"audit_{safe_ticker}_{timestamp}.md"
    path.write_text(render_audit_markdown(audit_report, source_outcome), encoding="utf-8")
    return str(path)


def render_final_markdown(final_report: dict[str, Any]) -> str:
    """把 FinalAnalysisReport 渲染为最终量化分析报告（Markdown，无 emoji 工程文档风）。

    高风险及以上级别时，在报告顶部显著标注风险提示并强制列出约束边界。
    """
    gate = final_report.get("risk_gate") or {}
    level = final_report.get("overall_risk_level", "low")
    label = _AUDIT_RISK_LABELS.get(level, level)
    blocked = final_report.get("final_decision") == "blocked"

    lines: list[str] = [f"# 最终量化分析报告：{final_report.get('symbol', '')}", ""]

    # ---- 顶部风险提示（致命/高风险显著标注）----
    if gate.get("risk_banner"):
        lines.extend([f"> **{gate['risk_banner']}**", ""])
    constraints = gate.get("constraint_boundaries") or []
    if constraints:
        lines.append("**约束边界（强制）**\n")
        lines.extend(f"- {c}" for c in constraints)
        lines.append("")

    if blocked:
        # blocked 可能来自 critical，也可能来自 tradability=prohibited；
        # 文案据实说明触发路径，不写死「致命」。
        trigger = (
            "综合风险定级为致命（critical）"
            if final_report.get("overall_risk_level") == "critical"
            else "交易可行性被判定为禁止（prohibited）"
        )
        lines.extend([
            f"> **本报告已拦截交易建议生成**：{trigger}，"
            "在缺陷修复并重新通过红队审计前，不输出任何可执行交易建议。",
            "",
        ])

    lines.extend([
        "| 项目 | 内容 |",
        "| --- | --- |",
        f"| 标的 | `{final_report.get('symbol', '')}` |",
        f"| 市场 | {final_report.get('market', '')} |",
        f"| 策略 | {final_report.get('strategy_name', '')} |",
        f"| 辩论 run_id | `{final_report.get('debate_run_id', '')}` |",
        f"| 审计 run_id | `{final_report.get('audit_run_id', '')}` |",
        f"| 综合风险定级 | **{label}（{level}）** |",
        f"| 最终决策 | **{final_report.get('final_decision', '')}** |",
        f"| 策略可信度 | {final_report.get('credibility_score', 'N/A')} / 100 |",
        "",
        "本报告由 Quant Asst 风控综合官在「多空辩论 + 红队审计」之后产出，"
        "仅用于研究与教育，不构成投资建议。",
        "",
    ])

    lines.extend(["## 执行摘要\n", f"{final_report.get('executive_summary', '')}", ""])

    kf = final_report.get("key_findings") or []
    lines.append(f"## 关键风险发现（{len(kf)} 条）\n")
    lines.extend(f"- {k}" for k in kf or ["（无）"])
    lines.append("")

    rec = final_report.get("recommendations") or []
    lines.append(f"## 改进建议（{len(rec)} 条）\n")
    lines.extend(f"- {r}" for r in rec or ["（无）"])
    lines.append("")

    advisory = final_report.get("trade_advisory") or ""
    lines.append("## 交易建议\n")
    # blocked 时门控写入拦截说明文案，直接呈现；仅当为空才用占位
    if not advisory:
        lines.append(
            "（无：致命风险已拦截交易建议生成，或当前风险级别未给出可执行建议。）"
        )
    else:
        lines.append(advisory)
    lines.append("")
    return "\n".join(lines)


def write_final_report(
    final_report: dict[str, Any], out_dir, ticker: str, timestamp: str
) -> str:
    """渲染并落盘最终量化分析报告到 ``<out_dir>/audit/final_{ticker}_{timestamp}.md``。

    与审计报告同目录（``./output/audit/``），便于 GitHub Demo 一次性展示审计与最终结论。
    """
    from pathlib import Path

    target = Path(out_dir)
    target.mkdir(parents=True, exist_ok=True)
    safe_ticker = _sanitize_ticker(ticker or final_report.get("symbol", "unknown"))
    path = target / f"final_{safe_ticker}_{timestamp}.md"
    path.write_text(render_final_markdown(final_report), encoding="utf-8")
    return str(path)


# ---------------------------------------------------------------------------
# 参数网格寻优报告（Step J）
# ---------------------------------------------------------------------------

#: 劣化判定阈值（与 backtest/optimizer.py 常量保持一致，报告须原样披露口径）
_OPTIMIZATION_SHARPE_RATIO = 0.5
_OPTIMIZATION_DRAWDOWN_EXTRA = 0.10

#: 选优/对照指标默认值（与 backtest/optimizer.py 常量一致，避免循环导入）
_OPTIMIZATION_PRIMARY_METRIC = "sharpe"
_OPTIMIZATION_COMPARISON_METRIC = "total_return"


def _fmt_num(v: float | int | None, digits: int = 3) -> str:
    """数值展示：None -> N/A；整数原样；浮点按指定位数。"""
    if v is None:
        return "N/A"
    if isinstance(v, int):
        return str(v)
    return f"{v:.{digits}f}"


def _fmt_metric(field: str, value: float | int | None) -> str:
    """按指标语义格式化：收益类带符号百分比、回撤百分比、其余数值。"""
    if field in ("total_return", "annual_return"):
        return _signed_pct(value)
    if field == "max_drawdown":
        return _pct(value)
    return _fmt_num(value)


def _optimization_param_keys(result: dict[str, Any]) -> list[str]:
    """取参数字段顺序（与网格声明顺序一致，保证报告确定性）。"""
    return [str(k) for k in (result.get("grid") or {}).keys()]


def render_optimization_markdown(result: dict[str, Any]) -> str:
    """把 :func:`backtest.optimizer.optimize_grid` 的结果渲染为 Markdown 寻优报告。

    风格与其他报告一致：工程文档风、无 emoji。包含全组合样本内/样本外对比表、
    样本内最优组合、样本外验证结论与明确的过拟合提示（劣化时原样标注 degraded）。
    """
    grid = result.get("grid") or {}
    param_keys = _optimization_param_keys(result)

    def _grid_desc() -> str:
        parts = []
        for key, values in grid.items():
            joined = ", ".join(str(v) for v in values)
            parts.append(f"{key} ∈ {{{joined}}}")
        return "; ".join(parts) or "（无）"

    combos = result.get("combinations") or []
    best_index = result.get("best_index")
    best = combos[best_index] if isinstance(best_index, int) and 0 <= best_index < len(combos) else {}
    best_in = best.get("in_sample") or {}
    best_out = best.get("out_sample") or {}
    best_overall = best.get("overall") or {}

    # ---- 准入与对照排名（确定性）----
    ineligible_by_index = {
        int(item["index"]): item for item in (result.get("ineligible") or [])
    }
    eligible_indexes = result.get("eligible_indexes")
    if eligible_indexes is None:  # 兼容旧结构：未标记者即视为合格
        eligible_indexes = [
            int(row.get("index", -1)) for row in combos
            if int(row.get("index", -1)) not in ineligible_by_index
        ]
    eligible_set = set(int(i) for i in eligible_indexes)

    def _return_rank_key(row: dict[str, Any]) -> tuple:
        value = (row.get("in_sample") or {}).get(
            result.get("comparison_metric", _OPTIMIZATION_COMPARISON_METRIC)
        )
        return (
            float("inf") if value is None else -float(value),
            repr(sorted((row.get("params") or {}).items())),
        )

    return_ranked = sorted(
        (row for row in combos if int(row.get("index", -1)) in eligible_set),
        key=_return_rank_key,
    )
    return_rank = {int(row["index"]): pos + 1 for pos, row in enumerate(return_ranked)}

    lines: list[str] = [
        f"# 参数网格寻优报告：{result.get('symbol', '')}",
        "",
        "| 项目 | 内容 |",
        "| --- | --- |",
        f"| 标的 | `{result.get('symbol', '')}` |",
        f"| 市场 | {result.get('market', '')} |",
        f"| 回测区间 | {result.get('period_start', '')} ~ {result.get('period_end', '')} |",
        f"| 样本内占比 | {float(result.get('train_ratio', 0.7)):.1%}"
        f"（样本外起点 {result.get('out_sample_start') or 'N/A'}） |",
        f"| 参数网格 | {_grid_desc()} |",
        f"| 组合数 | {result.get('n_combinations', len(combos))} |",
        f"| 选优指标 | 样本内 {result.get('selection_metric', _OPTIMIZATION_PRIMARY_METRIC)}"
        f"（固定主指标）；对照指标：样本内 "
        f"{result.get('comparison_metric', _OPTIMIZATION_COMPARISON_METRIC)} |",
        f"| 准入门槛 | 样本内成交笔数 ≥ "
        f"{result.get('min_in_sample_trades', 5)} 笔，不足者不参与选优 |",
        f"| 初始资金 | ¥{float(result.get('initial_capital', 0.0)):,.0f} |",
        f"| 沙箱模式 | {result.get('sandbox_mode', '')} |",
        "",
        "本报告由 Quant Asst 参数网格寻优流程自动生成，仅用于研究与教育，不构成投资建议。"
        "寻优过程为纯确定性网格遍历，不调用任何 LLM。",
        "",
    ]

    # ---- 全组合对比表 ----
    lines.append(f"## 全组合样本内 / 样本外指标对比（{len(combos)} 组）\n")
    header = ["#", *param_keys, "资格", "总收益排名",
              "样本内总收益", "样本外总收益",
              "样本内年化", "样本外年化",
              "样本内最大回撤", "样本外最大回撤",
              "样本内夏普", "样本外夏普",
              "样本内笔数", "样本外笔数"]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("| " + " | ".join(["---"] * len(header)) + " |")
    for row in combos:
        in_m = row.get("in_sample") or {}
        out_m = row.get("out_sample") or {}
        params = row.get("params") or {}
        index = int(row.get("index", -1))
        cells = [str(index), *(str(params.get(k, "")) for k in param_keys)]
        cells += [
            "不合格" if index in ineligible_by_index else "合格",
            str(return_rank[index]) if index in return_rank else "-",
            _signed_pct(in_m.get("total_return")), _signed_pct(out_m.get("total_return")),
            _signed_pct(in_m.get("annual_return")), _signed_pct(out_m.get("annual_return")),
            _pct(in_m.get("max_drawdown")), _pct(out_m.get("max_drawdown")),
            _fmt_num(in_m.get("sharpe")), _fmt_num(out_m.get("sharpe")),
            _fmt_num(in_m.get("n_trades")), _fmt_num(out_m.get("n_trades")),
        ]
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")

    # ---- 不参与选优的组合 ----
    lines.append("## 不参与选优的组合（样本内成交笔数不足）\n")
    if not ineligible_by_index:
        lines.extend(["全部组合均满足准入门槛。", ""])
    else:
        lines.append("| # | 参数 | 样本内笔数 | 原因 |")
        lines.append("| --- | --- | --- | --- |")
        for item in sorted(ineligible_by_index.values(), key=lambda x: int(x["index"])):
            param_text = ", ".join(f"{k}={v}" for k, v in (item.get("params") or {}).items())
            lines.append(
                f"| {item['index']} | {param_text} | "
                f"{_fmt_num(item.get('in_sample_n_trades'))} | {item.get('reason', '')} |"
            )
        lines.append("")

    # ---- 最优组合 ----
    selection_metric = result.get("selection_metric", _OPTIMIZATION_PRIMARY_METRIC)
    comparison_metric = result.get("comparison_metric", _OPTIMIZATION_COMPARISON_METRIC)
    lines.append(f"## 最优组合（按样本内 {selection_metric} 选定）\n")
    if not best:
        lines.extend(["（无有效组合）", ""])
    else:
        lines.append("| 参数 | 取值 |")
        lines.append("| --- | --- |")
        for key in param_keys:
            lines.append(f"| {key} | {best.get('params', {}).get(key, '')} |")
        lines.append("")
        lines.append("### 最优组合指标\n")
        lines.append("| 指标 | 全区间 | 样本内 | 样本外 |")
        lines.append("| --- | --- | --- | --- |")
        for field, label in (
            ("total_return", "总收益"), ("annual_return", "年化收益"),
            ("max_drawdown", "最大回撤"), ("sharpe", "夏普比率"),
            ("win_rate", "按笔胜率"), ("n_trades", "成交笔数"),
        ):
            lines.append(
                f"| {label} | {_fmt_metric(field, best_overall.get(field))} "
                f"| {_fmt_metric(field, best_in.get(field))} "
                f"| {_fmt_metric(field, best_out.get(field))} |"
            )
        lines.append("")

        return_best_index = result.get("return_best_index")
        lines.append("### 选优指标对照（并列呈现，不做加权综合）\n")
        lines.append(f"- 主指标（样本内 {selection_metric}）选定：组合 #{best_index}")
        lines.append(
            f"- 按样本内 {comparison_metric} 排序首位：组合 #{return_best_index}"
        )
        agreement = result.get("metric_agreement")
        if agreement is True:
            lines.append("- 结论：两个指标指向同一组合，结论一致。")
        elif agreement is False:
            lines.append(
                "- 结论：两个指标**指向不同组合，结论冲突**；上表已并列呈现，"
                "本流程不做加权综合，请结合样本外表现与红队审计人工判断。"
            )
        lines.append("")

    # ---- 防泄漏声明 ----
    lines.extend([
        "## 防泄漏声明",
        "",
        f"- 切分点在寻优开始前一次性固定：样本内占比 "
        f"{float(result.get('train_ratio', 0.7)):.1%}，样本外起点 "
        f"{result.get('out_sample_start') or 'N/A'}；全部分组合共用同一切分点，"
        "执行时已校验各组合样本外起点一致。",
        "- 网格遍历与选优仅使用样本内指标；样本外指标仅在选出最优组合后的最终验证中"
        "使用一次（劣化判定），不参与任何筛选或排序。",
        "- 寻优过程为纯确定性网格遍历，不调用任何 LLM，不使用随机数。",
        "",
    ])

    # ---- 样本外验证结论 ----
    lines.append("## 样本外验证结论\n")
    degraded = bool(result.get("degraded"))
    reasons = result.get("degradation_reasons") or []
    if degraded:
        lines.append("> **判定：degraded（样本外表现显著劣于样本内）**\n")
        lines.extend(f"- 触发原因：{r}" for r in reasons)
    else:
        lines.append("> **判定：未触发劣化阈值**（样本外未显著劣于样本内）\n")
        lines.append("- 本次最优组合的样本外指标未跌破下述任一阈值。")
    lines.extend([
        "",
        "### 劣化判定口径（确定性阈值）",
        "",
        f"- 样本内夏普为正且样本外夏普低于样本内的 {_OPTIMIZATION_SHARPE_RATIO:.0%}；",
        "- 样本内总收益为正而样本外总收益非正（符号翻转）；",
        f"- 样本外最大回撤比样本内更深超过 {_OPTIMIZATION_DRAWDOWN_EXTRA:.0%}。",
        "",
        "### 过拟合提示",
        "",
        "网格寻优按**样本内**指标挑出最优组合，本质是对同一批数据反复试参，"
        "样本内指标天然被高估；样本外未显著劣化只能说明该组合在既有切分下尚未暴露问题，"
        "**不能排除过拟合**。任何进入实盘讨论的参数仍须使用完全独立的样本外区间复验，"
        "并通过红队审计（未来函数 / 幸存者偏差 / 成本敏感性）确认。",
        "",
    ])
    return "\n".join(lines)


def write_optimization_report(result: dict[str, Any], out_dir) -> str:
    """渲染并落盘寻优报告到 ``<out_dir>/optimization/optimization_<symbol>_<start>_<end>.md``。

    文件名**不含时间戳**：同一输入重复运行必然生成同名同内容文件（确定性约定）。
    """
    from pathlib import Path

    target = Path(out_dir) / "optimization"
    target.mkdir(parents=True, exist_ok=True)
    safe_symbol = _sanitize_ticker(result.get("symbol", "unknown"))
    name = f"optimization_{safe_symbol}_{result.get('period_start', 'na')}_{result.get('period_end', 'na')}.md"
    path = target / name
    path.write_text(render_optimization_markdown(result), encoding="utf-8")
    return str(path)
