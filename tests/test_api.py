"""接口层测试（server/，Step B）。

覆盖：状态机流转、阶段产物结构、mock 全流程、密钥不泄漏、失败路径、报告读取。

行情数据用预置 Parquet 缓存（``test_settings`` 指向 tmp_path），避免联网取数，
保证本地与 CI 均可离线复现。
"""

from __future__ import annotations

import json
import time
from typing import Any

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from server.main import create_app
from server.tasks import TaskManager, redact_secrets

from core.i18n import EN_DISCLAIMER

# ---------------------------------------------------------------------------
# 夹具
# ---------------------------------------------------------------------------

STRATEGY = "双均线策略，5 日线上穿 20 日线买入，死叉卖出"
SYMBOL = "cn:600519"
START = "2024-01-01"
END = "2024-12-31"


def _seed_market_cache(settings) -> None:
    """写入命中缓存的日线 Parquet（标准 OHLCV schema）。"""
    cache = settings.market_cache_dir / "cn_stock"
    cache.mkdir(parents=True, exist_ok=True)
    dates = pd.bdate_range(START, END)
    rng = np.random.default_rng(7)
    close = 100 * (1 + rng.normal(0, 0.01, len(dates)).cumsum())
    df = pd.DataFrame(
        {
            "date": dates,
            "open": close,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": 1_000_000.0,
            "amount": close * 1_000_000.0,
            "suspended": False,
            "limit_up": np.nan,
            "limit_down": np.nan,
        }
    )
    df.to_parquet(cache / "600519__20240101__20241231.parquet", index=False)


@pytest.fixture()
def client(test_settings, monkeypatch):
    """mock 模式 + 隔离配置的客户端。

    teardown 等待后台任务全部进入终态，避免后台线程跨测试修改进程级
    LLM 开关（QUANT_ASST_LLM_MOCK）污染后续用例。
    """
    _seed_market_cache(test_settings)
    monkeypatch.setenv("QUANT_ASST_LLM_MOCK", "1")
    manager = TaskManager(settings=test_settings)
    yield TestClient(create_app(manager=manager))
    manager.wait_all()


