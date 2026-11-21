"""LocalRestrictedSandbox —— 开发调试用本地受限沙箱（安全隔离不足，禁止生产使用）。

⚠️ 红色警告（硬性要求，构造/执行/日志全程展示）：
    本沙箱仅在宿主机上以「独立子进程 + 静态安检 + 资源限额」提供弱隔离，
    安全性远低于 Docker 容器沙箱，仅供开发调试使用，
    禁止用于生产环境或执行不可信代码。

防线（纵深，但非完整沙箱）：
1. **AST 静态安检**：禁止 import os/subprocess/socket/requests 等高危模块；
   禁止 eval/exec/compile/__import__；open() 仅允许相对路径且不得逃逸出工作区；
2. **独立子进程**：策略代码在独立 Python 进程执行，异常/崩溃不影响宿主；
3. **资源限额**：超时强杀 + psutil 轮询进程树内存、超限强杀；
4. **文件限制**：工作目录锁定沙箱工作区（cwd），数据以只读 Parquet 预置。
"""

from __future__ import annotations

import ast
import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import psutil
from rich.console import Console

from core.config import Settings
from tools.backtest_sandbox import SandboxExecutor, SandboxResult

logger = logging.getLogger("quantsentinel.sandbox.local")
console = Console()

#: 红色安全警告文案（构造与执行时强制展示）
LOCAL_SANDBOX_WARNING = (
    "[bold red]⚠️ LOCAL SANDBOX WARNING：本地受限沙箱仅用于开发调试，"
    "安全隔离不足（弱隔离：子进程+静态安检+资源限额），禁止生产使用！[/bold red]"
)

#: 禁止策略代码导入的模块（按根模块名前缀匹配，shu 指定 + 纵深扩展）
BLOCKED_MODULES: frozenset[str] = frozenset({
    "os", "posix", "nt", "subprocess", "socket", "requests", "urllib", "http",
    "ftplib", "telnetlib", "smtplib", "ctypes", "shutil", "sys", "importlib",
    "pickle", "shelve", "marshal", "multiprocessing", "threading", "signal",
    "platform", "msvcrt", "resource", "pty", "fcntl", "tempfile", "webbrowser",
    "sqlite3", "socketserver", "asyncio",
})

#: 禁止调用的内建危险函数
BLOCKED_BUILTINS: frozenset[str] = frozenset({
    "eval", "exec", "compile", "__import__", "breakpoint", "globals", "locals",
})


def _parse_memory(limit: str) -> int:
    """解析内存限额字符串（如 '512m' / '1g' / '268435456'）为字节数。"""
    limit = limit.strip().lower()
    units = {"b": 1, "k": 1024, "m": 1024**2, "g": 1024**3}
    for suffix, factor in units.items():
        if limit.endswith(suffix):
            return int(float(limit[: -len(suffix)]) * factor)
    return int(limit)


def audit_strategy_code(code: str) -> list[str]:
    """对策略代码做静态安检（模块级函数，供沙箱与 HypothesisAgent 共用）。

    Returns:
        违规描述列表（空列表 = 通过）。

    已知局限（因此禁止生产使用）：getattr/importlib 等动态导入手法、
    C 扩展、环境变量注入等无法被静态分析完全覆盖。
    """
    violations: list[str] = []
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return [f"语法错误，拒绝执行：{exc}"]

    has_entrypoint = False
    for node in ast.walk(tree):
        # 0) 入口函数检查
        if isinstance(node, ast.FunctionDef) and node.name == "generate_positions":
            has_entrypoint = True
        # 1) import 黑名单
        elif isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in BLOCKED_MODULES:
                    violations.append(
                        f"L{node.lineno}: 禁止导入模块 {alias.name!r}（高危模块黑名单）"
                    )
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if root in BLOCKED_MODULES:
                violations.append(
                    f"L{node.lineno}: 禁止从模块 {node.module!r} 导入（高危模块黑名单）"
                )
        # 2) 危险内建调用
        elif isinstance(node, ast.Call):
            func = node.func
            name = func.id if isinstance(func, ast.Name) else (
                func.attr if isinstance(func, ast.Attribute) else ""
            )
            if name in BLOCKED_BUILTINS:
                violations.append(f"L{node.lineno}: 禁止调用 {name}()")
            # 3) open() 路径约束：仅相对路径且不得包含 ..（防逃逸）
            elif name == "open" and node.args:
                arg = node.args[0]
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    p = arg.value.replace("\\\\", "/")
                    is_absolute = p.startswith(("/", "~")) or (len(p) > 1 and p[1] == ":")
                    if is_absolute or ".." in p:
                        violations.append(
                            f"L{node.lineno}: open() 仅允许工作区相对路径，"
                            f"禁止绝对路径或 .. 逃逸（{arg.value!r}）"
                        )
    if not has_entrypoint:
        violations.append("缺少入口函数 generate_positions(df)（策略契约第 1 条）")
    return violations


