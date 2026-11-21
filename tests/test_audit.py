"""Step 5 红队审计 + 风控门控 单元测试。

覆盖：
- AuditReport / RiskGate / FinalAnalysisReport schema 校验；
- 确定性风控门控（致命拦截 / 高风险标注 / 阈值收紧）；
- mock 模式下红队与风控综合官角色 payload 的 schema 合法性；
- 审计图端到端（redteam -> gate -> risk_officer）；
- 审计 / 最终 Markdown 报告渲染与落盘（命名规则、无 emoji、风险提示）。
"""

from __future__ import annotations

import json

import pytest

from core.audit_graph import build_audit_graph
from core.config import Settings
from core.llm import MockCompletionBackend
from core.risk_gate import apply_risk_gate, final_decision
from core.schemas import (
    AuditFinding,
    AuditReport,
    FinalAnalysisReport,
    RiskGate,
)
from report.markdown import (
    render_audit_markdown,
    render_final_markdown,
    write_audit_report,
    write_final_report,
)

# 工程文档风格禁用符号（emoji / 装饰符），用于报告回归断言
_FORBIDDEN = ["🟥", "🟧", "⚠️", "✅", "❌", "📊", "🔴", "🟢", "✨", "🚀", "💡"]


def _mock_settings(tmp_path) -> Settings:
    s = Settings(_env_file=None, var_dir=tmp_path / "var")
    s.ensure_dirs()
    return s


# ---------------------------------------------------------------------------
# schema
# ---------------------------------------------------------------------------

def test_audit_report_schema_valid():
    rep = AuditReport(
        symbol="cn:300750",
        market="cn_stock",
        audit_run_id="audit-x",
        overall_risk_level="high",
        risk_grade_label="高",
        findings=[
            AuditFinding(
                category="overfitting",
                title="样本外劣化",
                description="描述",
                severity="high",
                evidence="backtest_metric: out_sample.total_return < in_sample",
                recommendation="加入波动率自适应",
            )
        ],
        summary="存在过拟合风险",
        tradability="restricted",
    )
    assert rep.overall_risk_level == "high"
    # 致命风险级别必须能表达
    AuditFinding(
        category="lookahead", title="未来函数", description="d",
        severity="critical", evidence="e", recommendation="r",
    )


def test_risk_gate_schema():
    gate = RiskGate(
        risk_level="critical",
        trade_suggestion_allowed=False,
        risk_banner="风险提示...",
        constraint_boundaries=["禁止生成交易建议"],
    )
    assert gate.trade_suggestion_allowed is False


# ---------------------------------------------------------------------------
# 确定性风控门控
# ---------------------------------------------------------------------------

def test_gate_critical_blocks_trading():
    audit = {"overall_risk_level": "critical"}
    gate = apply_risk_gate(audit)
    assert gate.trade_suggestion_allowed is False
    assert gate.risk_banner
    assert any("禁止生成交易建议" in c for c in gate.constraint_boundaries)
    assert final_decision(audit, {"decision": "adopt"}) == "blocked"


def test_gate_high_announces_and_constraints():
    audit = {"overall_risk_level": "high"}
    gate = apply_risk_gate(audit)
    assert gate.trade_suggestion_allowed is True
    assert gate.risk_banner  # 顶部显著风险提示
    assert gate.constraint_boundaries  # 强制约束边界非空
    assert final_decision(audit, {"decision": "revise"}) == "revise"


def test_gate_low_medium_no_banner_by_default():
    audit = {"overall_risk_level": "low"}
    assert apply_risk_gate(audit).risk_banner == ""
    audit_m = {"overall_risk_level": "medium"}
    assert apply_risk_gate(audit_m).risk_banner == ""


def test_gate_medium_threshold_tightens():
    """阈值收紧到 medium 时，中风险也触发风险提示与约束边界。"""
    audit = {"overall_risk_level": "medium"}
    gate = apply_risk_gate(audit, threshold="medium")
    assert gate.risk_banner
    assert gate.constraint_boundaries
    # 致命风险不受阈值影响，恒被拦截
    audit_c = {"overall_risk_level": "critical"}
    assert apply_risk_gate(audit_c, threshold="medium").trade_suggestion_allowed is False


# ---------------------------------------------------------------------------
# mock 角色 payload（schema 合法）
# ---------------------------------------------------------------------------

def _backend() -> MockCompletionBackend:
    return MockCompletionBackend()


