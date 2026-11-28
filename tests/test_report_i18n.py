"""报告层双语（Step K）单元测试。

覆盖：

- zh/en 目录键集合一致性与完整性（同型于前端 i18n dict 用例）；
- ``normalize_report_language`` fail-closed 与配置读取；
- 同一合成任务的 zh/en 渲染 golden 快照（关键节标题 + 免责声明原句）；
- Plotly HTML 的标题 / 章节 / 表头 / trace 名 / 轴标签随语言切换；
- 风控门控结论文案双语且判定结果不变；
- 默认 ``lang=None`` 与显式 ``zh`` 逐字一致（默认行为不变）。
"""

from __future__ import annotations

import json
import re

import pytest

from core.config import Settings
from core.i18n import (
    EN_DISCLAIMER,
    MESSAGES_EN,
    MESSAGES_ZH,
    MESSAGE_KEYS,
    normalize_report_language,
)
from core.risk_gate import apply_risk_gate, final_decision
from report.html import render_final_html
from report.markdown import (
    render_audit_markdown,
    render_debate_markdown,
    render_final_markdown,
    render_optimization_markdown,
)

# ---------------------------------------------------------------------------
# 合成任务数据（确定性，无 LLM / 无网络）
# ---------------------------------------------------------------------------


def _debate() -> dict:
    return {
        "run_id": "d1", "symbol": "cn:300750", "market": "cn_stock",
        "user_input": "双均线策略", "rounds": 1,
        "round_transcripts": [{
            "round": 1,
            "bull": {"stance": "看多", "points": [{"claim": "趋势向上", "evidence_type": "price",
                                                  "evidence": "均线多头排列"}],
                     "assumptions": ["流动性充足"]},
            "bear": {"stance": "看空", "points": [], "failure_scenarios": ["放量破位"]},
            "risk_check": {"data_validity": "有效",
                           "findings": [{"severity": "high", "target_side": "bull",
                                         "issue": "样本内过短", "falsifiable": "是"}],
                           "kept_bull_points": [1], "kept_bear_points": [],
                           "recommendation": "补充样本外验证"},
        }],
        "verdict": {"credibility_score": 60, "consensus": ["c1"], "disagreements": ["dd1"],
                    "decision": "revise", "rationale": "理由",
                    "revision": {"revised_strategy_text": "cn:300750 修订版",
                                 "entry_rule": "金叉", "exit_rule": "死叉",
                                 "params": {"fast": 5}, "expected_effect": "提升"}},
    }


def _audit(level: str = "high") -> dict:
    return {
        "symbol": "cn:300750", "market": "cn_stock", "strategy_name": "双均线",
        "audit_run_id": "a1", "source_run_id": "d1",
        "overall_risk_level": level, "tradability": "restricted",
        "findings": [{"category": "overfitting", "title": "t", "description": "d",
                      "severity": "high", "evidence": "e", "recommendation": "r"}],
        "summary": "审计结论",
    }


def _final(level: str = "high") -> dict:
    blocked = level == "critical"
    gate = apply_risk_gate(_audit(level), "high", "zh").model_dump()
    return {
        "symbol": "cn:300750", "market": "cn_stock", "strategy_name": "双均线",
        "debate_run_id": "d1", "audit_run_id": "a1",
        "final_decision": "blocked" if blocked else "revise",
        "credibility_score": 55, "overall_risk_level": level,
        "risk_gate": gate, "executive_summary": "摘要",
        "key_findings": ["f1"], "recommendations": ["r1"],
        "trade_advisory": "" if blocked else "建议",
    }


def _backtest() -> dict:
    return {
        "symbol": "cn:300750", "market": "cn_stock",
        "period_start": "2024-01-01", "period_end": "2024-12-31",
        "initial_capital": 1_000_000.0, "final_equity": 1_100_000.0,
        "total_cost": 1200.0, "out_sample_start": "2024-10-01",
        "overall": {"total_return": 0.1, "annual_return": 0.05, "max_drawdown": -0.15,
                    "sharpe": 1.2, "win_rate": 0.55, "n_trades": 20, "n_days": 240},
        "in_sample": {}, "out_sample": {}, "rules": {}, "signal_nonzero_days": 100,
        "equity_curve": {"dates": ["2024-01-02", "2024-01-03"],
                         "nav": [1_000_000.0, 1_001_000.0]},
        "trades": [{"date": "2024-01-02", "side": "buy", "price": 100.0, "shares": 100},
                   {"date": "2024-01-03", "side": "sell", "price": 101.0, "shares": 100}],
    }


