"""HTML 可视化报告的取数与编排（Step 6）。

独立于回测引擎 / 辩论 Agent / 红队审计 / 风控网关，只做两件事：
1. 按「修订策略文本」跑一次回测（复用既有 sandbox 工具与行情工具），
   取得 BacktestResult（含 equity_curve / trades）与 K 线 DataFrame；
2. 调用 :mod:`report.html` 的渲染器产出单文件 HTML。

取数失败不阻断主流程：HTML 报告降级为「仅文本摘要 + 指标面板」，
缺图表时在 HTML 内注明原因。
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

from core.config import Settings
from core.markets import Symbol
from report.html import render_final_html


def _resolve_period(
    hypothesis: dict[str, Any], period_days: int = 730
) -> tuple[str, str]:
    """解析回测区间：优先假设，缺失时回退最近 ``period_days`` 天。"""
    start = hypothesis.get("period_start")
    end = hypothesis.get("period_end")
    try:
        date.fromisoformat(str(start))
    except (TypeError, ValueError):
        start = (date.today() - timedelta(days=period_days)).strftime("%Y-%m-%d")
    try:
        date.fromisoformat(str(end))
    except (TypeError, ValueError):
        end = date.today().strftime("%Y-%m-%d")
    return str(start), str(end)


def run_reference_backtest(
    settings: Settings,
    revised_strategy_text: str,
    symbol: str,
    recorder: Any,
) -> tuple[dict[str, Any] | None, Any]:
    """对修订策略跑一次参考回测，返回 (BacktestResult dump, K线DataFrame)。

    用于 HTML 报告嵌入 K线/信号/净值/回撤图。失败时返回 (None, None)，
    渲染层据此降级为纯文本报告。
    """
    try:
        from agents.hypothesis import HypothesisAgent
        from tools.backtest_sandbox import run_backtest_in_sandbox
        from tools.market_data import get_backtest_frame

        market = settings.default_market.value
        ha = HypothesisAgent(settings, recorder)
        # 复用既有 hypothesis 解析（标的/区间），代码与回测走 sandbox 工具
        spec_state = ha.run({
            "user_input": revised_strategy_text,
            "market": market,
            "run_id": recorder.run_id,
            "iterations": 0,
        })
        spec = spec_state.get("hypothesis") or {}
        sym = Symbol.parse((spec.get("symbols") or [symbol])[0])
        start, end = _resolve_period(spec)
        df = get_backtest_frame(sym, start, end, settings)
        output = run_backtest_in_sandbox(
            spec_state.get("generated_code", ""), df, sym, settings,
            mode="local", initial_capital=1_000_000.0, run_id=recorder.run_id,
        )
        return output.result.model_dump(), df
    except Exception as exc:  # noqa: BLE001 —— 取数失败降级，不阻断报告
        try:
            recorder.log(node="html_report", event="backtest_degraded",
                         payload={"error": f"{type(exc).__name__}: {exc}"})
        except Exception:  # noqa: BLE001
            pass
        return None, None


def build_html_report(
    settings: Settings,
    final_report: dict[str, Any] | None,
    audit_report: dict[str, Any] | None,
    debate_outcome: dict[str, Any] | None,
    symbol: str,
    timestamp: str,
    revised_strategy_text: str = "",
    lang: str | None = None,
) -> str:
    """编排并落盘 HTML 最终报告，返回落盘路径。

    优先用 final_report/audit_report/debate_outcome 里的回测摘要；若缺回测明细，
    且调用方提供了修订策略文本，则补跑一次参考回测取数（失败降级）。
    ``lang`` 为报告语言（zh 默认 / en），透传给渲染层。

    参考回测的 trajectory 留痕使用**自建专用 recorder**（追加写，不依赖外部
    recorder 的生命周期——CLI 调用本函数时主 recorder 可能已 close()）。
    """
    from pathlib import Path

    backtest = None
    kline_df = None
    # 1) 优先使用辩论/裁决链路已带回测明细的情形（final_report 不直接携带曲线，
    #    但 debate_outcome 也不含；故需要时走参考回测）
    if revised_strategy_text:
        from core.trajectory import TrajectoryRecorder

        html_run_id = f"html-{timestamp}"
        ref_recorder = TrajectoryRecorder(html_run_id, settings.trajectory_dir)
        try:
            backtest, kline_df = run_reference_backtest(
                settings, revised_strategy_text, symbol, ref_recorder
            )
        finally:
            ref_recorder.close()

    html_text = render_final_html(
        backtest=backtest,
        final_report=final_report,
        audit_report=audit_report,
        debate_outcome=debate_outcome,
        kline_df=kline_df,
        lang=lang,
    )
    from report.html import write_final_html

    path = write_final_html(html_text, settings.output_dir, symbol, timestamp)
    # 同时写一份结构化 JSON 便于审计回放（与 md 同目录归类）
    try:
        json_path = Path(settings.output_dir) / "html" / f"final_{symbol.replace(':', '_')}_{timestamp}.json"
        json_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "final_report": final_report,
            "audit_report": audit_report,
            "backtest": backtest,
        }
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                             encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    return path
