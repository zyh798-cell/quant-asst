"""Docker 沙箱测试：最小挂载构造与宿主环境变量过滤（外部代码 review 第 3 项）。

不依赖 Docker daemon：只测纯函数 ``build_container_volumes`` / ``filter_host_env``，
真实容器执行由 local 沙箱端到端用例覆盖。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.backtest_sandbox import SandboxExecutionError
from tools.sandbox_docker import build_container_volumes, filter_host_env


class _FakeImage:
    def __init__(self, name: str) -> None:
        self.name = name


class _FakeImageList:
    def __init__(self, names: list[str]) -> None:
        self._names = names

    def list(self, name: str):
        return [_FakeImage(n) for n in self._names if n == name]


class _FakeDockerClient:
    def __init__(self, images: list[str]) -> None:
        self.images = _FakeImageList(images)


def test_resolve_image_name_prefers_configured(monkeypatch):
    """配置值存在时按配置使用。"""
    from core.config import Settings
    from tools.sandbox_docker import resolve_image_name

    settings = Settings(_env_file=None, var_dir=Path("var"))
    monkeypatch.setattr(
        "docker.from_env",
        lambda timeout=5: _FakeDockerClient([settings.sandbox_image]),
    )
    assert resolve_image_name(settings) == settings.sandbox_image


def test_resolve_image_name_falls_back_to_alias(monkeypatch):
    """配置镜像缺失时回退到旧名镜像（品牌改名兼容）。"""
    from core.config import Settings
    from tools.sandbox_docker import resolve_image_name

    settings = Settings(_env_file=None, var_dir=Path("var"))
    monkeypatch.setattr(
        "docker.from_env",
        lambda timeout=5: _FakeDockerClient(["quantsentinel-sandbox:latest"]),
    )
    assert resolve_image_name(settings) == "quantsentinel-sandbox:latest"


def test_resolve_image_name_keeps_configured_when_nothing_found(monkeypatch):
    """本地无任何可用镜像时仍返回配置值（由后续 healthcheck 明确报错）。"""
    from core.config import Settings
    from tools.sandbox_docker import resolve_image_name

    settings = Settings(_env_file=None, var_dir=Path("var"))
    monkeypatch.setattr("docker.from_env", lambda timeout=5: _FakeDockerClient([]))
    assert resolve_image_name(settings) == settings.sandbox_image


def _make_project(tmp_path: Path) -> Path:
    """构造最小项目树：backtest/ + core/markets.py。"""
    root = tmp_path / "proj"
    (root / "backtest").mkdir(parents=True)
    (root / "core").mkdir()
    (root / "core" / "markets.py").write_text("MARKET = 'cn_stock'\n", encoding="utf-8")
    return root


def test_volumes_are_minimal_and_readonly(tmp_path):
    """仅挂载工作区(rw) + backtest(ro) + core/markets.py(ro)。"""
    root = _make_project(tmp_path)
    workdir = tmp_path / "work"
    workdir.mkdir()

    mounts = build_container_volumes(workdir, root)

    assert set(mounts) == {
        str(workdir.resolve()),
        str((root / "backtest").resolve()),
        str((root / "core" / "markets.py").resolve()),
    }
    assert mounts[str(workdir.resolve())]["mode"] == "rw"
    assert mounts[str((root / "backtest").resolve())]["mode"] == "ro"
    assert mounts[str((root / "core" / "markets.py").resolve())]["mode"] == "ro"


def test_volumes_exclude_env_file(tmp_path):
    """.env 出现在挂载候选中即被拒绝（挂载列表层面排除）。"""
    root = _make_project(tmp_path)
    workdir = tmp_path / "work"
    workdir.mkdir()

    # 伪装成 .env 的工作区路径必须被拒
    with pytest.raises(SandboxExecutionError, match="拒绝挂载敏感文件"):
        build_container_volumes(tmp_path / ".env", root)


def test_volumes_missing_source_raises(tmp_path):
    """缺少回测引擎目录时在挂载前明确报错，不做半残执行。"""
    root = tmp_path / "proj"
    root.mkdir()  # 无 backtest / core
    workdir = tmp_path / "work"
    workdir.mkdir()
    with pytest.raises(SandboxExecutionError, match="缺少回测引擎目录"):
        build_container_volumes(workdir, root)


@pytest.mark.parametrize("secret", [
    "DEEPSEEK_API_KEY", "OPENAI_API_KEY", "GITHUB_TOKEN",
    "AWS_SECRET_ACCESS_KEY", "SSH_PRIVATE_KEY",
])
def test_filter_host_env_strips_secrets(secret):
    """宿主密钥类环境变量一律不进容器。"""
    env = filter_host_env({
        secret: "sk-leak",
        "PATH": "/usr/bin",
        "PYTHONPATH": "/project/backtest:/project/core",
    })
    assert secret not in env
    assert env["PATH"] == "/usr/bin"
    assert env["PYTHONPATH"] == "/project/backtest:/project/core"


def test_filter_host_env_keeps_only_allowlist():
    """非白名单变量即使不含密钥特征也被剔除（最小权限）。"""
    env = filter_host_env({"RANDOM_APP_FLAG": "1", "HOME": "/home/sandbox"})
    assert env == {"HOME": "/home/sandbox"}
