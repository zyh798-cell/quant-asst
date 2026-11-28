"""Markdown 报告渲染（Step 4 辩论纪要；Step 5 审计/最终报告；Step J 寻优；Step K 双语）。

风格约定（面向 GitHub Demo）：专业工程文档风格 —— **不使用任何 emoji 或装饰符号**，
标题层级规范、表格与代码块简洁、语言严谨客观。

双语（Step K）：所有静态文案取自 :mod:`core.i18n` 集中式目录，渲染代码不内联硬编码
文案；``lang`` 缺省为 ``zh``，默认行为与历史产物逐字一致。数字与日期格式不随语言变化。
"""

from __future__ import annotations

from typing import Any

from core.i18n import (
    format_message,
    normalize_report_language,
    risk_label,
    risk_level_display,
    t,
)


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


def _fmt_points(points: list[dict], lang: str) -> list[str]:
    out = []
    for i, p in enumerate(points or []):
        ev = (p.get("evidence") or "").replace("\n", " ")
        out.append(format_message(
            "debate.point_line", lang,
            i=i + 1,
            claim=p.get("claim", ""),
            evidence_type=p.get("evidence_type", ""),
            evidence=ev,
        ))
    return out or [t("common.none_paren", lang)]


def render_debate_markdown(outcome: dict[str, Any], lang: str | None = None) -> str:
    """把 DebateOutcome 渲染为 Markdown 辩论报告。

    Args:
        outcome: ``DebateOutcome.model_dump()`` 字典。
        lang: 报告语言（``zh`` 默认 / ``en``）；见 :mod:`core.i18n`。

    Returns:
        Markdown 文本（UTF-8）。
    """
    lang = normalize_report_language(lang)
    colon = t("punct.colon", lang)
    meta_lines = [
        format_message("debate.title", lang, symbol=outcome.get('symbol', '')),
        "",
        f"| {t('common.item', lang)} | {t('common.value', lang)} |",
        "| --- | --- |",
        f"| {t('debate.meta.symbol', lang)} | `{outcome.get('symbol', '')}` |",
        f"| {t('debate.meta.market', lang)} | {outcome.get('market', '')} |",
        f"| {t('debate.meta.strategy_desc', lang)} | {outcome.get('user_input', '')} |",
        f"| {t('debate.meta.rounds', lang)} | {outcome.get('rounds', 0)} |",
        f"| {t('debate.meta.run_id', lang)} | `{outcome.get('run_id', '')}` |",
        "",
        t("debate.disclaimer", lang),
        "",
    ]

    sections: list[str] = ["\n".join(meta_lines), f"\n{t('debate.transcripts_title', lang)}\n"]

    transcripts = outcome.get("round_transcripts") or []
    if not transcripts:
        sections.append(f"{t('debate.no_transcripts', lang)}\n")
    for tr in transcripts:
        round_no = tr.get("round", 0)
        bull = tr.get("bull") or {}
        bear = tr.get("bear") or {}
        risk = tr.get("risk_check") or {}

        sections.append(format_message("debate.round_heading", lang, round_no=round_no) + "\n")
        sections.append(f"{t('debate.bull_stance', lang)}\n")
        sections.append(f"> {bull.get('stance', '')}\n")
        sections.extend(_fmt_points(bull.get("points") or [], lang))
        if bull.get("assumptions"):
            sections.append("")
            sections.append(t("debate.assumptions_prefix", lang) + "；".join(bull["assumptions"]))
        sections.append("")

        sections.append(f"{t('debate.bear_stance', lang)}\n")
        sections.append(f"> {bear.get('stance', '')}\n")
        sections.extend(_fmt_points(bear.get("points") or [], lang))
        if bear.get("failure_scenarios"):
            sections.append("")
            sections.append(
                t("debate.failure_scenarios_prefix", lang) + "；".join(bear["failure_scenarios"])
            )
        sections.append("")

        sections.append(f"{t('debate.risk_check_title', lang)}\n")
        sections.append(f"- {t('debate.data_validity_label', lang)}{colon}{risk.get('data_validity', '')}")
        findings = risk.get("findings") or []
        if findings:
            sections.append(f"- {t('debate.findings_label', lang)}{colon}")
            for f in findings:
                sections.append(format_message(
                    "debate.finding_line", lang,
                    severity=f.get("severity", ""),
                    target_side=f.get("target_side", ""),
                    issue=f.get("issue", ""),
                    falsifiable=f.get("falsifiable", ""),
                ))
        sections.append(format_message(
            "debate.kept_points_line", lang,
            bull=risk.get("kept_bull_points", []),
            bear=risk.get("kept_bear_points", []),
        ))
        sections.append(
            f"- {t('debate.recommendation_label', lang)}{colon}"
            f"{risk.get('recommendation', '')}\n"
        )

    verdict = outcome.get("verdict") or {}
    sections.append(f"{t('debate.verdict_title', lang)}\n")
    sections.append(f"| {t('common.item', lang)} | {t('common.value', lang)} |")
    sections.append("| --- | --- |")
    sections.append(
        f"| {t('debate.credibility_label', lang)} | "
        f"{verdict.get('credibility_score', t('common.na', lang))} / 100 |"
    )
    sections.append(f"| {t('debate.decision_label', lang)} | {verdict.get('decision', '')} |")
    sections.append("")
    sections.append(f"{t('debate.rationale_label', lang)}{verdict.get('rationale', '')}\n")

    consensus = verdict.get("consensus") or []
    disagreements = verdict.get("disagreements") or []
    sections.append(f"{t('debate.consensus_label', lang)}\n")
    sections.extend(f"- {c}" for c in consensus or [t("common.none_paren", lang)])
    sections.append("")
    sections.append(f"{t('debate.disagreements_label', lang)}\n")
    sections.extend(f"- {d}" for d in disagreements or [t("common.none_paren", lang)])
    sections.append("")

    revision = verdict.get("revision") or {}
    sections.append(f"{t('debate.revision_title', lang)}\n")
    if revision:
        sections.append(
            f"{t('debate.revised_strategy_label', lang)}{revision.get('revised_strategy_text', '')}\n"
        )
        sections.append(f"- {t('debate.entry_rule_label', lang)}{colon}{revision.get('entry_rule', '')}")
        sections.append(f"- {t('debate.exit_rule_label', lang)}{colon}{revision.get('exit_rule', '')}")
        params = revision.get("params") or {}
        if params:
            param_str = "、".join(f"{k}={v}" for k, v in params.items())
            sections.append(f"- {t('debate.params_label', lang)}{colon}{param_str}")
        sections.append(
            f"- {t('debate.expected_effect_label', lang)}{colon}"
            f"{revision.get('expected_effect', '')}\n"
        )
        sections.append(t("debate.usage_hint", lang))
        sections.append("")
        sections.append("```bash")
        sections.append(f'uv run python cli.py run "{revision.get("revised_strategy_text", "")}"')
        sections.append("```")
    else:
        sections.append(t("debate.no_revision", lang))

    sections.append("")
    return "\n".join(sections)