def _create(client: TestClient, **overrides: Any) -> dict[str, Any]:
    payload = {
        "strategy": STRATEGY,
        "symbol": SYMBOL,
        "market": "cn_stock",
        "period_start": START,
        "period_end": END,
        "mode": "mock",
        "sandbox": "local",
    }
    payload.update(overrides)
    resp = client.post("/api/analyses", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _wait_terminal(client: TestClient, task_id: str, timeout: float = 180.0) -> dict[str, Any]:
    """轮询至任务进入终态（completed / failed）。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = client.get(f"/api/analyses/{task_id}")
        assert resp.status_code == 200
        data = resp.json()
        if data["status"] not in ("pending", "running", "stage_done"):
            return data
        time.sleep(0.2)
    raise AssertionError(f"任务 {task_id} 未在 {timeout}s 内进入终态")


def _stages(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {s["stage"]: s for s in data["stages"]}


# ---------------------------------------------------------------------------
# 创建与状态机
# ---------------------------------------------------------------------------


def test_create_returns_initial_state(client: TestClient) -> None:
    data = _create(client)
    assert data["status"] in ("pending", "running", "stage_done", "completed", "failed")
    assert data["id"].startswith("qs-")
    assert data["mode"] == "mock"
    assert [s["stage"] for s in data["stages"]] == [
        "parse", "backtest", "debate", "audit", "risk", "report",
    ]
    # 请求回显不含密钥字段
    assert set(data["request"]) == {
        "strategy", "symbol", "market", "period_start", "period_end",
        "mode", "sandbox", "debate_rounds", "risk_threshold", "initial_capital",
        "report_language",
    }


def test_state_machine_reaches_completed(client: TestClient) -> None:
    data = _create(client)
    final = _wait_terminal(client, data["id"])
    assert final["status"] == "completed", final.get("error")
    assert final["error"] is None
    assert final["current_stage"] == "report"
    stages = _stages(final)
    assert all(s["status"] == "done" for s in stages.values())
    # 每个阶段都有完成时间与摘要
    for stage in stages.values():
        assert stage["finished_at"] is not None
        assert stage["summary"]


def test_stage_artifacts_structure(client: TestClient) -> None:
    data = _create(client)
    final = _wait_terminal(client, data["id"])
    stages = _stages(final)

    parse = stages["parse"]["data"]
    assert parse["symbols"] == [SYMBOL]
    assert parse["strategy_name"]
    assert parse["period_start"] == START

    backtest = stages["backtest"]["data"]
    assert backtest["symbol"] == SYMBOL
    assert {"overall", "in_sample", "out_sample", "equity_curve", "trades"} <= set(backtest)
    assert backtest["overall"]["n_days"] > 0

    debate = stages["debate"]["data"]
    assert debate["symbol"] == SYMBOL
    assert debate["verdict"]["decision"] in ("adopt", "revise", "reject")
    assert 1 <= debate["rounds"] <= 3
    assert debate["risk_checks"]

    audit = stages["audit"]["data"]
    assert audit["overall_risk_level"] in ("low", "medium", "high", "critical")
    assert audit["audit_run_id"] == final["id"]
    assert isinstance(audit["findings"], list)

    risk = stages["risk"]["data"]
    assert risk["risk_gate"]["risk_level"] == audit["overall_risk_level"]
    assert risk["final_report"]["final_decision"] in (
        "adopt", "revise", "reject", "blocked",
    )
    # 致命风险必须拦截交易建议（确定性门控）
    if audit["overall_risk_level"] == "critical":
        assert risk["risk_gate"]["trade_suggestion_allowed"] is False
        # blocked 一致性：建议改为拦截说明文案，不输出可执行内容
        assert "已拦截" in risk["final_report"]["trade_advisory"]
        assert risk["final_report"]["final_decision"] == "blocked"

    assert stages["report"]["data"]["report"]["markdown_path"]


# ---------------------------------------------------------------------------
# 报告
# ---------------------------------------------------------------------------


def test_report_markdown_and_html(client: TestClient) -> None:
    data = _create(client)
    task_id = data["id"]
    _wait_terminal(client, task_id)

    md = client.get(f"/api/analyses/{task_id}/report", params={"format": "md"})
    assert md.status_code == 200
    assert md.headers["content-type"].startswith("text/markdown")
    assert "# " in md.text

    html = client.get(f"/api/analyses/{task_id}/report", params={"format": "html"})
    assert html.status_code == 200
    assert html.headers["content-type"].startswith("text/html")
    assert "<html" in html.text.lower()


def test_report_404_before_ready(client: TestClient) -> None:
    resp = client.get("/api/analyses/qs-doesnotexist/report")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 失败路径
# ---------------------------------------------------------------------------


def test_failure_path_marks_task_failed(client: TestClient, monkeypatch) -> None:
    # 取数失败（注入确定性异常，避免依赖网络）：任务应进入 failed 且错误可读
    def _boom(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("行情服务不可达：api_key=ZZSKY123456 鉴权失败")

    monkeypatch.setattr("tools.market_data.get_daily", _boom)
    data = _create(client)
    final = _wait_terminal(client, data["id"])
    assert final["status"] == "failed"
    assert final["error"]
    assert "ZZSKY123456" not in final["error"]  # 脱敏
    stages = _stages(final)
    assert stages["parse"]["status"] == "done"
    assert stages["backtest"]["status"] == "failed"
    # 失败阶段之后的阶段保持 pending，不伪造产物
    assert stages["audit"]["status"] == "pending"


def test_validation_rejects_bad_payload(client: TestClient) -> None:
    assert client.post("/api/analyses", json={"strategy": "", "market": "cn_stock"}).status_code == 422
    assert client.post("/api/analyses", json={"strategy": "x", "market": "zz"}).status_code == 422
    assert client.post(
        "/api/analyses", json={"strategy": "x", "symbol": "600519"}
    ).status_code == 422
    assert client.post(
        "/api/analyses", json={"strategy": "x", "period_start": "2024/01/01"}
    ).status_code == 422


# ---------------------------------------------------------------------------
# 密钥不泄漏
# ---------------------------------------------------------------------------


def test_redact_secrets_unit(monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-abcdef1234567890")
    text = "调用失败：sk-abcdef1234567890 已过期，api_key=ZZSKY123456 无效"
    redacted = redact_secrets(text)
    assert "sk-abcdef1234567890" not in redacted
    assert "ZZSKY123456" not in redacted
    assert "***" in redacted


def test_secret_not_leaked_in_success_response(client: TestClient, monkeypatch) -> None:
    fake = "sk-live-fake-secret-000111"
    monkeypatch.setenv("DEEPSEEK_API_KEY", fake)
    data = _create(client)
    final = _wait_terminal(client, data["id"])
    assert final["status"] == "completed"
    assert fake not in json.dumps(final, ensure_ascii=False)


def test_secret_not_leaked_in_failure_response(client: TestClient, monkeypatch) -> None:
    fake = "sk-live-fake-secret-999888"
    monkeypatch.setenv("DEEPSEEK_API_KEY", fake)

    def _boom(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError(f"行情服务不可达：{fake}")

    monkeypatch.setattr("tools.market_data.get_daily", _boom)
    data = _create(client)
    final = _wait_terminal(client, data["id"])
    assert final["status"] == "failed"
    assert fake not in json.dumps(final, ensure_ascii=False)


# --------------------------------------------------------------------------
# 增量轮询（阶段逐个完成，不等全部结束）
# ----------------------------------------------------------------------------------


def test_incremental_stage_progress(client: TestClient) -> None:
    data = _create(client)
    task_id = data["id"]
    seen_done: list[str] = []
    deadline = time.time() + 180
    while time.time() < deadline:
        body = client.get(f"/api/analyses/{task_id}").json()
        for stage in body["stages"]:
            if stage["status"] == "done" and stage["stage"] not in seen_done:
                seen_done.append(stage["stage"])
        if body["status"] == "completed":
            break
        time.sleep(0.2)
    # 至少观测到解析与回测两个阶段先后完成（增量渲染的前提）
    assert seen_done[:2] == ["parse", "backtest"], seen_done


def test_health_has_no_secret(client: TestClient) -> None:
    body = client.get("/api/health").json()
    assert body == {"status": "ok", "mode": "mock"}


# --------------------------------------------------------------------------
# 初始资金透传（表单值必须一路传到回测与报告，不得回落默认值）
# --------------------------------------------------------------------------


def test_initial_capital_is_threaded_to_backtest_and_report(
    client: TestClient, test_settings
) -> None:
    """自定义初始资金须同时体现在回测产物、请求回显与 HTML 报告中。

    回归对象：早期版本出现过「表单提交 100000、HTML 报告显示 1,000,000」的
    参数丢失（回落工具层默认值）。此处用非默认值 880_000 走完整链路，
    断言三个环节数值一致。
    """
    capital = 880_000.0
    data = _create(client, initial_capital=capital)
    task_id = data["id"]
    # 创建响应即回显请求参数
    assert data["request"]["initial_capital"] == capital

    final = _wait_terminal(client, task_id)
    assert final["status"] == "completed", final.get("error")

    stages = _stages(final)
    backtest = stages["backtest"]["data"]
    assert backtest["initial_capital"] == capital
    # 期末净值应随初始资金变化，而不是恒为默认值量级
    assert backtest["final_equity"] > 0

    # HTML 报告的指标面板展示同一数值
    html = client.get(f"/api/analyses/{task_id}/report", params={"format": "html"})
    assert html.status_code == 200
    expected = f"{capital:,.2f}"
    assert expected in html.text
    # 不得出现默认值的痕迹
    assert "1,000,000.00" not in html.text
    # 结构化 JSON 归档同样保留请求口径
    report_dir = test_settings.report_dir / task_id
    json_files = list(report_dir.glob("analysis_*.json"))
    assert len(json_files) == 1
    archived = json.loads(json_files[0].read_text(encoding="utf-8"))
    assert archived["request"]["initial_capital"] == capital
    assert archived["backtest"]["initial_capital"] == capital


# --------------------------------------------------------------------------
# 报告双语（Step K）：请求级覆盖、默认 zh、两语言产物 schema 一致
# --------------------------------------------------------------------------


def _run_task(client: TestClient, **overrides: Any) -> dict[str, Any]:
    data = _create(client, **overrides)
    final = _wait_terminal(client, data["id"])
    assert final["status"] == "completed", final.get("error")
    return final


def test_report_language_english_end_to_end(client: TestClient) -> None:
    """report_language=en 时 Markdown / HTML 报告的静态文案为英文。"""
    final = _run_task(client, report_language="en")
    task_id = final["id"]
    assert final["request"]["report_language"] == "en"

    md = client.get(f"/api/analyses/{task_id}/report", params={"format": "md"})
    assert md.status_code == 200
    for marker in (
        "# Bull/Bear Debate Report:",
        "## Audit Conclusion",
        "# Final Quantitative Analysis Report:",
        EN_DISCLAIMER,
    ):
        assert marker in md.text
    assert "## 逐轮辩论原文" not in md.text

    html = client.get(f"/api/analyses/{task_id}/report", params={"format": "html"})
    assert html.status_code == 200
    assert '<html lang="en">' in html.text
    assert "Risk Metrics" in html.text and "Analysis Summary" in html.text


def test_report_language_defaults_to_chinese(client: TestClient) -> None:
    """不指定 report_language 时沿用默认中文（行为不变）。"""
    final = _run_task(client)
    assert final["request"]["report_language"] == ""
    md = client.get(f"/api/analyses/{final['id']}/report", params={"format": "md"})
    assert "## 逐轮辩论原文" in md.text
    assert "# 最终量化分析报告：" in md.text


def test_report_language_invalid_rejected(client: TestClient) -> None:
    """非法语言值在请求校验阶段即被拒绝（fail-closed，422）。"""
    resp = client.post("/api/analyses", json={
        "strategy": STRATEGY, "symbol": SYMBOL, "market": "cn_stock",
        "period_start": START, "period_end": END, "mode": "mock",
        "sandbox": "local", "report_language": "fr",
    })
    assert resp.status_code == 422


def test_bilingual_artifacts_json_schema_parity(client: TestClient, test_settings) -> None:
    """同一合成任务两语言产物的结构化 JSON schema 必须一致（只文案不同）。"""
    zh_final = _run_task(client, report_language="zh")
    en_final = _run_task(client, report_language="en")

    def _load(task_id: str) -> dict[str, Any]:
        files = list((test_settings.report_dir / task_id).glob("analysis_*.json"))
        assert len(files) == 1
        return json.loads(files[0].read_text(encoding="utf-8"))

    zh, en = _load(zh_final["id"]), _load(en_final["id"])
    assert set(zh) == set(en)
    assert set(zh["request"]) == set(en["request"])
    for field in ("hypothesis", "backtest", "debate", "audit", "risk_gate", "final_report"):
        assert set(zh[field]) == set(en[field]), field
    assert set(zh["risk_gate"]) == set(en["risk_gate"])

    # 各阶段产物的键集合同样与语言无关
    zh_stages = {s["stage"]: s["data"] for s in zh_final["stages"]}
    en_stages = {s["stage"]: s["data"] for s in en_final["stages"]}
    assert set(zh_stages) == set(en_stages)
    for stage in zh_stages:
        assert set(zh_stages[stage]) == set(en_stages[stage]), stage

    # 门控判定字段完全一致（语言只影响文案）
    assert zh["risk_gate"]["risk_level"] == en["risk_gate"]["risk_level"]
    assert (zh["risk_gate"]["trade_suggestion_allowed"]
            == en["risk_gate"]["trade_suggestion_allowed"])
    assert zh["final_report"]["final_decision"] == en["final_report"]["final_decision"]
