"""Prompt 模板注册表。

六个角色各对应一个 Markdown 模板文件 ``core/prompts/templates/<role>.md``。
占位符使用 :class:`string.Template` 的 ``$var`` 语法（而非 str.format 的 ``{var}``），
避免与模板中 JSON 示例的花括号冲突。
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from string import Template

#: 角色清单（与 agents/ 目录一一对应；redteam / risk_officer 为 Step 5 红队审计角色）
ROLES: tuple[str, ...] = (
    "hypothesis", "bull", "bear", "risk", "redteam", "risk_officer", "reviewer",
)

TEMPLATE_DIR = Path(__file__).parent / "templates"


@lru_cache(maxsize=None)
def get_template(role: str) -> str:
    """读取角色模板原文（进程内缓存）。

    Raises:
        KeyError: 角色名不在 ROLES 中。
        FileNotFoundError: 模板文件缺失（随对应 Step 交付）。
    """
    if role not in ROLES:
        raise KeyError(f"未知角色：{role!r}，应为 {ROLES} 之一")
    path = TEMPLATE_DIR / f"{role}.md"
    if not path.exists():
        raise FileNotFoundError(
            f"角色 {role!r} 的 prompt 模板缺失：{path}（随对应 Step 交付）"
        )
    return path.read_text(encoding="utf-8")


def render_prompt(role: str, **ctx: str | int | float) -> str:
    """渲染角色模板：``$var`` 占位符替换；未提供的变量保持原样，便于渐进填充。"""
    return Template(get_template(role)).safe_substitute(**ctx)
