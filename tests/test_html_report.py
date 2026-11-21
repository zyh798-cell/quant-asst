"""Step 6 HTML 可视化报告 单元测试。

覆盖：
- render_final_html 的结构完整性（标题/指标面板/文本摘要/约束边界/页脚）；
- 有回测明细时嵌入图表 JSON，无明细时降级提示；
- 风险 banner 与约束边界在致命/高风险时出现，低风险不出现；
- write_final_html 命名规则、目录归类、临时文件清理；
- report/build.py 的区间解析与降级容错。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from report.build import _resolve_period
from report.html import (
    render_final_html,
    write_final_html,
    _cleanup_tmp_files,
    _safe_ticker,
)


def _backtest() -> dict:
    return {
        "symbol": "cn:300750", "market": "cn_stock",
        "period_start": "2024-01-01", "period_end": "2025-12-31",
        "initial_capital": 1_000_000.0, "final_equity": 1_100_000.0,
        "total_cost": 1200.0, "out_sample_start": "2025-06-01",
        "overall": {"total_return": 0.1, "annual_return": 0.05, "max_drawdown": -0.15,
                    "sharpe": 1.2, "win_rate": 0.55, "n_trades": 20, "n_days": 480},
        "in_sample": {}, "out_sample": {},
        "rules": {}, "signal_nonzero_days": 100,
        "equity_curve": {"dates": ["2024-01-02", "2024-01-03"], "nav": [1_000_000.0, 1_001_000.0]},
        "trades": [
            {"date": "2024-01-02", "side": "buy", "price": 100.0, "shares": 100,
             "amount": 10000.0, "pnl": 0.0},
            {"date": "2024-01-03", "side": "sell", "price": 101.0, "shares": 100,
             "amount": 10100.0, "pnl": 100.0},
        ],
    }


def _final(level="high") -> dict:
    blocked = level == "critical"
    gate = {
        "risk_level": level,
        "trade_suggestion_allowed": not blocked,
        # 低风险时无 banner / 约束边界（与 core.risk_gate 一致）
        "risk_banner": "" if level in ("low", "medium") else f"风险提示：{level}风险",
        "constraint_boundaries": [] if level in ("low", "medium")
        else ["禁止实盘下单", "样本外复验"],
    }
    return {
        "symbol": "cn:300750", "market": "cn_stock", "strategy_name": "双均线",
        "debate_run_id": "d1", "audit_run_id": "a1",
        "final_decision": "blocked" if blocked else "revise",
        "credibility_score": 55, "overall_risk_level": level,
        "risk_gate": gate,
        "executive_summary": "摘要", "key_findings": ["f1"],
        "recommendations": ["r1"],
        "trade_advisory": "" if blocked else "建议",
    }


def _audit() -> dict:
    return {
        "symbol": "cn:300750", "market": "cn_stock", "strategy_name": "双均线",
        "audit_run_id": "a1", "source_run_id": "d1",
        "overall_risk_level": "high", "risk_grade_label": "高",
        "findings": [{"category": "overfitting", "title": "t", "description": "d",
                      "severity": "high", "evidence": "e", "recommendation": "r"}],
        "summary": "审计结论", "tradability": "restricted",
    }


def _debate() -> dict:
    return {
        "run_id": "d1", "symbol": "cn:300750", "market": "cn_stock",
        "user_input": "双均线", "rounds": 2, "round_transcripts": [],
        "bull_final": {"stance": "多", "points": []},
        "bear_final": {"stance": "空", "points": []},
        "risk_checks": [], "verdict": {
            "credibility_score": 60, "consensus": ["c1"], "disagreements": ["d1"],
            "decision": "revise", "rationale": "r", "revision": None,
        },
        "revised_strategy_text": "cn:300750 修订版",
    }


# ---------------------------------------------------------------------------
# 渲染结构
# ---------------------------------------------------------------------------

def test_render_html_basic_structure():
    text = render_final_html(
        backtest=_backtest(), final_report=_final(), audit_report=_audit(),
        debate_outcome=_debate(),
    )
    assert "<!DOCTYPE html>" in text
    assert "最终量化分析报告" in text
    assert "风险指标汇总" in text
    assert "回测净值曲线" in text
    assert "最大回撤曲线" in text
    assert "辩论摘要" in text and "红队审计风险结论" in text and "风控综合结论" in text
    # 图表 spec 不含花哨动画/过场配置（plotly.js 库代码自身含这些词，故只查 spec 区）
    import re
    specs = json.loads(re.search(r"var CHARTS = (\[.*?\]);\n", text, re.DOTALL).group(1))
    blob = json.dumps(specs, ensure_ascii=False)
    assert '"transition"' not in blob
    assert "animate" not in blob.lower()
    assert len(specs) >= 2  # 净值 + 回撤（无K线因未传 df）


def test_render_html_with_kline_df():
    """传入 K线 DataFrame 时嵌入 K线 + 买卖信号图表。"""
    import pandas as pd

    df = pd.DataFrame({
        "date": pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"]),
        "open": [10.0, 10.5, 10.2], "high": [10.6, 10.8, 10.5],
        "low": [9.8, 10.1, 9.9], "close": [10.4, 10.3, 10.5],
        "volume": [100, 120, 90],
    })
    text = render_final_html(
        backtest=_backtest(), final_report=_final(), audit_report=_audit(),
        debate_outcome=_debate(), kline_df=df,
    )
    assert "标的K线行情与策略信号标记" in text
    assert "买入信号" in text and "卖出信号" in text


def test_render_html_high_risk_banner_and_constraints():
    text = render_final_html(
        backtest=_backtest(), final_report=_final("high"),
        audit_report=_audit(), debate_outcome=_debate(),
    )
    assert "风险提示" in text
    assert "约束边界（强制）" in text
    assert "禁止实盘下单" in text


def test_render_html_critical_blocks_advisory():
    text = render_final_html(
        backtest=_backtest(), final_report=_final("critical"),
        audit_report=_audit(), debate_outcome=_debate(),
    )
    assert "已拦截交易建议生成" in text
    assert "（致命风险已拦截交易建议生成" in text or "致命风险已拦截" in text


def test_render_html_low_risk_no_banner():
    text = render_final_html(
        backtest=_backtest(), final_report=_final("low"),
        audit_report=_audit(), debate_outcome=_debate(),
    )
    assert "约束边界（强制）" not in text


def test_render_html_decision_bar():
    """决策与风险定级摘要条：最终决策 + 综合风险定级。"""
    text = render_final_html(
        backtest=_backtest(), final_report=_final("high"),
        audit_report=_audit(), debate_outcome=_debate(),
    )
    assert "最终决策" in text and "revise" in text
    assert "综合风险定级" in text and "高（high）" in text


def test_render_html_decision_blocked():
    text = render_final_html(
        backtest=_backtest(), final_report=_final("critical"),
        audit_report=_audit(), debate_outcome=_debate(),
    )
    assert "blocked" in text and "致命（critical）" in text


def test_render_html_degrades_without_backtest():
    """无回测明细时降级为文本报告，不抛异常。"""
    text = render_final_html(
        backtest=None, final_report=_final(), audit_report=None, debate_outcome=None,
    )
    assert "（无回测数据）" in text
    assert "（无可视化数据" in text


def test_render_html_contains_plotly_spec_json():
    text = render_final_html(
        backtest=_backtest(), final_report=_final(), audit_report=_audit(),
        debate_outcome=_debate(),
    )
    # plotly spec 以 JSON 形式内嵌（data/layout）
    assert '"data"' in text and '"layout"' in text


def test_render_html_escapes_xss():
    final = _final()
    final["executive_summary"] = "<script>alert(1)</script>"
    text = render_final_html(backtest=_backtest(), final_report=final,
                             audit_report=_audit(), debate_outcome=_debate())
    assert "<script>alert(1)</script>" not in text
    assert "&lt;script&gt;" in text


# ---------------------------------------------------------------------------
# 落盘 + 命名 + 临时清理
# ---------------------------------------------------------------------------

def test_write_html_naming(tmp_path):
    text = render_final_html(backtest=_backtest(), final_report=_final(),
                             audit_report=_audit(), debate_outcome=_debate())
    path = write_final_html(text, tmp_path, "cn:300750", "20261120_120000")
    assert Path(path).name == "final_cn_300750_20261120_120000.html"
    assert Path(path).parent == tmp_path / "html"
    assert Path(path).read_text(encoding="utf-8")


def test_safe_ticker(tmp_path):
    assert _safe_ticker("cn:300750") == "cn_300750"
    assert _safe_ticker("crypto:BTC/USDT") == "crypto_BTC_USDT"


def test_cleanup_tmp_files(tmp_path):
    target = tmp_path / "html"
    target.mkdir()
    keep = target / "final_cn_300750_ts.html"
    keep.write_text("keep", encoding="utf-8")
    (target / "draft.tmp").write_text("tmp", encoding="utf-8")
    (target / "part.part").write_text("part", encoding="utf-8")
    (target / "~backup.html").write_text("bak", encoding="utf-8")
    (target / "final_cn_600519_ts.html").write_text("other", encoding="utf-8")
    _cleanup_tmp_files(target, keep=keep)
    names = {p.name for p in target.iterdir()}
    assert "draft.tmp" not in names
    assert "part.part" not in names
    assert "~backup.html" not in names
    assert "final_cn_300750_ts.html" in names  # keep
    assert "final_cn_600519_ts.html" in names  # 其他正式产物保留


# ---------------------------------------------------------------------------
# report/build.py 辅助
# ---------------------------------------------------------------------------

def test_resolve_period_from_hypothesis():
    start, end = _resolve_period({"period_start": "2024-01-01", "period_end": "2024-12-31"})
    assert (start, end) == ("2024-01-01", "2024-12-31")


def test_resolve_period_fallback_recent_year():
    start, end = _resolve_period({})
    assert len(start) == 10 and len(end) == 10
    assert start < end


def test_build_html_report_degrades_on_backtest_failure(monkeypatch, test_settings, tmp_path):
    """参考回测取数失败时，build_html_report 降级为纯文本 HTML 且仍落盘。"""
    monkeypatch.setenv("QUANTSENTINEL_LLM_MOCK", "1")
    from report import build as build_mod

    monkeypatch.setattr(
        build_mod, "run_reference_backtest",
        lambda settings, text, symbol, recorder: (None, None),
    )
    path = build_mod.build_html_report(
        settings=test_settings,
        final_report=_final(), audit_report=_audit(), debate_outcome=_debate(),
        symbol="cn:300750", timestamp="20261120_120000",
        revised_strategy_text="cn:300750 双均线",
    )
    assert Path(path).exists()
    content = Path(path).read_text(encoding="utf-8")
    assert "最终量化分析报告" in content
