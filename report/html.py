"""Plotly 交互式 HTML 最终报告（Step 6）。

与 ``report/markdown.py`` 并行：Markdown 维持工程归档风格，HTML 提供单文件交互可视化。
本模块为**纯渲染层**——不调用回测引擎、不触碰辩论/红队/门控逻辑，只消费
已由工具产出的数据（硬约束 1：数字全部来自工具返回）。

产物约定：
- 路径 ``./output/html/``，命名 ``final_<ticker>_<timestamp>.html``；
- 静态单文件（plotly.js 内联），无需前端服务，浏览器直接打开；
- 配色克制专业（金融量化风），图表自带注释（数据来源/回测约束边界），无花哨动画。
"""

from __future__ import annotations

import html
import json
from typing import Any

from core.i18n import (
    format_message,
    normalize_report_language,
    risk_label,
    risk_level_display,
    t,
)

#: 克制专业的金融量化调色板（深蓝主系 + 红绿涨跌辅助）
_COLORS = {
    "nav": "#1f4e79",          # 净值曲线：深蓝
    "benchmark": "#7f7f7f",    # 基准（初始资金线）：灰
    "drawdown": "#c0392b",     # 回撤曲线：暗红
    "buy": "#1e8449",          # 买入信号：深绿
    "sell": "#922b21",         # 卖出信号：深红
    "candle_up": "#b03a2e",    # K线上涨：红（A股口径）
    "candle_down": "#1e8449",  # K线下跌：绿（A股口径）
    "ma_fast": "#2471a3",      # 快线
    "ma_slow": "#b9770e",      # 慢线
    "text": "#2c3e50",
    "panel_bg": "#f8f9fa",
    "border": "#d5dbdb",
}


def _pct(v: float | None) -> str:
    if v is None:
        return "N/A"
    return f"{v * 100:+.2f}%"


def _fmt(v: Any, unit: str = "") -> str:
    if v is None:
        return "N/A"
    if isinstance(v, float):
        return f"{v:,.2f}{unit}"
    return f"{v}{unit}"


def _esc(text: str) -> str:
    return html.escape(str(text))


def _safe_ticker(ticker: str) -> str:
    return (ticker or "unknown").replace(":", "_").replace("/", "_")


# ---------------------------------------------------------------------------
# 图表构造（Plotly express / graph_objects，离线内联）
# ---------------------------------------------------------------------------

def _build_candlestick_with_signals(df: Any, trades: list[dict], lang: str) -> Any:
    """K线 + 买卖信号标记。买入在低点下方标注，卖出在高点上方标注。"""
    import plotly.graph_objects as go

    dates = df["date"]
    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=dates, open=df["open"], high=df["high"], low=df["low"], close=df["close"],
        name=t("html.chart.kline", lang), increasing_line_color=_COLORS["candle_up"],
        decreasing_line_color=_COLORS["candle_down"],
    ))
    buys = [t_ for t_ in trades if t_.get("side") == "buy"]
    sells = [t_ for t_ in trades if t_.get("side") == "sell"]
    if buys:
        fig.add_trace(go.Scatter(
            x=[x["date"] for x in buys], y=[x["price"] for x in buys],
            mode="markers", marker=dict(symbol="triangle-up", size=10,
                                        color=_COLORS["buy"], line=dict(width=1, color="#145a32")),
            name=t("html.chart.buy", lang),
            hovertext=[format_message("html.chart.buy_hover", lang, shares=x.get("shares", ""))
                      for x in buys],
        ))
    if sells:
        fig.add_trace(go.Scatter(
            x=[x["date"] for x in sells], y=[x["price"] for x in sells],
            mode="markers", marker=dict(symbol="triangle-down", size=10,
                                        color=_COLORS["sell"], line=dict(width=1, color="#641e16")),
            name=t("html.chart.sell", lang),
            hovertext=[format_message("html.chart.sell_hover", lang, shares=x.get("shares", ""))
                      for x in sells],
        ))
    fig.update_layout(
        title=dict(text=t("html.chart.candle_title", lang), x=0.5, font=dict(size=15)),
        xaxis_title=t("html.chart.date", lang), yaxis_title=t("html.chart.price", lang),
        template="plotly_white", height=460, showlegend=True,
        margin=dict(l=50, r=20, t=60, b=40),
        xaxis_rangeslider_visible=False,
    )
    return fig


