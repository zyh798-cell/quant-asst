# -*- coding: utf-8 -*-
"""示例 03：全链路一键跑（Step 3 -> 4 -> 5 -> 6）。

用途：回测（自然语言 -> 假设 -> 代码 -> 沙箱执行） -> 多 Agent 辩论 ->
    红队审计 -> 风控定级 -> 输出 Markdown 双报告 + Plotly 交互式 HTML 报告。
适用场景：查看完整研究流水线一次跑通，并产出可交互浏览的 HTML 报告。
是否需要 API Key：否。默认 mock 离线模式，跳过真实 LLM、不消耗 token。
是否依赖本地 parquet 缓存：是。回测标的 cn:600519 使用本地缓存区间
    （2024-11-17 ~ 2026-11-17）；本地无缓存时会经 AkShare 联网抓取一次后缓存。

运行命令（在项目根目录执行）:
    uv run python examples/example_3_full_pipeline.py

预期产出:
    - output/debate_reports/<run_id>.md          辩论报告
    - output/audit/audit_<ticker>_<timestamp>.md 审计意见书
    - output/audit/final_<ticker>_<timestamp>.md 最终量化分析报告
    - output/html/final_<ticker>_<timestamp>.html Plotly 交互式报告（单文件）
    - var/trajectories/<run_id>.jsonl            各阶段轨迹

说明:
    - 默认启用 mock 离线模式，不消耗 LLM token、无需密钥。
    - 回测标的 cn:600519 使用本地缓存区间（2024-11-17 ~ 2026-11-17）；
      若本地无缓存会经 AkShare 联网抓取。
    - HTML 报告内嵌 plotly.js（约 4.8 MB 单文件），浏览器直接打开即可交互浏览。
    - 如需真实 LLM，删除 examples/_common.py 顶部的 QUANTSENTINEL_LLM_MOCK 设置，
      并在 .env 配置有效 DEEPSEEK_API_KEY。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _common  # noqa: E402

#: 示例硬编码参数；cn:600519 为项目默认标的，本地缓存齐全
SYMBOL = "cn:600519"
HYPOTHESIS = (
    f"{SYMBOL} 双均线趋势策略：5 日线上穿 20 日线买入，死叉卖出，"
    "测近两年（2024-11-17 ~ 2026-11-17）"
)
THRESHOLD = "high"


def main() -> int:
    _common.banner("示例 03：全链路一键跑（回测 -> 辩论 -> 审计 -> 风控 -> HTML）")
    print(f"标的       : {SYMBOL}")
    print(f"策略描述   : {HYPOTHESIS}")
    print(f"门控阈值   : {THRESHOLD}")
    print("模式       : mock 离线（QUANTSENTINEL_LLM_MOCK=1，不消耗 token）")

    settings = _common.settings()

    _common.step(1, "回测（Step 3：自然语言 -> 假设 -> 代码 -> 沙箱执行）")
    print("  执行中，请稍候（首次含沙箱启动与行情读取）...")

    _common.step(2, "多 Agent 辩论（Step 4：bull / bear / risk_check / reviewer）")
    _common.step(3, "红队审计 + 风控综合（Step 5：redteam -> gate -> risk_officer）")
    _common.step(4, "生成 Markdown 双报告 + Plotly HTML 报告（Step 6）")

    result = _common.run_full_pipeline(
        settings, HYPOTHESIS, SYMBOL, threshold=THRESHOLD, with_html=True
    )

    _common.step(5, "各阶段结果")
    print("  [回测]")
    _common.print_backtest_summary(result["backtest_state"])
    print("\n  [辩论]")
    _common.print_debate_summary(result["outcome"])
    print("\n  [审计 / 风控]")
    _common.print_audit_summary(result["final_report"])

    _common.step(6, "产物")
    print(f"  辩论报告 md   : {result['debate_md']}")
    print(f"  审计意见书    : {result['audit_md']}")
    print(f"  最终分析报告  : {result['final_md']}")
    print(f"  交互式 HTML   : {result['html_path']}")

    print("\n完成：浏览器打开 HTML 报告即可查看 K 线 / 信号 / 净值 / 回撤交互图表。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
