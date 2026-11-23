"""示例脚本可运行性回归（Step 7）。

以子进程方式运行每个示例（mock 离线模式，不消耗 LLM token、无需密钥），
断言：返回码为 0、stdout 含预期关键信息。

说明：
- 示例脚本会写 output/ 与 var/trajectories/（均已 .gitignore 排除），属预期行为；
- 示例 03 / 04 含真实回测（local 沙箱）与 HTML 渲染，耗时较长，单独设置超时；
- 使用 ``sys.executable`` 保证与当前 pytest 同一虚拟环境。
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "examples"

#: (脚本名, 预期 stdout 关键词, 超时秒)
_CASES = [
    ("example_1_basic_debate.py", ["示例 01", "Markdown 报告"], 300),
    ("example_2_audit_only.py", ["示例 02", "审计意见书"], 300),
    ("example_3_full_pipeline.py", ["示例 03", "交互式 HTML"], 900),
    ("example_4_mock_offline.py", ["示例 04", "密钥要求"], 900),
    ("example_5_custom_threshold.py", ["示例 05", "阈值收紧是否触发风险提示"], 300),
]


def _run_example(script: str, timeout: int) -> subprocess.CompletedProcess:
    """在项目根目录以子进程运行示例脚本（mock 离线模式）。"""
    env = dict(os.environ)
    env["QUANT_ASST_LLM_MOCK"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, str(EXAMPLES / script)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


@pytest.mark.parametrize("script,keywords,timeout", _CASES)
def test_example_runs(script: str, keywords: list[str], timeout: int) -> None:
    """示例脚本可正常启动、执行完成且不抛异常。"""
    proc = _run_example(script, timeout)

    assert proc.returncode == 0, (
        f"{script} 退出码 {proc.returncode}\n"
        f"--- stdout ---\n{proc.stdout[-2000:]}\n"
        f"--- stderr ---\n{proc.stderr[-2000:]}"
    )
    for kw in keywords:
        assert kw in proc.stdout, f"{script} stdout 缺少预期关键词：{kw}"


def test_common_helper_is_mock_by_default() -> None:
    """共享底座默认启用 mock 离线模式（不依赖密钥）。"""
    env = dict(os.environ)
    env.pop("QUANT_ASST_LLM_MOCK", None)  # 移除后由 _common 的 setdefault 兜底
    env["PYTHONIOENCODING"] = "utf-8"
    code = (
        "import sys; sys.path.insert(0, r'" + str(EXAMPLES) + "');"
        "import _common;"
        "from core.llm import is_mock_mode;"
        "print('MOCK=' + str(is_mock_mode()))"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    assert "MOCK=True" in proc.stdout
