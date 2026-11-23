# -*- coding: utf-8 -*-
"""示例 04：离线 mock 模式演示（无需 LLM 密钥，推荐初次体验）。

用途：在完全不配置任何 API 密钥的前提下，跑通「回测 -> 辩论 -> 审计 ->
    风控定级 -> Markdown + HTML 报告」全流程。所有 LLM 调用由脚本化 mock
    后端接管，返回确定性、schema 合法的占位内容，不产生任何网络请求与
    真实模型消耗。
适用场景：新用户首次体验、CI/离线环境演示（推荐入口）。
是否需要 API Key：否。不读取、不校验 DEEPSEEK_API_KEY。
是否依赖本地 parquet 缓存：是。回测标的 cn:600519 使用本地缓存区间
    （2024-11-17 ~ 2026-11-17）；本地无缓存时会经 AkShare 联网抓取一次后缓存。

运行命令（在项目根目录执行）:
    uv run python examples/example_4_mock_offline.py

预期产出:
    - output/debate_reports/<run_id>.md          辩论报告
    - output/audit/audit_<ticker>_<timestamp>.md 审计意见书
    - output/audit/final_<ticker>_<timestamp>.md 最终量化分析报告
    - output/html/final_<ticker>_<timestamp>.html Plotly 交互式报告
    - var/trajectories/<run_id>.jsonl            运行轨迹

说明:
    - 本示例是新用户推荐入口：无需 .env、无需 DEEPSEEK_API_KEY。
    - mock 后端按 prompt 首行特征词判定角色，返回确定性 JSON，
      可重复执行且结果稳定，适合 CI 与离线演示。
    - 行情使用本地缓存（cn:600519，2024-11-17 ~ 2026-11-17）；
      若本地无缓存会经 AkShare 联网抓取一次后缓存。
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
    _common.banner("示例 04：离线 mock 模式全流程演示（无需 LLM 密钥）")
    print(f"标的       : {SYMBOL}")
    print(f"策略描述   : {HYPOTHESIS}")
    print(f"门控阈值   : {THRESHOLD}")
    print("模式       : mock 离线（QUANT_ASST_LLM_MOCK=1）")
    print("密钥要求   : 无（不读取、不校验 DEEPSEEK_API_KEY）")

    settings = _common.settings()

    _common.step(1, "执行全流程：回测 -> 辩论 -> 审计 -> 风控定级 -> 报告")
    result = _common.run_full_pipeline(
        settings, HYPOTHESIS, SYMBOL, threshold=THRESHOLD, with_html=True
    )

    _common.step(2, "流程结论摘要")
    print("  [回测]")
    _common.print_backtest_summary(result["backtest_state"])
    print("\n  [辩论]")
    _common.print_debate_summary(result["outcome"])
    print("\n  [审计 / 风控]")
    _common.print_audit_summary(result["final_report"])

    _common.step(3, "产物")
    print(f"  辩论报告 md   : {result['debate_md']}")
    print(f"  审计意见书    : {result['audit_md']}")
    print(f"  最终分析报告  : {result['final_md']}")
    print(f"  交互式 HTML   : {result['html_path']}")

    print("\n完成：这是零密钥、零 token 消耗的离线演示，可安全重复执行。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