def _optimization() -> dict:
    def combo(index, params, in_ret, out_ret, in_n=14):
        return {
            "index": index, "params": params,
            "overall": {"total_return": in_ret + out_ret, "annual_return": 0.0,
                        "max_drawdown": -0.2, "sharpe": 0.5, "win_rate": 0.4,
                        "n_trades": in_n + 6},
            "in_sample": {"total_return": in_ret, "annual_return": 0.0,
                          "max_drawdown": -0.2, "sharpe": 0.5, "win_rate": 0.4,
                          "n_trades": in_n},
            "out_sample": {"total_return": out_ret, "annual_return": 0.0,
                           "max_drawdown": -0.05, "sharpe": 0.2, "win_rate": 0.5,
                           "n_trades": 6},
        }

    combos = [
        combo(0, {"short_window": 5, "long_window": 20}, -0.31, -0.06),
        combo(1, {"short_window": 5, "long_window": 30}, -0.20, -0.02),
        combo(2, {"short_window": 10, "long_window": 20}, -0.38, -0.09, in_n=22),
    ]
    return {
        "symbol": "cn:600519", "market": "cn_stock",
        "period_start": "2024-01-02", "period_end": "2025-12-31",
        "train_ratio": 0.7, "out_sample_start": "2025-06-03",
        "grid": {"short_window": (5, 10), "long_window": (20, 30)},
        "n_combinations": 3,
        "selection_metric": "sharpe", "comparison_metric": "total_return",
        "min_in_sample_trades": 5,
        "combinations": combos,
        "eligible_indexes": [0, 1, 2], "ineligible": [],
        "best_index": 1, "return_best_index": 1,
        "metric_agreement": True,
        "degraded": False, "degradation_reasons": [],
        "initial_capital": 1_000_000.0, "sandbox_mode": "local",
    }


# ---------------------------------------------------------------------------
# 1. 目录键集合一致性
# ---------------------------------------------------------------------------


def test_catalog_key_parity():
    """zh / en 目录键集合必须完全一致，且均非空、无空值。"""
    assert MESSAGES_ZH.keys() == MESSAGES_EN.keys()
    assert set(MESSAGE_KEYS) == set(MESSAGES_ZH)
    assert len(MESSAGE_KEYS) >= 80
    for lang, table in (("zh", MESSAGES_ZH), ("en", MESSAGES_EN)):
        for key, value in table.items():
            assert isinstance(value, str) and value.strip(), f"{lang}:{key} 为空"


def test_catalog_no_placeholder_mismatch():
    """同名占位符在两语言中必须一致（避免插值缺参）。"""
    pattern = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
    for key in MESSAGE_KEYS:
        zh_ph = set(pattern.findall(MESSAGES_ZH[key]))
        en_ph = set(pattern.findall(MESSAGES_EN[key]))
        assert zh_ph == en_ph, f"{key}: 占位符不一致 {zh_ph} vs {en_ph}"


def test_en_disclaimer_is_release_note_sentence():
    """英文免责声明固定用 Release notes 原句。"""
    assert EN_DISCLAIMER == (
        "Research and education use only; not investment advice; "
        "backtest results do not represent future returns."
    )


# ---------------------------------------------------------------------------
# 2. 语言归一化与配置（fail-closed）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("raw,expected", [
    (None, "zh"), ("", "zh"), ("   ", "zh"),
    ("zh", "zh"), ("ZH", "zh"), (" zh ", "zh"),
    ("en", "en"), ("EN", "en"),
])
def test_normalize_accepts_supported(raw, expected):
    assert normalize_report_language(raw) == expected


@pytest.mark.parametrize("raw", ["cn", "fr", "zh-CN", "english", "0"])
def test_normalize_rejects_unknown(raw):
    with pytest.raises(ValueError, match="不支持的报告语言"):
        normalize_report_language(raw)


def test_settings_report_language_default(test_settings):
    assert test_settings.report_language == "zh"