def write_debate_report(outcome: dict[str, Any], out_dir, lang: str | None = None) -> str:
    """渲染并落盘辩论 Markdown 报告到 ``<out_dir>/debate_reports/<run_id>.md``。"""
    from pathlib import Path

    target = Path(out_dir) / "debate_reports"
    target.mkdir(parents=True, exist_ok=True)
    path = target / f"{outcome.get('run_id', 'debate')}.md"
    path.write_text(render_debate_markdown(outcome, lang), encoding="utf-8")
    return str(path)


# ---------------------------------------------------------------------------
# 红队审计报告 + 最终量化分析报告（Step 5）
# ---------------------------------------------------------------------------

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
    audit_report: dict[str, Any],
    source_outcome: dict[str, Any] | None = None,
    lang: str | None = None,
) -> str:
    """把 AuditReport 渲染为红队审计意见书（Markdown，无 emoji 工程文档风）。

    Args:
        audit_report: ``AuditReport.model_dump()`` 字典。
        source_outcome: 被审计的 ``DebateOutcome`` dump（可选，用于展示审计来源）。
        lang: 报告语言（``zh`` 默认 / ``en``）。
    """
    lang = normalize_report_language(lang)
    colon = t("punct.colon", lang)
    level = audit_report.get("overall_risk_level", "low")
    label = risk_label(level, lang)
    banner = (
        format_message("audit.banner", lang, label=label)
        if level in ("high", "critical") else ""
    )

    lines: list[str] = [
        format_message("audit.title", lang, symbol=audit_report.get('symbol', '')),
        "",
        f"| {t('common.item', lang)} | {t('common.value', lang)} |",
        "| --- | --- |",
        f"| {t('debate.meta.symbol', lang)} | `{audit_report.get('symbol', '')}` |",
        f"| {t('debate.meta.market', lang)} | {audit_report.get('market', '')} |",
        f"| {t('audit.meta.strategy', lang)} | {audit_report.get('strategy_name', '')} |",
        f"| {t('audit.meta.audit_run_id', lang)} | `{audit_report.get('audit_run_id', '')}` |",
    ]
    src = (source_outcome or {}).get("run_id") or audit_report.get("source_run_id")
    if src:
        lines.append(f"| {t('audit.meta.source_run_id', lang)} | `{src}` |")
    lines.extend([
        f"| {t('audit.meta.overall_risk', lang)} | **{risk_level_display(level, lang)}** |",
        f"| {t('audit.meta.tradability', lang)} | {audit_report.get('tradability', '')} |",
        "",
        t("audit.disclaimer", lang),
        "",
    ])
    if banner:
        lines.extend([banner, ""])

    lines.append(f"{t('audit.conclusion_title', lang)}\n")
    lines.append(f"{audit_report.get('summary', '')}\n")

    findings = _sort_findings(audit_report.get("findings") or [])
    lines.append(format_message("audit.findings_title", lang, n=len(findings)) + "\n")
    if not findings:
        lines.extend([t("audit.no_findings", lang), ""])
    for i, f in enumerate(findings, start=1):
        sev = f.get("severity", "")
        lines.append(format_message(
            "audit.finding_heading", lang, i=i, sev=sev.upper(), title=f.get("title", "")
        ) + "\n")
        lines.extend([
            f"- {t('audit.risk_category', lang)}{colon}`{f.get('category', '')}`",
            f"- {t('audit.severity', lang)}{colon}{sev}",
            f"- {t('audit.description', lang)}{colon}{f.get('description', '')}",
            f"- {t('audit.evidence', lang)}{colon}{f.get('evidence', '')}",
            f"- {t('audit.recommendation', lang)}{colon}{f.get('recommendation', '')}",
            "",
        ])

    lines.append(f"{t('audit.scale_title', lang)}\n")
    lines.append(
        f"| {t('audit.scale_col_level', lang)} | {t('audit.scale_col_meaning', lang)} |"
    )
    lines.append("| --- | --- |")
    for code in ("low", "medium", "high", "critical"):
        lines.append(f"| {risk_level_display(code, lang)} | {t(f'audit.scale.{code}', lang)} |")
    lines.append("")
    return "\n".join(lines)


