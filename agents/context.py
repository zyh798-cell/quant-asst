"""Agent 共享上下文工具：组装辩论材料文本（仅引用工具产出与用户输入）。

硬约束 1 的落地：给 LLM 的「数字类上下文」只能来自 ``backtest_result`` 等
工具产物字段，不允许拼接任何自由生成的预测值。
"""

from __future__ import annotations

from typing import Any


def market_label(market: str) -> str:
    """市场枚举值 -> 中文展示名。"""
    return {
        "cn_stock": "A股",
        "us_stock": "美股",
        "hk_stock": "港股（中国香港市场）",
        "futures": "期货",
        "crypto": "加密货币",
    }.get(market, market)


def backtest_context(state: dict[str, Any]) -> str:
    """从 State 中的回测结果提取上下文；无回测结果时返回明确说明。

    返回的文本只包含 BacktestResult 中已由工具计算并校验的字段。
    """
    br = state.get("backtest_result")
    if not br:
        return (
            "回测上下文：本次辩论未附带回测结果（可先执行 cli.py run 或在 debate 命令传入）。"
        )
    overall = br.get("overall", {})
    in_s = br.get("in_sample", {})
    out_s = br.get("out_sample", {})
    return "\n".join([
        "回测上下文（来自回测引擎，已通过 schema 校验）：",
        f"  标的 {br.get('symbol')} | 区间 {br.get('period_start')} ~ {br.get('period_end')}",
        f"  初始资金 {br.get('initial_capital')} | 期末净值 {br.get('final_equity')}",
        f"  总收益 {overall.get('total_return')} | 年化 {overall.get('annual_return')}"
        f" | 最大回撤 {overall.get('max_drawdown')}",
        f"  夏普 {overall.get('sharpe')} | 按笔胜率 {overall.get('win_rate')}"
        f" | 成交笔数 {overall.get('n_trades')}",
        f"  样本外起点 {br.get('out_sample_start')} | 样本外收益 {out_s.get('total_return')}"
        f" | 样本内收益 {in_s.get('total_return')}",
        f"  累计成本 {br.get('total_cost')}",
    ])


def _fmt_argument(arg: dict | None) -> str:
    """把一份多空观点格式化为可读文本。"""
    if not arg:
        return "（无）"
    lines = [f"观点：{arg.get('stance', '')}"]
    for i, p in enumerate(arg.get("points", [])):
        lines.append(
            f"  论点[{i}] {p.get('claim', '')} | 证据({p.get('evidence_type')})："
            f"{p.get('evidence', '')}"
        )
    for key, label in (("assumptions", "假设前提"), ("failure_scenarios", "失效场景")):
        items = arg.get(key) or []
        if items:
            lines.append(f"  {label}：" + "；".join(str(x) for x in items))
    return "\n".join(lines)


def debate_material(state: dict[str, Any], side: str = "both") -> str:
    """组装待校验/裁决的材料文本。

    Args:
        state: 全局状态。
        side: bull | bear | both —— 需要包含哪些材料。
    """
    parts: list[str] = []
    if side in {"bull", "both"}:
        parts.append("【多头草稿】\n" + _fmt_argument(state.get("bull_draft")))
    if side in {"bear", "both"}:
        parts.append("【空头草稿】\n" + _fmt_argument(state.get("bear_draft")))

    kept_bull = state.get("bull_kept") or []
    kept_bear = state.get("bear_kept") or []
    if kept_bull or kept_bear:
        flat_bull = sorted({i for group in kept_bull for i in group})
        flat_bear = sorted({i for group in kept_bear for i in group})
        parts.append(
            f"【此前已通过校验的多头论点索引】{flat_bull}\n"
            f"【此前已通过校验的空头论点索引】{flat_bear}"
        )
    risk = state.get("risk_verdict")
    if risk:
        findings = "\n".join(
            f"  - [{f.get('severity')}] {f.get('target_side')}: {f.get('issue')}"
            f"（可证伪={f.get('falsifiable')}）"
            for f in risk.get("findings", [])
        )
        parts.append(
            f"【上一轮风控核验】数据有效性：{risk.get('data_validity', '')}\n"
            f"{findings}\n  建议：{risk.get('recommendation', '')}"
        )
    return "\n\n".join(parts)
