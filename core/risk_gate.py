"""风控门控（确定性规则，Step 5）。

依据红队审计的综合风险级别，对「是否允许生成交易建议」做**确定性**判定。
本模块不依赖 LLM，保证拦截行为可复现、可单元测试。

**fail-closed 原则**（外部代码 review 要求）：缺失或无法识别的风险等级一律按最高级
``critical`` 处理并告警，**绝不回落为 low**。归一化由 :func:`core.schemas.normalize_risk_level`
统一承担（白名单别名 -> 规范级别；白名单外 / 缺失 -> critical）。

拦截规则（对应需求）：
- 致命（critical）：**禁止生成交易建议** —— ``trade_suggestion_allowed=False``，
  交易建议强制置空，最终决策恒为 ``blocked``，并在报告顶部显著标注风险提示。
- 高风险（high，或不低于 ``threshold`` 的级别）：允许交易建议，但须在报告顶部
  **显著标注风险提示**，并**强制写明约束边界**（``constraint_boundaries`` 非空）。
- 中 / 低（medium / low）：允许交易建议，无强制风险提示。

``threshold`` 参数允许 CLI 在「高风险」默认线之上进一步收紧，例如设为
``medium`` 时，中风险也会触发风险提示与约束边界。致命风险恒被拦截，不受
``threshold`` 影响。

blocked 一致性：只要 ``final_decision == "blocked"``（无论 critical 还是
``tradability == "prohibited"``），交易建议必须清空并写入拦截说明文案，
避免出现「决策已拦截但建议文本仍在输出」的不一致。
"""

from __future__ import annotations

import logging

from core.schemas import RISK_RANK, RiskGate, normalize_risk_level

logger = logging.getLogger("quantsentinel.risk")

#: 默认风险阈值：达到或超过该级别即触发风险提示与约束边界
DEFAULT_RISK_THRESHOLD = "high"

#: blocked 时的交易建议占位文案（替代被清空的建议）
BLOCKED_ADVISORY_TEXT = (
    "（交易建议已被风控门控拦截：本策略存在致命缺陷或明确禁止交易，"
    "禁止生成任何实盘买卖建议）"
)


def _constraints_for(level: str) -> list[str]:
    """按风险级别给出强制约束边界清单（高风险及以上适用）。"""
    base = [
        "本报告仅为研究与教育用途，不构成投资建议，禁止直接用于实盘下单",
        "策略信号须经样本外与滚动窗口复验后方可评估落地",
        "仓位与止损须按标的流动性单独核定，不得套用默认满仓假设",
    ]
    if level == "critical":
        base.insert(0, "存在致命缺陷：在缺陷修复并重新审计前，禁止生成交易建议")
    return base


def _banner_for(level: str) -> str:
    """报告顶部的显著风险提示文本（致命/高风险及以上非空）。"""
    if level == "critical":
        return (
            "风险提示：本策略经红队审计判定为致命风险，已拦截交易建议生成。"
            "在缺陷修复并重新通过审计前，请勿将本报告用于任何实盘决策。"
        )
    if level == "high":
        return "风险提示：本策略存在高风险，须严格遵守下列约束边界后方可评估使用。"
    return ""


def apply_risk_gate(
    audit_report: dict, threshold: str = DEFAULT_RISK_THRESHOLD
) -> RiskGate:
    """把红队审计结果套上门控规则，产出 :class:`RiskGate`。

    Args:
        audit_report: ``AuditReport.model_dump()`` 字典（须含 overall_risk_level）。
        threshold: 触发风险提示/约束边界的最低风险级别（默认 high，可收紧为 medium）。

    Returns:
        确定性门控结论（不由 LLM 决定，保证可复现）。
    """
    level = normalize_risk_level(audit_report.get("overall_risk_level"))
    threshold_rank = RISK_RANK.get(
        normalize_risk_level(threshold), RISK_RANK[DEFAULT_RISK_THRESHOLD]
    )
    rank = RISK_RANK[level]

    allowed = level != "critical"
    banner = ""
    constraints: list[str] = []

    if level == "critical":
        banner = _banner_for("critical")
        constraints = _constraints_for("critical")
    elif rank >= threshold_rank:
        banner = _banner_for("high")
        constraints = _constraints_for(level)

    return RiskGate(
        risk_level=level,
        trade_suggestion_allowed=allowed,
        risk_banner=banner,
        constraint_boundaries=constraints,
    )


def final_decision(audit_report: dict, debate_verdict: dict | None = None) -> str:
    """确定性最终决策：致命风险恒为 blocked，否则沿用辩论裁决。

    Args:
        audit_report: 审计结果（须含 overall_risk_level / tradability）。
        debate_verdict: 辩论裁决 dump（提供 decision 作为放行后的默认决策）。

    Returns:
        adopt | revise | reject | blocked。
    """
    level = normalize_risk_level(audit_report.get("overall_risk_level"))
    if level == "critical" or audit_report.get("tradability") == "prohibited":
        return "blocked"
    if debate_verdict and debate_verdict.get("decision"):
        return debate_verdict["decision"]
    return "revise"


def advisory_for_decision(decision: str, draft_advisory: str = "") -> str:
    """按最终决策产出交易建议文本，保证 blocked 与建议内容一致。

    - ``blocked``：一律返回 :data:`BLOCKED_ADVISORY_TEXT`（拦截说明），
      无论该 blocked 来自 critical 还是 ``tradability == "prohibited"``；
    - 其他决策：保留 LLM 草稿建议（缺省空串）。

    Args:
        decision: ``final_decision`` 的结果。
        draft_advisory: LLM 草稿中的交易建议原文。
    """
    if decision == "blocked":
        logger.warning("最终决策 blocked：交易建议已清空并写入拦截说明")
        return BLOCKED_ADVISORY_TEXT
    return draft_advisory or ""