def test_mock_redteam_payload_schema():
    backend = _backend()
    msgs = [
        {"role": "system", "content": "你是 QuantSentinel 的红队审计员（RedTeamAgent）..."},
        {"role": "user", "content": "请审计 cn:300750"},
    ]
    assert backend.infer_role(msgs) == "redteam"
    payload = json.loads(backend.completion(messages=msgs).choices[0].message.content)
    rep = AuditReport.model_validate(payload)
    assert rep.overall_risk_level in {"low", "medium", "high", "critical"}
    for f in rep.findings:
        assert f.severity in {"low", "medium", "high", "critical"}


def test_mock_risk_officer_payload_schema():
    backend = _backend()
    msgs = [
        {"role": "system", "content": "你是 QuantSentinel 的风控综合官（RiskOfficerAgent）..."},
        {"role": "user", "content": "请综合 cn:300750"},
    ]
    assert backend.infer_role(msgs) == "risk_officer"
    payload = json.loads(backend.completion(messages=msgs).choices[0].message.content)
    # FinalAnalysisDraft 形状（final 报告组装前的 LLM 输出）
    assert payload["credibility_score"] in range(0, 101)
    assert payload["overall_risk_level"] in {"low", "medium", "high", "critical"}


def test_mock_role_markers_no_crosstalk():
    """风险相关角色 marker 互不串扰。"""
    backend = _backend()
    redteam_marker = "你是 QuantSentinel 的红队审计员（RedTeamAgent）"
    officer_marker = "你是 QuantSentinel 的风控综合官（RiskOfficerAgent）"
    risk_marker = "你是 QuantSentinel 的风控核验员（RiskCheckAgent）"
    assert backend.infer_role([{"role": "system", "content": redteam_marker}]) == "redteam"
    assert backend.infer_role([{"role": "system", "content": officer_marker}]) == "risk_officer"
    assert backend.infer_role([{"role": "system", "content": risk_marker}]) == "risk"


# ---------------------------------------------------------------------------
# 审计图端到端（mock 模式）
# ---------------------------------------------------------------------------

def _sample_debate_outcome() -> dict:
    """构造最小合法 DebateOutcome dump（供审计图调用）。"""
    bull = {"stance": "看多", "points": [{"claim": "c", "evidence": "e", "evidence_type": "logic"}]}
    bear = {"stance": "看空", "points": [{"claim": "c", "evidence": "e", "evidence_type": "logic"}]}
    verdict = {
        "credibility_score": 60, "consensus": ["x"], "disagreements": ["y"],
        "decision": "revise", "rationale": "r", "revision": None,
    }
    return {
        "run_id": "debate-src",
        "symbol": "cn:300750",
        "market": "cn_stock",
        "user_input": "双均线策略",
        "rounds": 1,
        "round_transcripts": [],
        "bull_final": bull,
        "bear_final": bear,
        "risk_checks": [],
        "verdict": verdict,
        "revised_strategy_text": "cn:300750 双均线修订版",
    }


def test_audit_graph_end_to_end_mock(monkeypatch, test_settings):
    monkeypatch.setenv("QUANTSENTINEL_LLM_MOCK", "1")
    graph, recorder = build_audit_graph(test_settings, run_id="audit-test",
                                        source_run_id="debate-src")
    try:
        state = graph.invoke({
            "run_id": "audit-test",
            "user_input": "双均线策略",
            "market": "cn_stock",
            "symbol": "cn:300750",
            "hypothesis": {},
            "debate_outcome": _sample_debate_outcome(),
            "iterations": 0,
        })
    finally:
        recorder.close()

    assert not state.get("error")
    audit = state["redteam_report"]
    assert AuditReport.model_validate(audit)
    gate = RiskGate.model_validate(state["risk_gate"])
    assert gate.risk_level == audit["overall_risk_level"]
    final = FinalAnalysisReport.model_validate(state["final_report"])
    assert final.audit_run_id == "audit-test"
    assert final.final_decision in {"adopt", "revise", "reject", "blocked"}


