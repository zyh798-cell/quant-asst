"""DockerSandbox —— Release 正式版本默认沙箱（硬约束 3 的标准形态）。

执行模型：每次回测在一次性容器内运行（用后即毁）——
- 禁网（``network_disabled=True``）：数据以只读 Parquet 挂载，容器无外联；
- 资源限额：内存（``mem_limit``）+ CPU 配额（``nano_cpus``）+ 超时；
- 非 root：沙箱镜像内置 ``sandbox`` 用户；
- 文件边界：仅工作区可写（rw），项目源码只读挂载（ro）供 import 引擎。
"""

from __future__ import annotations

import logging
from pathlib import Path

from core.config import Settings
from tools.backtest_sandbox import SandboxExecutionError, SandboxExecutor, SandboxResult

logger = logging.getLogger("quantsentinel.sandbox.docker")

#: 容器内固定路径
_CONTAINER_WORKDIR = "/sandbox/work"
_CONTAINER_PROJECT = "/project"


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
            container = client.containers.run(
                image=self.settings.sandbox_image,
                command=["python", "-B", entrypoint],
                detach=True,
                working_dir=_CONTAINER_WORKDIR,
                volumes={
                    str(workdir): {"bind": _CONTAINER_WORKDIR, "mode": "rw"},
                    str(project_root): {"bind": _CONTAINER_PROJECT, "mode": "ro"},
                },
                environment={"PYTHONPATH": _CONTAINER_PROJECT},
                network_disabled=self.settings.sandbox_network_disabled,
                mem_limit=self.settings.sandbox_memory_limit,
                nano_cpus=int(self.settings.sandbox_cpu_quota * 1e9),
            )
            exit_info = container.wait(timeout=self.settings.sandbox_timeout_seconds)
            exit_code = int(exit_info.get("StatusCode", -1))
            logs = container.logs(stdout=True, stderr=True).decode("utf-8", errors="replace")
        except Exception as exc:  # noqa: BLE001 —— docker SDK 异常统一转沙箱错误
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
        """项目根目录（只读挂载进容器，使容器内可 import backtest / core 包）。"""
        return Path(__file__).resolve().parent.parent