def write_audit_report(
    audit_report: dict[str, Any],
    out_dir,
    ticker: str,
    timestamp: str,
    source_outcome: dict[str, Any] | None = None,
    lang: str | None = None,
) -> str:
    """渲染并落盘红队审计意见书到 ``<out_dir>/audit/audit_{ticker}_{timestamp}.md``。

    Args:
        audit_report: ``AuditReport.model_dump()`` 字典。
        out_dir: 交付物根目录（默认 ``./output``）。
        ticker: 标的统一 symbol（``cn:300750``），落盘时转为文件名安全形式。
        timestamp: 时间戳串（``YYYYMMDD_HHMMSS``）。
        source_outcome: 被审计的辩论纪要（可选）。
        lang: 报告语言（``zh`` 默认 / ``en``）。
    """
    from pathlib import Path

    target = Path(out_dir)
    target.mkdir(parents=True, exist_ok=True)
    safe_ticker = _sanitize_ticker(ticker or audit_report.get("symbol", "unknown"))
    path = target / f"audit_{safe_ticker}_{timestamp}.md"
    path.write_text(render_audit_markdown(audit_report, source_outcome, lang), encoding="utf-8")
    return str(path)


def render_final_markdown(final_report: dict[str, Any], lang: str | None = None) -> str:
    """把 FinalAnalysisReport 渲染为最终量化分析报告（Markdown，无 emoji 工程文档风）。

    高风险及以上级别时，在报告顶部显著标注风险提示并强制列出约束边界。

    Args:
        final_report: ``FinalAnalysisReport.model_dump()`` 字典。
        lang: 报告语言（``zh`` 默认 / ``en``）。注意 ``risk_gate`` 中的
            banner / 约束边界文案由 :mod:`core.risk_gate` 在产出时已按同一语言生成。
    """
    lang = normalize_report_language(lang)
    colon = t("punct.colon", lang)
    gate = final_report.get("risk_gate") or {}
    level = final_report.get("overall_risk_level", "low")
    blocked = final_report.get("final_decision") == "blocked"

    lines: list[str] = [
        format_message("final.title", lang, symbol=final_report.get('symbol', '')),
        "",
    ]

    # ---- 顶部风险提示（致命/高风险显著标注）----
    if gate.get("risk_banner"):
        lines.extend([f"> **{gate['risk_banner']}**", ""])
    constraints = gate.get("constraint_boundaries") or []
    if constraints:
        lines.append(f"{t('final.constraints_title', lang)}\n")
        lines.extend(f"- {c}" for c in constraints)
        lines.append("")

    if blocked:
        # blocked 可能来自 critical，也可能来自 tradability=prohibited；
        # 文案据实说明触发路径，不写死「致命」。
        trigger_key = (
            "final.trigger_critical"
            if final_report.get("overall_risk_level") == "critical"
            else "final.trigger_prohibited"
        )
        lines.extend([
            format_message("final.blocked_note", lang, trigger=t(trigger_key, lang)),
            "",
        ])

    lines.extend([
        f"| {t('common.item', lang)} | {t('common.value', lang)} |",
        "| --- | --- |",
        f"| {t('debate.meta.symbol', lang)} | `{final_report.get('symbol', '')}` |",
        f"| {t('debate.meta.market', lang)} | {final_report.get('market', '')} |",
        f"| {t('final.meta.strategy', lang)} | {final_report.get('strategy_name', '')} |",
        f"| {t('final.meta.debate_run_id', lang)} | `{final_report.get('debate_run_id', '')}` |",
        f"| {t('final.meta.audit_run_id', lang)} | `{final_report.get('audit_run_id', '')}` |",
        f"| {t('final.meta.overall_risk', lang)} | **{risk_level_display(level, lang)}** |",
        f"| {t('final.meta.decision', lang)} | **{final_report.get('final_decision', '')}** |",
        f"| {t('final.meta.credibility', lang)} | "
        f"{final_report.get('credibility_score', t('common.na', lang))} / 100 |",
        "",
        t("final.disclaimer", lang),
        "",
    ])

    lines.extend([
        f"{t('final.executive_summary_title', lang)}\n",
        f"{final_report.get('executive_summary', '')}",
        "",
    ])

    kf = final_report.get("key_findings") or []
    lines.append(format_message("final.key_findings_title", lang, n=len(kf)) + "\n")
    lines.extend(f"- {k}" for k in kf or [t("common.none_paren", lang)])
    lines.append("")

    rec = final_report.get("recommendations") or []
    lines.append(format_message("final.recommendations_title", lang, n=len(rec)) + "\n")
    lines.extend(f"- {r}" for r in rec or [t("common.none_paren", lang)])
    lines.append("")

    advisory = final_report.get("trade_advisory") or ""
    lines.append(f"{t('final.advisory_title', lang)}\n")
    # blocked 时门控写入拦截说明文案，直接呈现；仅当为空才用占位
    if not advisory:
        lines.append(t("final.no_advisory", lang))
    else:
        lines.append(advisory)
    lines.append("")
    return "\n".join(lines)


