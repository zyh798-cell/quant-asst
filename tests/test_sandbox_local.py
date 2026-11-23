"""本地受限沙箱测试：AST 安检、正常执行、超时强杀、内存限额、密钥隔离。"""

from __future__ import annotations

import pytest

from tools.sandbox_local import (
    LocalRestrictedSandbox,
    build_sandbox_env,
    is_secret_like_name,
)


@pytest.fixture()
def local_sandbox(test_settings) -> LocalRestrictedSandbox:
    return LocalRestrictedSandbox(test_settings)


# ---------------------------------------------------------------------------
# AST 静态安检
# ---------------------------------------------------------------------------

def test_audit_blocks_os_import(local_sandbox: LocalRestrictedSandbox) -> None:
    violations = local_sandbox.audit_strategy("import os\nprint(os.getcwd())\n")
    assert any("os" in v for v in violations)


def test_audit_blocks_subprocess_and_requests(local_sandbox: LocalRestrictedSandbox) -> None:
    code = "import subprocess\nfrom requests import get\n"
    violations = local_sandbox.audit_strategy(code)
    joined = "\n".join(violations)
    assert "subprocess" in joined and "requests" in joined


def test_audit_blocks_from_os_path(local_sandbox: LocalRestrictedSandbox) -> None:
    """from os.path import join 同样被根模块名匹配拦截。"""
    violations = local_sandbox.audit_strategy("from os.path import join\n")
    assert any("os" in v for v in violations)


def test_audit_blocks_eval_exec(local_sandbox: LocalRestrictedSandbox) -> None:
    violations = local_sandbox.audit_strategy("eval('1+1')\nexec('x=1')\n")
    joined = "\n".join(violations)
    assert "eval()" in joined and "exec()" in joined


def test_audit_blocks_open_escape(local_sandbox: LocalRestrictedSandbox) -> None:
    """open() 绝对路径 / 盘符路径 / .. 逃逸全部拦截。"""
    for bad in ("open('/etc/passwd')", "open('C:/secrets.txt')", "open('../x.parquet')"):
        assert local_sandbox.audit_strategy(bad), f"应拦截：{bad}"


def test_audit_allows_relative_open_and_numpy(local_sandbox: LocalRestrictedSandbox) -> None:
    """正常策略代码（相对路径读数据 + numpy 计算 + 入口函数）必须通过安检。"""
    code = (
        "import numpy as np\n"
        "def generate_positions(df):\n"
        "    with open('data.parquet', 'rb') as f:\n"
        "        pass\n"
        "    return None\n"
    )
    assert local_sandbox.audit_strategy(code) == []


def test_audit_rejects_syntax_error(local_sandbox: LocalRestrictedSandbox) -> None:
    assert "语法错误" in local_sandbox.audit_strategy("def broken(:\n")[0]


# ---------------------------------------------------------------------------
# 密钥隔离（外部代码 review 第 3 项）
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name,expected", [
    ("DEEPSEEK_API_KEY", True),
    ("OPENAI_API_KEY", True),
    ("GITHUB_TOKEN", True),
    ("AWS_SECRET_ACCESS_KEY", True),
    ("SSH_PRIVATE_KEY", True),
    ("MY_SECRET", True),
    ("PATH", False),
    ("PYTHONPATH", False),
    ("HOME", False),
])
def test_is_secret_like_name(name, expected) -> None:
    assert is_secret_like_name(name) is expected


def test_build_sandbox_env_strips_secret_keys(monkeypatch) -> None:
    """含 DEEPSEEK_API_KEY 的宿主环境不得透传进沙箱子进程。"""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-must-not-leak")
    monkeypatch.setenv("PATH", r"C:\Windows\System32")
    env = build_sandbox_env({"PYTHONPATH": "/project"})
    assert "DEEPSEEK_API_KEY" not in env
    assert env["PATH"] == r"C:\Windows\System32"      # 白名单保留
    assert env["PYTHONPATH"] == "/project"            # 运行必需注入保留


def test_build_sandbox_env_rejects_secret_extra() -> None:
    """显式注入的密钥类变量同样被拒绝。"""
    env = build_sandbox_env({"DEEPSEEK_API_KEY": "sk-x", "SAFE_VAR": "ok"})
    assert "DEEPSEEK_API_KEY" not in env
    assert env["SAFE_VAR"] == "ok"


