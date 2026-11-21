"""运行轨迹（trajectory）落盘与回放 —— 硬约束 4。

每次 Agent 运行对应一个 ``run_id``，产出 ``var/trajectories/<run_id>.jsonl``，
每行一个 JSON 事件::

    {"seq": 1, "ts": "...", "run_id": "...", "node": "...", "event": "...", "payload": {...}}

全程追加写、实时 flush；支持从 JSONL 逐事件回放一次运行的完整过程。
注意：LLM 密钥等敏感信息禁止写入 payload。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


class TrajectoryRecorder:
    """JSONL 运行轨迹记录器（与 LangGraph 单线程执行模型匹配，非线程安全）。"""

    def __init__(self, run_id: str, out_dir: Path) -> None:
        """创建记录器并写入 run_start 事件。

        Args:
            run_id: 本次运行唯一 ID。
            out_dir: JSONL 输出目录（不存在则自动创建）。
        """
        self.run_id = run_id
        self.path = out_dir / f"{run_id}.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._seq = 0
        self._fh = self.path.open("a", encoding="utf-8")
        self.log(node="meta", event="run_start", payload={"run_id": run_id})

    def log(self, node: str, event: str, payload: dict[str, Any] | None = None) -> None:
        """追加一条事件并立即落盘。

        Args:
            node: 产生事件的节点（角色名 / 工具名 / meta）。
            event: 事件类型（invoke / output / tool_call / error ...）。
            payload: 事件负载，必须可 JSON 序列化（不可序列化字段自动转 str）。
        """
        self._seq += 1
        record = {
            "seq": self._seq,
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "run_id": self.run_id,
            "node": node,
            "event": event,
            "payload": payload or {},
        }
        self._fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        self._fh.flush()

    def close(self) -> None:
        """关闭文件句柄（写入 run_end 事件）。"""
        if not self._fh.closed:
            self.log(node="meta", event="run_end")
            self._fh.close()

    # ---- 上下文管理器支持 ----
    def __enter__(self) -> "TrajectoryRecorder":
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self.close()


def load_trajectory(path: Path) -> list[dict[str, Any]]:
    """读取一份 trajectory JSONL 为事件列表。

    Raises:
        FileNotFoundError: 文件不存在。
        ValueError: 存在无法解析的行。
    """
    if not path.exists():
        raise FileNotFoundError(f"trajectory 文件不存在：{path}")
    events: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"trajectory 第 {line_no} 行不是合法 JSON：{exc}") from exc
    return events


def replay(path: Path) -> Iterator[dict[str, Any]]:
    """按序逐事件产出（用于回放/调试/审计）。"""
    yield from load_trajectory(path)
