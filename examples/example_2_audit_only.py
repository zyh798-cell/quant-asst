# -*- coding: utf-8 -*-
"""示例 02：单独调用红队审计（Step 5）。

用途：对一份已有的辩论报告 JSON 执行红队审计 + 风控综合，输出独立审计意见书
    与最终量化分析报告。本示例先自动跑一场辩论生成输入，再执行审计，
    保证开箱即用（无需手工准备输入文件）。
适用场景：只关心风险审计与定级，或需要单独复算某份辩论报告的风险结论。
是否需要 API Key：否。默认 mock 离线模式，跳过真实 LLM、不消耗 token。
是否依赖本地 parquet 缓存：否。辩论与审计均不取行情数据。

运行命令（在项目根目录执行）:
    uv run python examples/example_2_audit_only.py

预期产出:
    - output/audit/audit_<ticker>_<timestamp>.md   红队审计意见书
    - output/audit/final_<ticker>_<timestamp>.md  最终量化分析报告
    - output/debate_reports/<run_id>.json         作为审计输入的辩论报告
    - var/trajectories/<audit_run_id>.jsonl       审计轨迹

说明:
    - 默认启用 mock 离线模式，不消耗 LLM token、无需密钥。
    - 红队审计挖掘逻辑漏洞 / 过拟合 / 未来函数 / 幸存者偏差 / 流动性陷阱五类风险，
      并做风险定级（低/中/高/致命）；致命风险将拦截交易建议。
    - 若已有辩论报告 JSON，可把 SOURCE_JSON 改为该路径，跳过自动辩论步骤。
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
THRESHOLD = "high"  # 风险门控阈值：high（默认）| medium（收紧）

#: 可选：指定已有辩论报告 JSON 作为审计输入；留空则自动跑一场辩论生成
SOURCE_JSON = ""


def main() -> int:
    _common.banner("示例 02：单独调用红队审计 + 风控综合（mock 离线模式）")
    print(f"标的       : {SYMBOL}")
    print(f"门控阈值   : {THRESHOLD}")
    print("模式       : mock 离线（QUANT_ASST_LLM_MOCK=1，不消耗 token）")

    settings = _common.settings()

    # ---- 准备审计输入：优先用已有 JSON，否则自动跑一场辩论 ----
    if SOURCE_JSON:
        debate_json = SOURCE_JSON
        print(f"\n[1] 使用已有辩论报告作为审计输入：{SOURCE_JSON}")
    else:
        _common.step(1, "自动执行一场多空辩论，生成审计输入")
        _, debate_json, debate_md = _common.run_debate(settings, HYPOTHESIS, SYMBOL)
        print(f"  辩论报告 md : {debate_md}")
        print(f"  辩论报告 json: {debate_json}")

    _common.step(2, "执行红队审计 + 风控综合（redteam -> gate -> risk_officer）")
    audit_report, final_report, audit_md, final_md = _common.run_audit(
        settings, debate_json, threshold=THRESHOLD
    )

    _common.step(3, "审计结论")
    print(f"  综合风险定级 : {audit_report.get('overall_risk_level')}")
    print(f"  审计发现     : {len(audit_report.get('findings') or [])} 条")
    print(f"  最终决策     : {final_report.get('final_decision')}")
    print(f"  交易建议     : {'已拦截' if not (final_report.get('risk_gate') or {}).get('trade_suggestion_allowed', True) else '放行'}")

    _common.step(4, "产物")
    print(f"  审计意见书   : {audit_md}")
    print(f"  最终分析报告 : {final_md}")

    print("\n完成：审计链路不依赖真实 LLM，可重复执行。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
