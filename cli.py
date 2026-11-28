"""Quant Asst 命令行入口（typer）。"""

from __future__ import annotations

import importlib.util
import os
import platform
import uuid
from datetime import datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from core.config import Settings, get_settings
from core.secrets import load_env_file, present_keys, secret_exists

app = typer.Typer(
    help="Quant Asst —— 多智能体多市场量化研究引擎（仅用于教育与研究，不构成投资建议）",
    no_args_is_help=True,
)
console = Console()


@app.callback()
def _startup_key_check() -> None:
    """CLI 启动全局钩子：打印密钥存在性。

    隐私约束：只输出「存在 / 不存在」，**绝不读取或打印密钥明文**。
    """
    load_env_file()  # 先加载项目 .env（不覆盖已有环境变量）
    deepseek_ok = secret_exists("DEEPSEEK_API_KEY")
    console.print(
        f"[dim]密钥检查：DEEPSEEK_API_KEY: {'存在' if deepseek_ok else '不存在'}"
        "（仅显示存在性，不输出明文）[/dim]"
    )
    others = [k for k in present_keys() if k != "DEEPSEEK_API_KEY"]
    if others:
        console.print(f"[dim]其他已配置密钥：{', '.join(others)}[/dim]")


#: 自检的第三方依赖清单
_REQUIRED_MODULES: tuple[str, ...] = (
    "langgraph", "litellm", "akshare", "ccxt", "duckdb", "pyarrow",
    "pandas", "numpy", "qdrant_client", "plotly", "docker", "psutil",
)

#: local 沙箱红色警告（CLI 层强制展示，与 executor 内警告双保险）
LOCAL_SANDBOX_CLI_WARNING = (
    "[bold red]⚠️  使用 --sandbox local：本地受限沙箱仅用于开发调试，"
    "安全隔离不足，禁止生产使用！[/bold red]"
)


@app.command()
def run(
    hypothesis: str = typer.Argument(..., help="自然语言策略假设，例如：双均线策略，5日线上穿20日线买入茅台"),
    market: str = typer.Option(
        None, "--market", "-m",
        help="目标市场前缀：cn / us / hk / futures / crypto（缺省用配置默认）",
    ),
    sandbox: str = typer.Option("docker", "--sandbox", help="沙箱模式：docker（默认，Release 级）| local（开发调试，弱隔离）"),
) -> None:
    """从自然语言策略假设出发运行完整研究流水线（Step 3 链路）。"""
    import uuid
    from datetime import datetime

    if sandbox == "local":
        console.print(LOCAL_SANDBOX_CLI_WARNING)  # 红色警告（CLI 层）

    from core.graph import build_graph

    settings = get_settings()
    run_id = f"run-{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"
    console.print(f"[cyan]run_id[/cyan] = {run_id}（trajectory 与沙箱工作区共用）")

    graph, recorder = build_graph(settings, run_id=run_id, sandbox_mode=sandbox)
    try:
        final_state = graph.invoke({
            "run_id": run_id,
            "user_input": hypothesis,
            "market": market or settings.default_market.value,
            "iterations": 0,
        })
    finally:
        recorder.close()

    if final_state.get("error"):
        console.print(f"[bold red]流水线失败：{final_state['error']}[/bold red]")
        console.print(f"[dim]trajectory：var/trajectories/{run_id}.jsonl[/dim]")
        raise typer.Exit(code=1)

    from core.schemas import BacktestResult

    spec = final_state.get("hypothesis", {})
    console.print(
        f"\n[bold cyan]策略假设[/bold cyan]：{spec.get('strategy_name')} | "
        f"标的 {', '.join(spec.get('symbols', []))} | "
        f"区间 {spec.get('period_start')} ~ {spec.get('period_end')}"
    )
    if spec.get("assumptions"):
        console.print(f"[yellow]默认假设：{'; '.join(spec['assumptions'])}[/yellow]")
    _print_backtest_result(BacktestResult.model_validate(final_state["backtest_result"]), run_id)


