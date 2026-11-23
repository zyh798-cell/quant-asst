"""未来函数（look-ahead）确定性检查（外部代码 review 第 4 项）。

原理（截断历史等价性 / truncated-history equivalence）：
    策略在 t 日收盘后产出信号，结构上只能依赖 t 日及之前的 K 线。因此把数据
    截断到前 k 行重跑同一策略时：
    - 前 ``k-1`` 行信号必须与全量运行完全一致（这些行不依赖被截掉的数据）；
    - **第 k 行本身也必须一致**（t=k-1 日信号所用数据全部保留在截断集内）。

    任何一处不一致都说明策略读到了「当时还不可见」的未来数据。典型手法：
    ``shift(-n)``、``iloc[::-1]`` 反序、``df.max()`` / ``mean()`` / ``std()``
    等全局统计量泄漏、跨列的整表对齐。

只比对前 ``k-1`` 行会漏掉 ``shift(-1)``——截断数据的最后一行仍能看到它在
全量里的「未来」，差异被推迟到下一个检查点才显现。因此这里把比对范围放宽到
整个截断窗口（含末行），使末行型未来引用同样被抓。

引擎本身已是「t 日信号 t+1 开盘执行」的结构性防未来设计（见
``backtest.engine`` 模块 docstring），本模块提供的是**独立的确定性审计**：
不依赖红队 LLM 的主观判断，纯 Python 复算即可复现结论。

定位：先作为测试基建落地；CLI 侧以 ``--lookahead-check`` 可选开关暴露
（默认关闭），挂在 ``backtest`` / ``audit`` 命令上，成本可控。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from backtest.engine import PositionFn

logger = logging.getLogger("quantsentinel.lookahead")

#: 默认截断检查点集合（前若干行；至少保留 5 根 K 线以满足引擎最小长度）
DEFAULT_CHECKPOINTS: tuple[int, ...] = (30, 60, 120)

#: 比较容差：浮点相等判定阈值（仓位为 0/1 类离散值，正常应严格相等）
_TOL = 1e-9


@dataclass
class LookaheadVerdict:
    """单次未来函数检查结论。"""

    passed: bool
    #: 各检查点的比对明细（检查点 -> 是否一致）
    checkpoints: dict[int, bool] = field(default_factory=dict)
    #: 首个发现不一致的检查点（全部一致时为 None）
    first_violation_at: int | None = None
    #: 不一致详情（人类可读）
    detail: str = ""
    #: 参与比对的交易日数（取各检查点最大值）
    compared_days: int = 0

    def __bool__(self) -> bool:  # 便于直接 if verdict:
        return self.passed


def _extract_signal(position_fn: PositionFn, df: pd.DataFrame) -> np.ndarray:
    """调用策略并归一化为逐行 float 数组（与引擎 ``_align_target`` 同口径）。"""
    raw = position_fn(df)
    if isinstance(raw, pd.Series):
        values = raw.to_numpy(dtype=float)
    else:
        values = np.asarray(raw, dtype=float)
    if values.ndim != 1 or len(values) != len(df):
        raise ValueError(
            f"策略输出 shape={values.shape} 与 K 线数 {len(df)} 不一致，无法比对"
        )
    return values


def check_lookahead_determinism(
    df: pd.DataFrame,
    position_fn: PositionFn,
    checkpoints: tuple[int, ...] | list[int] | None = None,
) -> LookaheadVerdict:
    """数据截断一致性检查：识别策略是否引用未来数据。

    Args:
        df: 标准 OHLCV DataFrame（date 升序，至少 6 行）。
        position_fn: 策略函数（与回测同一函数对象）。
        checkpoints: 截断行数集合；缺省 ``DEFAULT_CHECKPOINTS``。

    Returns:
        ``LookaheadVerdict``；``passed=False`` 表示存在未来函数嫌疑。

    Raises:
        ValueError: 数据行数不足以支撑任何检查点。
    """
    n = len(df)
    points = sorted({int(k) for k in (checkpoints or DEFAULT_CHECKPOINTS) if 5 <= k < n})
    if not points:
        raise ValueError(
            f"数据仅 {n} 行，无可用检查点（需满足 5 <= k < {n}）"
        )

    full_signal = _extract_signal(position_fn, df)
    details: dict[int, bool] = {}
    first_bad: int | None = None
    compared = 0
    messages: list[str] = []

    for k in points:
        truncated = df.iloc[:k].reset_index(drop=True)
        try:
            part = _extract_signal(position_fn, truncated)
        except Exception as exc:  # noqa: BLE001 —— 截断执行失败即视为不可信
            details[k] = False
            if first_bad is None:
                first_bad = k
                messages.append(
                    f"k={k}: 截断数据下策略执行失败（{type(exc).__name__}: {exc}）"
                )
            continue

        # 比对整个截断窗口（含末行）：t=k-1 日信号只应依赖截断集内的数据
        a = full_signal[:k]
        b = part[:k]
        same = len(a) == len(b) and bool(np.allclose(a, b, atol=_TOL, rtol=0.0))
        details[k] = same
        compared = max(compared, min(k, len(b)))
        if not same and first_bad is None:
            first_bad = k
            diff_idx = np.nonzero(~np.isclose(a, b, atol=_TOL, rtol=0.0))[0]
            sample = diff_idx[:3]
            messages.append(
                f"k={k}: 截断窗口内有 {len(diff_idx)} 处与全量不一致"
                f"（首处行号 {sample.tolist()}，全量值 {a[sample].tolist()} vs "
                f"截断值 {b[sample].tolist()}）"
            )

    passed = first_bad is None
    if passed:
        logger.info("未来函数确定性检查通过：%d 个检查点全一致", len(points))
    else:
        logger.warning("未来函数确定性检查未通过：%s", "; ".join(messages))

    return LookaheadVerdict(
        passed=passed,
        checkpoints=details,
        first_violation_at=first_bad,
        detail="; ".join(messages),
        compared_days=compared,
    )


def format_lookahead_verdict(verdict: LookaheadVerdict, strategy_name: str = "") -> str:
    """把检查结论渲染为 Markdown 片段（供报告与 CLI 复用）。"""
    tag = f"策略 {strategy_name}：" if strategy_name else ""
    if verdict.passed:
        return (
            f"- 未来函数确定性检查：通过（{len(verdict.checkpoints)} 个截断检查点，"
            f"覆盖 {verdict.compared_days} 个交易日，信号序列完全一致）"
        )
    return (
        f"- 未来函数确定性检查：**未通过** —— {tag}存在引用未来数据的嫌疑。"
        f"首个不一致检查点 k={verdict.first_violation_at}。{verdict.detail}"
    )
