# -*- coding: utf-8 -*-
"""examples 共享工具（Step 7）。

本模块是 5 个示例脚本的公共底座，职责：

1. **默认启用 mock 离线模式**：在导入 ``core``（其间接导入 litellm）之前设置
   ``QUANT_ASST_LLM_MOCK=1``，保证示例无需 LLM 密钥、不消耗 token、可重复执行。
   若调用方已显式设置该变量（真值或假值），则尊重调用方设置，不覆盖。
2. **路径与配置**：把项目根加入 ``sys.path`` 并统一工作目录为项目根，
   提供 ``get_settings`` 封装，保证 ``output/``、``var/``、``.env`` 等相对路径
   不随调用目录漂移（Windows / PowerShell 下同样适用）。
3. **流程封装**：``run_backtest``（Step 3 单链路）、``run_debate``（Step 4）、
   ``run_audit``（Step 5）、``build_html``（Step 6）与 ``run_full_pipeline``（全链路），
   与 ``cli.py`` 的各命令行为保持一致，只是把参数固化为示例默认值。

本文件不属于核心业务代码（core / agents / report），仅服务于 examples 演示。
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

# ---- mock 开关（必须在导入 core / litellm 之前设置）----
# QUANT_ASST_LLM_MOCK 优先级：
#   - 真值（1/true/yes/on，大小写不敏感）：启用 mock 离线模式，**跳过真实 LLM 调用**，
#     由 MockCompletionBackend 读取本地预生成的样例输出（确定性、schema 合法），
#     不消耗 token，无需任何 API 密钥；
#   - 假值（0/false/no/off）：**走真实 LiteLLM API**，需在 .env 配置有效
#     DEEPSEEK_API_KEY；
#   - 未设置：示例用 setdefault 兜底为 "1"（开箱即用、零密钥）。
# 该判据在 core.llm 运行时读取，且 mock 模式会同时设置 LITELLM_OFFLINE_MODE=true，
# 禁止 LiteLLM 后台拉取远端 cost 映射。
os.environ.setdefault("QUANT_ASST_LLM_MOCK", "1")

#: 项目根目录（QuantSentinel/）
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.config import Settings, get_settings  # noqa: E402


# ---------------------------------------------------------------------------
# 基础工具
# ---------------------------------------------------------------------------

def ensure_project_root() -> Path:
    """统一工作目录为项目根，避免相对路径随调用目录漂移。

    示例脚本可能从任意目录被调用（如 ``uv run python /abs/path/example.py``），
    此时 ``Settings`` 的 ``output/``、``var/``、``.env`` 等相对路径会落到调用目录，
    导致产物分散或找不到缓存。这里在首次取配置前把工作目录切到项目根，
    并在发生切换时打印提示。路径全部经由 :mod:`pathlib` 处理，
    分隔符在 Windows / PowerShell 下自动兼容。
    """
    cwd = Path.cwd().resolve()
    if cwd != ROOT:
        os.chdir(ROOT)
        print(f"[路径] 当前目录非项目根，已切换至：{ROOT}")
    return ROOT


def settings() -> Settings:
    """返回进程级配置单例（首次调用时创建运行时目录，工作目录统一到项目根）。"""
    ensure_project_root()
    return get_settings()


def banner(title: str) -> None:
    """打印示例标题分隔线。"""
    print("=" * 78)
    print(title)
    print("=" * 78)


def step(no: int, text: str) -> None:
    """打印步骤行。"""
    print(f"\n[{no}] {text}")


def new_run_id(prefix: str) -> str:
    """生成 run_id（与 CLI 命名风格一致，便于 trajectory 检索）。"""
    return f"{prefix}-{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"


# ---------------------------------------------------------------------------
# 流程封装（与 cli.py 命令行为一致）
# ---------------------------------------------------------------------------

def run_backtest(
    settings: Settings,
    hypothesis: str,
    sandbox_mode: str = "local",
) -> dict[str, Any]:
    """Step 3 单链路：自然语言 -> 假设 -> 代码 -> 沙箱回测。

    Args:
        settings: 全局配置。
        hypothesis: 自然语言策略描述（需包含标的标识，如 ``cn:300750``）。
        sandbox_mode: 沙箱模式，示例默认 ``local``（开发调试）。

    Returns:
        LangGraph final_state（含 ``backtest_result`` / ``equity_curve``）。

    Raises:
        RuntimeError: 链路出错（State['error'] 非空）。
    """
    from core.graph import build_graph
    from core.trajectory import TrajectoryRecorder

    run_id = new_run_id("example-run")
    graph, recorder = build_graph(settings, run_id=run_id, sandbox_mode=sandbox_mode)
    try:
        final_state = graph.invoke({
            "run_id": run_id,
            "user_input": hypothesis,
            "market": settings.default_market.value,
            "iterations": 0,
        })
    finally:
        recorder.close()

    if final_state.get("error"):
        raise RuntimeError(f"回测链路失败：{final_state['error']}")
    return final_state


def run_debate(
    settings: Settings,
    hypothesis: str,
    symbol: str,
    rounds: int = 3,
) -> tuple[dict[str, Any], str, str]:
    """Step 4：多空辩论并落盘报告。

    Returns:
        (outcome, json_path, md_path)。
    """
    from core.debate_graph import build_debate_graph
    from core.trajectory import TrajectoryRecorder
    from report.markdown import write_debate_report

    run_id = new_run_id("example-debate")
    recorder = TrajectoryRecorder(run_id, settings.trajectory_dir)
    graph, _ = build_debate_graph(settings, run_id=run_id, max_rounds=rounds, recorder=recorder)
    try:
        final_state = graph.invoke({
            "run_id": run_id,
            "user_input": hypothesis,
            "market": settings.default_market.value,
            "symbol": symbol,
            "hypothesis": {},
            "iterations": 0,
            "debate_rounds": rounds,
        })
    finally:
        recorder.close()

    outcome = final_state.get("debate_outcome")
    if not outcome:
        raise RuntimeError(f"辩论失败：{final_state.get('error')}")

    md_path = write_debate_report(outcome, settings.output_dir)
    json_path = settings.output_dir / "debate_reports" / f"{run_id}.json"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(outcome, ensure_ascii=False, indent=2), encoding="utf-8")
    return outcome, str(json_path), md_path


def run_audit(
    settings: Settings,
    debate_json_path: str,
    threshold: str = "high",
    timestamp: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any], str, str]:
    """Step 5：红队审计 + 风控综合并落盘报告。

    Args:
        settings: 全局配置。
        debate_json_path: 已有辩论报告 JSON 路径。
        threshold: 风险门控阈值（high 默认 / medium 收紧）。
        timestamp: 落盘时间戳（缺省即时生成，全链路示例复用同一时间戳）。

    Returns:
        (audit_report, final_report, audit_md_path, final_md_path)。
    """
    from core.audit_graph import build_audit_graph
    from core.trajectory import TrajectoryRecorder
    from report.markdown import write_audit_report, write_final_report

    outcome = json.loads(Path(debate_json_path).read_text(encoding="utf-8"))
    symbol = outcome.get("symbol", "")
    market = outcome.get("market", settings.default_market.value)
    timestamp = timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")

    audit_run_id = new_run_id("example-audit")
    recorder = TrajectoryRecorder(audit_run_id, settings.trajectory_dir)
    graph, _ = build_audit_graph(
        settings, run_id=audit_run_id, source_run_id=outcome.get("run_id", ""),
        threshold=threshold, recorder=recorder,
    )
    try:
        final_state = graph.invoke({
            "run_id": audit_run_id,
            "user_input": outcome.get("user_input", ""),
            "market": market,
            "symbol": symbol,
            "hypothesis": {},
            "debate_outcome": outcome,
            "iterations": 0,
        })
    finally:
        recorder.close()

    if final_state.get("error"):
        raise RuntimeError(f"审计失败：{final_state['error']}")

    audit_report = final_state.get("redteam_report") or {}
    final_report = final_state.get("final_report") or {}
    audit_md = write_audit_report(
        audit_report, settings.audit_dir, symbol, timestamp, source_outcome=outcome
    )
    final_md = write_final_report(final_report, settings.audit_dir, symbol, timestamp)
    return audit_report, final_report, audit_md, final_md


def build_html(
    settings: Settings,
    final_report: dict[str, Any] | None,
    audit_report: dict[str, Any] | None,
    debate_outcome: dict[str, Any] | None,
    symbol: str,
    timestamp: str,
    revised_strategy_text: str = "",
) -> str:
    """Step 6：生成 Plotly 交互式 HTML 最终报告，返回落盘路径。"""
    from report.build import build_html_report

    return build_html_report(
        settings=settings,
        final_report=final_report,
        audit_report=audit_report,
        debate_outcome=debate_outcome,
        symbol=symbol,
        timestamp=timestamp,
        revised_strategy_text=revised_strategy_text,
    )


def run_full_pipeline(
    settings: Settings,
    hypothesis: str,
    symbol: str,
    threshold: str = "high",
    with_html: bool = True,
) -> dict[str, Any]:
    """全链路一键跑：回测 -> 辩论 -> 审计 -> 风控定级 -> （可选）HTML 报告。

    Returns:
        含各阶段产物路径与关键结论的字典，便于示例脚本打印。
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    backtest_state = run_backtest(settings, hypothesis)
    outcome, debate_json, debate_md = run_debate(settings, hypothesis, symbol)
    audit_report, final_report, audit_md, final_md = run_audit(
        settings, debate_json, threshold=threshold, timestamp=timestamp
    )

    revised = (outcome.get("verdict") or {}).get("revision") or {}
    revised_text = revised.get("revised_strategy_text", "") if isinstance(revised, dict) else ""

    html_path = ""
    if with_html:
        html_path = build_html(
            settings, final_report, audit_report, outcome, symbol, timestamp, revised_text
        )

    return {
        "backtest_state": backtest_state,
        "outcome": outcome,
        "debate_json": debate_json,
        "debate_md": debate_md,
        "audit_report": audit_report,
        "final_report": final_report,
        "audit_md": audit_md,
        "final_md": final_md,
        "html_path": html_path,
        "timestamp": timestamp,
    }


