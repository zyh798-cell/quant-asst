"""参数网格寻优（Step J）测试：解析、展开、选优、劣化判定、确定性与沙箱透传。

全部使用确定性合成数据，不依赖网络与 LLM。
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backtest.optimizer import (
    DEGRADATION_DRAWDOWN_EXTRA,
    DEGRADATION_SHARPE_RATIO,
    MAX_GRID_COMBINATIONS,
    MIN_IN_SAMPLE_TRADES,
    SELECT_METRICS,
    evaluate_degradation,
    expand_grid,
    optimize_grid,
    parse_param_grid,
    select_best,
)
from report.markdown import render_optimization_markdown, write_optimization_report
from tools.backtest_sandbox import strategy_accepts_params


# ---------------------------------------------------------------------------
# 网格解析与展开
# ---------------------------------------------------------------------------


def test_parse_param_grid_braces_and_semicolon() -> None:
    """用户示例写法（花括号 + 空格分隔）与分号写法等价。"""
    a = parse_param_grid("short={5,10} long={20,30}")
    b = parse_param_grid("short_window=5,10;long_window=20,30")
    assert list(a.values()) == [(5, 10), (20, 30)]
    assert list(b.values()) == [(5, 10), (20, 30)]


def test_parse_param_grid_json_and_numeric_normalization() -> None:
    """JSON 写法可用；整值浮点归一为 int，重复值去重且保序。"""
    grid = parse_param_grid('{"a": [1, 2.0, 2], "b": [0.5]}')
    assert grid == {"a": (1, 2), "b": (0.5,)}


@pytest.mark.parametrize(
    "raw",
    ["", "short_window", "short_window=", "=5,10", "short_window=a,b",
     "1bad=5", "short_window=inf"],
)
def test_parse_param_grid_invalid_raises(raw: str) -> None:
    """非法输入一律 fail-closed 报错，绝不静默忽略。"""
    with pytest.raises(ValueError):
        parse_param_grid(raw)


def test_expand_grid_is_cartesian_in_stable_order() -> None:
    """笛卡尔展开顺序确定（键与值均按输入顺序）。"""
    grid = parse_param_grid("short_window=5,10;long_window=20,30")
    combos = expand_grid(grid)
    assert combos == [
        {"short_window": 5, "long_window": 20},
        {"short_window": 5, "long_window": 30},
        {"short_window": 10, "long_window": 20},
        {"short_window": 10, "long_window": 30},
    ]


def test_expand_grid_enforces_combination_cap() -> None:
    """组合数超限直接报错，避免误写巨型网格阻塞流程。"""
    grid = {f"k{i}": (1, 2) for i in range(MAX_GRID_COMBINATIONS)}
    with pytest.raises(ValueError, match="超过上限"):
        expand_grid(grid)


# ---------------------------------------------------------------------------
# 选优与劣化判定
# ---------------------------------------------------------------------------


def _row(index: int, short: int, long_: int, in_m: dict, out_m: dict) -> dict:
    return {
        "index": index,
        "params": {"short_window": short, "long_window": long_},
        "overall": {},
        "in_sample": in_m,
        "out_sample": out_m,
    }


def test_select_best_by_in_sample_metric_with_deterministic_tiebreak() -> None:
    """按样本内指标选优；完全并列时由参数字典序决定，结果稳定可复现。"""
    rows = [
        _row(0, 5, 20, {"sharpe": 1.0, "total_return": 0.1}, {"sharpe": 0.9}),
        _row(1, 10, 30, {"sharpe": 1.5, "total_return": 0.2}, {"sharpe": 0.2}),
        _row(2, 5, 30, {"sharpe": 1.0, "total_return": 0.1}, {"sharpe": 0.9}),
    ]
    index, best = select_best(rows, "sharpe")
    assert index == 1
    assert best["params"] == {"short_window": 10, "long_window": 30}

    tied = [
        _row(0, 5, 30, {"sharpe": 1.0, "total_return": 0.1}, {"sharpe": 0.5}),
        _row(1, 5, 20, {"sharpe": 1.0, "total_return": 0.1}, {"sharpe": 0.5}),
    ]
    first = select_best(tied, "sharpe")
    second = select_best(list(reversed(tied)), "sharpe")
    assert first[1]["params"] == second[1]["params"]


def test_select_best_rejects_unknown_metric() -> None:
    with pytest.raises(ValueError, match="不支持的选优指标"):
        select_best([_row(0, 5, 20, {}, {})], "not_a_metric")


def test_degradation_triggers_on_sharpe_collapse() -> None:
    best = _row(
        0, 5, 20,
        {"sharpe": 1.0, "total_return": 0.2, "max_drawdown": -0.1},
        {"sharpe": 1.0 * DEGRADATION_SHARPE_RATIO * 0.5, "total_return": 0.1, "max_drawdown": -0.1},
    )
    degraded, reasons = evaluate_degradation(best)
    assert degraded is True
    assert reasons and "夏普" in reasons[0]


def test_degradation_triggers_on_return_sign_flip() -> None:
    best = _row(
        0, 5, 20,
        {"sharpe": 0.5, "total_return": 0.1, "max_drawdown": -0.1},
        {"sharpe": 0.4, "total_return": -0.02, "max_drawdown": -0.1},
    )
    degraded, reasons = evaluate_degradation(best)
    assert degraded is True
    assert any("符号翻转" in r for r in reasons)


def test_degradation_triggers_on_drawdown_widening() -> None:
    best = _row(
        0, 5, 20,
        {"sharpe": 0.5, "total_return": 0.1, "max_drawdown": -0.1},
        {"sharpe": 0.45, "total_return": 0.05,
         "max_drawdown": -0.1 - DEGRADATION_DRAWDOWN_EXTRA - 0.05},
    )
    degraded, reasons = evaluate_degradation(best)
    assert degraded is True
    assert any("回撤" in r for r in reasons)


def test_degradation_not_triggered_when_oos_holds() -> None:
    best = _row(
        0, 5, 20,
        {"sharpe": 1.0, "total_return": 0.2, "max_drawdown": -0.1},
        {"sharpe": 0.8, "total_return": 0.15, "max_drawdown": -0.12},
    )
    degraded, reasons = evaluate_degradation(best)
    assert degraded is False
    assert reasons == []


# ---------------------------------------------------------------------------
# 端到端编排（注入确定性假执行器）
# ---------------------------------------------------------------------------


def _fake_evaluator(df, params, index):
    """纯确定性执行器：指标只由 params 决定，用于验证遍历/选优/劣化链路。"""
    short = params.get("short_window", params.get("short", 5))
    long_ = params.get("long_window", params.get("long", 20))
    spread = max(0.0, 1.0 - abs(short - 5) * 0.3)
    in_m = {"sharpe": 0.2 + spread, "total_return": 0.1 + spread,
            "max_drawdown": -0.1, "n_trades": 6 + index, "annual_return": None,
            "win_rate": None}
    out_m = {"sharpe": 0.2 + spread, "total_return": 0.05 + spread,
             "max_drawdown": -0.15, "n_trades": 2, "annual_return": None,
             "win_rate": None}
    return {
        "overall": dict(in_m),
        "in_sample": in_m,
        "out_sample": out_m,
        "out_sample_start": "2024-09-02",
    }


def _synthetic_frame(n: int = 120) -> pd.DataFrame:
    close = np.linspace(100.0, 200.0, n)
    return pd.DataFrame({
        "date": pd.bdate_range("2024-01-01", periods=n),
        "open": close,
        "high": close * 1.01,
        "low": close * 0.99,
        "close": close,
        "volume": 1e6,
        "amount": 1e7,
        "suspended": False,
        "limit_up": np.nan,
        "limit_down": np.nan,
    })


def test_optimize_grid_passes_each_combo_and_selects_best() -> None:
    """每个组合都以其自身 params 调用执行器，并按样本内指标选出最优。"""
    seen: list[dict] = []

    def recording_evaluator(df, params, index):
        seen.append(dict(params))
        return _fake_evaluator(df, params, index)

    grid = parse_param_grid("short_window=5,10;long_window=20,30")
    result = optimize_grid(
        _synthetic_frame(), "strategy_code", _symbol("cn", "600519"),
        _settings(), grid, evaluator=recording_evaluator, sandbox_mode="local",
    )

    assert len(seen) == 4
    assert seen == [
        {"short_window": 5, "long_window": 20}, {"short_window": 5, "long_window": 30},
        {"short_window": 10, "long_window": 20}, {"short_window": 10, "long_window": 30},
    ]
    assert result["n_combinations"] == 4
    # 样本内 sharpe 在 short=5 时更高（spread 更大），两列中取字典序最小 => (5, 20)
    assert result["best_params"] == {"short_window": 5, "long_window": 20}
    assert result["best_index"] == 0
    assert result["degraded"] is False
    assert result["out_sample_start"] == "2024-09-02"


def test_optimize_grid_marks_degraded_and_keeps_reasons() -> None:
    def degrading_evaluator(df, params, index):
        metrics = _fake_evaluator(df, params, index)
        if params["short_window"] == 5 and params["long_window"] == 20:
            metrics["out_sample"] = {"sharpe": 0.01, "total_return": -0.05,
                                     "max_drawdown": -0.4, "n_trades": 0,
                                     "annual_return": None, "win_rate": None}
        return metrics

    grid = parse_param_grid("short_window=5,10;long_window=20,30")
    result = optimize_grid(
        _synthetic_frame(), "strategy_code", _symbol("cn", "600519"),
        _settings(), grid, evaluator=degrading_evaluator,
    )
    assert result["degraded"] is True
    assert result["degradation_reasons"]


def test_ineligible_combos_are_excluded_and_listed() -> None:
    """样本内笔数不足门槛的组合不参与选优，并单独列出原因。"""
    def sparse_evaluator(df, params, index):
        metrics = _fake_evaluator(df, params, index)
        metrics["in_sample"]["n_trades"] = 2 if params["short_window"] == 5 else 9
        return metrics

    grid = parse_param_grid("short_window=5,10;long_window=20,30")
    result = optimize_grid(
        _synthetic_frame(), "strategy_code", _symbol("cn", "600519"),
        _settings(), grid, evaluator=sparse_evaluator,
    )
    assert {item["index"] for item in result["ineligible"]} == {0, 1}
    assert all("成交笔数" in item["reason"] for item in result["ineligible"])
    # 若允许 short=5 参选，它会靠更高夏普当选；现在必须落在合格组合上
    assert result["best_params"]["short_window"] == 10
    assert result["best_index"] in set(result["eligible_indexes"])
    md = render_optimization_markdown(result)
    assert "不参与选优的组合" in md
    assert "样本内成交笔数" in md


def test_all_ineligible_raises_instead_of_fake_best() -> None:
    """全部组合不合格时报错，绝不退而求其次给出「最优」。"""
    def too_sparse(df, params, index):
        metrics = _fake_evaluator(df, params, index)
        metrics["in_sample"]["n_trades"] = 1
        return metrics
    with pytest.raises(ValueError, match="门槛"):
        optimize_grid(
            _synthetic_frame(), "code", _symbol("cn", "600519"), _settings(),
            {"short_window": (5, 10)}, evaluator=too_sparse,
        )


def test_metric_disagreement_presented_without_weighting() -> None:
    """主指标（夏普）与总收益首位不一致时如实并列，不做加权综合。"""
    def conflicting_evaluator(df, params, index):
        metrics = _fake_evaluator(df, params, index)
        if params["short_window"] == 5:
            metrics["in_sample"]["sharpe"] = 2.0
            metrics["in_sample"]["total_return"] = 0.1
        else:
            metrics["in_sample"]["sharpe"] = 0.5
            metrics["in_sample"]["total_return"] = 0.9
        out = dict(metrics["in_sample"])
        out["max_drawdown"] = -0.1
        metrics["out_sample"] = out
        return metrics

    grid = parse_param_grid("short_window=5,10;long_window=20,30")
    result = optimize_grid(
        _synthetic_frame(), "code", _symbol("cn", "600519"),
        _settings(), grid, evaluator=conflicting_evaluator,
    )
    assert result["best_params"]["short_window"] == 5
    assert result["best_index"] != result["return_best_index"]
    assert result["metric_agreement"] is False
    md = render_optimization_markdown(result)
    assert "结论冲突" in md


def test_split_point_inconsistency_is_rejected() -> None:
    """各组合样本外起点不一致 => 判定切分泄漏风险并中止（防泄漏硬性检查）。"""
    def leaking_evaluator(df, params, index):
        metrics = _fake_evaluator(df, params, index)
        metrics["out_sample_start"] = f"2024-0{8 + index}-01"
        return metrics

    with pytest.raises(ValueError, match="切分泄漏"):
        optimize_grid(
            _synthetic_frame(), "code", _symbol("cn", "600519"), _settings(),
            {"short_window": (5, 10)}, evaluator=leaking_evaluator,
        )


def test_optimize_grid_is_deterministic(tmp_path) -> None:
    """同一输入两次运行：结构化结果与报告文本逐字节一致（无时间戳/随机量）。"""
    grid = parse_param_grid("short_window=5,10;long_window=20,30")
    kwargs = dict(
        df=_synthetic_frame(), strategy_code="strategy_code",
        symbol=_symbol("cn", "600519"), settings=_settings(tmp_path),
        grid=grid, evaluator=_fake_evaluator,
    )
    first = optimize_grid(**kwargs)
    second = optimize_grid(**kwargs)
    assert first == second

    md_first = render_optimization_markdown(first)
    md_second = render_optimization_markdown(second)
    assert md_first == md_second


def test_optimize_grid_rejects_bad_train_ratio() -> None:
    with pytest.raises(ValueError, match="样本内占比"):
        optimize_grid(
            _synthetic_frame(), "code", _symbol("cn", "600519"), _settings(),
            {"short_window": (5,)}, train_ratio=1.5, evaluator=_fake_evaluator,
        )


def test_optimize_grid_wraps_evaluator_failure_with_context() -> None:
    def boom(df, params, index):
        raise RuntimeError("sandbox exploded")

    with pytest.raises(RuntimeError, match="params="):
        optimize_grid(
            _synthetic_frame(), "code", _symbol("cn", "600519"), _settings(),
            {"short": (5, 10)}, evaluator=boom,
        )


# ---------------------------------------------------------------------------
# 报告渲染与落盘
# ---------------------------------------------------------------------------


def test_optimization_report_contains_required_sections(tmp_path) -> None:
    grid = parse_param_grid("short_window=5,10;long_window=20,30")
    result = optimize_grid(
        _synthetic_frame(), "code", _symbol("cn", "600519"), _settings(tmp_path),
        grid, evaluator=_fake_evaluator,
    )
    md = render_optimization_markdown(result)
    for header in ("全组合样本内 / 样本外指标对比", "最优组合", "选优指标对照",
                   "防泄漏声明", "样本外验证结论", "过拟合提示",
                   "资格", "总收益排名", "准入门槛",
                   "样本内总收益", "样本外总收益", "样本内年化",
                   "样本外最大回撤", "样本内夏普", "样本外笔数"):
        assert header in md

    path = write_optimization_report(result, tmp_path / "output")
    expected_name = (
        f"optimization_cn_600519_{result['period_start']}_{result['period_end']}.md"
    )
    assert path.endswith(expected_name)
    written = open(path, encoding="utf-8").read()
    assert written == md


def test_optimization_report_marks_degraded_explicitly(tmp_path) -> None:
    grid = parse_param_grid("short_window=5,10;long_window=20,30")
    result = optimize_grid(
        _synthetic_frame(), "code", _symbol("cn", "600519"), _settings(tmp_path),
        grid, evaluator=_fake_evaluator,
    )
    result["degraded"] = True
    result["degradation_reasons"] = ["样本外夏普 0.100 低于样本内夏普 1.200 的 50%"]
    md = render_optimization_markdown(result)
    assert "判定：degraded（样本外表现显著劣于样本内）" in md
    assert "样本外夏普 0.100 低于样本内夏普 1.200 的 50%" in md


# ---------------------------------------------------------------------------
# 策略契约静态检查
# ---------------------------------------------------------------------------


def test_strategy_accepts_params_contract_check() -> None:
    assert strategy_accepts_params("def generate_positions(df, params=None):\n    return df\n")
    assert strategy_accepts_params("def generate_positions(df, **kwargs):\n    return df\n")
    assert not strategy_accepts_params("def generate_positions(df):\n    return df\n")


# ---------------------------------------------------------------------------
# 真实沙箱透传（合成数据，离线）
# ---------------------------------------------------------------------------

_STRATEGY_WITH_PARAMS = '''\
import pandas as pd

PARAMS = {"short_window": 5, "long_window": 20}


def generate_positions(df, params=None):
    p = {**PARAMS, **(params or {})}
    close = df["close"].astype(float)
    fast = close.rolling(int(p["short_window"])).mean()
    slow = close.rolling(int(p["long_window"])).mean()
    pos = (fast > slow).astype(float)
    return pd.Series(pos.to_numpy(), index=df.index, dtype=float)
'''

_STRATEGY_WITHOUT_PARAMS = '''\
import pandas as pd


def generate_positions(df):
    close = df["close"].astype(float)
    fast = close.rolling(5).mean()
    slow = close.rolling(20).mean()
    return pd.Series((fast > slow).astype(float).to_numpy(), index=df.index, dtype=float)
'''


def test_real_sandbox_plumbs_params_into_strategy(test_settings) -> None:
    """默认执行器把每个组合的 params 注入策略：不同参数产生不同的成交笔数。"""
    from core.markets import Symbol

    n = 200
    # 三个完整周期的正弦：保证双均线在样本内出现多次金叉/死叉（可成交）
    close = 100.0 + 20.0 * np.sin(np.linspace(0.0, 6.0 * np.pi, n))
    df = pd.DataFrame({
        "date": pd.bdate_range("2024-01-01", periods=n),
        "open": close, "high": close * 1.01, "low": close * 0.99, "close": close,
        "volume": 1e6, "amount": 1e7, "suspended": False,
        "limit_up": np.nan, "limit_down": np.nan,
    })
    symbol = Symbol.parse("cn:600519")
    grid = parse_param_grid("short_window=5,20;long_window=10,40")
    result = optimize_grid(
        df, _STRATEGY_WITH_PARAMS, symbol, test_settings, grid,
        sandbox_mode="local", run_id="opt-test",
    )
    assert result["n_combinations"] == 4
    assert set(result["eligible_indexes"]), "应至少有一个组合满足准入门槛"
    trade_counts = {
        (r["params"]["short_window"], r["params"]["long_window"]): r["in_sample"]["n_trades"]
        for r in result["combinations"]
    }
    assert len(set(trade_counts.values())) > 1, f"参数未实际影响策略：{trade_counts}"
    best = result["combinations"][result["best_index"]]
    assert best["in_sample"]["n_trades"] >= MIN_IN_SAMPLE_TRADES
    # 切分点一次性固定：所有组合样本外起点一致
    assert len({r.get("out_sample_start") for r in result["combinations"]}) == 1


def test_real_sandbox_rejects_strategy_without_params(test_settings) -> None:
    """fail-closed：策略不接受 params 形参时在执行前给出明确错误。"""
    from core.markets import Symbol
    from tools.backtest_sandbox import SandboxExecutionError

    with pytest.raises(SandboxExecutionError, match="params"):
        optimize_grid(
            _synthetic_frame(), _STRATEGY_WITHOUT_PARAMS, Symbol.parse("cn:600519"),
            test_settings, {"short_window": (5, 10)}, sandbox_mode="local",
        )


# ---------------------------------------------------------------------------
# 小工具：避免测试依赖全局单例配置
# ---------------------------------------------------------------------------


def _symbol(market: str, code: str):
    from core.markets import Symbol

    return Symbol.parse(f"{market}:{code}")


def _settings(tmp_path=None):
    from core.config import Settings

    if tmp_path is None:
        return Settings(_env_file=None, var_dir="var")
    return Settings(_env_file=None, var_dir=str(tmp_path / "var"))