def _build_equity_curve(
    equity: dict, initial_capital: float, out_sample_start: str, lang: str
) -> Any:
    """净值曲线 + 初始资金基准线 + 样本外起点标注。"""
    import plotly.graph_objects as go

    dates = equity.get("dates", [])
    nav = equity.get("nav", [])
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=dates, y=nav, mode="lines", name=t("html.chart.nav", lang),
        line=dict(color=_COLORS["nav"], width=2),
    ))
    fig.add_trace(go.Scatter(
        x=dates, y=[initial_capital] * len(dates), mode="lines",
        name=t("html.chart.benchmark", lang),
        line=dict(color=_COLORS["benchmark"], width=1, dash="dash"),
    ))
    fig.add_vline(x=out_sample_start, line_dash="dot", line_color="#7f8c8d",
                  annotation_text=t("html.chart.oos_mark", lang),
                  annotation_position="top left")
    fig.update_layout(
        title=dict(text=t("html.chart.equity_title", lang), x=0.5, font=dict(size=15)),
        xaxis_title=t("html.chart.date", lang), yaxis_title=t("html.chart.nav_axis", lang),
        template="plotly_white", height=380, margin=dict(l=50, r=20, t=60, b=40),
    )
    return fig


def _build_drawdown_curve(equity: dict, lang: str) -> Any:
    """最大回撤曲线（净值相对历史峰值的回撤，负值）。"""
    import plotly.graph_objects as go

    nav = equity.get("nav", [])
    dates = equity.get("dates", [])
    peak = None
    dd: list[float] = []
    for v in nav:
        peak = v if peak is None else max(peak, v)
        dd.append((v / peak - 1.0) if peak else 0.0)
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=dates, y=dd, mode="lines", name=t("html.chart.dd", lang), fill="tozeroy",
        line=dict(color=_COLORS["drawdown"], width=1.5),
    ))
    fig.update_layout(
        title=dict(text=t("html.chart.dd_title", lang), x=0.5, font=dict(size=15)),
        xaxis_title=t("html.chart.date", lang), yaxis_title=t("html.chart.dd_axis", lang),
        template="plotly_white", height=300, margin=dict(l=50, r=20, t=60, b=40),
    )
    return fig


# ---------------------------------------------------------------------------
# HTML 组装
# ---------------------------------------------------------------------------

def _metrics_table(backtest: dict, lang: str) -> str:
    """风险指标汇总面板：夏普/最大回撤/胜率/盈亏比等。"""
    ov = backtest.get("overall", {})
    rows = [
        (t("html.metric.total_return", lang), _pct(ov.get("total_return"))),
        (t("html.metric.annual_return", lang), _pct(ov.get("annual_return"))),
        (t("html.metric.max_drawdown", lang), _pct(ov.get("max_drawdown"))),
        (t("html.metric.sharpe", lang), _fmt(ov.get("sharpe"))),
        (t("html.metric.win_rate", lang),
         _fmt(ov.get("win_rate")) if ov.get("win_rate") is not None else t("common.na", lang)),
        (t("html.metric.n_trades", lang), str(ov.get("n_trades", 0))),
        (t("html.metric.initial_capital", lang), _fmt(backtest.get("initial_capital"))),
        (t("html.metric.final_equity", lang), _fmt(backtest.get("final_equity"))),
        (t("html.metric.total_cost", lang), _fmt(backtest.get("total_cost"))),
        (t("html.metric.out_sample_start", lang), str(backtest.get("out_sample_start", "N/A"))),
    ]
    trs = "\n".join(f"<tr><td>{k}</td><td>{html.escape(str(v))}</td></tr>" for k, v in rows)
    return (
        '<table class="metrics"><thead><tr>'
        f'<th>{t("html.metrics_col.name", lang)}</th>'
        f'<th>{t("html.metrics_col.value", lang)}</th></tr></thead>'
        f"<tbody>{trs}</tbody></table>"
    )


