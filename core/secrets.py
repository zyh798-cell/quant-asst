"""密钥环境变量读取与隐私安全展示。

约定：**只判断存在性，绝不读取/输出密钥明文**。所有对外展示统一走
:func:`mask_secret`，仅返回「存在 / 不存在」级别的信息。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

#: QuantSentinel 可识别的 LLM 密钥环境变量（LiteLLM 官方约定名）
KNOWN_LLM_KEYS: tuple[str, ...] = (
    "DEEPSEEK_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "MOONSHOT_API_KEY",
    "QWEN_API_KEY",
)

#: 项目根目录下的环境变量文件（cli.py 必须在项目根目录运行，故按 cwd 查找）
ENV_FILE = ".env"


def load_env_file(path: str | Path | None = None) -> bool:
    """把项目 ``.env`` 读入进程环境变量（不覆盖已存在的值）。

    络：LiteLLM 虽然会自行加载 ``.env``，但那发生在 ``import litellm`` 之后，
    CLI 启动阶段的密钥存在性检查会早于此，因此需要显式先加载一次。

    Returns:
        找到并加载了环境变量文件返回 True，否则 False。
    """
    target = Path(path) if path is not None else Path(ENV_FILE)
    if not target.is_file():
        return False
    try:
        from dotenv import load_dotenv
    except Exception:  # noqa: BLE001 —— 无 python-dotenv 时静默跳过
        return False
    load_dotenv(target, override=False)
    return True


def secret_exists(name: str) -> bool:
    """判断某密钥环境变量是否已配置（值为非空字符串即视为存在）。"""
    value = os.getenv(name)
    return bool(value and str(value).strip())


def present_keys(names: Iterable[str] = KNOWN_LLM_KEYS) -> list[str]:
    """返回已配置的密钥名列表（仅名称，不含值）。"""
    return [n for n in names if secret_exists(n)]


def mask_secret(name: str) -> str:
    """把密钥名转为隐私安全描述：``DEEPSEEK_API_KEY: 存在`` / ``: 不存在``。

    任何情况下都不返回密钥内容本身。
    """
    return f"{name}: {'存在' if secret_exists(name) else '不存在'}"


def describe_keys(names: Iterable[str] = KNOWN_LLM_KEYS) -> list[str]:
    """逐项列出密钥存在性描述，便于启动日志与 doctor 展示。"""
    return [mask_secret(n) for n in names]