@app.command()
def debate(
    hypothesis: str = typer.Argument(..., help="自然语言策略假设，例如：宁德时代双均线策略，5日线上穿20日线买入，死叉卖出，测近两年"),
    symbol_raw: str = typer.Option(None, "--symbol", "-s", help="标的（如 cn:300750）；缺省由 HypothesisAgent 推断"),
    market: str = typer.Option(None, "--market", "-m", help="目标市场前缀：cn / us / hk / futures / crypto（缺省配置默认）"),
    rounds: int = typer.Option(3, "--rounds", min=1, max=3, help="最大辩论轮次（1~3）"),
    no_mock: bool = typer.Option(False, "--no-mock", help="强制调用真实 LLM（缺省：无密钥时自动使用 mock 离线模式）"),
    html: bool = typer.Option(False, "--html", help="额外生成 Plotly 交互式 HTML 最终报告（默认只输出 md）"),
) -> None:
    """多智能体多空辩论：输入策略描述，输出逐轮辩论 + 风控核验 + 裁决结论与修订建议（Step 4）。"""
    import json as _json

    from core.config import get_settings

    settings = get_settings()
    if not no_mock and not os.getenv("QUANT_ASST_LLM_MOCK"):
        # 无显式指定且未检测到密钥时自动启用离线 mock，保证 CI/无网可用
        if not secret_exists("DEEPSEEK_API_KEY"):
            os.environ["QUANT_ASST_LLM_MOCK"] = "1"
            console.print("[yellow]未检测到 DEEPSEEK_API_KEY，已自动切换 mock 离线模式"
                          "（加 --no-mock 可强制真实调用）[/yellow]")

    from core.debate_graph import build_debate_graph
    from core.trajectory import TrajectoryRecorder

    run_id = f"debate-{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"
    console.print(f"[cyan]run_id[/cyan] = {run_id}")

    recorder = TrajectoryRecorder(run_id, settings.trajectory_dir)

    # ---- 前置：HypothesisAgent 解析标的与区间（复用 Step 3 能力，输出仅供辩论引用）----
    resolved_symbol = symbol_raw or ""
    hypothesis_spec: dict = {}
    if not resolved_symbol:
        try:
            from agents.hypothesis import HypothesisAgent

            with console.status("解析策略假设（标的/区间）..."):
                ha = HypothesisAgent(settings, recorder)
                hypo_state = ha.run({
                    "user_input": hypothesis,
                    "market": market or settings.default_market.value,
                    "run_id": run_id,
                    "iterations": 0,
                })
            hypothesis_spec = hypo_state.get("hypothesis") or {}
            symbols = (hypothesis_spec.get("symbols") or []) if hypothesis_spec else []
            resolved_symbol = symbols[0] if symbols else ""
            console.print(f"    标的推断为 [bold]{resolved_symbol}[/bold]")
        except Exception as exc:  # noqa: BLE001 —— 解析失败不阻塞辩论
            console.print(f"[yellow]标的自动推断失败（{type(exc).__name__}: {exc}），"
                          "将在辩论中使用用户原始描述[/yellow]")

    graph, _ = build_debate_graph(settings, run_id=run_id, max_rounds=rounds, recorder=recorder)
    try:
        final_state = graph.invoke({
            "run_id": run_id,
            "user_input": hypothesis,
            "market": market or settings.default_market.value,
            "symbol": resolved_symbol,
            "hypothesis": hypothesis_spec,
            "iterations": 0,
            "debate_rounds": rounds,
        })
    finally:
        recorder.close()

    outcome = final_state.get("debate_outcome")
    if not outcome:
        console.print(f"[bold red]辩论失败：{final_state.get('error')}[/bold red]")
        console.print(f"[dim]trajectory：var/trajectories/{run_id}.jsonl[/dim]")
        raise typer.Exit(code=1)

    # ---- Markdown 报告落盘 ./output/debate_reports/ ----
    from report.markdown import write_debate_report

    md_path = write_debate_report(outcome, settings.output_dir)
    json_path = settings.output_dir / "debate_reports" / f"{run_id}.json"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(_json.dumps(outcome, ensure_ascii=False, indent=2), encoding="utf-8")

    verdict = outcome.get("verdict") or {}
    console.print(f"\n[bold cyan]裁决[/bold cyan]：{verdict.get('decision')} | "
                  f"可信度 {verdict.get('credibility_score')}/100 | "
                  f"轮次 {outcome.get('rounds')}")
    console.print(f"共识：{'; '.join(verdict.get('consensus') or [])}")
    console.print(f"分歧：{'; '.join(verdict.get('disagreements') or [])}")
    if outcome.get("revised_strategy_text"):
        console.print(f"[green]修订策略[/green]：{outcome['revised_strategy_text'][:120]}...")
    console.print(f"\n[dim]Markdown 报告：{md_path}[/dim]")
    console.print(f"[dim]结构化 JSON：{json_path}[/dim]")
    console.print(f"[dim]trajectory：var/trajectories/{run_id}.jsonl[/dim]")

    if outcome.get("revised_strategy_text"):
        console.print("\n[bold]将修订策略送入回测引擎验证：[/bold]")
        console.print(f'  uv run python cli.py run "{outcome["revised_strategy_text"]}"')

    # ---- 可选：Plotly 交互式 HTML 最终报告（--html）----
    if html:
        from report.build import build_html_report

        with console.status("生成 Plotly HTML 报告（含参考回测取数）..."):
            html_path = build_html_report(
                settings=settings,
                final_report=None,
                audit_report=None,
                debate_outcome=outcome,
                symbol=resolved_symbol or outcome.get("symbol", ""),
                timestamp=datetime.now().strftime("%Y%m%d_%H%M%S"),
                revised_strategy_text=outcome.get("revised_strategy_text", ""),
            )
        console.print(f"[dim]HTML 报告：{html_path}[/dim]")


