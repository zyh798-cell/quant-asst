"""trajectory 落盘与回放测试（硬约束 4）。"""

from __future__ import annotations

import json

import pytest

from core.trajectory import TrajectoryRecorder, load_trajectory, replay


def test_recorder_writes_valid_jsonl(test_settings) -> None:
    """记录器产出逐行合法 JSON，包含 run_start 事件。"""
    with TrajectoryRecorder("run-001", test_settings.trajectory_dir) as rec:
        rec.log(node="hypothesis", event="invoke", payload={"user_input": "双均线策略"})
        rec.log(node="hypothesis", event="output", payload={"k": 1})

    events = load_trajectory(rec.path)
    assert events[0]["event"] == "run_start"
    assert [e["seq"] for e in events] == [1, 2, 3, 4]
    assert events[1]["node"] == "hypothesis"

    # 每行必须是独立合法 JSON（JSONL 格式约束）
    lines = rec.path.read_text(encoding="utf-8").splitlines()
    assert all(json.loads(line) for line in lines)


def test_recorder_appends_mode(test_settings) -> None:
    """同名 run 重复打开为追加写，不覆盖历史。"""
    rec1 = TrajectoryRecorder("run-002", test_settings.trajectory_dir)
    rec1.log(node="a", event="x")
    rec1.close()

    rec2 = TrajectoryRecorder("run-002", test_settings.trajectory_dir)
    rec2.log(node="b", event="y")
    rec2.close()

    events = load_trajectory(rec2.path)
    nodes = [e["node"] for e in events]
    assert "a" in nodes and "b" in nodes


def test_replay_order(test_settings) -> None:
    """replay 按文件顺序逐事件产出。"""
    rec = TrajectoryRecorder("run-003", test_settings.trajectory_dir)
    try:
        for i in range(5):
            rec.log(node="n", event="e", payload={"i": i})
        # log 内部实时 flush，close 前即可读取；此时含 run_start 共 6 条
        seqs = [e["seq"] for e in replay(rec.path)]
        assert seqs == [1, 2, 3, 4, 5, 6]
        payloads = [e["payload"]["i"] for e in replay(rec.path) if "i" in e["payload"]]
        assert payloads == [0, 1, 2, 3, 4]
    finally:
        rec.close()


def test_close_writes_run_end(test_settings) -> None:
    """close 会追加 run_end 事件作为收尾。"""
    rec = TrajectoryRecorder("run-005", test_settings.trajectory_dir)
    rec.log(node="n", event="e")
    rec.close()
    events = load_trajectory(rec.path)
    assert events[-1]["event"] == "run_end"


def test_load_missing_file_raises(test_settings) -> None:
    """文件不存在时明确报错。"""
    with pytest.raises(FileNotFoundError):
        load_trajectory(test_settings.trajectory_dir / "nope.jsonl")


def test_unserializable_payload_fallback(test_settings) -> None:
    """不可序列化对象自动转 str 而不抛异常（default=str 兜底）。"""
    rec = TrajectoryRecorder("run-004", test_settings.trajectory_dir)
    try:
        rec.log(node="t", event="e", payload={"obj": object()})
        events = load_trajectory(rec.path)
        assert isinstance(events[-1]["payload"]["obj"], str)
    finally:
        rec.close()