def test_settings_report_language_env(monkeypatch):
    monkeypatch.setenv("QUANT_ASST_REPORT_LANG", "en")
    assert Settings(_env_file=None).report_language == "en"


def test_settings_report_language_invalid(monkeypatch):
    monkeypatch.setenv("QUANT_ASST_REPORT_LANG", "fr")
    with pytest.raises(ValueError, match="不支持的报告语言"):
        Settings(_env_file=None)


# ---------------------------------------------------------------------------
# 3. Markdown golden 快照（同一合成任务，两语言）
# ---------------------------------------------------------------------------


def test_default_lang_equals_zh_every_renderer():
    """lang 缺省（None）与显式 zh 输出逐字一致 —— 默认行为不变。"""
    assert render_debate_markdown(_debate()) == render_debate_markdown(_debate(), "zh")
    assert render_audit_markdown(_audit()) == render_audit_markdown(_audit(), None, "zh")
    assert render_final_markdown(_final()) == render_final_markdown(_final(), "zh")
    assert render_optimization_markdown(_optimization()) == \
        render_optimization_markdown(_optimization(), "zh")


def test_debate_golden_snapshot():
    zh = render_debate_markdown(_debate())
    en = render_debate_markdown(_debate(), "en")
    for line in (
        "# 多空辩论报告：cn:300750",
        "## 逐轮辩论原文",
        "### 第 1 轮",
        "**多头观点**",
        "## 裁决结论",
        "## 策略修订建议",
    ):
        assert line in zh
    for line in (
        "# Bull/Bear Debate Report: cn:300750",
        "## Round-by-Round Debate Transcript",
        "### Round 1",
        "**Bull stance**",
        "## Verdict",
        "## Strategy Revision Proposal",
        EN_DISCLAIMER,
    ):
        assert line in en
    # 结构骨架一致：表格分隔行数量相同
    assert zh.count("| --- |") == en.count("| --- |")


def test_audit_golden_snapshot():
    zh = render_audit_markdown(_audit(), _debate())
    en = render_audit_markdown(_audit(), _debate(), "en")
    for line in ("# 红队审计意见书：cn:300750", "## 审计结论", "## 审计发现（1 条）",
                 "## 风险定级说明", "高（high）"):
        assert line in zh
    for line in ("# Red-Team Audit Opinion: cn:300750", "## Audit Conclusion",
                 "## Audit Findings (1)", "## Risk Level Reference", "High (high)",
                 EN_DISCLAIMER):
        assert line in en
    assert zh.count("| --- |") == en.count("| --- |")


def test_final_golden_snapshot_and_blocked_note():
    zh = render_final_markdown(_final())
    en = render_final_markdown(_final(), "en")
    assert "# 最终量化分析报告：cn:300750" in zh
    assert "## 执行摘要" in zh and "## 交易建议" in zh
    assert "# Final Quantitative Analysis Report: cn:300750" in en
    assert "## Executive Summary" in en and "## Trade Suggestion" in en
    assert EN_DISCLAIMER in en

    zh_blocked = render_final_markdown(_final("critical"))
    en_blocked = render_final_markdown(_final("critical"), "en")
    assert "本报告已拦截交易建议生成" in zh_blocked
    assert "Trade suggestion generation has been blocked" in en_blocked


def test_optimization_golden_snapshot():
    zh = render_optimization_markdown(_optimization())
    en = render_optimization_markdown(_optimization(), "en")
    for line in (
        "# 参数网格寻优报告：cn:600519",
        "## 全组合样本内 / 样本外指标对比（3 组）",
        "## 最优组合（按样本内 sharpe 选定）",
        "### 选优指标对照（并列呈现，不做加权综合）",
        "## 防泄漏声明",
        "## 样本外验证结论",
        "### 过拟合提示",
        "全部组合均满足准入门槛。",
    ):
        assert line in zh
    for line in (
        "# Parameter Grid Optimization Report: cn:600519",
        "## All Combinations: In-Sample vs Out-of-Sample (3)",
        "## Best Combination (selected by in-sample sharpe)",
        "## Leakage Statement",
        "## Out-of-Sample Validation",
        "### Overfitting Warning",
        "All combinations meet the eligibility threshold.",
        EN_DISCLAIMER,
    ):
        assert line in en
    assert zh.count("| --- |") == en.count("| --- |")


