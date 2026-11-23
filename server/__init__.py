"""Quant Asst Web 接口层（Step B）。

职责边界：
- 只做 HTTP 编排与 DTO 转换，业务逻辑全部复用 ``core/`` / ``agents/`` / ``report/``；
- 任务存进程内存（本地单用户工具，不引入数据库与消息队列）；
- LLM 密钥由 LiteLLM 从进程环境变量读取，本层不接触、不记录、不返回密钥。
"""

from __future__ import annotations
