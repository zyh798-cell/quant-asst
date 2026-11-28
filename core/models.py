"""模型清单与密钥判定（Step L：多模型辩论对比）。

把「LiteLLM 模型串 → 所需密钥环境变量」的映射集中于此，供多模型编排判定
逐个模型的可用性（密钥是否已配置）。设计约束：

- **不读密钥明文**：复用 :mod:`core.secrets` 的存在性判断（``secret_exists``）；
- **provider 归一化**：LiteLLM 模型串形如 ``provider/model``（如
  ``deepseek/deepseek-chat``、``openai/gpt-4o-mini``），provider 取冒号段前缀；
- **fail-closed**：已知 provider 且其密钥缺失 → 该模型跳过；未知 provider
  无法确认密钥需求 → 在真实模式下保守跳过并标注原因，绝不静默放行。
  mock 模式不受密钥约束（离线演示一等公民）。
"""

from __future__ import annotations

from core.secrets import secret_exists

#: provider（LiteLLM 模型串前缀，小写）-> 所需密钥环境变量名
#: （取值须落在 :data:`core.secrets.KNOWN_LLM_KEYS`，保持命名一致）
_PROVIDER_SECRET_ENV: dict[str, str] = {
    "deepseek": "DEEPSEEK_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "google": "GEMINI_API_KEY",
    "moonshot": "MOONSHOT_API_KEY",
    "qwen": "QWEN_API_KEY",
    "dashscope": "QWEN_API_KEY",
}


class AllModelsSkippedError(RuntimeError):
    """真实模式下所有候选模型均不可用（密钥缺失），无法执行多模型对比。"""


def provider_of(model: str) -> str:
    """从 LiteLLM 模型串提取 provider 前缀（小写、去空白）。

    形如 ``provider/model`` 取 ``provider``；无前缀（如裸 ``gpt-4o-mini``）
    返回空串，交由 :func:`required_secret_env` 判为「未知 provider」。
    """
    prefix = str(model or "").split("/", 1)[0].strip().lower()
    return prefix


def required_secret_env(model: str) -> str | None:
    """该模型所需的密钥环境变量名；未知 provider 返回 ``None``（无法确认）。"""
    return _PROVIDER_SECRET_ENV.get(provider_of(model))


def model_is_available(model: str, mock_mode: bool) -> tuple[bool, str]:
    """判定单模型在给定模式下是否可用。

    - ``mock_mode``：一律可用（离线确定性演示，密钥不约束 mock）。
    - 真实模式 + 已知 provider + 密钥缺失：不可用，原因「密钥缺失」。
    - 真实模式 + 未知 provider：不可用，原因「无法识别所需密钥」
      （fail-closed，不静默放行）。

    Returns:
        ``(available, reason)``；``available=True`` 时 ``reason`` 为空串。
    """
    if mock_mode:
        return True, ""
    env = required_secret_env(model)
    if env is None:
        return False, f"无法识别 {model} 所需密钥（未知 provider）"
    if not secret_exists(env):
        return False, f"{env} 未配置"
    return True, ""


def split_models(spec: str | None) -> list[str]:
    """把模型列表字符串解析为规范模型名清单（去空白、去重、保序）。

    接受逗号 / 分号 / 空白分隔，如 ``"deepseek,openai/gpt-4o-mini"``。
    空 / 全空白输入返回空列表（由调用方决定缺省行为）。
    """
    if not spec:
        return []
    import re

    parts = re.split(r"[,;\s]+", str(spec).strip())
    seen: set[str] = set()
    out: list[str] = []
    for p in parts:
        p = p.strip()
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return out