def test_subprocess_env_excludes_api_key(local_sandbox, test_settings, monkeypatch, tmp_path):
    """端到端：runner 子进程内读到的环境变量中不存在宿主 API Key。

    策略代码不能 ``import os``（AST 安检会拦截），故由宿主生成的可信
    runner 读取 ``os.environ`` 落盘，再断言其中无密钥类变量。
    """
    import json

    import pandas as pd

    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-must-not-leak")

    workdir = tmp_path / "work"
    workdir.mkdir()
    # runner 由宿主生成，属可信代码：执行前把「当前子进程的 KEY 类环境变量」
    # 落盘为 env_dump.json，策略只需确认文件为空对象。
    runner = (
        "import json\n"
        "import os\n"
        "with open('env_snapshot.json', 'w', encoding='utf-8') as f:\n"
        "    json.dump(dict(os.environ), f)\n"
    )
    (workdir / "runner.py").write_text(runner, encoding="utf-8")
    n = 10
    df = pd.DataFrame({
        "date": pd.bdate_range("2024-01-01", periods=n),
        "open": 10.0, "high": 10.0, "low": 10.0, "close": 10.0,
        "volume": 1e6, "amount": 1e7, "suspended": False,
        "limit_up": float("nan"), "limit_down": float("nan"),
    })
    df.to_parquet(workdir / "data.parquet", index=False)
    from backtest.market_rules import get_rules
    from core.markets import Symbol

    symbol = Symbol.parse("us:AAPL")
    rules = get_rules(symbol.market)
    (workdir / "spec.json").write_text(
        json.dumps({"rules": rules.dump(), "initial_capital": 1_000_000.0,
                    "train_ratio": 0.7, "periods_per_year": 252}, ensure_ascii=False),
        encoding="utf-8",
    )
    (workdir / "strategy.py").write_text(
        "def generate_positions(df):\n    return df['close'] * 0.0\n", encoding="utf-8"
    )

    result = local_sandbox.execute(workdir)
    assert result.exit_code == 0, result.stderr[-2000:]
    dumped = json.loads((workdir / "env_snapshot.json").read_text(encoding="utf-8"))
    keys_like_secret = {k: v for k, v in dumped.items()
                        if any(m in k.upper() for m in ("KEY", "TOKEN", "SECRET", "PRIVATE"))}
    assert "DEEPSEEK_API_KEY" not in dumped
    assert keys_like_secret == {}, f"子进程不应含任何密钥类变量，实际：{keys_like_secret}"


# ---------------------------------------------------------------------------
# 执行行为（合成数据，不依赖网络）
# ---------------------------------------------------------------------------

_STRATEGY_OK = '''
SHORT_WINDOW = 3
LONG_WINDOW = 5

def generate_positions(df):
    close = df.set_index("date")["close"]
    pos = (close.rolling(SHORT_WINDOW).mean() > close.rolling(LONG_WINDOW).mean()).astype(float)
    return pos
'''


def test_execute_runs_strategy_end_to_end(local_sandbox, test_settings) -> None:
    """安检通过 -> 子进程执行 -> result.json 产出 -> BacktestResult 校验通过。"""
    import numpy as np
    import pandas as pd

    from core.markets import Symbol
    from tools.backtest_sandbox import run_backtest_in_sandbox

    n = 60
    rng = np.random.default_rng(42)
    prices = 100 + np.cumsum(rng.normal(0, 1, n))
    df = pd.DataFrame({
        "date": pd.bdate_range("2024-01-01", periods=n),
        "open": prices, "high": prices * 1.01, "low": prices * 0.99,
        "close": prices, "volume": 1e6, "amount": 1e7,
        "suspended": False, "limit_up": np.nan, "limit_down": np.nan,
    })
    output = run_backtest_in_sandbox(
        _STRATEGY_OK, df, Symbol.parse("us:AAPL"), test_settings, mode="local",
        run_id="test-ok",
    )
    assert output.result.symbol == "us:AAPL"
    assert output.result.final_equity > 0
    assert output.result.overall.n_days == n - 1
    assert output.result.out_sample_start  # 样本外起点已计算
    assert output.details.get("equity_curve")  # 净值明细随 details 返回
    assert len(output.details["equity_curve"]["dates"]) == n - 1


def test_execute_blocks_malicious_strategy(local_sandbox, test_settings) -> None:
    """恶意策略（import os）在安检阶段即被拒绝，不进入执行。"""
    import pandas as pd

    from core.markets import Symbol
    from tools.backtest_sandbox import run_backtest_in_sandbox
    from tools.sandbox_local import SandboxSecurityViolation

    df = pd.DataFrame({"date": pd.bdate_range("2024-01-01", periods=10)})
    with pytest.raises(SandboxSecurityViolation, match="os"):
        run_backtest_in_sandbox(
            "import os\nos.system('echo hacked')\n",
            df.assign(open=10.0, high=10.0, low=10.0, close=10.0, volume=1, amount=1,
                      suspended=False, limit_up=float("nan"), limit_down=float("nan")),
            Symbol.parse("us:AAPL"), test_settings, mode="local", run_id="test-evil",
        )


