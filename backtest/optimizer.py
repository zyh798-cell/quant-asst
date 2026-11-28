"""参数网格寻优 + 样本外验证（Step J）。

设计原则（与项目硬约束一致）：

- **纯确定性**：不调用 LLM、不使用随机数、不写入时间戳；同一输入重复运行
  得到逐字节一致的指标与报告。
- **fail-closed**：网格解析失败、参数类型非法、组合数超限（>100）、策略不接受
  ``params`` 形参，一律显式报错，绝不静默忽略或降级。
- **准入门槛**：样本内成交笔数不足 :data:`MIN_IN_SAMPLE_TRADES` 的组合标记
  ineligible，不参与选优，避免「零成交 + 零回撤」噪声组合靠指标当选。
- **防泄漏**：切分点在寻优前一次性固定并校验一致；选优只用样本内指标，
  样本外仅在最终验证时使用一次。
- **过拟合显式化**：先按样本内指标选最优组合，再对照该组合的样本外表现；
  样本外显著劣于样本内时标注 ``degraded`` 并写明触发原因，不隐藏。

典型用法（CLI 入口见 ``cli.py optimize``）::

    grid = parse_param_grid("short_window=5,10;long_window=20,30")
    result = optimize_grid(df, strategy_code, symbol, settings, grid)
"""

from __future__ import annotations

import itertools
import json
import math
import re
from typing import Any, Callable

from core.config import Settings
from core.markets import Symbol

#: 参数候选值允许的类型
ParamValue = float | int

#: 参数网格：参数名 -> 有序去重的候选值（顺序即展开顺序，保证确定性）
ParamGrid = dict[str, tuple[ParamValue, ...]]

#: 组合回测执行器：``(df, params, index) -> {"overall"/"in_sample"/"out_sample"}``
#: 指标字典；默认实现走沙箱回测，测试可注入确定性假执行器。
Evaluator = Callable[[Any, dict[str, ParamValue], int], dict[str, Any]]

#: 选优指标（均「越大越好」：最大回撤为负值，越接近 0 越好）
SELECT_METRICS: tuple[str, ...] = ("sharpe", "total_return", "max_drawdown")

#: 主选优指标（固定为样本内夏普，Step J 补充要求第 3 条）
PRIMARY_METRIC = "sharpe"

#: 对照指标：按样本内总收益另做排序，结论冲突时并列呈现、不做加权综合
COMPARISON_METRIC = "total_return"

#: 组合数上限（Step J 补充要求第 4 条：超过 100 拒绝执行）
MAX_GRID_COMBINATIONS = 100

#: 样本内最少成交笔数门槛：低于此值的组合标记 ineligible，不参与选优
MIN_IN_SAMPLE_TRADES = 5

#: 样本外劣化判定阈值（全部为确定性常量，报告须原样披露）
DEGRADATION_SHARPE_RATIO = 0.5      # 样本外夏普 < 样本内夏普 × 50%
DEGRADATION_DRAWDOWN_EXTRA = 0.10   # 样本外最大回撤比样本内更深超过 10 个百分点


# ---------------------------------------------------------------------------
# 网格解析与展开
# ---------------------------------------------------------------------------


def _normalize_values(key: str, values: Any) -> tuple[ParamValue, ...]:
    """把候选值归一化为去重后的数字元组（保序，确定性）。"""
    if isinstance(values, (str, bytes)) or not isinstance(values, (list, tuple)):
        raise ValueError(f"参数 {key!r} 的候选值必须是数组或逗号分隔的数字")

    out: list[ParamValue] = []
    for raw in values:
        if isinstance(raw, bool):
            raise ValueError(f"参数 {key!r} 的取值 {raw!r} 不是合法数字（布尔值不允许）")
        if isinstance(raw, str):
            text = raw.strip()
            try:
                num: ParamValue = int(text)
            except ValueError:
                try:
                    num = float(text)
                except ValueError as exc:
                    raise ValueError(f"参数 {key!r} 的取值 {raw!r} 不是数字") from exc
        elif isinstance(raw, (int, float)):
            num = raw
        else:
            raise ValueError(f"参数 {key!r} 的取值 {raw!r} 类型不受支持")

        if isinstance(num, float):
            if not math.isfinite(num):
                raise ValueError(f"参数 {key!r} 的取值 {raw!r} 必须是非无穷有限数")
            if num.is_integer():
                num = int(num)
        if num not in out:
            out.append(num)

    if not out:
        raise ValueError(f"参数 {key!r} 没有任何候选值")
    return tuple(out)