@app.command()
def audit(
    debate_report: Path = typer.Argument(..., exists=True, readable=True,
                                         help="已有辩论报告 JSON 路径（output/debate_reports/<run_id>.json）"),
    threshold: str = typer.Option("high", "--threshold", "-t",
                                  help="风险门控阈值：high（默认）| medium（收紧，中风险即触发风险提示）"),
    no_mock: bool = typer.Option(False, "--no-mock",
                                 help="强制真实 LLM（缺省：未检测到 DEEPSEEK_API_KEY 时自动 mock）"),
    html: bool = typer.Option(False, "--html", help="额外生成 Plotly 交互式 HTML 最终报告（默认只输出 md）"),
) -> None:
    """对已有辩论报告执行红队审计 + 风控综合，产出审计报告与最终量化分析报告（Step 5）。

    流程：读取辩论 JSON -> 红队审计 Agent -> 确定性风控门控 -> 风控综合官 ->
    输出 ``output/audit/audit_<ticker>_<timestamp>.md`` 与
    ``output/audit/final_<ticker>_<timestamp>.md``；加 ``--html`` 时额外输出
    ``output/html/final_<ticker>_<timestamp>.html``。
    """
    import json as _json

    from core.audit_graph import build_audit_graph
    from core.config import get_settings
    from core.trajectory import TrajectoryRecorder
    from report.markdown import write_audit_report, write_final_report

    settings = get_settings()
    if not no_mock and not os.getenv("QUANT_ASST_LLM_MOCK"):
        if not secret_exists("DEEPSEEK_API_KEY"):
            os.environ["QUANT_ASST_LLM_MOCK"] = "1"
            console.print("[yellow]未检测到 DEEPSEEK_API_KEY，已自动切换 mock 离线模式"
                          "（加 --no-mock 可强制真实调用）[/yellow]")

    outcome = _json.loads(debate_report.read_text(encoding="utf-8"))
    source_run_id = outcome.get("run_id", "")
    symbol = outcome.get("symbol", "")
    market = outcome.get("market", settings.default_market.value)

    audit_run_id = f"audit-{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    console.print(f"[cyan]audit_run_id[/cyan] = {audit_run_id}（来源辩论 {source_run_id}）")

    recorder = TrajectoryRecorder(audit_run_id, settings.trajectory_dir)
    graph, _ = build_audit_graph(settings, run_id=audit_run_id, source_run_id=source_run_id,
                                 threshold=threshold, recorder=recorder)
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
        console.print(f"[bold red]审计失败：{final_state['error']}[/bold red]")
        raise typer.Exit(code=1)

    audit_report = final_state.get("redteam_report") or {}
    final_report = final_state.get("final_report") or {}

    audit_md = write_audit_report(audit_report, settings.audit_dir, symbol, timestamp, source_outcome=outcome)
    final_md = write_final_report(final_report, settings.audit_dir, symbol, timestamp)

    gate = final_report.get("risk_gate") or {}
    console.print(f"\n[bold cyan]审计结果[/bold cyan]：综合风险 {final_report.get('overall_risk_level')}"
                  f" | 最终决策 {final_report.get('final_decision')}"
                  f" | 交易建议 {'已拦截' if not gate.get('trade_suggestion_allowed', True) else '放行'}"
                  f"（阈值 {threshold}）")
    console.print(f"[dim]审计报告：{audit_md}[/dim]")
    console.print(f"[dim]最终报告：{final_md}[/dim]")
    console.print(f"[dim]trajectory：var/trajectories/{audit_run_id}.jsonl[/dim]")

    # ---- 可选：Plotly 交互式 HTML 最终报告（--html）----
    if html:
        from report.build import build_html_report

        revised_text = (outcome.get("verdict") or {}).get("revision") or {}
        revised_text = revised_text.get("revised_strategy_text", "") if isinstance(revised_text, dict) else ""
        with console.status("生成 Plotly HTML 报告（含参考回测取数）..."):
            html_path = build_html_report(
                settings=settings,
                final_report=final_report,
                audit_report=audit_report,
                debate_outcome=outcome,
                symbol=symbol,
                timestamp=timestamp,
                revised_strategy_text=revised_text,
            )
        console.print(f"[dim]HTML 报告：{html_path}[/dim]")


