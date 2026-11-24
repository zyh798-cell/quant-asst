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
from core.risk_gate import (
    BLOCKED_ADVISORY_TEXT,
    advisory_for_decision,
    apply_risk_gate,
    final_decision,
)
from core.schemas import (
    AuditFinding,
    AuditReport,
    FinalAnalysisReport,
    RiskGate,
    normalize_risk_level,
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


def _patch_redteam_payload(monkeypatch, mutate):
    """安全改写 mock 红队 payload。

    必须先捕获原始函数再包装：``core.llm._payload_for`` 在模块内直接引用
    ``_mock_redteam_payload``，若补丁内部回写 ``llm_mod._mock_redteam_payload``
    会变成自递归。
    """
    import core.llm as llm_mod

    original = llm_mod._mock_redteam_payload

    def patched(messages):
        return mutate(dict(original(messages)))

    monkeypatch.setattr(llm_mod, "_mock_redteam_payload", patched)


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
    # 必须显式启用 mock：否则红队节点会走真实 litellm，无密钥环境（CI）直接认证失败。
    # （回归：批量改名时此行曾丢失，本机因 uv run 自动加载 .env 的真实密钥而“假绿”）
    monkeypatch.setenv("QUANT_ASST_LLM_MOCK", "1")
    # 再显式清空宿主密钥，保证本用例不依赖 .env / shell 环境（与 CI 条件一致）
    for name in ("DEEPSEEK_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)
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
    monkeypatch.setenv("QUANT_ASST_LLM_MOCK", "1")

    def mutate(p):
        p["overall_risk_level"] = "critical"
        p["risk_grade_label"] = "致命"
        p["tradability"] = "prohibited"
        return p

    _patch_redteam_payload(monkeypatch, mutate)
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
    # fail-closed 一致性：blocked 时建议不输出可执行内容，改为拦截说明文案
    assert BLOCKED_ADVISORY_TEXT in final.trade_advisory
    assert "禁止生成任何实盘买卖建议" in final.trade_advisory
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
    blocked = level == "critical"
    return {
        "symbol": "cn:300750", "market": "cn_stock", "strategy_name": "双均线",
        "debate_run_id": "debate-t", "audit_run_id": "audit-t",
        "final_decision": "blocked" if blocked else "revise",
        "credibility_score": 55, "overall_risk_level": level, "risk_gate": gate,
        "executive_summary": "摘要", "key_findings": ["f1"],
        "recommendations": ["r1"],
        # blocked 一致性：门控把建议替换为拦截说明文案
        "trade_advisory": advisory_for_decision("blocked" if blocked else "revise",
                                                "" if blocked else "cn:300750 修订版建议"),
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
        # 门控写入的拦截说明文案会直接呈现，不含可执行建议原文
        assert "禁止生成任何实盘买卖建议" in text
        assert "cn:300750 修订版建议" not in text


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


# ---------------------------------------------------------------------------
# fail-closed 风险定级归一化（外部代码 review 第 1 项）
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("severe", "critical"),      # 常见英文别名 -> critical
    ("极高", "critical"),         # 中文别名 -> critical
    ("致命", "critical"),
    ("high", "high"),
    ("高", "high"),
    ("medium", "medium"),
    ("中", "medium"),
    ("low", "low"),
    ("低", "low"),
    # 白名单外 / 缺失 -> 一律 critical（fail-closed，绝不回落 low）
    ("catastrophic_plus", "critical"),
    ("超高", "critical"),
    ("", "critical"),
    (None, "critical"),
])
def test_normalize_risk_level_fail_closed(raw, expected):
    assert normalize_risk_level(raw) == expected


def test_missing_level_does_not_fall_back_to_low(caplog):
    """缺失等级必须告警并按 critical 处理（不得静默回落 low）。"""
    audit = {}  # 无 overall_risk_level
    with caplog.at_level("WARNING", logger="quantsentinel.risk"):
        gate = apply_risk_gate(audit)
    assert gate.risk_level == "critical"
    assert gate.trade_suggestion_allowed is False
    assert any("fail-closed" in r.message for r in caplog.records)


def test_unknown_custom_level_blocks():
    """自造等级（如 'very_high'）按 critical 拦截。"""
    audit = {"overall_risk_level": "very_high"}
    gate = apply_risk_gate(audit)
    assert gate.risk_level == "critical"
    assert gate.trade_suggestion_allowed is False
    assert final_decision(audit, {"decision": "adopt"}) == "blocked"


def test_llm_raw_severe_output_is_critical_end_to_end(monkeypatch, test_settings):
    """红队 LLM 原始输出 'severe' -> schema 归一化为 critical -> 门控拦截。"""
    monkeypatch.setenv("QUANT_ASST_LLM_MOCK", "1")

    def mutate(p):
        p["overall_risk_level"] = "severe"   # LLM 原始别名，非规范值
        p["risk_grade_label"] = "严重"
        p["tradability"] = "prohibited"
        return p

    _patch_redteam_payload(monkeypatch, mutate)
    graph, recorder = build_audit_graph(test_settings, run_id="audit-severe")
    try:
        state = graph.invoke({
            "run_id": "audit-severe", "user_input": "双均线", "market": "cn_stock",
            "symbol": "cn:300750", "hypothesis": {},
            "debate_outcome": _sample_debate_outcome(), "iterations": 0,
        })
    finally:
        recorder.close()

    final = FinalAnalysisReport.model_validate(state["final_report"])
    assert final.overall_risk_level == "critical"
    assert final.final_decision == "blocked"
    assert BLOCKED_ADVISORY_TEXT in final.trade_advisory


def test_llm_missing_level_field_blocks(monkeypatch, test_settings):
    """LLM 输出缺失 overall_risk_level 字段 -> blocked（fail-closed）。"""
    monkeypatch.setenv("QUANT_ASST_LLM_MOCK", "1")

    def mutate(p):
        p.pop("overall_risk_level", None)    # 模拟模型漏字段
        return p

    _patch_redteam_payload(monkeypatch, mutate)
    graph, recorder = build_audit_graph(test_settings, run_id="audit-nolevel")
    try:
        state = graph.invoke({
            "run_id": "audit-nolevel", "user_input": "双均线", "market": "cn_stock",
            "symbol": "cn:300750", "hypothesis": {},
            "debate_outcome": _sample_debate_outcome(), "iterations": 0,
        })
    finally:
        recorder.close()

    final = FinalAnalysisReport.model_validate(state["final_report"])
    assert final.overall_risk_level == "critical"   # 缺失字段 fail-closed 到最高级
    assert final.final_decision == "blocked"
    assert BLOCKED_ADVISORY_TEXT in final.trade_advisory


# ---------------------------------------------------------------------------
# blocked 与 trade_advisory 一致性（外部代码 review 第 2 项）
# ---------------------------------------------------------------------------

def test_prohibited_non_critical_still_blocks_and_clears_advisory():
    """tradability=prohibited 但等级非 critical：decision=blocked，建议必须清空。"""
    audit = {"overall_risk_level": "medium", "tradability": "prohibited"}
    assert final_decision(audit, {"decision": "revise"}) == "blocked"

    advisory = advisory_for_decision(
        final_decision(audit, {"decision": "revise"}),
        "cn:300750 满仓买入",     # LLM 草稿仍给了建议
    )
    assert BLOCKED_ADVISORY_TEXT in advisory
    assert "满仓买入" not in advisory


def test_blocked_consistency_any_trigger_path():
    """无论哪条路径触发 blocked，trade_advisory 都必须是拦截说明文案。"""
    # 路径 A：critical
    a = advisory_for_decision("blocked", "建议A")
    # 路径 B：prohibited + 非 critical
    b = advisory_for_decision(final_decision(
        {"overall_risk_level": "low", "tradability": "prohibited"}), "建议B")
    assert a == BLOCKED_ADVISORY_TEXT
    assert b == BLOCKED_ADVISORY_TEXT
    assert "风控门控拦截" in a and "风控门控拦截" in b


def test_audit_graph_prohibited_non_critical_consistency(monkeypatch, test_settings):
    """端到端：prohibited + medium，最终报告 blocked 且建议被替换为拦截说明。"""
    monkeypatch.setenv("QUANT_ASST_LLM_MOCK", "1")

    def mutate(p):
        p["overall_risk_level"] = "medium"
        p["risk_grade_label"] = "中"
        p["tradability"] = "prohibited"
        return p

    _patch_redteam_payload(monkeypatch, mutate)
    graph, recorder = build_audit_graph(test_settings, run_id="audit-prohib")
    try:
        state = graph.invoke({
            "run_id": "audit-prohib", "user_input": "双均线", "market": "cn_stock",
            "symbol": "cn:300750", "hypothesis": {},
            "debate_outcome": _sample_debate_outcome(), "iterations": 0,
        })
    finally:
        recorder.close()

    final = FinalAnalysisReport.model_validate(state["final_report"])
    assert final.overall_risk_level == "medium"       # 等级本身未被篡改
    assert final.final_decision == "blocked"          # 但决策被 prohibited 拦截
    assert BLOCKED_ADVISORY_TEXT in final.trade_advisory  # 建议一致：无原文残留
    assert "MA5>MA20" not in final.trade_advisory