def write_final_report(
    final_report: dict[str, Any],
    out_dir,
    ticker: str,
    timestamp: str,
    lang: str | None = None,
) -> str:
    """渲染并落盘最终量化分析报告到 ``<out_dir>/audit/final_{ticker}_{timestamp}.md``。

    与审计报告同目录（``./output/audit/``），便于 GitHub Demo 一次性展示审计与最终结论。
    ``lang`` 为报告语言（``zh`` 默认 / ``en``）。
    """
    from pathlib import Path

    target = Path(out_dir)
    target.mkdir(parents=True, exist_ok=True)
    safe_ticker = _sanitize_ticker(ticker or final_report.get("symbol", "unknown"))
    path = target / f"final_{safe_ticker}_{timestamp}.md"
    path.write_text(render_final_markdown(final_report, lang), encoding="utf-8")
    return str(path)


# ---------------------------------------------------------------------------
# 参数网格寻优报告（Step J；Step K 双语）
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


def render_optimization_markdown(result: dict[str, Any], lang: str | None = None) -> str:
    """把 :func:`backtest.optimizer.optimize_grid` 的结果渲染为 Markdown 寻优报告。

    风格与其他报告一致：工程文档风、无 emoji。包含全组合样本内/样本外对比表、
    样本内最优组合、样本外验证结论与明确的过拟合提示（劣化时原样标注 degraded）。
    ``lang`` 为报告语言（``zh`` 默认 / ``en``）。
    """
    lang = normalize_report_language(lang)
    grid = result.get("grid") or {}
    param_keys = _optimization_param_keys(result)

    def _grid_desc() -> str:
        parts = []
        for key, values in grid.items():
            joined = ", ".join(str(v) for v in values)
            parts.append(f"{key} ∈ {{{joined}}}")
        return "; ".join(parts) or t("common.none_paren", lang)

    combos = result.get("combinations") or []
    best_index = result.get("best_index")
    best = combos[best_index] if isinstance(best_index, int) and 0 <= best_index < len(combos) else {}
    best_in = best.get("in_sample") or {}
    best_out = best.get("out_sample") or {}
    best_overall = best.get("overall") or {}

    selection_metric = result.get("selection_metric", _OPTIMIZATION_PRIMARY_METRIC)
    comparison_metric = result.get("comparison_metric", _OPTIMIZATION_COMPARISON_METRIC)
    train_ratio = float(result.get("train_ratio", 0.7))

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
        value = (row.get("in_sample") or {}).get(comparison_metric)
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
        format_message("opt.title", lang, symbol=result.get('symbol', '')),
        "",
        f"| {t('common.item', lang)} | {t('common.value', lang)} |",
        "| --- | --- |",
        f"| {t('debate.meta.symbol', lang)} | `{result.get('symbol', '')}` |",
        f"| {t('debate.meta.market', lang)} | {result.get('market', '')} |",
        f"| {t('opt.meta.period', lang)} | {result.get('period_start', '')} ~ "
        f"{result.get('period_end', '')} |",
        f"| {t('opt.meta.train_ratio', lang)} | {train_ratio:.1%}"
        + format_message(
            "opt.meta.out_sample_start", lang, start=result.get('out_sample_start') or t('common.na', lang)
        ) + " |",
        f"| {t('opt.meta.grid', lang)} | {_grid_desc()} |",
        f"| {t('opt.meta.combinations', lang)} | {result.get('n_combinations', len(combos))} |",
        f"| {t('opt.meta.selection_metric', lang)} | "
        + format_message(
            "opt.meta.selection_metric_value", lang,
            metric=selection_metric, comparison=comparison_metric,
        ) + " |",
        f"| {t('opt.meta.threshold', lang)} | "
        + format_message(
            "opt.meta.threshold_value", lang,
            n=result.get('min_in_sample_trades', 5),
        ) + " |",
        f"| {t('opt.meta.initial_capital', lang)} | ¥{float(result.get('initial_capital', 0.0)):,.0f} |",
        f"| {t('opt.meta.sandbox', lang)} | {result.get('sandbox_mode', '')} |",
        "",
        t("opt.disclaimer", lang),
        "",
    ]

    # ---- 全组合对比表 ----
    lines.append(format_message("opt.compare_title", lang, n=len(combos)) + "\n")
    header = [
        "#", *param_keys,
        t("opt.col.eligible", lang), t("opt.col.return_rank", lang),
        t("opt.col.in_total", lang), t("opt.col.out_total", lang),
        t("opt.col.in_annual", lang), t("opt.col.out_annual", lang),
        t("opt.col.in_drawdown", lang), t("opt.col.out_drawdown", lang),
        t("opt.col.in_sharpe", lang), t("opt.col.out_sharpe", lang),
        t("opt.col.in_trades", lang), t("opt.col.out_trades", lang),
    ]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("| " + " | ".join(["---"] * len(header)) + " |")
    for row in combos:
        in_m = row.get("in_sample") or {}
        out_m = row.get("out_sample") or {}
        params = row.get("params") or {}
        index = int(row.get("index", -1))
        cells = [str(index), *(str(params.get(k, "")) for k in param_keys)]
        cells += [
            t("opt.cell.ineligible", lang) if index in ineligible_by_index
            else t("opt.cell.eligible", lang),
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
    lines.append(f"{t('opt.ineligible_title', lang)}\n")
    if not ineligible_by_index:
        lines.extend([t("opt.ineligible_none", lang), ""])
    else:
        lines.append(
            f"| # | {t('opt.ineligible_col.params', lang)} | "
            f"{t('opt.ineligible_col.in_trades', lang)} | {t('opt.ineligible_col.reason', lang)} |"
        )
        lines.append("| --- | --- | --- | --- |")
        for item in sorted(ineligible_by_index.values(), key=lambda x: int(x["index"])):
            param_text = ", ".join(f"{k}={v}" for k, v in (item.get("params") or {}).items())
            lines.append(
                f"| {item['index']} | {param_text} | "
                f"{_fmt_num(item.get('in_sample_n_trades'))} | {item.get('reason', '')} |"
            )
        lines.append("")

    # ---- 最优组合 ----
    lines.append(format_message("opt.best_title", lang, metric=selection_metric) + "\n")
    if not best:
        lines.extend([t("opt.no_valid", lang), ""])
    else:
        lines.append(f"| {t('opt.param_col', lang)} | {t('opt.value_col', lang)} |")
        lines.append("| --- | --- |")
        for key in param_keys:
            lines.append(f"| {key} | {best.get('params', {}).get(key, '')} |")
        lines.append("")
        lines.append(f"{t('opt.best_metrics_title', lang)}\n")
        lines.append(
            f"| {t('opt.metric_col', lang)} | {t('opt.overall_col', lang)} | "
            f"{t('opt.in_col', lang)} | {t('opt.out_col', lang)} |"
        )
        lines.append("| --- | --- | --- | --- |")
        for field in (
            "total_return", "annual_return", "max_drawdown",
            "sharpe", "win_rate", "n_trades",
        ):
            lines.append(
                f"| {t(f'opt.metric.{field}', lang)} "
                f"| {_fmt_metric(field, best_overall.get(field))} "
                f"| {_fmt_metric(field, best_in.get(field))} "
                f"| {_fmt_metric(field, best_out.get(field))} |"
            )
        lines.append("")

        return_best_index = result.get("return_best_index")
        lines.append(f"{t('opt.compare_metric_title', lang)}\n")
        lines.append(format_message(
            "opt.primary_selected", lang, metric=selection_metric, index=best_index
        ))
        lines.append(format_message(
            "opt.return_first", lang, metric=comparison_metric, index=return_best_index
        ))
        agreement = result.get("metric_agreement")
        if agreement is True:
            lines.append(t("opt.agree", lang))
        elif agreement is False:
            lines.append(t("opt.conflict", lang))
        lines.append("")

    # ---- 防泄漏声明 ----
    lines.extend([
        f"{t('opt.leak_title', lang)}",
        "",
        format_message(
            "opt.leak.split", lang,
            ratio=f"{train_ratio:.1%}",
            start=result.get('out_sample_start') or t('common.na', lang),
        ),
        t("opt.leak.selection", lang),
        t("opt.leak.deterministic", lang),
        "",
    ])

    # ---- 样本外验证结论 ----
    lines.append(f"{t('opt.oos_title', lang)}\n")
    degraded = bool(result.get("degraded"))
    reasons = result.get("degradation_reasons") or []
    if degraded:
        lines.append(t("opt.degraded", lang) + "\n")
        lines.extend(format_message("opt.degraded_reason", lang, reason=r) for r in reasons)
    else:
        lines.append(t("opt.not_degraded", lang) + "\n")
        lines.append(t("opt.no_threshold_hit", lang))
    lines.extend([
        "",
        f"{t('opt.threshold_title', lang)}",
        "",
        format_message("opt.threshold.sharpe", lang, ratio=f"{_OPTIMIZATION_SHARPE_RATIO:.0%}"),
        t("opt.threshold.sign", lang),
        format_message(
            "opt.threshold.drawdown", lang, extra=f"{_OPTIMIZATION_DRAWDOWN_EXTRA:.0%}"
        ),
        "",
        f"{t('opt.overfit_title', lang)}",
        "",
        t("opt.overfit", lang),
        "",
    ])
    return "\n".join(lines)


def write_optimization_report(result: dict[str, Any], out_dir, lang: str | None = None) -> str:
    """渲染并落盘寻优报告到 ``<out_dir>/optimization/optimization_<symbol>_<start>_<end>.md``。

    文件名**不含时间戳**：同一输入重复运行必然生成同名同内容文件（确定性约定）。
    ``lang`` 为报告语言（``zh`` 默认 / ``en``）。
    """
    from pathlib import Path

    target = Path(out_dir) / "optimization"
    target.mkdir(parents=True, exist_ok=True)
    safe_symbol = _sanitize_ticker(result.get("symbol", "unknown"))
    name = (
        f"optimization_{safe_symbol}_{result.get('period_start', 'na')}_"
        f"{result.get('period_end', 'na')}.md"
    )
    path = target / name
    path.write_text(render_optimization_markdown(result, lang), encoding="utf-8")
    return str(path)