@app.command()
def fetch(
    symbol_raw: str = typer.Argument(..., help="统一 symbol，如 cn:600519 / us:AAPL / crypto:BTC/USDT"),
    start: str = typer.Option("2024-01-01", "--start", help="起始日 YYYY-MM-DD"),
    end: str = typer.Option(None, "--end", help="结束日 YYYY-MM-DD（缺省今天）"),
    refresh: bool = typer.Option(False, "--refresh", help="忽略缓存强制抓取"),
) -> None:
    """抓取日线行情并写入本地 Parquet/DuckDB 缓存。"""
    from core.markets import Symbol
    from tools.market_data import fetch_daily_dict

    settings = get_settings()
    end = end or datetime.now().strftime("%Y-%m-%d")
    symbol = Symbol.parse(symbol_raw)
    with console.status(f"抓取 {symbol.full} {start} ~ {end} ..."):
        payload = fetch_daily_dict(symbol, start, end, settings, force_refresh=refresh)

    table = Table(title=f"{symbol.full} 日线（{payload['n_rows']} 根，已缓存）")
    for col in ("date", "open", "high", "low", "close", "volume", "suspended"):
        table.add_column(col)
    for row in payload["rows"][:5]:
        table.add_row(*(str(row.get(c)) for c in ("date", "open", "high", "low", "close", "volume", "suspended")))
    table.add_row("...", "", "", "", "", "", "")
    console.print(table)