def test_execute_timeout_kill(test_settings) -> None:
    """死循环策略在超时后被强杀，错误信息包含超时说明。"""
    import numpy as np
    import pandas as pd
    import pytest

    from core.markets import Symbol
    from tools.backtest_sandbox import SandboxExecutionError, run_backtest_in_sandbox

    test_settings.sandbox_timeout_seconds = 3  # 缩短超时便于测试
    n = 30
    prices = np.full(n, 10.0)
    df = pd.DataFrame({
        "date": pd.bdate_range("2024-01-01", periods=n),
        "open": prices, "high": prices, "low": prices, "close": prices,
        "volume": 1e6, "amount": 1e7, "suspended": False,
        "limit_up": np.nan, "limit_down": np.nan,
    })
    with pytest.raises(SandboxExecutionError, match="超时"):
        run_backtest_in_sandbox(
            "def generate_positions(df):\n    while True:\n        pass\n",
            df, Symbol.parse("us:AAPL"), test_settings, mode="local", run_id="test-timeout",
        )


def test_execute_memory_limit_kill(test_settings) -> None:
    """内存超限策略被强杀（64MB 上限 vs 策略申请大数组）。"""
    import numpy as np
    import pandas as pd
    import pytest

    from core.markets import Symbol
    from tools.backtest_sandbox import SandboxExecutionError, run_backtest_in_sandbox

    test_settings.sandbox_memory_limit = "64m"
    n = 30
    prices = np.full(n, 10.0)
    df = pd.DataFrame({
        "date": pd.bdate_range("2024-01-01", periods=n),
        "open": prices, "high": prices, "low": prices, "close": prices,
        "volume": 1e6, "amount": 1e7, "suspended": False,
        "limit_up": np.nan, "limit_down": np.nan,
    })
    # 策略持有大数组并睡眠，保证监控线程能捕捉到超限
    greedy = (
        "import numpy as np\n"
        "import time\n"
        "def generate_positions(df):\n"
        "    big = np.ones(200_000_000, dtype=np.float64)  # ~1.6 GB\n"
        "    time.sleep(5)\n"
        "    return None\n"
    )
    with pytest.raises(SandboxExecutionError, match="失败"):
        run_backtest_in_sandbox(
            greedy, df, Symbol.parse("us:AAPL"), test_settings,
            mode="local", run_id="test-mem",
        )


# ---------------------------------------------------------------------------
# 端到端回归：策略输出对齐 / 零成交诊断
# ---------------------------------------------------------------------------

def _trending_frame(n: int = 30):
    """前 10 天 10 元、之后 12 元的趋势数据（MA3 上穿 MA5）。"""
    import numpy as np
    import pandas as pd

    prices = np.concatenate([np.full(10, 10.0), np.full(n - 10, 12.0)])
    return pd.DataFrame({
        "date": pd.bdate_range("2024-01-01", periods=n),
        "open": prices, "high": prices * 1.01, "low": prices * 0.99,
        "close": prices, "volume": 1e6, "amount": 1e7,
        "suspended": False, "limit_up": np.nan, "limit_down": np.nan,
    })


def test_end_to_end_rangeindex_strategy_trades(test_settings) -> None:
    """回归零成交事故：策略返回 RangeIndex 索引 Series 时端到端必须有成交。

    旧链路在引擎 ``reindex(df["date"])`` 处静默丢光信号，沙箱退出码仍为 0、
    净值恒等于初始资金。现断言沙箱全链路产出非零成交与非零收益。
    """
    from core.markets import Symbol
    from tools.backtest_sandbox import run_backtest_in_sandbox

    strategy = (
        "def generate_positions(df):\n"
        "    close = df['close'].astype(float)\n"
        "    fast = close.rolling(3).mean()\n"
        "    slow = close.rolling(5).mean()\n"
        "    return (fast > slow).astype(float)\n"   # RangeIndex 索引
    )
    output = run_backtest_in_sandbox(
        strategy, _trending_frame(), Symbol.parse("us:AAPL"), test_settings,
        mode="local", run_id="test-rangeindex",
    )
    assert output.result.overall.n_trades >= 1, "端到端应产生成交"
    assert output.result.overall.total_return != 0.0
    assert output.result.signal_nonzero_days > 0


def test_zero_signal_emits_warning(test_settings) -> None:
    """真正无信号时输出显式告警（避免「净值不变」被误读为回测成功）。"""
    from core.markets import Symbol
    from tools.backtest_sandbox import run_backtest_in_sandbox

    output = run_backtest_in_sandbox(
        "def generate_positions(df):\n    return df['close'] * 0.0\n",
        _trending_frame(), Symbol.parse("us:AAPL"), test_settings,
        mode="local", run_id="test-zero",
    )
    assert output.result.overall.n_trades == 0
    assert any("n_trades=0" in w for w in output.sandbox.warnings), \
        f"应有零成交告警，实际 warnings={output.sandbox.warnings}"
