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
        "本报告由 QuantSentinel 多智能体辩论流程自动生成，仅用于研究与教育，不构成投资建议。",
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
        "本意见书由 QuantSentinel 红队审计 Agent 独立产出，不参与多空辩论，仅做风险定级；"
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
        lines.extend([
            "> **本报告已拦截交易建议生成**：综合风险定级为致命（critical），"
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
        "本报告由 QuantSentinel 风控综合官在「多空辩论 + 红队审计」之后产出，"
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
    if blocked or not advisory:
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
