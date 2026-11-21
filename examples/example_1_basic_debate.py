# -*- coding: utf-8 -*-
"""示例 01：基础多空辩论流程（Step 4）。

用途：输入标的与自然语言策略描述，经多轮多空交替辩论、逐轮风控核验，
    输出结构化裁决结论与可回测的修订策略建议，并落盘 Markdown 报告。
适用场景：首次了解多 Agent 辩论链路（bull / bear / risk_check / reviewer）。
是否需要 API Key：否。默认 mock 离线模式，跳过真实 LLM、不消耗 token；
    如需真实模型，见文末说明。
是否依赖本地 parquet 缓存：否。本示例只跑辩论链路，不取行情数据。

运行命令（在项目根目录执行）:
    uv run python examples/example_1_basic_debate.py

预期产出:
    - output/debate_reports/<run_id>.md   逐轮辩论 + 风控意见 + 裁决报告
    - output/debate_reports/<run_id>.json 结构化 DebateOutcome
    - var/trajectories/<run_id>.jsonl     运行轨迹

说明:
    - 默认启用 mock 离线模式（不消耗 LLM token、无需密钥），见 examples/_common.py。
    - 硬编码标的 cn:300750（宁德时代，A股常见标的）。
    - 本示例只跑辩论链路，不执行回测与审计；需要完整链路请见 example_3。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _common  # noqa: E402

#: 示例硬编码参数（开箱即用）；cn:600519 为项目默认标的，本地缓存齐全
SYMBOL = "cn:600519"
HYPOTHESIS = (
    f"{SYMBOL} 双均线趋势策略：5 日线上穿 20 日线买入，死叉卖出，"
    "测近两年（2024-11-17 ~ 2026-11-17）"
)
ROUNDS = 3


def main() -> int:
    _common.banner("示例 01：基础多空辩论流程（mock 离线模式）")
    print(f"标的       : {SYMBOL}")
    print(f"策略描述   : {HYPOTHESIS}")
    print(f"辩论轮次   : {ROUNDS}")
    print("模式       : mock 离线（QUANTSENTINEL_LLM_MOCK=1，不消耗 token）")

    settings = _common.settings()

    _common.step(1, "构建多空辩论状态机并执行（bull/bear/risk_check/reviewer）")
    outcome, json_path, md_path = _common.run_debate(
        settings, HYPOTHESIS, SYMBOL, rounds=ROUNDS
    )

    _common.step(2, "裁决结论")
    _common.print_debate_summary(outcome)

    _common.step(3, "产物")
    print(f"  Markdown 报告 : {md_path}")
    print(f"  结构化 JSON   : {json_path}")
    print(f"  运行轨迹      : var/trajectories/{outcome.get('run_id')}.jsonl")

    print("\n完成：可继续执行示例 02 对该辩论报告做红队审计。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