def parse_param_grid(raw: str) -> ParamGrid:
    """解析参数网格字符串（fail-closed：非法输入直接抛 ValueError）。

    支持两种写法：

    - 分号或空格分隔的 ``key=v1,v2``，花括号可选：
      ``short_window=5,10;long_window=20,30`` 或 ``short={5,10} long={20,30}``；
    - JSON 对象：``{"short_window": [5, 10], "long_window": [20, 30]}``。

    Returns:
        ``{参数名: (候选值, ...)}``，键与值均保持输入顺序（决定展开顺序）。
    """
    text = (raw or "").strip()
    if not text:
        raise ValueError("参数网格不能为空（示例：--grid 'short_window=5,10;long_window=20,30'）")

    if text.startswith("{"):
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"参数网格 JSON 解析失败：{exc}") from exc
        if not isinstance(payload, dict) or not payload:
            raise ValueError('参数网格 JSON 必须是非空对象，如 {"short_window": [5, 10]}')
        grid: ParamGrid = {}
        for key, values in payload.items():
            grid[str(key)] = _normalize_values(str(key), values)
        return grid

    grid = {}
    for part in re.split(r"[;\s]+", text):
        if not part:
            continue
        if "=" not in part:
            raise ValueError(
                f"网格项 {part!r} 缺少 '='（正确写法如 short_window=5,10）"
            )
        key, _, raw_values = part.partition("=")
        key = key.strip()
        if not key:
            raise ValueError(f"网格项 {part!r} 的参数名为空")
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            raise ValueError(f"参数名 {key!r} 非法（只允许字母/数字/下划线，且不以数字开头）")
        values_text = raw_values.strip().strip("{}()[]")
        items = [v.strip() for v in re.split(r"[,，]+", values_text) if v.strip()]
        grid[key] = _normalize_values(key, items)
    if not grid:
        raise ValueError("参数网格为空")
    return grid


def expand_grid(grid: ParamGrid) -> list[dict[str, ParamValue]]:
    """笛卡尔展开参数网格（顺序确定：键按插入序、值按输入序）。"""
    if not isinstance(grid, dict) or not grid:
        raise ValueError("参数网格必须是非空字典")
    keys: list[str] = []
    value_lists: list[tuple[ParamValue, ...]] = []
    for key, values in grid.items():
        normalized = _normalize_values(str(key), values)
        keys.append(str(key))
        value_lists.append(normalized)

    # 上限在展开**之前**判定：避免超大网格真的生成天量组合而卡死
    total = 1
    for values in value_lists:
        total *= len(values)
    if total > MAX_GRID_COMBINATIONS:
        raise ValueError(
            f"参数组合数 {total} 超过上限 {MAX_GRID_COMBINATIONS}（缩小网格或提高单参数分辨率）"
        )
    return [dict(zip(keys, combo)) for combo in itertools.product(*value_lists)]


# ---------------------------------------------------------------------------
# 选优与劣化判定
# ---------------------------------------------------------------------------


def _rank_num(value: float | None) -> float:
    """排序用数值：指标缺失排最后（+inf），否则取负值使「越大越靠前」。"""
    return float("inf") if value is None else -float(value)


def _param_repr(params: dict[str, ParamValue]) -> str:
    """参数的确定性字符串表示（仅用于并列时的稳定排序）。"""
    return repr(sorted(params.items()))