def _load_position_fn(strategy_code: str, strategy_file: Path):
    """从策略代码中加载 ``generate_positions``（仅静态检查入口是否存在）。

    只解析 AST 校验契约，不执行策略代码；真实执行一律在沙箱内进行。
    """
    import ast

    try:
        tree = ast.parse(strategy_code)
    except SyntaxError as exc:
        raise typer.BadParameter(f"{strategy_file} 语法错误：{exc}") from exc
    if not any(
        isinstance(node, ast.FunctionDef) and node.name == "generate_positions"
        for node in tree.body
    ):
        raise typer.BadParameter(
            f"{strategy_file} 未定义 generate_positions(df)，无法执行回测"
        )

    # 在隔离命名空间中加载策略模块（执行面仍由沙箱承担）
    import types

    module = types.ModuleType("quant_asst_strategy_check")
    module.__file__ = str(strategy_file)
    code = compile(strategy_code, str(strategy_file), "exec")
    exec(code, module.__dict__)  # noqa: S102 —— 显式加载用户指定策略文件
    return module.generate_positions


@app.command()
def backtest(
    symbol_raw: str = typer.Argument("cn:600519", help="回测标的（默认 cn:600519）"),
    start: str = typer.Option("2024-01-01", "--start", help="起始日"),
    end: str = typer.Option(None, "--end", help="结束日（缺省今天）"),
    strategy_file: Path = typer.Option(
        Path("examples/dual_ma.py"), "--strategy", "-s",
        help="策略文件路径（须定义 generate_positions(df)）",
    ),
    sandbox: str = typer.Option("local", "--sandbox", help="沙箱模式：docker（Release 默认）| local（开发调试）"),
    capital: float = typer.Option(1_000_000.0, "--capital", help="初始资金"),
    lookahead_check: bool = typer.Option(
        False, "--lookahead-check",
        help="执行前做未来函数确定性检查（截断历史一致性，默认关）",
    ),
) -> None:
    """把策略送入沙箱执行双均线回测（Step 2 链路验证命令）。"""
    from core.markets import Symbol
    from tools.backtest_sandbox import run_backtest_in_sandbox
    from tools.market_data import get_backtest_frame

    settings = get_settings()
    if sandbox == "local":
        console.print(LOCAL_SANDBOX_CLI_WARNING)  # 红色警告（CLI 层）

    end = end or datetime.now().strftime("%Y-%m-%d")
    symbol = Symbol.parse(symbol_raw)
    strategy_code = strategy_file.read_text(encoding="utf-8")

    with console.status(f"[1/3] 抓取 {symbol.full} 日线 ..."):
        df = get_backtest_frame(symbol, start, end, settings)
    console.print(f"    数据：{len(df)} 根 K 线（{df['date'].iloc[0].date()} ~ {df['date'].iloc[-1].date()}）")

    # ---- 未来函数确定性检查（可选，默认关）----
    if lookahead_check:
        from backtest.lookahead import (
            check_lookahead_determinism,
            format_lookahead_verdict,
        )

        with console.status("[2/3] 未来函数确定性检查（截断历史重跑）..."):
            position_fn = _load_position_fn(strategy_code, strategy_file)
            verdict = check_lookahead_determinism(df, position_fn)
        console.print(format_lookahead_verdict(verdict, strategy_file.stem))
        if not verdict.passed:
            console.print(
                "[bold red]未来函数确定性检查未通过：策略疑似引用未来数据，"
                "已中止回测（可通过移除 --lookahead-check 强制运行）。[/bold red]"
            )
            raise typer.Exit(code=2)

    run_id = f"bt-{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"
    step_no = "3/3" if lookahead_check else "2/2"
    with console.status(f"[{step_no}] 沙箱({sandbox})执行回测 ..."):
        output = run_backtest_in_sandbox(
            strategy_code, df, symbol, settings,
            mode=sandbox, initial_capital=capital, run_id=run_id,
        )

    for w in output.sandbox.warnings:
        console.print(f"[bold red]{w}[/bold red]")

    _print_backtest_result(output.result, run_id)


