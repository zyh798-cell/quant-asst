"""LangGraph 全局状态定义（Step 1 定型，Step 3 起接入图编排）。

设计约定：
- State 使用 TypedDict（LangGraph 官方推荐方式）；
- 复杂对象一律存 Pydantic 模型的 ``model_dump()`` 字典，
  节点间只传可 JSON 序列化的数据，保证 trajectory 完整落盘可回放（硬约束 4）；
- 每个节点返回「增量字典」，由 LangGraph 合并进 State。
"""

from __future__ import annotations

from typing import TypedDict


class QuantAsstState(TypedDict, total=False):
    """图的全局状态。``total=False`` 允许各阶段渐进式填充。"""

    # ---- 运行元信息 ----
    run_id: str             # 本次运行唯一 ID（trajectory 文件名）
    user_input: str         # 用户自然语言策略假设
    market: str             # 目标市场（core.markets.Market 枚举值）
    iterations: int         # 防死循环迭代计数
    error: str              # 最近一次错误信息（非致命时流程继续）

    # ---- 阶段产物（数字一律来自工具返回，硬约束 1）----
    hypothesis: dict        # HypothesisSpec：结构化策略假设（Step 3）
    generated_code: str     # LLM 生成的回测代码（Step 3，仅沙箱执行）
    backtest_result: dict   # BacktestResult：回测指标（Step 2/3，工具产出）
    equity_curve: dict      # 净值曲线数据（供报告图表，工具产出）
    bull_argument: dict     # 多方论点（Step 4）
    bear_argument: dict     # 空方论点（Step 4）

    # ---- Step 4 辩论专用字段 ----
    symbol: str             # 辩论标的（如 cn:300750，缺省由 hypothesis.symbols[0] 解析）
    debate_rounds: int      # 允许的最大辩论轮次（默认 3）
    debate_round: int       # 当前轮次计数（从 1 开始）
    bull_draft: dict        # 本轮多头草稿（未经风控校验）
    bear_draft: dict        # 本轮空头草稿（未经风控校验）
    risk_draft: dict        # 本轮风控核验报告（RiskCheckReport.model_dump()）
    round_transcripts: list  # 逐轮原文累积：[{round, bull, bear, risk_check}]
    risk_checks: list       # 各轮 RiskCheckReport.model_dump() 累积
    bull_kept: list         # 累计通过校验的多头论点索引（按轮次分组的 list[list[int]]）
    bear_kept: list         # 累计通过校验的空头论点索引
    risk_verdict: dict      # 最近一轮风控报告（供裁决引用）
    debate_outcome: dict    # DebateOutcome.model_dump()：辩论完整纪要
    revised_strategy_text: str  # 可直接送入 cli.py run 的修订策略文本

    risk_report: dict       # RiskOfficer 风险评估（Step 5）
    redteam_report: dict    # RedTeamer 审计报告（Step 5，AuditReport.model_dump()）
    redteam_verdict: str    # 红队综合风险定级（low|medium|high|critical）
    risk_gate: dict         # 风控门控结论（RiskGate.model_dump()，Step 5）
    final_report: dict      # FinalAnalysisReport.model_dump()（Step 5 最终报告）
    final_report_path: str  # 最终 Markdown 报告落盘路径（Step 6）