def select_best(
    combinations: list[dict[str, Any]], metric: str = "sharpe"
) -> tuple[int, dict[str, Any]]:
    """按样本内指标选出最优组合（确定性：并列时依次比较次级指标与参数串）。

    排序优先级（全部为**样本内**指标，绝不引入样本外信息）：
    样本内 ``metric`` > 样本内 ``total_return`` > 参数字典序。
    任何指标缺失（``None``）都排在有值之后。

    Raises:
        ValueError: 组合列表为空或 ``metric`` 不在 :data:`SELECT_METRICS`。
    """
    if metric not in SELECT_METRICS:
        raise ValueError(f"不支持的选优指标 {metric!r}（可选：{', '.join(SELECT_METRICS)}）")
    if not combinations:
        raise ValueError("组合列表为空，无法选优")

    def rank(index_row: tuple[int, dict[str, Any]]) -> tuple:
        _, row = index_row
        in_m = row.get("in_sample") or {}
        return (
            _rank_num(in_m.get(metric)),
            _rank_num(in_m.get("total_return")),
            _param_repr(row.get("params") or {}),
        )

    return sorted(enumerate(combinations), key=rank)[0]


def evaluate_degradation(best: dict[str, Any]) -> tuple[bool, list[str]]:
    """判断最优组合是否「样本外显著劣于样本内」（确定性阈值，不隐藏）。

    命中任一条件即判 ``degraded``：

    1. 样本内夏普为正且样本外夏普低于其 50%（:data:`DEGRADATION_SHARPE_RATIO`）；
    2. 样本内总收益为正而样本外总收益非正（符号翻转）；
    3. 样本外最大回撤比样本内更深超过 10 个百分点（:data:`DEGRADATION_DRAWDOWN_EXTRA`）。
    """
    in_m = best.get("in_sample") or {}
    out_m = best.get("out_sample") or {}

    s_in, s_out = in_m.get("sharpe"), out_m.get("sharpe")
    r_in, r_out = in_m.get("total_return"), out_m.get("total_return")
    dd_in, dd_out = in_m.get("max_drawdown"), out_m.get("max_drawdown")

    reasons: list[str] = []
    if (
        isinstance(s_in, (int, float)) and isinstance(s_out, (int, float))
        and s_in > 0 and s_out < s_in * DEGRADATION_SHARPE_RATIO
    ):
        reasons.append(
            f"样本外夏普 {s_out:.3f} 低于样本内夏普 {s_in:.3f} 的 "
            f"{DEGRADATION_SHARPE_RATIO:.0%}"
        )
    if (
        isinstance(r_in, (int, float)) and isinstance(r_out, (int, float))
        and r_in > 0 and r_out <= 0
    ):
        reasons.append(
            f"样本内总收益 {r_in:+.2%} 为正，样本外总收益 {r_out:+.2%} 非正（符号翻转）"
        )
    if (
        isinstance(dd_in, (int, float)) and isinstance(dd_out, (int, float))
        and dd_out < dd_in - DEGRADATION_DRAWDOWN_EXTRA
    ):
        reasons.append(
            f"样本外最大回撤 {dd_out:.2%} 比样本内 {dd_in:.2%} 更深超过 "
            f"{DEGRADATION_DRAWDOWN_EXTRA:.0%}"
        )
    return bool(reasons), reasons


# ---------------------------------------------------------------------------
# 沙箱执行器与编排
# ---------------------------------------------------------------------------


def _sandbox_evaluator(
    strategy_code: str,
    symbol: Symbol,
    settings: Settings,
    *,
    initial_capital: float,
    train_ratio: float,
    sandbox_mode: str,
    run_id: str,
) -> Evaluator:
    """构造默认执行器：逐组合送入沙箱回测（不调用 LLM，结果确定性）。"""
    from tools.backtest_sandbox import run_backtest_in_sandbox

    def evaluate(df: Any, params: dict[str, ParamValue], index: int) -> dict[str, Any]:
        output = run_backtest_in_sandbox(
            strategy_code,
            df,
            symbol,
            settings,
            mode=sandbox_mode,
            initial_capital=initial_capital,
            train_ratio=train_ratio,
            run_id=f"{run_id}-c{index}",
            params=params,
        )
        dumped = output.result.model_dump()
        return {
            "overall": dumped["overall"],
            "in_sample": dumped["in_sample"],
            "out_sample": dumped["out_sample"],
            "out_sample_start": dumped.get("out_sample_start"),
        }

    return evaluate