@app.command()
def optimize(
    symbol_raw: str = typer.Argument("cn:600519", help="回测标的（默认 cn:600519）"),
    grid: str = typer.Option(
        ..., "--grid", "-g",
        help='参数网格，如 "short_window=5,10;long_window=20,30"（花括号可省略）',
    ),
    start: str = typer.Option("2024-01-01", "--start", help="起始日"),
    end: str = typer.Option(None, "--end", help="结束日（缺省今天）"),
    strategy_file: Path = typer.Option(
        Path("examples/dual_ma.py"), "--strategy", "-s",
        help="策略文件路径（须定义 generate_positions(df, params=None)）",
    ),
    sandbox: str = typer.Option("local", "--sandbox", help="沙箱模式：docker（Release 默认）| local（开发调试）"),
    capital: float = typer.Option(1_000_000.0, "--capital", help="初始资金"),
    train_ratio: float = typer.Option(None, "--train-ratio", min=0.1, max=0.9,
                                      help="样本内占比（缺省用配置 0.7）"),
) -> None:
    """参数网格寻优 + 样本外验证（纯确定性网格遍历，不调用 LLM）。"""
    from backtest.optimizer import (
        MAX_GRID_COMBINATIONS,
        expand_grid,
        optimize_grid,
        parse_param_grid,
    )
    from core.markets import Symbol
    from tools.market_data import get_backtest_frame

    settings = get_settings()
    if sandbox == "local":
        console.print(LOCAL_SANDBOX_CLI_WARNING)  # 红色警告（CLI 层）

    try:
        param_grid = parse_param_grid(grid)
        combos = expand_grid(param_grid)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if len(combos) > MAX_GRID_COMBINATIONS:
        raise typer.BadParameter(
            f"参数组合数 {len(combos)} 超过上限 {MAX_GRID_COMBINATIONS}，请缩小网格"
        )

    end = end or datetime.now().strftime("%Y-%m-%d")
    symbol = Symbol.parse(symbol_raw)
    strategy_code = strategy_file.read_text(encoding="utf-8")

    with console.status(f"[1/3] 抓取 {symbol.full} 日线 ..."):
        df = get_backtest_frame(symbol, start, end, settings)
    console.print(f"    数据：{len(df)} 根 K 线（{df['date'].iloc[0].date()} ~ {df['date'].iloc[-1].date()}）")

    run_id = f"opt-{datetime.now():%Y%m%d-%H%M%S}"
    try:
        with console.status(f"[2/3] 逐组合沙箱({sandbox})回测（共 {len(combos)} 组）..."):
            result = optimize_grid(
                df, strategy_code, symbol, settings, param_grid,
                initial_capital=capital,
                train_ratio=train_ratio,
                sandbox_mode=sandbox,
                run_id=run_id,
            )
    except (ValueError, RuntimeError) as exc:
        console.print(f"[bold red]寻优失败：{exc}[/bold red]")
        raise typer.Exit(code=1)

    from report.markdown import write_optimization_report

    with console.status("[3/3] 渲染并落盘寻优报告 ..."):
        md_path = write_optimization_report(result, settings.output_dir)

    _print_optimization_result(result, md_path)


