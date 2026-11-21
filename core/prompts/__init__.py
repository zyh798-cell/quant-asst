"""Prompt 模板子包：六个角色的 system prompt 模板与注册表。"""

from core.prompts.registry import ROLES, get_template, render_prompt

__all__ = ["ROLES", "get_template", "render_prompt"]