def test_optimization_degraded_snapshot_en():
    result = _optimization()
    result["degraded"] = True
    result["degradation_reasons"] = ["样本外夏普跌破阈值"]
    en = render_optimization_markdown(result, "en")
    assert "Verdict: degraded" in en
    assert "- Trigger: 样本外夏普跌破阈值" in en  # 数据原文不翻译


# ---------------------------------------------------------------------------
# 4. Plotly HTML 双语
# ---------------------------------------------------------------------------


def test_html_default_is_chinese():
    text = render_final_html(backtest=_backtest(), final_report=_final(),
                             audit_report=_audit(), debate_outcome=_debate())
    assert '<html lang="zh-CN">' in text
    assert "最终量化分析报告" in text
    assert "风险指标汇总" in text and "辩论摘要" in text


def test_html_english_static_labels_and_chart_names():
    text = render_final_html(backtest=_backtest(), final_report=_final(),
                             audit_report=_audit(), debate_outcome=_debate(), lang="en")
    assert '<html lang="en">' in text
    for marker in (
        "Final Quantitative Analysis Report",
        "Risk Metrics",
        "Analysis Summary",
        "Debate Summary",
        "Trade Suggestion",
        "Mandatory Constraint Boundaries",
    ):
        assert marker in text
    assert EN_DISCLAIMER not in text  # HTML 免责声明为 HTML 版措辞，见下方专门断言
    assert "Research and education use only" in text

    specs = json.loads(re.search(r"var CHARTS = (\[.*?\]);\n", text, re.DOTALL).group(1))
    blob = json.dumps(specs, ensure_ascii=False)
    for name in ("Strategy NAV", "Initial capital baseline", "Max Drawdown Curve",
                 "Out-of-sample start"):
        assert name in blob
    # 中文图例不得残留
    for zh_name in ("策略净值", "初始资金基准", "最大回撤曲线"):
        assert zh_name not in blob


def test_html_kline_chart_names_bilingual():
    pd = pytest.importorskip("pandas")
    df = pd.DataFrame({
        "date": pd.to_datetime(["2024-01-02", "2024-01-03"]),
        "open": [10.0, 10.5], "high": [10.6, 10.8],
        "low": [9.8, 10.1], "close": [10.4, 10.3], "volume": [100, 120],
    })
    zh = render_final_html(backtest=_backtest(), final_report=_final(),
                           audit_report=_audit(), debate_outcome=_debate(), kline_df=df)
    en = render_final_html(backtest=_backtest(), final_report=_final(),
                           audit_report=_audit(), debate_outcome=_debate(), kline_df=df,
                           lang="en")
    assert "标的K线行情与策略信号标记" in zh and "买入信号" in zh
    assert "Buy signal" in en and "Sell signal" in en
    assert "Underlying K-Line and Strategy Signal Markers" in en


# ---------------------------------------------------------------------------
# 5. 风控门控：文案双语，判定不变
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("level", ["low", "medium", "high", "critical"])
def test_risk_gate_decisions_language_independent(level):
    audit = _audit(level)
    zh = apply_risk_gate(audit, "high", "zh")
    en = apply_risk_gate(audit, "high", "en")
    assert zh.risk_level == en.risk_level
    assert zh.trade_suggestion_allowed == en.trade_suggestion_allowed
    assert bool(zh.risk_banner) == bool(en.risk_banner)
    assert len(zh.constraint_boundaries) == len(en.constraint_boundaries)
    assert final_decision(audit) == final_decision(audit)


def test_risk_gate_banner_text_differs_by_language():
    zh = apply_risk_gate(_audit("critical"), "high", "zh")
    en = apply_risk_gate(_audit("critical"), "high", "en")
    assert "致命风险" in zh.risk_banner
    assert "critical risk" in en.risk_banner
    assert zh.risk_banner != en.risk_banner
    assert zh.trade_suggestion_allowed is False


def test_risk_gate_invalid_language_fails_closed():
    with pytest.raises(ValueError, match="不支持的报告语言"):
        apply_risk_gate(_audit("high"), "high", "fr")