def _validate_frame(df: Any) -> None:
    """回测数据前置校验（缺列直接报错，fail-closed）。"""
    columns = getattr(df, "columns", None)
    if columns is None:
        raise ValueError("回测数据缺少 DataFrame 列信息")
    required = {"date", "open", "high", "low", "close", "volume"}
    missing = required - set(columns)
    if missing:
        raise ValueError(f"回测数据缺少必需列：{sorted(missing)}")
    if len(df) < 5:
        raise ValueError(f"回测数据不足 5 根 K 线（当前 {len(df)} 根）")


def split_eligibility(rows: list[dict[str, Any]]) -> tuple[list[int], list[dict[str, Any]]]:
    """按样本内成交笔数门槛把组合分为可参与选优 / ineligible。

    门槛（:data:`MIN_IN_SAMPLE_TRADES`）的目的：零成交或极少成交的组合可能
    「零回撤 + 高夏普」，纯属噪声而非有效策略，不允许靠这类指标当选。

    Returns:
        ``(eligible_indexes, ineligible_records)``；ineligible 记录含
        ``index / params / in_sample_n_trades / reason``，供报告单独列出。
    """
    eligible: list[int] = []
    ineligible: list[dict[str, Any]] = []
    for row in rows:
        n_trades = (row.get("in_sample") or {}).get("n_trades")
        if isinstance(n_trades, int) and n_trades >= MIN_IN_SAMPLE_TRADES:
            eligible.append(int(row["index"]))
        else:
            shown = "N/A" if n_trades is None else str(n_trades)
            ineligible.append({
                "index": int(row["index"]),
                "params": row.get("params") or {},
                "in_sample_n_trades": n_trades,
                "reason": f"样本内成交笔数 {shown} < {MIN_IN_SAMPLE_TRADES}（不参与选优）",
            })
    return eligible, ineligible