def _list_section(title: str, items: list[str] | None, empty_text: str) -> str:
    lis = "".join(f"<li>{_esc(x)}</li>" for x in (items or []))
    return f'<h3>{_esc(title)}</h3><ul>{lis or f"<li>{empty_text}</li>"}</ul>'


def _text_panel(sections: list[tuple[str, str]]) -> str:
    """文本摘要面板：辩论摘要 / 审计结论 / 风控定级。"""
    blocks = []
    for title, body in sections:
        blocks.append(
            f'<div class="panel"><h3>{_esc(title)}</h3>'
            f'<p>{_esc(body)}</p></div>'
        )
    return "\n".join(blocks)


def render_final_html(
    backtest: dict[str, Any] | None,
    final_report: dict[str, Any] | None,
    audit_report: dict[str, Any] | None,
    debate_outcome: dict[str, Any] | None,
    kline_df: Any = None,
    source_note: str = "Quant Asst 多智能体量化研究引擎",
    lang: str | None = None,
) -> str:
    """渲染单文件交互式 HTML 最终报告。

    Args:
        backtest: ``BacktestResult.model_dump()``（含 equity_curve / trades，可选）。
        final_report: ``FinalAnalysisReport.model_dump()``（Step 5 产物，可选）。
        audit_report: ``AuditReport.model_dump()``（红队审计，可选）。
        debate_outcome: ``DebateOutcome.model_dump()``（辩论纪要，可选）。
        kline_df: 标的日线 OHLCV DataFrame（用于K线图，可选；缺省跳过K线图）。
        source_note: 数据来源注释。
        lang: 报告语言（``zh`` 默认 / ``en``）；标题、章节标题、表头、图例、
            轴标签与免责声明随语言切换，数字与日期格式不变。
    """
    import plotly.io as pio

    lang = normalize_report_language(lang)
    colon = t("punct.colon", lang)

    equity = (backtest or {}).get("equity_curve") or {}
    trades = (backtest or {}).get("trades") or []
    out_sample_start = (backtest or {}).get("out_sample_start", "")
    initial_capital = (backtest or {}).get("initial_capital", 0.0)

    # ---- 图表 JSON（静态单文件，无动画）----
    charts: list[str] = []
    if kline_df is not None and not kline_df.empty and trades:
        charts.append(pio.to_json(
            _build_candlestick_with_signals(kline_df, trades, lang), pretty=True
        ))
    if equity.get("dates") and equity.get("nav"):
        charts.append(pio.to_json(
            _build_equity_curve(equity, initial_capital, out_sample_start, lang), pretty=True
        ))
        charts.append(pio.to_json(_build_drawdown_curve(equity, lang), pretty=True))

    # plotly.js 内联 + 图表占位（离线单文件）
    plotly_js = _plotly_js_bundle()

    symbol = (final_report or backtest or debate_outcome or {}).get("symbol", "N/A")

    # ---- 风险定级与约束边界 ----
    gate = (final_report or {}).get("risk_gate") or {}
    risk_level = (final_report or {}).get("overall_risk_level") or \
                 (audit_report or {}).get("overall_risk_level", "low")
    final_decision = (final_report or {}).get("final_decision", "")
    banner = gate.get("risk_banner", "") or ""
    constraints = gate.get("constraint_boundaries") or []
    risk_banner_html = ""
    if banner:
        risk_banner_html = f'<div class="risk-banner">{_esc(banner)}</div>'
    constraints_html = ""
    if constraints:
        lis = "".join(f"<li>{_esc(c)}</li>" for c in constraints)
        constraints_html = (
            f'<div class="constraints"><h3>{t("html.constraints_title", lang)}</h3>'
            f"<ul>{lis}</ul></div>"
        )

    # ---- 决策与风险定级摘要条 ----
    decision_html = (
        '<div class="decision-bar">'
        f'<span>{t("html.decision_label", lang)}{colon}<b>{_esc(final_decision or "N/A")}</b></span>'
        f'<span>{t("html.risk_label", lang)}{colon}'
        f'<b>{_esc(risk_level_display(risk_level, lang))}</b></span>'
        '</div>'
        if (final_decision or risk_level) else ""
    )

    # ---- 文本摘要 ----
    debate_summary = ""
    if debate_outcome:
        verdict = debate_outcome.get("verdict") or {}
        consensus_text = "；".join(verdict.get("consensus") or []) \
            or t("common.none_paren", lang)
        debate_summary = (
            f"{t('debate.meta.rounds', lang)} {debate_outcome.get('rounds', 0)} | "
            f"{t('html.summary.verdict', lang)} {verdict.get('decision', 'N/A')} | "
            f"{t('debate.credibility_label', lang)} "
            f"{verdict.get('credibility_score', 'N/A')}/100。"
            f"{t('html.summary.consensus_prefix', lang)}{consensus_text}。"
        )
    audit_summary = (audit_report or {}).get("summary", "") or t("html.empty.audit", lang)
    officer_summary = (final_report or {}).get("executive_summary", "") \
        or t("html.empty.officer", lang)
    trade_advisory = (final_report or {}).get("trade_advisory", "")

    metrics_panel = _metrics_table(backtest, lang) if backtest \
        else f"<p>{t('html.empty.backtest', lang)}</p>"
    text_panel = _text_panel([
        (t("html.panel.debate", lang), debate_summary or t("html.empty.debate", lang)),
        (t("html.panel.audit", lang), audit_summary),
        (t("html.panel.officer", lang), officer_summary),
    ])
    advisory_html = (
        f'<div class="panel advisory"><h3>{t("html.panel.advisory", lang)}</h3>'
        f'<p>{_esc(trade_advisory)}</p></div>'
        if trade_advisory else
        '<div class="panel advisory">'
        f'<h3>{t("html.panel.advisory", lang)}</h3>'
        f'<p>{t("html.empty.advisory", lang)}</p></div>'
    )

    chart_slots = "\n".join(
        f'<div class="chart" id="chart-{i}"></div>' for i in range(len(charts))
    )

    return f"""<!DOCTYPE html>
<html lang="{t('html.lang_attr', lang)}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(format_message('html.title', lang, symbol=str(symbol)))}</title>
<script>{plotly_js}</script>
<style>
  :root {{ --nav:{_COLORS['nav']}; --dd:{_COLORS['drawdown']}; --text:{_COLORS['text']};
           --bg:{_COLORS['panel_bg']}; --border:{_COLORS['border']}; }}
  body {{ font-family: -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif;
         color: var(--text); background:#fff; margin:0; padding:24px; }}
  h1 {{ font-size:22px; border-bottom:2px solid var(--nav); padding-bottom:8px; }}
  h2 {{ font-size:17px; margin-top:28px; color:var(--nav); }}
  h3 {{ font-size:14px; margin:8px 0; }}
  .meta {{ color:#555; font-size:13px; margin:8px 0 16px; }}
  .risk-banner {{ background:#fdecea; border:1px solid #c0392b; color:#922b21;
                  padding:10px 14px; margin:12px 0; font-weight:bold; }}
  .decision-bar {{ background:#eaf2f8; border:1px solid #2471a3; color:#1b4f72;
                   padding:8px 14px; margin:10px 0; font-size:14px; }}
  .decision-bar span {{ margin-right:24px; }}
  .constraints {{ background:var(--bg); border:1px solid var(--border);
                  padding:10px 14px; margin:12px 0; }}
  .metrics {{ border-collapse:collapse; width:100%; max-width:560px; font-size:13px; }}
  .metrics th, .metrics td {{ border:1px solid var(--border); padding:6px 10px; text-align:left; }}
  .metrics th {{ background:var(--bg); }}
  .chart {{ margin:16px 0; }}
  .panel {{ background:var(--bg); border:1px solid var(--border); border-radius:4px;
            padding:10px 14px; margin:10px 0; }}
  .panel.advisory {{ border-left:4px solid var(--nav); }}
  ul {{ margin:6px 0; padding-left:20px; }}
  .footer {{ color:#888; font-size:12px; margin-top:24px; border-top:1px solid var(--border);
             padding-top:8px; }}
</style>
</head>
<body>
<h1>{_esc(format_message('html.title', lang, symbol=str(symbol)))}</h1>
<div class="meta">{format_message('html.meta', lang, note=_esc(source_note))}</div>
{decision_html}
{risk_banner_html}
{constraints_html}
<h2>{t('html.metrics_title', lang)}</h2>
{metrics_panel}
<h2>{t('html.charts_title', lang)}</h2>
{chart_slots if chart_slots else f"<p>{t('html.empty.charts', lang)}</p>"}
<h2>{t('html.summary_title', lang)}</h2>
{text_panel}
{advisory_html}
<div class="footer">
{format_message('html.footer', lang, note=_esc(source_note))}
</div>
<script>
var CHARTS = {json.dumps(charts, ensure_ascii=False)};
CHARTS.forEach(function(spec, i) {{
  var el = document.getElementById('chart-' + i);
  if (el) {{ Plotly.newPlot(el, spec.data, spec.layout, {{responsive:true, displayModeBar:false}}); }}
}});
</script>
</body>
</html>"""