def test_audit_graph_critical_blocks(monkeypatch, test_settings):
    """把审计结果改写为致命风险时，门控必须拦截交易建议。"""
    monkeypatch.setenv("QUANTSENTINEL_LLM_MOCK", "1")
    from core.llm import _mock_redteam_payload

    # 让 mock 红队返回 critical，验证门控拦截
    import core.llm as llm_mod

    def patched_redteam(messages):
        p = dict(_mock_redteam_payload(messages))
        p["overall_risk_level"] = "critical"
        p["risk_grade_label"] = "致命"
        p["tradability"] = "prohibited"
        return p

    monkeypatch.setattr(llm_mod, "_mock_redteam_payload", patched_redteam)
    graph, recorder = build_audit_graph(test_settings, run_id="audit-crit")
    try:
        state = graph.invoke({
            "run_id": "audit-crit", "user_input": "双均线", "market": "cn_stock",
            "symbol": "cn:300750", "hypothesis": {},
            "debate_outcome": _sample_debate_outcome(), "iterations": 0,
        })
    finally:
        recorder.close()

    final = FinalAnalysisReport.model_validate(state["final_report"])
    assert final.final_decision == "blocked"
    assert final.trade_advisory == ""  # 致命风险强制清空交易建议
    assert final.risk_gate.trade_suggestion_allowed is False
    assert final.risk_gate.risk_banner


# ---------------------------------------------------------------------------
# Markdown 报告渲染与落盘
# ---------------------------------------------------------------------------

def _audit_dict(level="high") -> dict:
    return {
        "symbol": "cn:300750", "market": "cn_stock", "strategy_name": "双均线",
        "audit_run_id": "audit-t", "source_run_id": "debate-t",
        "overall_risk_level": level,
        "risk_grade_label": {"high": "高", "critical": "致命"}.get(level, "中"),
        "findings": [
            {"category": "overfitting", "title": "样本外劣化", "description": "d",
             "severity": level, "evidence": "e", "recommendation": "r"},
        ],
        "summary": "存在风险", "tradability": "restricted" if level != "critical" else "prohibited",
    }


def _final_dict(level="high") -> dict:
    audit = _audit_dict(level)
    gate = apply_risk_gate(audit).model_dump()
    return {
        "symbol": "cn:300750", "market": "cn_stock", "strategy_name": "双均线",
        "debate_run_id": "debate-t", "audit_run_id": "audit-t",
        "final_decision": "blocked" if level == "critical" else "revise",
        "credibility_score": 55, "overall_risk_level": level, "risk_gate": gate,
        "executive_summary": "摘要", "key_findings": ["f1"],
        "recommendations": ["r1"],
        "trade_advisory": "" if level == "critical" else "cn:300750 修订版建议",
    }


@pytest.mark.parametrize("level", ["low", "medium", "high", "critical"])
def test_render_audit_markdown_no_emoji(level):
    text = render_audit_markdown(_audit_dict(level))
    for sym in _FORBIDDEN:
        assert sym not in text
    assert "红队审计意见书" in text
    assert "审计发现" in text


def test_render_audit_markdown_critical_banner():
    text = render_audit_markdown(_audit_dict("critical"))
    assert "风险提示" in text
    text_low = render_audit_markdown(_audit_dict("low"))
    assert "风险提示" not in text_low


@pytest.mark.parametrize("level", ["low", "medium", "high", "critical"])
def test_render_final_markdown_banner_and_advisory(level):
    text = render_final_markdown(_final_dict(level))
    for sym in _FORBIDDEN:
        assert sym not in text
    assert "最终量化分析报告" in text
    if level in ("high", "critical"):
        assert "风险提示" in text
    if level == "critical":
        assert "已拦截交易建议生成" in text
        assert "（无" in text  # 交易建议被清空后的占位


def test_write_audit_and_final_report(tmp_path):
    audit_path = write_audit_report(_audit_dict("high"), tmp_path, "cn:300750",
                                    "20261120_120000", source_outcome={"run_id": "debate-src"})
    assert audit_path.endswith("audit_cn_300750_20261120_120000.md")
    assert open(audit_path, encoding="utf-8").read()

    final_path = write_final_report(_final_dict("high"), tmp_path, "cn:300750",
                                    "20261120_120000")
    assert final_path.endswith("final_cn_300750_20261120_120000.md")
    assert open(final_path, encoding="utf-8").read()


def test_report_dir_under_output(tmp_path):
    # CLI 传入 settings.audit_dir（= output/audit），文件直接落该目录；
    # 这里用 tmp_path 模拟该目录，校验命名与位置。
    p = write_audit_report(_audit_dict(), tmp_path, "cn:600519", "ts")
    assert p.endswith("audit_cn_600519_ts.md")
    import os
    assert os.path.dirname(p) == str(tmp_path)