class LocalRestrictedSandbox(SandboxExecutor):
    """本地受限沙箱：独立子进程 + AST 安检 + 超时/内存限额（开发调试专用）。"""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.memory_limit_bytes = _parse_memory(settings.sandbox_memory_limit)
        # 红色警告：构造时即展示（硬性要求）
        console.print(LOCAL_SANDBOX_WARNING)
        logger.warning(
            "LocalRestrictedSandbox 启用：本地沙箱仅用于开发调试，安全隔离不足，禁止生产使用"
        )

    @property
    def mode(self) -> str:
        return "local"

    def healthcheck(self) -> str:
        return (
            f"local 沙箱就绪（python={sys.executable}, "
            f"mem_limit={self.settings.sandbox_memory_limit}, "
            f"timeout={self.settings.sandbox_timeout_seconds}s）"
        )

    # ---- AST 静态安检 ----

    def audit_strategy(self, code: str) -> list[str]:
        """对策略代码做静态安检（委托模块级 audit_strategy_code）。"""
        return audit_strategy_code(code)

    # ---- 执行 ----

    def execute(self, workdir: Path, entrypoint: str = "runner.py") -> SandboxResult:
        """在独立子进程中执行沙箱工作区入口，超时/超内存强杀。"""
        start = time.monotonic()
        warnings = [LOCAL_SANDBOX_WARNING.replace("[bold red]", "").replace("[/bold red]", "")]

        # 策略代码安检（runner/engine 为宿主可信代码，不在此列）
        strategy_path = workdir / "strategy.py"
        if strategy_path.exists():
            violations = self.audit_strategy(strategy_path.read_text(encoding="utf-8"))
            if violations:
                raise SandboxSecurityViolation(
                    "策略代码未通过本地沙箱静态安检：\n" + "\n".join(violations)
                )

        env = {**os.environ, "PYTHONPATH": str(self._project_root())}
        proc = subprocess.Popen(
            [sys.executable, "-B", entrypoint],
            cwd=str(workdir),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        killed_reason: list[str] = []

        # ---- 内存监控线程：进程树 RSS 超限即强杀 ----
        def monitor() -> None:
            try:
                ps = psutil.Process(proc.pid)
                while proc.poll() is None:
                    rss = ps.memory_info().rss
                    for child in ps.children(recursive=True):
                        try:
                            rss += child.memory_info().rss
                        except psutil.NoSuchProcess:
                            continue
                    if rss > self.memory_limit_bytes:
                        killed_reason.append(
                            f"内存超限（{rss / 1024**2:.0f} MB > "
                            f"{self.settings.sandbox_memory_limit}），进程树已强杀"
                        )
                        proc.kill()
                        return
                    time.sleep(0.5)
            except psutil.NoSuchProcess:
                return

        monitor_thread = threading.Thread(target=monitor, daemon=True)
        monitor_thread.start()

        timed_out = False
        try:
            stdout, stderr = proc.communicate(timeout=self.settings.sandbox_timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            proc.kill()
            stdout, stderr = proc.communicate()
            killed_reason.append(
                f"执行超时（> {self.settings.sandbox_timeout_seconds}s），进程已强杀"
            )
        monitor_thread.join(timeout=2)

        if killed_reason:
            stderr = (stderr or "") + "\n[quantsentinel] " + "; ".join(killed_reason)
        warnings.extend(killed_reason)

        duration_ms = int((time.monotonic() - start) * 1000)
        logger.info("local 沙箱执行完成：exit=%s, %d ms", proc.returncode, duration_ms)
        return SandboxResult(
            exit_code=proc.returncode if proc.returncode is not None else -1,
            stdout=stdout or "",
            stderr=stderr or "",
            duration_ms=duration_ms,
            warnings=warnings,
        )

    def _project_root(self) -> Path:
        """项目根目录（使沙箱子进程可 import backtest / core 包）。"""
        return Path(__file__).resolve().parent.parent


class SandboxSecurityViolation(RuntimeError):
    """策略代码未通过静态安检。"""
