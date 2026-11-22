"""FastAPI 应用入口。

启动::

    uv run uvicorn server.main:app --reload --port 8000

隐私：本模块只调用 :func:`core.secrets.load_env_file` 把项目 ``.env`` 读入进程
环境变量，供 LiteLLM 读取；密钥不进入 ``Settings``、不写日志、不出现在响应中。
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.secrets import load_env_file
from server.routes import create_router
from server.tasks import TaskManager

#: 允许跨域的本地前端来源（Vite 开发服务器）
ALLOWED_ORIGINS: tuple[str, ...] = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
)


def create_app(manager: TaskManager | None = None) -> FastAPI:
    """构建 FastAPI 应用（工厂便于测试注入隔离的 TaskManager）。"""
    load_env_file()  # 真实模式下读取项目 .env 中的 LLM 密钥

    app = FastAPI(
        title="QuantSentinel API",
        description=(
            "多智能体协作量化研究引擎接口层。仅用于研究与教育，不构成投资建议，"
            "不提供实盘下单能力。"
        ),
        version="0.1.0",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(ALLOWED_ORIGINS),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    task_manager = manager or TaskManager()
    app.include_router(create_router(task_manager))
    app.state.task_manager = task_manager

    @app.get("/api/health", tags=["meta"])
    def health() -> dict[str, Any]:
        """健康检查（不含任何密钥信息）。"""
        return {"status": "ok", "mode": task_manager.mode}

    return app


app = create_app()
