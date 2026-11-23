"""DockerSandbox —— Release 正式版本默认沙箱（硬约束 3 的标准形态）。

执行模型：每次回测在一次性容器内运行（用后即毁）——
- 禁网（``network_disabled=True``）：数据以只读 Parquet 挂载，容器无外联；
- 资源限额：内存（``mem_limit``）+ CPU 配额（``nano_cpus``）+ 超时；
- 非 root：沙箱镜像内置 ``sandbox`` 用户；
- **最小挂载**（外部代码 review 第 3 项）：不再整根挂载项目目录，
  仅挂载回测引擎必需的 ``backtest/`` 与 ``core/markets.py``（均为只读），
  并在挂载列表层面显式排除 ``.env`` 及任何密钥类文件；
- **不传宿主环境变量**：容器内只保留 ``PYTHONPATH`` 等运行必需项，
  宿主的 ``*_API_KEY`` / ``*_TOKEN`` / ``*_SECRET`` 一律不进容器。
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from core.config import Settings
from tools.backtest_sandbox import SandboxExecutionError, SandboxExecutor, SandboxResult

logger = logging.getLogger("quantsentinel.sandbox.docker")

#: 容器内固定路径
_CONTAINER_WORKDIR = "/sandbox/work"
_CONTAINER_BACKTEST = "/project/backtest"
_CONTAINER_CORE = "/project/core"

#: 允许进入容器的环境变量白名单（仅运行必需项）
_ALLOWED_ENV_KEYS: frozenset[str] = frozenset({
    "PYTHONPATH", "PATH", "LANG", "LC_ALL", "LC_CTYPE", "HOME", "TMPDIR",
})

#: 镜像名兼容别名：品牌改名前的旧镜像名仍可启动（避免本地已构建镜像失效）。
_IMAGE_ALIASES: tuple[str, ...] = (
    "quant-asst-sandbox:latest",
    "quantsentinel-sandbox:latest",
)


def resolve_image_name(settings: Settings) -> str:
    """解析可用的沙箱镜像名：优先配置值，其次按别名表探测本地已有镜像。

    品牌改名（quant-ast -> quant-asst）后，本机可能仍只有旧名镜像；
    此处做向后兼容探测，避免既有镜像无法使用。
    """
    configured = settings.sandbox_image
    try:
        import docker

        client = docker.from_env(timeout=5)
        if client.images.list(name=configured):
            return configured
        for alias in _IMAGE_ALIASES:
            if alias != configured and client.images.list(name=alias):
                logger.warning(
                    "配置的沙箱镜像 %s 不存在，回退到本地已有镜像 %s", configured, alias
                )
                return alias
    except Exception as exc:  # noqa: BLE001 —— 探测失败不阻断启动
        logger.debug("镜像别名探测跳过：%s", exc)
    return configured


def filter_host_env(env: dict[str, str] | None = None) -> dict[str, str]:
    """按白名单过滤宿主环境变量（剔除一切密钥类与未知变量）。

    用于 Docker 容器启动：避免把 ``DEEPSEEK_API_KEY`` 等宿主密钥透传进
    不可信策略代码的执行环境。

    Args:
        env: 待过滤的环境变量映射（缺省取 ``os.environ``）。

    Returns:
        仅含白名单键值的新字典。
    """
    source = dict(os.environ if env is None else env)
    return {k: v for k, v in source.items() if k in _ALLOWED_ENV_KEYS}


def build_container_volumes(workdir: Path, project_root: Path) -> dict[str, dict[str, str]]:
    """构造最小化只读挂载表（回测执行必需目录，显式排除 .env）。

    Args:
        workdir: 沙箱工作区（可写，宿主备好的 data.parquet / strategy.py / runner.py）。
        project_root: 项目根（只用于定位 backtest / core 源文件）。

    Returns:
        ``{宿主机路径: {"bind": 容器路径, "mode": "ro"|"rw"}}`` 挂载表。

    Raises:
        SandboxExecutionError: 必需源码目录缺失（挂载前拦截，避免半残执行）。
    """
    backtest_dir = (project_root / "backtest").resolve()
    markets_file = (project_root / "core" / "markets.py").resolve()

    # 显式排除 .env：挂载列表层面不允许出现任何 .env / .env.* 路径
    forbidden_names = {".env"}
    for path in (workdir.resolve(), backtest_dir, markets_file):
        if path.name in forbidden_names or path.name.startswith(".env."):
            raise SandboxExecutionError(f"拒绝挂载敏感文件：{path}")

    mounts: dict[str, dict[str, str]] = {
        str(workdir.resolve()): {"bind": _CONTAINER_WORKDIR, "mode": "rw"},
    }
    if backtest_dir.is_dir():
        mounts[str(backtest_dir)] = {"bind": _CONTAINER_BACKTEST, "mode": "ro"}
    else:
        raise SandboxExecutionError(f"缺少回测引擎目录，无法挂载：{backtest_dir}")
    if markets_file.is_file():
        mounts[str(markets_file)] = {"bind": f"{_CONTAINER_CORE}/markets.py", "mode": "ro"}
    else:
        raise SandboxExecutionError(f"缺少 core.markets 模块，无法挂载：{markets_file}")

    # 二次校验：任何挂载源都不得是密钥类文件（纵深防御）
    for src in mounts:
        if Path(src).name in forbidden_names or Path(src).name.startswith(".env."):
            raise SandboxExecutionError(f"拒绝挂载敏感文件：{src}")
    logger.info("docker 沙箱最小挂载：%s", list(mounts))
    return mounts


class DockerSandbox(SandboxExecutor):
    """Docker 容器沙箱：LLM 生成代码的唯一 Release 级执行环境。"""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def mode(self) -> str:
        return "docker"

    def healthcheck(self) -> str:
        """验证 Docker daemon 可达与沙箱镜像存在；失败抛异常。"""
        import docker

        client = docker.from_env(timeout=5)
        client.ping()
        images = client.images.list(name=self.settings.sandbox_image)
        if not images:
            raise SandboxExecutionError(
                f"沙箱镜像 {self.settings.sandbox_image} 不存在，"
                "请先执行：docker compose build sandbox"
            )
        return f"docker 引擎就绪，镜像 {self.settings.sandbox_image} 可用"

    def execute(self, workdir: Path, entrypoint: str = "runner.py") -> SandboxResult:
        """在一次性容器内执行工作区入口；无论成败，容器用后即毁。"""
        import time as _time

        import docker

        project_root = self._project_root()
        start = _time.monotonic()
        client = docker.from_env(timeout=10)

        container = None
        try:
            volumes = build_container_volumes(workdir, project_root)
            env = filter_host_env()
            env["PYTHONPATH"] = f"{_CONTAINER_BACKTEST}:{_CONTAINER_CORE}"
            container = client.containers.run(
                image=resolve_image_name(self.settings),
                command=["python", "-B", entrypoint],
                detach=True,
                working_dir=_CONTAINER_WORKDIR,
                volumes=volumes,
                environment=env,
                network_disabled=self.settings.sandbox_network_disabled,
                mem_limit=self.settings.sandbox_memory_limit,
                nano_cpus=int(self.settings.sandbox_cpu_quota * 1e9),
            )
            exit_info = container.wait(timeout=self.settings.sandbox_timeout_seconds)
            exit_code = int(exit_info.get("StatusCode", -1))
            logs = container.logs(stdout=True, stderr=True).decode("utf-8", errors="replace")
        except Exception as exc:  # docker SDK 异常统一转沙箱错误
            raise SandboxExecutionError(
                f"Docker 沙箱执行异常：{type(exc).__name__}: {exc}"
            ) from exc
        finally:
            if container is not None:
                try:
                    container.remove(force=True)  # 用后即毁
                except Exception:  # noqa: BLE001 —— 清理失败不影响主流程
                    logger.warning("容器清理失败（%s），建议 docker ps 检查残留", container.id)

        duration_ms = int((_time.monotonic() - start) * 1000)
        logger.info("docker 沙箱执行完成：exit=%s, %d ms", exit_code, duration_ms)
        return SandboxResult(
            exit_code=exit_code,
            stdout=logs,
            stderr=logs,
            duration_ms=duration_ms,
            warnings=[],
        )

    def _project_root(self) -> Path:
        """项目根目录（仅用于定位需只读挂载的最小源码集）。"""
        return Path(__file__).resolve().parent.parent
