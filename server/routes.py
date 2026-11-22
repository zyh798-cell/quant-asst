"""API 路由：任务创建 / 状态查询 / 报告读取。

路径与前端约定（Step B）：

- ``POST /api/analyses``              创建任务，返回初始状态（201）
- ``GET  /api/analyses``              任务列表（便于调试）
- ``GET  /api/analyses/{id}``         状态 + 已完成阶段产物（前端 1~2s 轮询）
- ``GET  /api/analyses/{id}/report``  报告内容（``format=md|html``）
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Response

from server.schemas import (
    AnalysisCreateRequest,
    AnalysisStatusResponse,
    ReportFormat,
)
from server.tasks import TaskManager


def create_router(manager: TaskManager) -> APIRouter:
    """绑定具体 :class:`TaskManager` 的路由（便于测试注入隔离配置）。"""
    router = APIRouter(prefix="/api", tags=["analyses"])

    @router.post("/analyses", response_model=AnalysisStatusResponse, status_code=201)
    def create_analysis(payload: AnalysisCreateRequest) -> AnalysisStatusResponse:
        """创建分析任务并立即在后台启动执行。"""
        return manager.create(payload)

    @router.get("/analyses", response_model=list[AnalysisStatusResponse])
    def list_analyses() -> list[AnalysisStatusResponse]:
        """按创建时间倒序列出全部任务。"""
        return manager.list()

    @router.get("/analyses/{task_id}", response_model=AnalysisStatusResponse)
    def get_analysis(task_id: str) -> AnalysisStatusResponse:
        """查询任务状态与已完成阶段的产物。"""
        task = manager.get(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="分析任务不存在")
        return task

    @router.get(
        "/analyses/{task_id}/report",
        responses={
            200: {
                "content": {"text/markdown": {}, "text/html": {}},
                "description": "报告正文（Markdown 或单文件 HTML）",
            }
        },
    )
    def get_report(
        task_id: str,
        format: ReportFormat = Query("md"),  # noqa: B008 —— format 为报告格式语义，保留命名
    ) -> Response:
        """读取报告内容（md / html）。报告未生成的时候返回 404。"""
        result = manager.read_report(task_id, format)
        if result is None:
            raise HTTPException(status_code=404, detail="报告尚未生成或任务不存在")
        content, content_type = result
        return Response(content=content, media_type=content_type)

    return router
