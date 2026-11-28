"""多模型辩论对比报告（Step L；走 Step K 双语 i18n 目录）。

把 :func:`core.comparison.run_model_comparison` 的总结果渲染为一份 Markdown
对比报告：各模型裁决 / 风险 / 交易建议对比表、跳过模型标注、一致 / 分歧汇总
（分歧单独列出，**不做加权仲裁**）。静态文案全部取自 :mod:`core.i18n` 的
``cmp.*`` 键（zh/en 键集合一致，由 ``tests/test_report_i18n.py`` 守护）；
``lang`` 缺省 ``zh``，默认行为与历史一致。

确定性约定：报告只呈现编排结果（逐模型结果 + 一致 / 分歧汇总），不含 wall-clock
等运行期变量；mock 下耗时恒 0.0，故同一输入两次运行渲染结果逐字一致。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.comparison import ComparisonResult
from core.i18n import (
    format_message,
    normalize_report_language,
    risk_level_display,
    t,
)


def _elapsed_text(comparison: ComparisonResult, r: Any, lang: str) -> str:
    """耗时展示（秒，保留 1 位；mock 下恒 0.0 -> 确定性）。"""
    seconds = f"{float(getattr(r, 'elapsed_seconds', 0.0)):.1f}"
    return format_message("cmp.elapsed_value", lang, seconds=seconds)


def _tokens_text(r: Any, lang: str) -> str:
    """token 用量展示：输入 + 输出（合计），无记录则 N/A。"""
    usage = getattr(r, "usage") or {}
    prompt = usage.get("prompt_tokens", 0)
    completion = usage.get("completion_tokens", 0)
    total = usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0)
    if not usage:
        return t("cmp.tokens_na", lang)
    return format_message(
        "cmp.tokens_value", lang, prompt=prompt, completion=completion, total=total
    )


def _advisory_cell(r: Any, lang: str) -> str:
    """交易建议门控展示：放行 / 拦截（取各模型门控结论，语言随 ``lang``）。"""
    return t("cmp.advisory_allowed", lang) if r.advisory_allowed else t("cmp.advisory_blocked", lang)


def _dimension_values(comparison: ComparisonResult, getter: Any) -> list[tuple[str, str]]:
    """按某维度取各成功模型的取值（模型名, 取值）列表，保序。"""
    out: list[tuple[str, str]] = []
    for r in comparison.ok_models:
        out.append((r.model, str(getter(r))))
    return out


def _summarize_dimensions(comparison: ComparisonResult, lang: str) -> list[str]:
    """生成「一致 / 分歧」汇总行：逐维度比较各成功模型取值，差异单独列出、不做加权。

    三个对比维度：最终决策 / 综合风险 / 交易建议门控。某维度各模型取值相同 -> 进
    「一致」清单（附取值）；不同 -> 进「分歧」清单（附各模型取值）。全部成功模型
    不足 2 个时无法比较，两清单均标注无法对比。
    """
    lines: list[str] = []
    ok = comparison.ok_models
    dims: list[tuple[str, Any]] = [
        (t("cmp.dim.decision", lang), lambda r: r.decision),
        (t("cmp.dim.risk", lang), lambda r: r.risk_level),
        (t("cmp.dim.advisory", lang), lambda r: _advisory_cell(r, lang)),
    ]
    consistent: list[str] = []
    disagreements: list[str] = []
    for label, getter in dims:
        values = _dimension_values(comparison, getter)
        distinct = sorted({v for _, v in values})
        if len(ok) >= 2 and len(distinct) == 1:
            consistent.append(format_message("cmp.consistent_line", lang, field=label, value=distinct[0]))
        elif len(ok) >= 2 and len(distinct) > 1:
            values_text = "；".join(f"{m}={v}" for m, v in values)
            disagreements.append(format_message("cmp.disagreement_line", lang, field=label, values=values_text))
        # 成功模型不足 2 个：无法做模型间比较，该维度既不一致也不分歧（不臆断）

    lines.append(f"{t('cmp.consistent_label', lang)}\n")
    lines.extend(consistent or [t("cmp.no_consistent", lang)])
    lines.append("")
    lines.append(f"{t('cmp.disagreements_label', lang)}\n")
    if disagreements:
        lines.extend(disagreements)
    else:
        lines.append(t("cmp.no_disagreement", lang))
    lines.append("")
    return lines


def render_comparison_markdown(comparison: ComparisonResult, lang: str | None = None) -> str:
    """把 :class:`ComparisonResult` 渲染为 Markdown 多模型对比报告。

    Args:
        comparison: 多模型对比总结果。
        lang: 报告语言（``zh`` 默认 / ``en``）；见 :mod:`core.i18n`。

    Returns:
        Markdown 文本（UTF-8）。
    """
    lang = normalize_report_language(lang)
    colon = t("punct.colon", lang)

    lines: list[str] = [
        format_message("cmp.title", lang, symbol=comparison.symbol or ""),
        "",
        f"| {t('common.item', lang)} | {t('common.value', lang)} |",
        "| --- | --- |",
        f"| {t('cmp.meta.symbol', lang)} | `{comparison.symbol or ''}` |",
        f"| {t('cmp.meta.market', lang)} | {comparison.market or ''} |",
        f"| {t('cmp.meta.strategy_desc', lang)} | {comparison.user_input or ''} |",
        f"| {t('cmp.meta.rounds', lang)} | {comparison.rounds} |",
        f"| {t('cmp.meta.models', lang)} | {', '.join(comparison.models) or t('common.none_paren', lang)} |",
        f"| {t('cmp.meta.mode', lang)} | "
        f"{t('cmp.mode.mock', lang) if comparison.mode == 'mock' else t('cmp.mode.real', lang)} |",
        f"| {t('cmp.meta.run_id', lang)} | `{comparison.run_id}` |",
        "",
        t("cmp.disclaimer", lang),
        "",
    ]

    # ---- 逐模型对比表 ----
    ok = comparison.ok_models
    lines.append(format_message("cmp.compare_title", lang, n=len(comparison.models)) + "\n")
    if not ok:
        lines.extend([t("cmp.all_skipped", lang), ""])
    else:
        header = [
            t("cmp.col.model", lang),
            t("cmp.col.decision", lang),
            t("cmp.col.risk", lang),
            t("cmp.col.credibility", lang),
            t("cmp.col.advisory", lang),
            t("cmp.col.elapsed", lang),
            t("cmp.col.tokens", lang),
        ]
        lines.append("| " + " | ".join(header) + " |")
        lines.append("| " + " | ".join(["---"] * len(header)) + " |")
        for r in ok:
            credibility = r.final_report.get("credibility_score", t("common.na", lang))
            risk = r.risk_level or t("common.na", lang)
            lines.append(
                "| "
                + " | ".join(
                    [
                        r.model,
                        r.decision or t("common.na", lang),
                        risk_level_display(risk, lang),
                        str(credibility),
                        _advisory_cell(r, lang),
                        _elapsed_text(comparison, r, lang),
                        _tokens_text(r, lang),
                    ]
                )
                + " |"
            )
        lines.append("")

    # ---- 跳过模型 ----
    skipped = comparison.skipped
    lines.append(f"{format_message('cmp.skipped_title', lang, n=len(skipped))}\n")
    if not skipped:
        lines.extend([t("cmp.skipped_none", lang), ""])
    else:
        for r in skipped:
            lines.append(format_message("cmp.skipped_line", lang, model=r.model, reason=r.reason or "-"))
        lines.append("")

    # ---- 一致 / 分歧汇总 ----
    lines.append(f"{t('cmp.agreement_title', lang)}\n")
    lines.extend(_summarize_dimensions(comparison, lang))

    lines.append("")
    return "\n".join(lines)


def write_comparison_report(
    comparison: ComparisonResult, out_dir: Path | str, lang: str | None = None
) -> str:
    """渲染并落盘多模型对比报告到 ``<out_dir>/comparison/<run_id>/comparison.md``。

    与各模型独立产物（``models/<slug>/``）同目录，便于一次展示对比全貌。
    文件名不含 wall-clock：同一输入两次运行生成同名同内容文件（确定性约定）。
    返回报告路径。
    """
    from core.comparison import COMPARISON_DIR_NAME

    root = Path(out_dir) / COMPARISON_DIR_NAME / comparison.run_id
    root.mkdir(parents=True, exist_ok=True)
    path = root / "comparison.md"
    path.write_text(render_comparison_markdown(comparison, lang), encoding="utf-8")
    return str(path)