def _print_optimization_result(result: dict, md_path: str) -> None:
    """用 rich 表格打印寻优对比与样本外结论（数字全部来自优化结果，硬约束 1）。"""
    grid_keys = [str(k) for k in (result.get("grid") or {}).keys()]
    combos = result.get("combinations") or []
    best_index = result.get("best_index")
    ineligible = {
        int(item["index"]): item for item in (result.get("ineligible") or [])
    }
    eligible_set = {int(i) for i in (result.get("eligible_indexes") or [])}

    def _return_rank_key(row):
        value = (row.get("in_sample") or {}).get("total_return")
        return (
            float("inf") if value is None else -float(value),
            repr(sorted((row.get("params") or {}).items())),
        )

    return_ranked = sorted(
        (row for row in combos if int(row.get("index", -1)) in eligible_set),
        key=_return_rank_key,
    )
    return_rank = {int(row["index"]): pos + 1 for pos, row in enumerate(return_ranked)}

    table = Table(
        title=f"参数网格寻优对比（{len(combos)} 组；主指标=样本内夏普，"
              f"门槛≥{result.get('min_in_sample_trades', 5)}笔）"
    )
    table.add_column("#", justify="right")
    for key in grid_keys:
        table.add_column(key, justify="right")
    table.add_column("资格", justify="center")
    table.add_column("收益排名", justify="right")
    for label in ("样本内收益", "样本外收益", "样本内夏普", "样本外夏普",
                  "样本内回撤", "样本外回撤", "样本内笔数", "样本外笔数"):
        table.add_column(label, justify="right")

    def pct(v) -> str:
        return "-" if v is None else f"{v * 100:+.1f}%"

    def num(v) -> str:
        return "-" if v is None else (str(v) if isinstance(v, int) else f"{v:.3f}")

    for row in combos:
        in_m = row.get("in_sample") or {}
        out_m = row.get("out_sample") or {}
        params = row.get("params") or {}
        index = int(row.get("index", -1))
        cells = [str(index), *(str(params.get(k, "")) for k in grid_keys)]
        cells += [
            "不合格" if index in ineligible else "合格",
            str(return_rank[index]) if index in return_rank else "-",
            pct(in_m.get("total_return")), pct(out_m.get("total_return")),
            num(in_m.get("sharpe")), num(out_m.get("sharpe")),
            pct(in_m.get("max_drawdown")), pct(out_m.get("max_drawdown")),
            num(in_m.get("n_trades")), num(out_m.get("n_trades")),
        ]
        table.add_row(*cells)
    console.print(table)

    best = combos[best_index] if isinstance(best_index, int) and 0 <= best_index < len(combos) else {}
    best_in = best.get("in_sample") or {}
    best_out = best.get("out_sample") or {}
    console.print(f"\n[bold cyan]最优组合[/bold cyan] #{best_index}：{best.get('params', {})}")
    console.print(
        f"样本内 总收益 {pct(best_in.get('total_return'))} / 夏普 {num(best_in.get('sharpe'))}；"
        f"样本外 总收益 {pct(best_out.get('total_return'))} / 夏普 {num(best_out.get('sharpe'))}"
    )

    return_best_index = result.get("return_best_index")
    console.print(
        f"指标对照：主指标（样本内夏普）选定 #{best_index}；"
        f"按样本内总收益首位 #{return_best_index}；"
        f"{'结论一致' if result.get('metric_agreement') else '结论冲突（已并列呈现，不做加权综合）'}"
    )
    if ineligible:
        console.print(
            f"[yellow]准入门槛：{len(ineligible)} 个组合样本内成交笔数不足 "
            f"{result.get('min_in_sample_trades', 5)} 笔，未参与选优（明细见报告）[/yellow]"
        )

    if result.get("degraded"):
        console.print("[bold red]判定：degraded（样本外表现显著劣于样本内）[/bold red]")
        for reason in result.get("degradation_reasons") or []:
            console.print(f"  - {reason}")
    else:
        console.print("[green]判定：未触发劣化阈值（不构成对过拟合的排除，详见报告提示）[/green]")
    console.print(f"[dim]Markdown 报告：{md_path}[/dim]")


