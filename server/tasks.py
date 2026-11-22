"""内存任务管理器：创建 / 查询 / 后台串行执行分析任务。

设计约束（Step B）：

- **本地单用户工具**：不引入数据库与消息队列，任务存进程内存字典；
- **串行执行**：全局执行锁避免并发任务的 mock / real 环境变量互串；
- **逐阶段写入产物**：每阶段结束即更新任务快照，前端轮询可增量渲染；
- **隐私防线**：错误文本写入前统一脱敏，密钥永不进入日志或任何响应字段。

业务复用：解析用 ``HypothesisAgent``，回测用 ``get_backtest_frame`` +
``run_backtest_in_sandbox``，辩论用 ``build_debate_graph``，审计用 ``RedTeamAgent``，
门控用 ``apply_risk_gate`` / ``final_decision``，报告用 ``report.markdown`` /
``report.html`` —— 不新写任何策略逻辑。
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from agents.final_risk_officer import FinalRiskOfficerAgent
from agents.hypothesis import HypothesisAgent
from agents.redteam import RedTeamAgent
from core.config import Settings, get_settings
from core.llm import is_mock_mode
from core.markets import Symbol
from core.risk_gate import apply_risk_gate, final_decision
from core.schemas import FinalAnalysisReport
from core.secrets import KNOWN_LLM_KEYS
from core.trajectory import TrajectoryRecorder
from report.html import render_final_html
from report.markdown import (
    render_audit_markdown,
    render_debate_markdown,
    render_final_markdown,
)
from server.schemas import (
    AnalysisCreateRequest,
    AnalysisRequestEcho,
    AnalysisStatus,
    AnalysisStatusResponse,
    ReportFormat,
    ReportRef,
    StageArtifact,
    StageId,
)
from tools.backtest_sandbox import run_backtest_in_sandbox
from tools.market_data import get_backtest_frame

#: 阶段顺序与中文名（与前端 STAGE_DEFS 对齐）
STAGE_DEFS: tuple[tuple[StageId, str], ...] = (
    ("parse", "解析"),
    ("backtest", "回测"),
    ("debate", "辩论"),
    ("audit", "审计"),
    ("risk", "风控"),
    ("report", "报告"),
)

#: 进行中的状态（轮询终止条件取反）
_ACTIVE_STATUSES: frozenset[str] = frozenset({"pending", "running", "stage_done"})

#: 通用密钥字面量脱敏（sk- 前缀 / api_key= 形式）
_SECRET_PATTERN = re.compile(
    r"(sk-[A-Za-z0-9_\-]{8,}|(?:api[_-]?key|secret|token)\s*[:=]\s*[^\s,;\"']{6,})",
    re.IGNORECASE,
)


def redact_secrets(text: str | None) -> str | None:
    """把已知密钥的值与常见密钥字面量替换为占位符。

    任何来自异常 / 日志的文本在写入任务快照前都必须经过本函数，
    保证密钥不进入响应字段（隐私硬约束）。
    """
    if not text:
        return text
    out = text
    for name in KNOWN_LLM_KEYS:
        value = os.getenv(name)
        if value and len(value) >= 6:
            out = out.replace(value, "***")
    return _SECRET_PATTERN.sub("***", out)


def _now() -> datetime:
    return datetime.now(UTC)


class TaskManager:
    """进程内任务管理器（线程安全）。"""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._tasks: dict[str, dict[str, Any]] = {}
        self._ctx: dict[str, dict[str, Any]] = {}
        self._lock = threading.RLock()
        # 串行执行锁：保证 mock/real 环境变量与 trajectory 不被并发任务互串
        self._exec_lock = threading.Lock()
        self.mode: str = "mock" if is_mock_mode() else "real"

    # ------------------------------------------------------------------
    # 对外接口
    # ------------------------------------------------------------------

    def create(self, request: AnalysisCreateRequest) -> AnalysisStatusResponse:
        """创建任务并启动后台执行，立即返回初始状态。"""
        task_id = f"qs-{uuid.uuid4().hex[:12]}"
        created = _now()
        echo = AnalysisRequestEcho(
            strategy=request.strategy,
            symbol=request.symbol,
            market=request.market,
            period_start=request.period_start,
            period_end=request.period_end,
            mode=request.mode,
            sandbox=request.sandbox,
            debate_rounds=request.debate_rounds,
            risk_threshold=request.risk_threshold,
            initial_capital=request.initial_capital,
        )
        with self._lock:
            self._tasks[task_id] = {
                "id": task_id,
                "status": "pending",
                "mode": request.mode,
                "sandbox": request.sandbox,
                "created_at": created,
                "updated_at": created,
                "current_stage": None,
                "stages": {
                    stage: {
                        "stage": stage,
                        "status": "pending",
                        "started_at": None,
                        "finished_at": None,
                        "summary": "",
                        "data": {},
                    }
                    for stage, _ in STAGE_DEFS
                },
                "error": None,
                "notice": self._notice_for(request),
                "report": None,
                "request": echo.model_dump(),
                "_request": request,
            }
            self._ctx[task_id] = {}

        thread = threading.Thread(
            target=self._run_safely, args=(task_id,), name=f"qs-task-{task_id}", daemon=True
        )
        thread.start()
        return self.get(task_id)  # type: ignore[return-value]

    def get(self, task_id: str) -> AnalysisStatusResponse | None:
        """按 ID 查询任务状态（不存在返回 None）。"""
        with self._lock:
            task = self._tasks.get(task_id)
            return self._to_response(task) if task else None

    def list(self) -> list[AnalysisStatusResponse]:
        """按创建时间倒序列出全部任务。"""
        with self._lock:
            tasks = sorted(
                self._tasks.values(), key=lambda t: t["created_at"], reverse=True
            )
            return [self._to_response(t) for t in tasks]  # type: ignore[misc]

    def wait_all(self, timeout: float = 300.0) -> None:
        """等待全部任务进入终态（测试 teardown / 优雅退出用）。"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                active = [
                    t for t in self._tasks.values() if t["status"] in _ACTIVE_STATUSES
                ]
            if not active:
                return
            time.sleep(0.1)

    def read_report(self, task_id: str, fmt: ReportFormat) -> tuple[str, str] | None:
        """读取报告内容，返回 ``(内容, content_type)``；不可用时返回 None。"""
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return None
            ref = task.get("report") or {}
            if fmt == "md":
                path = ref.get("markdown_path")
                content_type = "text/markdown; charset=utf-8"
            else:
                path = ref.get("html_path")
                content_type = "text/html; charset=utf-8"
            if not path:
                return None
            file_path = Path(path)
            if not file_path.is_file():
                return None
            return file_path.read_text(encoding="utf-8"), content_type

    # ------------------------------------------------------------------
    # 后台执行
    # ------------------------------------------------------------------

    def _run_safely(self, task_id: str) -> None:
        """后台线程入口：串行执行 + 异常兜底。"""
        with self._exec_lock:
            task = self._tasks.get(task_id)
            if task is None:
                return
            request: AnalysisCreateRequest = task["_request"]
            env_snapshot = {k: os.environ.get(k) for k in
                            ("QUANTSENTINEL_LLM_MOCK", "LITELLM_OFFLINE_MODE")}
            self._set_status(task_id, "running")
            recorder = TrajectoryRecorder(task_id, self._settings.trajectory_dir)
            try:
                self._apply_mode(request.mode)
                self._execute(task_id, request, recorder)
                self._set_status(task_id, "completed")
            except Exception as exc:  # noqa: BLE001 —— 任务级兜底，线程不静默死亡
                self._fail(task_id, exc)
            finally:
                try:
                    recorder.close()
                except Exception:  # noqa: BLE001, S110 —— 关闭失败不改变任务结果
                    pass
                for key, value in env_snapshot.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

    def _execute(
        self,
        task_id: str,
        request: AnalysisCreateRequest,
        recorder: TrajectoryRecorder,
    ) -> None:
        """按阶段执行完整研究流水线，每阶段结束即写产物。"""
        ctx = self._ctx.setdefault(task_id, {})

        self._stage_parse(task_id, request, ctx, recorder)
        self._stage_backtest(task_id, request, ctx, recorder)
        self._stage_debate(task_id, request, ctx, recorder)
        self._stage_audit(task_id, request, ctx, recorder)
        self._stage_risk(task_id, request, ctx, recorder)
        self._stage_report(task_id, request, ctx, recorder)

    # ---- 阶段 1：解析（自然语言 -> 结构化假设 + 策略代码）----

    def _stage_parse(
        self,
        task_id: str,
        request: AnalysisCreateRequest,
        ctx: dict[str, Any],
        recorder: TrajectoryRecorder,
    ) -> None:
        self._begin_stage(task_id, "parse")
        agent = HypothesisAgent(self._settings, recorder)
        state = agent.run(
            {
                "run_id": recorder.run_id,
                "user_input": request.strategy,
                "market": request.market,
                "iterations": 0,
            }
        )
        spec = dict(state.get("hypothesis") or {})
        if not spec:
            raise RuntimeError("策略解析未产出结构化假设（hypothesis 为空）")
        code = state.get("generated_code") or ""
        if not code:
            raise RuntimeError("策略解析未产出可执行策略代码")

        # 用户显式输入优先于模型推断（标的 / 区间）
        spec["market"] = request.market
        if request.symbol:
            spec["symbols"] = [request.symbol]
        if request.period_start:
            spec["period_start"] = request.period_start
        if request.period_end:
            spec["period_end"] = request.period_end
        symbols = spec.get("symbols") or []
        if not symbols:
            raise RuntimeError("未能解析出标的：请在策略描述或标的字段中明确代码")

        symbol = Symbol.parse(symbols[0])
        ctx["spec"] = spec
        ctx["generated_code"] = code
        ctx["symbol"] = symbol

        summary = (
            f"已解析：{spec.get('strategy_name', '')}｜标的 {symbol.full}｜"
            f"{spec.get('period_start', '')} ~ {spec.get('period_end', '')}"
        )
        self._finish_stage(task_id, "parse", summary, spec)

    # ---- 阶段 2：回测（取数 + 沙箱执行，数字全部来自工具）----

    def _stage_backtest(
        self,
        task_id: str,
        request: AnalysisCreateRequest,
        ctx: dict[str, Any],
        recorder: TrajectoryRecorder,
    ) -> None:
        self._begin_stage(task_id, "backtest")
        spec: dict[str, Any] = ctx["spec"]
        symbol: Symbol = ctx["symbol"]
        start = spec.get("period_start") or (date.today() - timedelta(days=365)).isoformat()
        end = spec.get("period_end") or date.today().isoformat()

        df = get_backtest_frame(symbol, start, end, self._settings)
        output = run_backtest_in_sandbox(
            ctx["generated_code"],
            df,
            symbol,
            self._settings,
            mode=request.sandbox,
            initial_capital=request.initial_capital,
            run_id=recorder.run_id,
        )
        result = output.result.model_dump()
        warnings = list(output.sandbox.warnings or [])
        ctx["backtest"] = result
        ctx["sandbox_warnings"] = warnings

        overall = result.get("overall") or {}
        summary = (
            f"回测完成：{result.get('period_start', start)} ~ {result.get('period_end', end)}｜"
            f"总收益 {(overall.get('total_return') or 0) * 100:.2f}%｜"
            f"最大回撤 {(overall.get('max_drawdown') or 0) * 100:.2f}%｜"
            f"成交 {overall.get('n_trades', 0)} 笔"
        )
        if warnings:
            summary += f"｜沙箱告警 {len(warnings)} 条"
        data = dict(result)
        data["sandbox_warnings"] = warnings
        self._finish_stage(task_id, "backtest", summary, data)

    # ---- 阶段 3：多空辩论（复用 build_debate_graph）----

    def _stage_debate(
        self,
        task_id: str,
        request: AnalysisCreateRequest,
        ctx: dict[str, Any],
        recorder: TrajectoryRecorder,
    ) -> None:
        self._begin_stage(task_id, "debate")
        from core.debate_graph import build_debate_graph

        graph, _ = build_debate_graph(
            self._settings,
            run_id=recorder.run_id,
            max_rounds=request.debate_rounds,
            recorder=recorder,
        )
        final_state = graph.invoke(
            {
                "run_id": recorder.run_id,
                "user_input": request.strategy,
                "market": request.market,
                "symbol": ctx["symbol"].full,
                "hypothesis": ctx["spec"],
                "iterations": 0,
                "debate_rounds": request.debate_rounds,
            }
        )
        outcome = final_state.get("debate_outcome")
        if not outcome:
            raise RuntimeError(
                redact_secrets(final_state.get("error")) or "辩论未产出纪要（debate_outcome 为空）"
            )
        ctx["debate"] = outcome
        verdict = outcome.get("verdict") or {}
        summary = (
            f"辩论 {outcome.get('rounds', 0)} 轮｜裁决 {verdict.get('decision', '')}｜"
            f"可信度 {verdict.get('credibility_score', 0)}/100"
        )
        self._finish_stage(task_id, "debate", summary, outcome)

    # ---- 阶段 4：红队审计（复用 RedTeamAgent）----

    def _stage_audit(
        self,
        task_id: str,
        request: AnalysisCreateRequest,
        ctx: dict[str, Any],
        recorder: TrajectoryRecorder,
    ) -> None:
        self._begin_stage(task_id, "audit")
        agent = RedTeamAgent(self._settings, recorder)
        result = agent.run(
            {
                "run_id": recorder.run_id,
                "user_input": request.strategy,
                "market": request.market,
                "symbol": ctx["symbol"].full,
                "hypothesis": ctx["spec"],
                "backtest_result": ctx["backtest"],
                "debate_outcome": ctx["debate"],
                "iterations": 0,
            }
        )
        report = dict(result["redteam_report"])
        # 用真实 run_id 覆盖 LLM 输出中的占位标识，保证可追溯
        report["audit_run_id"] = recorder.run_id
        report["source_run_id"] = (ctx["debate"].get("run_id") or "")
        ctx["audit"] = report

        findings = report.get("findings") or []
        summary = (
            f"综合风险 {report.get('risk_grade_label', '')}"
            f"（{report.get('overall_risk_level', '')}）｜"
            f"发现 {len(findings)} 条｜可行性 {report.get('tradability', '')}"
        )
        self._finish_stage(task_id, "audit", summary, report)

    # ---- 阶段 5：风控门控 + 最终分析（确定性门控，复用 final_decision）----

    def _stage_risk(
        self,
        task_id: str,
        request: AnalysisCreateRequest,
        ctx: dict[str, Any],
        recorder: TrajectoryRecorder,
    ) -> None:
        self._begin_stage(task_id, "risk")
        report: dict[str, Any] = ctx["audit"]
        outcome: dict[str, Any] = ctx["debate"]

        gate = apply_risk_gate(report, request.risk_threshold)
        officer = FinalRiskOfficerAgent(self._settings, recorder)
        result = officer.run(
            {
                "run_id": recorder.run_id,
                "user_input": request.strategy,
                "market": request.market,
                "symbol": ctx["symbol"].full,
                "hypothesis": ctx["spec"],
                "backtest_result": ctx["backtest"],
                "debate_outcome": outcome,
                "redteam_report": report,
                "risk_gate": gate.model_dump(),
                "iterations": 0,
            }
        )
        draft = result["risk_report"]
        decision = final_decision(report, outcome.get("verdict") or {})
        # 致命风险强制清空交易建议（门控拦截，不依赖 LLM 自觉）
        trade_advisory = (
            "" if not gate.trade_suggestion_allowed else draft.get("trade_advisory", "")
        )
        final = FinalAnalysisReport(
            symbol=draft.get("symbol") or ctx["symbol"].full,
            market=draft.get("market") or request.market,
            strategy_name=draft.get("strategy_name", ""),
            debate_run_id=outcome.get("run_id", ""),
            audit_run_id=recorder.run_id,
            final_decision=decision,
            credibility_score=draft.get("credibility_score", 0),
            overall_risk_level=gate.risk_level,
            risk_gate=gate.model_dump(),
            executive_summary=draft.get("executive_summary", ""),
            key_findings=list(draft.get("key_findings") or []),
            recommendations=list(draft.get("recommendations") or []),
            trade_advisory=trade_advisory,
        )
        ctx["gate"] = gate.model_dump()
        ctx["final"] = final.model_dump()

        allowed = "放行" if gate.trade_suggestion_allowed else "已拦截"
        summary = (
            f"最终决策 {decision}｜风险 {gate.risk_level}｜"
            f"交易建议 {allowed}（阈值 {request.risk_threshold}）"
        )
        self._finish_stage(
            task_id,
            "risk",
            summary,
            {"risk_gate": gate.model_dump(), "final_report": final.model_dump()},
        )

    # ---- 阶段 6：报告落盘（Markdown + HTML + 结构化 JSON）----

    def _stage_report(
        self,
        task_id: str,
        request: AnalysisCreateRequest,
        ctx: dict[str, Any],
        recorder: TrajectoryRecorder,
    ) -> None:
        self._begin_stage(task_id, "report")
        symbol: Symbol = ctx["symbol"]
        out_dir = self._settings.report_dir / recorder.run_id
        out_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe = symbol.full.replace(":", "_")

        md_text = "\n\n".join(
            [
                render_debate_markdown(ctx["debate"]),
                "---\n",
                render_audit_markdown(ctx["audit"], ctx["debate"]),
                "---\n",
                render_final_markdown(ctx["final"]),
            ]
        )
        md_path = out_dir / f"report_{safe}_{timestamp}.md"
        md_path.write_text(md_text, encoding="utf-8")

        json_path = out_dir / f"analysis_{safe}_{timestamp}.json"
        json_path.write_text(
            json.dumps(
                {
                    "task_id": task_id,
                    "mode": request.mode,
                    "sandbox": request.sandbox,
                    "request": request.model_dump(),
                    "hypothesis": ctx["spec"],
                    "backtest": ctx["backtest"],
                    "debate": ctx["debate"],
                    "audit": ctx["audit"],
                    "risk_gate": ctx["gate"],
                    "final_report": ctx["final"],
                },
                ensure_ascii=False,
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )

        html_path: Path | None = None
        try:
            html_text = render_final_html(
                backtest=ctx["backtest"],
                final_report=ctx["final"],
                audit_report=ctx["audit"],
                debate_outcome=ctx["debate"],
                kline_df=None,
            )
            html_path = out_dir / f"report_{safe}_{timestamp}.html"
            html_path.write_text(html_text, encoding="utf-8")
        except Exception as exc:  # noqa: BLE001 —— HTML 降级不阻断任务
            recorder.log(
                node="report",
                event="html_degraded",
                payload={"error": redact_secrets(f"{type(exc).__name__}: {exc}")},
            )

        ref = ReportRef(
            markdown_path=str(md_path),
            html_path=str(html_path) if html_path else None,
            json_path=str(json_path),
            available_formats=["md"] + (["html"] if html_path else []),
        )
        with self._lock:
            task = self._tasks.get(task_id)
            if task is not None:
                task["report"] = ref.model_dump()

        summary = (
            f"已生成 Markdown 报告（{md_path.name}）"
            + ("与 HTML 单文件报告" if html_path else "（HTML 生成失败已降级）")
            + "及结构化 JSON"
        )
        self._finish_stage(task_id, "report", summary, {"report": ref.model_dump()})

    # ------------------------------------------------------------------
    # 快照维护
    # ------------------------------------------------------------------

    def _begin_stage(self, task_id: str, stage: StageId) -> None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return
            now = _now()
            task["status"] = "running"
            task["current_stage"] = stage
            task["updated_at"] = now
            entry = task["stages"][stage]
            entry["status"] = "running"
            entry["started_at"] = now
            entry["finished_at"] = None
            entry["summary"] = ""

    def _finish_stage(
        self, task_id: str, stage: StageId, summary: str, data: dict[str, Any]
    ) -> None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return
            now = _now()
            entry = task["stages"][stage]
            entry["status"] = "done"
            entry["finished_at"] = now
            entry["summary"] = summary
            entry["data"] = data
            task["status"] = "stage_done"
            task["updated_at"] = now

    def _set_status(self, task_id: str, status: AnalysisStatus) -> None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return
            task["status"] = status
            task["updated_at"] = _now()

    def _fail(self, task_id: str, exc: Exception) -> None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return
            now = _now()
            stage = task.get("current_stage")
            if stage and stage in task["stages"]:
                entry = task["stages"][stage]
                entry["status"] = "failed"
                entry["finished_at"] = now
            task["status"] = "failed"
            task["updated_at"] = now
            task["error"] = redact_secrets(f"[{stage or 'task'}] {type(exc).__name__}: {exc}")

    def _apply_mode(self, mode: str) -> None:
        """按任务模式设置进程级 LLM 开关（串行执行保证不串扰）。"""
        if mode == "mock":
            os.environ["QUANTSENTINEL_LLM_MOCK"] = "1"
            os.environ["LITELLM_OFFLINE_MODE"] = "true"
        else:
            os.environ.pop("QUANTSENTINEL_LLM_MOCK", None)
            os.environ.pop("LITELLM_OFFLINE_MODE", None)

    def _notice_for(self, request: AnalysisCreateRequest) -> str | None:
        """模式与进程默认不一致时给出提示（前端可展示）。"""
        if request.mode != self.mode:
            return (
                f"任务以 {request.mode} 模式执行；进程启动时检测到默认模式为 {self.mode}，"
                "执行期间已按任务模式切换。"
            )
        return None

    def _to_response(self, task: dict[str, Any]) -> AnalysisStatusResponse:
        """内部快照 -> 响应 DTO。"""
        stages = [
            StageArtifact(
                stage=entry["stage"],
                status=entry["status"],
                started_at=entry["started_at"],
                finished_at=entry["finished_at"],
                summary=entry["summary"],
                data=entry["data"],
            )
            for entry in (task["stages"][stage] for stage, _ in STAGE_DEFS)
        ]
        report = task.get("report")
        return AnalysisStatusResponse(
            id=task["id"],
            status=task["status"],
            mode=task["mode"],
            sandbox=task["sandbox"],
            created_at=task["created_at"],
            updated_at=task["updated_at"],
            current_stage=task.get("current_stage"),
            stages=stages,
            error=task.get("error"),
            notice=task.get("notice"),
            report=ReportRef.model_validate(report) if report else None,
            request=AnalysisRequestEcho.model_validate(task["request"])
            if task.get("request")
            else None,
        )