def optimize_grid(
    df: Any,
    strategy_code: str,
    symbol: Symbol,
    settings: Settings,
    grid: ParamGrid,
    *,
    initial_capital: float = 1_000_000.0,
    train_ratio: float | None = None,
    sandbox_mode: str = "local",
    run_id: str = "optimize",
    evaluator: Evaluator | None = None,
    on_progress: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    """逐组合回测并选出样本内最优，输出报告所需的结构化结果。

    防泄漏约定（Step J 补充要求第 4 条）：

    - 切分点在寻优开始前由 ``train_ratio`` **一次性固定**，全部分组合共用；
      若各组合返回的样本外起点不一致，立即报错中止（视为切分泄漏风险）。
    - 网格遍历与选优**只读样本内指标**；样本外指标仅在选出最优组合后做最终
      验证时使用一次（劣化判定），不参与任何筛选或排序。

    选优规则：主指标固定为样本内夏普（:data:`PRIMARY_METRIC`）；样本内成交笔数
    不足 :data:`MIN_IN_SAMPLE_TRADES` 的组合标记 ineligible、不参与选优。另按
    样本内总收益（:data:`COMPARISON_METRIC`）给出对照排名，结论冲突时并列呈现。

    Args:
        df: 标准 OHLCV DataFrame（缓存帧即可，本函数不做网络请求）。
        strategy_code: 策略代码文本（须定义 ``generate_positions(df, params=None)``）。
        symbol: 回测标的。
        settings: 全局配置。
        grid: 参数网格（通常来自 :func:`parse_param_grid`）。
        initial_capital: 初始资金。
        train_ratio: 样本内占比；None 用 ``settings.train_test_split``。
        sandbox_mode: 沙箱模式（docker | local）。
        run_id: 沙箱工作区前缀。
        evaluator: 可选自定义执行器（测试注入用）；缺省走沙箱回测。
        on_progress: 可选进度回调 ``(已完成数, 总数)``。

    Returns:
        报告用字典（键稳定、无时间戳，保证同一输入重复运行逐字节一致）。

    Raises:
        ValueError: 参数非法（网格/切分比例/数据列）、全部组合 ineligible、切分点不一致。
        RuntimeError: 某个组合回测失败（附参数与原始原因）。
    """
    _validate_frame(df)
    ratio = settings.train_test_split if train_ratio is None else float(train_ratio)
    if not 0.0 < ratio < 1.0:
        raise ValueError(f"样本内占比必须在 (0, 1) 区间，收到 {ratio}")

    combos = expand_grid(grid)
    active_evaluator = evaluator or _sandbox_evaluator(
        strategy_code, symbol, settings,
        initial_capital=initial_capital,
        train_ratio=ratio,
        sandbox_mode=sandbox_mode,
        run_id=run_id,
    )

    rows: list[dict[str, Any]] = []
    for index, params in enumerate(combos):
        try:
            metrics = active_evaluator(df, params, index)
        except Exception as exc:  # noqa: BLE001 —— 附带组合上下文后统一上抛
            from tools.backtest_sandbox import SandboxExecutionError

            if isinstance(exc, SandboxExecutionError):
                # 契约类错误（如策略不接受 params）原样上抛，保留明确原因
                raise
            raise RuntimeError(
                f"参数组合 #{index} 回测失败（params={params}）：{exc}"
            ) from exc
        row = {"index": index, "params": params}
        row.update(metrics)
        rows.append(row)
        if on_progress is not None:
            on_progress(index + 1, len(combos))

    # ---- 切分点一致性（防泄漏硬性检查）----
    starts = {row.get("out_sample_start") for row in rows}
    if len(starts) > 1:
        raise ValueError(
            f"各组合样本外起点不一致（{sorted(str(s) for s in starts)}），存在切分泄漏风险，已中止"
        )

    # ---- 准入门槛 + 双指标选优（只用样本内指标）----
    eligible_indexes, ineligible = split_eligibility(rows)
    if not eligible_indexes:
        raise ValueError(
            f"全部 {len(rows)} 个组合均不满足样本内成交笔数门槛"
            f"（≥{MIN_IN_SAMPLE_TRADES} 笔），无法选优；请扩大回测区间或调整参数网格"
        )
    eligible_rows = [rows[i] for i in eligible_indexes]
    primary_pos, best = select_best(eligible_rows, PRIMARY_METRIC)
    best_index = eligible_indexes[primary_pos]

    comparison_pos, _ = select_best(eligible_rows, COMPARISON_METRIC)
    return_best_index = eligible_indexes[comparison_pos]

    degraded, reasons = evaluate_degradation(best)

    dates = df["date"]
    first, last = dates.iloc[0], dates.iloc[-1]
    return {
        "symbol": symbol.full,
        "market": symbol.market.value,
        "period_start": first.strftime("%Y-%m-%d"),
        "period_end": last.strftime("%Y-%m-%d"),
        "train_ratio": ratio,
        "out_sample_start": rows[0].get("out_sample_start") if rows else None,
        "initial_capital": float(initial_capital),
        "selection_metric": PRIMARY_METRIC,
        "comparison_metric": COMPARISON_METRIC,
        "min_in_sample_trades": MIN_IN_SAMPLE_TRADES,
        "sandbox_mode": sandbox_mode,
        "grid": {key: list(values) for key, values in grid.items()},
        "n_combinations": len(rows),
        "combinations": rows,
        "eligible_indexes": eligible_indexes,
        "ineligible": ineligible,
        "best_index": best_index,
        "best_params": best["params"],
        "return_best_index": return_best_index,
        "metric_agreement": bool(return_best_index == best_index),
        "degraded": degraded,
        "degradation_reasons": reasons,
    }