def _print_backtest_result(result, run_id: str) -> None:
    """用 rich 表格打印回测结果（数字全部来自工具返回，硬约束 1）。"""
    console.print(f"\n[bold cyan]回测结果[/bold cyan]（run_id={run_id}，trajectory 已落盘）")
    console.print(
        f"标的 {result.symbol} | 区间 {result.period_start} ~ {result.period_end} | "
        f"初始资金 ¥{result.initial_capital:,.0f} | 期末净值 ¥{result.final_equity:,.2f} | "
        f"总成本 ¥{result.total_cost:,.2f}"
    )
    console.print(f"样本外起点：[bold]{result.out_sample_start}[/bold]（样本内/外对比供过拟合审计）\n")

    table = Table(title="绩效指标（overall / in_sample / out_sample）")
    for col in ("指标", "全区间", "样本内", "样本外"):
        table.add_column(col)

    def fmt(v) -> str:
        return "-" if v is None else f"{v:.4f}" if isinstance(v, float) else str(v)

    m_over, m_in, m_out = result.overall, result.in_sample, result.out_sample
    for field, label in (
        ("total_return", "总收益"), ("annual_return", "年化收益"),
        ("max_drawdown", "最大回撤"), ("sharpe", "夏普比率"),
        ("win_rate", "按笔胜率"), ("n_trades", "成交笔数"), ("n_days", "交易日数"),
    ):
        table.add_row(
            label,
            fmt(getattr(m_over, field)),
            fmt(getattr(m_in, field)),
            fmt(getattr(m_out, field)),
        )
    console.print(table)
    console.print(f"生效规则：[dim]{result.rules}[/dim]")


@app.command()
def doctor() -> None:
    """环境自检：配置、依赖、Docker、Qdrant、运行时目录。"""
    settings = get_settings()
    rows: list[tuple[str, str, str]] = []  # (检查项, 状态, 说明)

    # ---- 配置 ----
    rows.append(("配置加载", "OK", f"model={settings.llm_model}, market={settings.default_market.value}"))
    rows.append(("默认市场", "OK", settings.default_market.value))

    # ---- LLM 密钥（只查存在性，不显示值）----
    key_found = present_keys()
    rows.append((
        "LLM 密钥", "OK" if key_found else "FAIL",
        f"检测到 {key_found[0]}" if key_found else "未检测到任何 API 密钥（复制 .env.example 为 .env 并填写）",
    ))

    # ---- 第三方依赖 ----
    for mod in _REQUIRED_MODULES:
        ok = importlib.util.find_spec(mod) is not None
        rows.append((f"依赖 {mod}", "OK" if ok else "FAIL", "已安装" if ok else "缺失"))

    # ---- Docker daemon ----
    try:
        import docker

        client = docker.from_env(timeout=3)
        client.ping()
        rows.append(("Docker daemon", "OK", f"version={client.version()['Version']}"))
    except Exception as exc:  # noqa: BLE001 —— 自检必须容错
        rows.append(("Docker daemon", "WARN", f"不可用（{type(exc).__name__}），沙箱功能将不可用"))

    # ---- Qdrant ----
    if settings.qdrant_mode == "local":
        rows.append(("Qdrant", "OK", "local 模式（进程内，无需服务）"))
    else:
        try:
            from qdrant_client import QdrantClient

            QdrantClient(url=settings.qdrant_url, timeout=3).get_collections()
            rows.append(("Qdrant", "OK", settings.qdrant_url))
        except Exception as exc:  # noqa: BLE001
            rows.append(("Qdrant", "WARN", f"server 模式不可达（{type(exc).__name__}），可 docker compose up -d qdrant"))

    # ---- 运行时目录 ----
    dirs_ok = all(
        d.exists() for d in (
            settings.var_dir, settings.trajectory_dir,
            settings.market_cache_dir, settings.report_dir, settings.sandbox_workdir,
        )
    )
    rows.append(("运行时目录 var/", "OK" if dirs_ok else "FAIL", "已创建" if dirs_ok else "缺失"))

    table = Table(title=f"Quant Asst 环境自检（Python {platform.python_version()}）")
    table.add_column("检查项", style="cyan")
    table.add_column("状态")
    table.add_column("说明", overflow="fold")
    status_style = {"OK": "green", "WARN": "yellow", "FAIL": "red"}
    for name, status, note in rows:
        table.add_row(name, f"[{status_style[status]}]{status}[/{status_style[status]}]", note)
    console.print(table)


@app.command()
def settings() -> None:
    """打印当前生效配置（不含任何密钥）。"""
    s: Settings = get_settings()
    for k, v in sorted(s.model_dump(mode="json").items()):
        console.print(f"[cyan]{k}[/cyan] = {v}")


if __name__ == "__main__":
    app()