def _plotly_js_bundle() -> str:
    """读取 plotly.js 离线包内容（内联进单文件 HTML）。"""
    import plotly

    import pathlib
    pkg_dir = pathlib.Path(plotly.__file__).parent
    candidates = [
        pkg_dir / "package_data" / "plotly.min.js",
        pkg_dir / "package_data" / "plotly-latest.min.js",
    ]
    for c in candidates:
        if c.exists():
            return c.read_text(encoding="utf-8")
    # 兜底：plotly.io.get_plotlyjs()
    try:
        import plotly.io as pio
        return pio.get_plotlyjs()
    except Exception:  # noqa: BLE001
        return ""


def write_final_html(
    html_text: str,
    out_dir,
    ticker: str,
    timestamp: str,
) -> str:
    """落盘 HTML 最终报告到 ``<out_dir>/html/final_<ticker>_<timestamp>.html``。

    目录不存在自动创建；同时清理同目录下同 ticker 的历史临时/半成品文件，
    避免目录嵌套与残留。
    """
    from pathlib import Path

    target = Path(out_dir) / "html"
    target.mkdir(parents=True, exist_ok=True)
    safe = _safe_ticker(ticker)
    path = target / f"final_{safe}_{timestamp}.html"
    path.write_text(html_text, encoding="utf-8")
    _cleanup_tmp_files(target, keep=path)
    return str(path)


def _cleanup_tmp_files(target_dir, keep) -> None:
    """清理同目录下的临时/半成品文件（.tmp / ~ 临时副本），保留正式产物。"""
    from pathlib import Path

    d = Path(target_dir)
    if not d.is_dir():
        return
    for p in d.iterdir():
        if p == keep or not p.is_file():
            continue
        name = p.name
        if name.endswith(".tmp") or name.startswith("~") or name.endswith(".part"):
            try:
                p.unlink()
            except OSError:
                pass
