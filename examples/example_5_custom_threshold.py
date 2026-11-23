# -*- coding: utf-8 -*-
"""示例 05：自定义风控阈值演示（medium 严格模式拦截规则）。

用途：对同一份辩论报告分别使用默认阈值 ``high`` 与收紧阈值 ``medium`` 执行
    红队审计 + 风控门控，对比两种阈值下风险提示（banner）与强制约束边界
    （constraint_boundaries）的差异，直观展示「阈值收紧」的拦截效果。
适用场景：风控阈值边界调试，理解「同风险级别在不同阈值下是否触发提示」。
是否需要 API Key：否。默认 mock 离线模式，跳过真实 LLM、不消耗 token。
是否依赖本地 parquet 缓存：否。辩论与审计均不取行情数据。

运行命令（在项目根目录执行）:
    uv run python examples/example_5_custom_threshold.py

预期产出:
    - 终端打印 high / medium 两种阈值下的门控结论对比
    - output/audit/audit_<ticker>_<timestamp>.md   两次审计意见书
    - output/audit/final_<ticker>_<timestamp>.md  两次最终量化分析报告

门控规则（core/risk_gate.py，确定性、可复现）:
    - 致命（critical）：恒拦截交易建议，最终决策 blocked，与阈值无关；
    - 达到或超过阈值：触发报告顶部风险提示 + 强制约束边界；
    - 低于阈值：无强制风险提示。

    本示例中 mock 审计定级为「中（medium）」：
    - 阈值 high   ：medium < high，不触发风险提示（默认宽松）；
    - 阈值 medium ：medium >= medium，触发风险提示与约束边界（严格模式）。

说明:
    - 默认启用 mock 离线模式，不消耗 LLM token、无需密钥。
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _common  # noqa: E402

#: 示例硬编码参数；cn:600519 为项目默认标的，本地缓存齐全
SYMBOL = "cn:600519"
HYPOTHESIS = (
    f"{SYMBOL} 双均线趋势策略：5 日线上穿 20 日线买入，死叉卖出，"
    "测近两年（2024-11-17 ~ 2026-11-17）"
)


def _print_gate(tag: str, final_report: dict) -> None:
    """打印单次审计的门控结论。"""
    gate = final_report.get("risk_gate") or {}
    print(f"\n  [{tag}]")
    print(f"    综合风险定级 : {final_report.get('overall_risk_level')}")
    print(f"    最终决策     : {final_report.get('final_decision')}")
    print(f"    交易建议     : {'已拦截' if not gate.get('trade_suggestion_allowed', True) else '放行'}")
    print(f"    风险提示     : {gate.get('risk_banner') or '（无）'}")
    constraints = gate.get("constraint_boundaries") or []
    print(f"    约束边界     : {len(constraints)} 条")
    for c in constraints:
        print(f"      - {c}")


def main() -> int:
    _common.banner("示例 05：自定义风控阈值演示（medium 严格模式）")
    print(f"标的       : {SYMBOL}")
    print(f"策略描述   : {HYPOTHESIS}")
    print("模式       : mock 离线（QUANT_ASST_LLM_MOCK=1，不消耗 token）")

    settings = _common.settings()

    _common.step(1, "生成一份辩论报告作为审计输入（mock）")
    _, debate_json, debate_md = _common.run_debate(settings, HYPOTHESIS, SYMBOL)
    print(f"  辩论报告 : {debate_md}")

    # 两次审计使用可区分的落盘时间戳，避免同名文件相互覆盖
    base_ts = datetime.now()
    ts_high = base_ts.strftime("%Y%m%d_%H%M%S")
    ts_medium = (base_ts + timedelta(seconds=1)).strftime("%Y%m%d_%H%M%S")

    _common.step(2, "阈值 high（默认）：medium 风险不触发风险提示")
    _, final_high, audit_md_high, final_md_high = _common.run_audit(
        settings, debate_json, threshold="high", timestamp=ts_high
    )

    _common.step(3, "阈值 medium（收紧）：medium 风险触发风险提示与约束边界")
    _, final_medium, audit_md_medium, final_md_medium = _common.run_audit(
        settings, debate_json, threshold="medium", timestamp=ts_medium
    )

    _common.step(4, "门控结论对比")
    _print_gate("阈值 high", final_high)
    _print_gate("阈值 medium", final_medium)

    _common.step(5, "结论")
    gate_high = final_high.get("risk_gate") or {}
    gate_medium = final_medium.get("risk_gate") or {}
    triggered = bool(gate_medium.get("risk_banner")) and not bool(gate_high.get("risk_banner"))
    print(f"  阈值收紧是否触发风险提示：{'是' if triggered else '否'}")
    print("  说明：同一份中风险审计结论，在 medium 严格模式下被强制标注并列出约束边界，")
    print("        而默认 high 阈值下不触发。致命风险则与阈值无关，恒被拦截。")

    _common.step(6, "产物")
    print(f"  high   审计意见书 : {audit_md_high}")
    print(f"  high   最终报告   : {final_md_high}")
    print(f"  medium 审计意见书 : {audit_md_medium}")
    print(f"  medium 最终报告   : {final_md_medium}")

    print("\n完成：可通过修改 THRESHOLD 常量体验不同阈值。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
