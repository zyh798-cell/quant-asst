"""多模型辩论对比编排（Step L）。

把「模型可插拔」从架构事实变成可见交付物：同一策略假设、同一数据、同一辩论
轮次上限，**逐模型独立**跑完整「多空辩论 -> 红队审计 -> 风控门控」，各模型
输出互不影响（每个模型用独立 settings 副本 + 独立 run_id + 独立落盘），
最终汇总成一份对比报告（:mod:`report.comparison`）。

设计约束（与既有工程约定一致）：

- **不改单模型辩论 / 门控逻辑本体**：复用 :func:`core.debate_graph.build_debate_graph`
  与 :func:`core.audit_graph.build_audit_graph`，逐模型仅覆写 ``settings.llm_model``
  （``model_copy`` 副本，绝不共享可变配置），其余行为与单模型链路逐字一致。
- **不做模型间加权仲裁 / 自动选优**：对比报告只并列呈现各模型裁决 / 风险 / 建议
  与一致 / 分歧汇总，分歧单独列出，绝不下「哪个模型更好」的裁判结论。
- **mock 一等公民**：mock 下各模型返回确定性输出，编排全程离线（不取数、不回测，
  仅 LLM 角色调用），CI 不依赖真实密钥；mock 下耗时记 0.0 以保证「同输入两次运行
  逐字一致」的确定性测试。
- **密钥 fail-closed**：真实模式下某模型密钥缺失 -> 该模型跳过并标注原因（不中断
  其他模型）；全部模型密钥缺失 -> 抛 :class:`AllModelsSkippedError` 报错退出。
  未知 provider 无法确认密钥需求 -> 保守跳过并标注原因，绝不静默放行。
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.audit_graph import build_audit_graph
from core.config import Settings
from core.debate_graph import build_debate_graph
from core.llm import reset_usage, usage_for
from core.models import AllModelsSkippedError, model_is_available
from core.trajectory import TrajectoryRecorder

#: 对比报告落盘根目录名（``output/`` 下新目录）
COMPARISON_DIR_NAME = "comparison"


# ---------------------------------------------------------------------------
# 确定性 run_id / 文件名（同输入两次运行逐字一致，含 mock 确定性测试）
# ---------------------------------------------------------------------------


def _slug(model: str) -> str:
    """模型名转文件名安全短串（保留可读前缀 + 稳定 hash 尾巴，去重同名）。"""
    import re

    base = re.sub(r"[^A-Za-z0-9]+", "_", str(model or "model")).strip("_").lower() or "model"
    digest = hashlib.sha1(str(model or "model").encode("utf-8")).hexdigest()[:6]
    return f"{base[:24]}_{digest}"


def deterministic_run_id(symbol: str, market: str, rounds: int, models: list[str]) -> str:
    """由输入（标的/市场/轮次/模型清单）派生确定性 run_id，保证可复现、可落稳定文件名。"""
    key = "|".join([symbol or "", market or "", str(rounds), ",".join(models)])
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:10]
    return f"cmp-{digest}"


# ---------------------------------------------------------------------------
# 结果结构
# ---------------------------------------------------------------------------


@dataclass
class ModelRunResult:
    """单个模型的运行结果（成功 / 跳过）。"""

    model: str
    status: str = "ok"            # "ok" | "skipped"
    reason: str = ""             # 跳过原因（status=skipped 时非空）
    debate_outcome: dict[str, Any] = field(default_factory=dict)
    audit_report: dict[str, Any] = field(default_factory=dict)
    final_report: dict[str, Any] = field(default_factory=dict)
    elapsed_seconds: float = 0.0
    usage: dict[str, int] = field(default_factory=dict)
    artifacts: dict[str, str] = field(default_factory=dict)
    run_id: str = ""

    @property
    def decision(self) -> str:
        return str(self.final_report.get("final_decision", ""))

    @property
    def risk_level(self) -> str:
        return str(self.final_report.get("overall_risk_level", ""))

    @property
    def advisory_allowed(self) -> bool:
        gate = self.final_report.get("risk_gate") or {}
        return bool(gate.get("trade_suggestion_allowed", True))

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "status": self.status,
            "reason": self.reason,
            "run_id": self.run_id,
            "debate_outcome": self.debate_outcome,
            "audit_report": self.audit_report,
            "final_report": self.final_report,
            "elapsed_seconds": self.elapsed_seconds,
            "usage": self.usage,
            "artifacts": self.artifacts,
        }


@dataclass
class ComparisonResult:
    """多模型对比总结果（:func:`run_model_comparison` 的返回）。"""

    run_id: str
    symbol: str
    market: str
    user_input: str
    rounds: int
    models: list[str]
    mode: str                      # "mock" | "real"
    per_model: list[ModelRunResult] = field(default_factory=list)

    @property
    def ok_models(self) -> list[ModelRunResult]:
        return [m for m in self.per_model if m.status == "ok"]

    @property
    def skipped(self) -> list[ModelRunResult]:
        return [m for m in self.per_model if m.status == "skipped"]

    @property
    def all_skipped(self) -> bool:
        return bool(self.per_model) and all(m.status == "skipped" for m in self.per_model)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "symbol": self.symbol,
            "market": self.market,
            "user_input": self.user_input,
            "rounds": self.rounds,
            "models": list(self.models),
            "mode": self.mode,
            "per_model": [m.to_dict() for m in self.per_model],
        }


# ---------------------------------------------------------------------------
# 单模型独立执行（辩论 -> 审计 -> 门控；逐模型独立 settings 副本 + 独立 recorder）
# ---------------------------------------------------------------------------


def _run_single_model(
    settings: Settings,
    model: str,
    run_id_base: str,
    symbol: str,
    market: str,
    user_input: str,
    hypothesis: dict[str, Any],
    rounds: int,
    threshold: str,
    mock_mode: bool,
) -> ModelRunResult:
    """对单个模型独立跑完整辩论 + 审计 + 门控，落盘该模型产物。

    各模型互不影响：``settings.model_copy`` 产生独立副本，仅覆写 ``llm_model``；
    独立 recorder / run_id / 落盘目录；usage 在该模型执行前 :func:`reset_usage`、
    执行后 :func:`usage_for` 读取，绝不跨模型串扰。
    """
    model_settings = settings.model_copy(update={"llm_model": model})
    model_slug = _slug(model)
    run_id = f"{run_id_base}__{model_slug}"

    reset_usage(model)
    started = time.monotonic()
    result = ModelRunResult(model=model, run_id=run_id)

    recorder = TrajectoryRecorder(run_id, model_settings.trajectory_dir)
    try:
        # ---- 1) 多空辩论（复用单模型链路，仅换模型）----
        graph, _ = build_debate_graph(
            model_settings, run_id=run_id, max_rounds=rounds, recorder=recorder
        )
        debate_state = graph.invoke(
            {
                "run_id": run_id,
                "user_input": user_input,
                "market": market,
                "symbol": symbol,
                "hypothesis": hypothesis,
                "iterations": 0,
                "debate_rounds": rounds,
            }
        )
        outcome = debate_state.get("debate_outcome")
        if not outcome:
            # 辩论失败：该模型标记 skipped（不中断其他模型），原因据实记录
            result.status = "skipped"
            result.reason = f"辩论未产出纪要：{debate_state.get('error')}"
            return result
        result.debate_outcome = outcome

        # ---- 2) 红队审计 + 风控门控 + 综合官（复用审计图，仅换模型）----
        audit_graph, _ = build_audit_graph(
            model_settings, run_id=run_id, source_run_id=run_id,
            threshold=threshold, recorder=recorder,
            lang=settings.report_language,
        )
        audit_state = audit_graph.invoke(
            {
                "run_id": run_id,
                "user_input": user_input,
                "market": market,
                "symbol": symbol,
                "hypothesis": hypothesis,
                "debate_outcome": outcome,
                "iterations": 0,
            }
        )
        if audit_state.get("error"):
            result.status = "skipped"
            result.reason = f"审计阶段失败：{audit_state['error']}"
            return result
        result.audit_report = audit_state.get("redteam_report") or {}
        result.final_report = audit_state.get("final_report") or {}
    except Exception as exc:  # noqa: BLE001 —— 单模型异常不中断其他模型
        result.status = "skipped"
        result.reason = f"{type(exc).__name__}: {exc}"
        return result
    finally:
        recorder.close()

    # ---- usage 与耗时（mock 下耗时记 0.0 保证确定性；真实走 wall-clock）----
    result.usage = usage_for(model)
    result.elapsed_seconds = 0.0 if mock_mode else round(time.monotonic() - started, 3)
    result.status = "ok"
    return result


def _persist_model_artifacts(
    result: ModelRunResult, out_root: Path, model_slug: str
) -> None:
    """把单模型的辩论 / 审计 / 最终报告独立落盘到 ``<out_root>/models/<slug>/``。"""
    model_dir = out_root / "models" / model_slug
    model_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, str] = {}
    if result.debate_outcome:
        p = model_dir / "debate.json"
        p.write_text(json.dumps(result.debate_outcome, ensure_ascii=False, indent=2), encoding="utf-8")
        paths["debate_json"] = str(p)
    if result.audit_report:
        p = model_dir / "audit.json"
        p.write_text(json.dumps(result.audit_report, ensure_ascii=False, indent=2), encoding="utf-8")
        paths["audit_json"] = str(p)
    if result.final_report:
        p = model_dir / "final.json"
        p.write_text(json.dumps(result.final_report, ensure_ascii=False, indent=2), encoding="utf-8")
        paths["final_json"] = str(p)
    result.artifacts = paths


# ---------------------------------------------------------------------------
# 编排入口
# ---------------------------------------------------------------------------


def run_model_comparison(
    settings: Settings,
    models: list[str],
    user_input: str,
    symbol: str,
    market: str,
    rounds: int = 3,
    threshold: str = "high",
    hypothesis: dict[str, Any] | None = None,
    mock_mode: bool | None = None,
) -> ComparisonResult:
    """逐模型独立执行完整「辩论 -> 审计 -> 门控」，返回 :class:`ComparisonResult`。

    - 各模型互不影响：独立 settings 副本、独立 run_id / recorder / 落盘目录；
    - 某模型密钥缺失（真实模式）：跳过并标注原因，不中断其他模型；
    - 真实模式全部模型密钥缺失：抛 :class:`AllModelsSkippedError`。

    Args:
        settings: 全局配置（基线；逐模型用其 ``model_copy`` 副本）。
        models: 模型名清单（LiteLLM 格式 ``provider/model``）。
        user_input: 自然语言策略假设（同一份输入给所有模型）。
        symbol: 标的（如 ``cn:600519``）。
        market: 市场前缀。
        rounds: 辩论轮次上限（各模型一致）。
        threshold: 风险门控阈值（各模型一致）。
        hypothesis: 结构化假设（可选，供辩论引用；缺省空 dict）。
        mock_mode: 是否 mock；``None`` 时由 :func:`core.llm.is_mock_mode` 自动判定。

    Returns:
        含各模型逐模型结果与跳过原因的 :class:`ComparisonResult`。

    Raises:
        AllModelsSkippedError: 真实模式下所有模型均不可用（密钥缺失 / 未知 provider）。
    """
    from core.llm import is_mock_mode

    if not models:
        raise ValueError("models 不能为空（多模型对比至少需要一个模型）")
    mock = is_mock_mode() if mock_mode is None else mock_mode
    run_id = deterministic_run_id(symbol, market, rounds, models)
    comparison = ComparisonResult(
        run_id=run_id, symbol=symbol, market=market,
        user_input=user_input, rounds=rounds, models=list(models),
        mode="mock" if mock else "real",
    )

    for model in models:
        available, reason = model_is_available(model, mock)
        if not available:
            comparison.per_model.append(
                ModelRunResult(model=model, status="skipped", reason=reason)
            )
            continue
        result = _run_single_model(
            settings, model, run_id, symbol, market, user_input,
            hypothesis or {}, rounds, threshold, mock,
        )
        comparison.per_model.append(result)

    # 真实模式全缺失 -> 报错退出（mock 模式恒可用，不会走到这里）
    if not mock and comparison.all_skipped:
        names = ", ".join(m.model for m in comparison.per_model)
        reasons = "; ".join(f"{m.model}: {m.reason}" for m in comparison.per_model)
        raise AllModelsSkippedError(
            f"全部模型均不可用（{len(names)} 个）：{reasons}"
        )
    return comparison


def write_comparison_artifacts(
    comparison: ComparisonResult, out_dir: Path | str
) -> str:
    """落盘各模型独立产物到 ``<out_dir>/<run_id>/models/<slug>/``，返回该目录。

    逐个模型独立成目录，互不影响；返回根目录路径供 :mod:`report.comparison`
    在其下生成汇总报告。
    """
    root = Path(out_dir) / COMPARISON_DIR_NAME / comparison.run_id
    root.mkdir(parents=True, exist_ok=True)
    for result in comparison.per_model:
        if result.status != "ok":
            # 跳过的模型也留一份占位说明，便于审计「为什么没跑」
            slug = _slug(result.model)
            skipped_dir = root / "models" / slug
            skipped_dir.mkdir(parents=True, exist_ok=True)
            (skipped_dir / "skipped.json").write_text(
                json.dumps(
                    {"model": result.model, "status": result.status, "reason": result.reason},
                    ensure_ascii=False, indent=2,
                ),
                encoding="utf-8",
            )
            continue
        _persist_model_artifacts(result, root, _slug(result.model))
    return str(root)