def print_backtest_summary(backtest_state: dict[str, Any]) -> None:
    """打印回测关键指标（数字全部来自工具返回）。"""
    result = backtest_state.get("backtest_result") or {}
    overall = result.get("overall", {})
    print(f"  标的         : {result.get('symbol', 'N/A')}")
    print(f"  区间         : {result.get('period_start')} ~ {result.get('period_end')}")
    print(f"  样本外起点   : {result.get('out_sample_start', 'N/A')}")
    print(f"  总收益       : {overall.get('total_return')}")
    print(f"  年化收益     : {overall.get('annual_return')}")
    print(f"  最大回撤     : {overall.get('max_drawdown')}")
    print(f"  夏普比率     : {overall.get('sharpe')}")
    print(f"  按笔胜率     : {overall.get('win_rate')}")
    print(f"  成交笔数     : {overall.get('n_trades')}")


def print_debate_summary(outcome: dict[str, Any]) -> None:
    """打印辩论裁决摘要。"""
    verdict = outcome.get("verdict") or {}
    print(f"  轮次         : {outcome.get('rounds')}")
    print(f"  裁决         : {verdict.get('decision')}")
    print(f"  可信度       : {verdict.get('credibility_score')}/100")
    print(f"  共识         : {'; '.join(verdict.get('consensus') or []) or '（无）'}")
    print(f"  分歧         : {'; '.join(verdict.get('disagreements') or []) or '（无）'}")
    if outcome.get("revised_strategy_text"):
        print(f"  修订策略     : {outcome['revised_strategy_text'][:100]}...")


def print_audit_summary(final_report: dict[str, Any]) -> None:
    """打印审计 / 风控定级摘要。"""
    gate = final_report.get("risk_gate") or {}
    print(f"  综合风险定级 : {final_report.get('overall_risk_level')}")
    print(f"  最终决策     : {final_report.get('final_decision')}")
    print(f"  交易建议     : {'已拦截' if not gate.get('trade_suggestion_allowed', True) else '放行'}")
    if gate.get("risk_banner"):
        print(f"  风险提示     : {gate['risk_banner']}")
    if gate.get("constraint_boundaries"):
        print(f"  约束边界     : {len(gate['constraint_boundaries'])} 条（强制）")
