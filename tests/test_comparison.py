"""多模型辩论对比（Step L）离线测试。

覆盖（全部离线、合成 / mock，不破坏 316 基线）：

- ``core.models``：模型清单解析、provider->密钥映射、单模型可用性判定
  （真实模式密钥缺失 / 未知 provider 跳过，mock 全放行）；
- ``core.comparison``：多模型编排正确性（逐模型独立、互不影响、独立落盘）、
  单模型密钥缺失跳过（不中断其他）、全缺失报错（``AllModelsSkippedError``）、
  mock 多模型确定性（同一输入两次运行渲染结果逐字一致）；
- ``report.comparison``：对比报告结构与 Step K 双语键齐全（38 个 ``cmp.*`` 键
  在 zh/en 目录均存在且非空）、分歧 / 一致汇总节正确呈现。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from core.config import Settings
from core.comparison import (
    ComparisonResult,
    ModelRunResult,
    run_model_comparison,
    write_comparison_artifacts,
)
from core.i18n import MESSAGES_EN, MESSAGES_ZH
from core.models import AllModelsSkippedError, model_is_available, split_models
from report.comparison import render_comparison_markdown, write_comparison_report

#: LLM 密钥环境变量（真实模式可用性判定依赖，测试须可控）
_LLM_KEY_ENVS = (
    "DEEPSEEK_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY", "MOONSHOT_API_KEY", "QWEN_API_KEY",
)


def _clear_llm_keys(monkeypatch) -> None:
    """清空全部 LLM 密钥环境变量（保证真实模式用例不依赖本机 .env / shell）。"""
    for name in _LLM_KEY_ENVS:
        monkeypatch.delenv(name, raising=False)


def _mock_settings(tmp_path) -> Settings:
    """指向临时目录的配置（不读 .env、不污染真实 var/）。"""
    s = Settings(_env_file=None, var_dir=tmp_path / "var")
    s.ensure_dirs()
    return s


# ---------------------------------------------------------------------------
# core.models：模型清单解析与可用性判定
# ---------------------------------------------------------------------------


def test_split_models_parses_and_dedupes():
    assert split_models("deepseek,openai/gpt-4o-mini") == ["deepseek", "openai/gpt-4o-mini"]
    # 分号 / 空白分隔、去重保序
    assert split_models("a, b; c a") == ["a", "b", "c"]
    assert split_models("") == []
    assert split_models(None) == []
    assert split_models("   , ,") == []


def test_single_model_available_real_missing_key(monkeypatch):
    """真实模式：已知 provider 密钥缺失 -> 不可用（fail-closed）。"""
    monkeypatch.delenv("QUANT_ASST_LLM_MOCK", raising=False)
    _clear_llm_keys(monkeypatch)
    assert model_is_available("deepseek/deepseek-chat", False) == (False, "DEEPSEEK_API_KEY 未配置")
    assert model_is_available("openai/gpt-4o-mini", False) == (False, "OPENAI_API_KEY 未配置")
    # 未知 provider：无法确认密钥需求 -> 保守跳过（不静默放行）
    assert model_is_available("foo/bar", False)[0] is False


def test_single_model_available_real_present_key(monkeypatch):
    """真实模式：密钥存在 -> 可用。"""
    monkeypatch.delenv("QUANT_ASST_LLM_MOCK", raising=False)
    _clear_llm_keys(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert model_is_available("openai/gpt-4o-mini", False) == (True, "")


def test_mock_mode_always_available(monkeypatch):
    """mock 一等公民：无论密钥是否存在，mock 下模型一律可用。"""
    monkeypatch.setenv("QUANT_ASST_LLM_MOCK", "1")
    _clear_llm_keys(monkeypatch)
    assert model_is_available("deepseek/deepseek-chat", True) == (True, "")
    assert model_is_available("openai/gpt-4o-mini", True) == (True, "")


# ---------------------------------------------------------------------------
# core.comparison：多模型编排（独立 / 互不影响 / 逐个落盘 / 确定性）
# ---------------------------------------------------------------------------


def test_mock_multi_model_independent_and_persisted(
    monkeypatch, tmp_path: Path
):
    """mock 下多模型逐模型独立运行、独立落盘、互不影响（run_id 含模型 slug）。"""
    monkeypatch.setenv("QUANT_ASST_LLM_MOCK", "1")
    s = _mock_settings(tmp_path)
    out = tmp_path / "out"

    comparison = run_model_comparison(
        s, ["deepseek/deepseek-chat", "openai/gpt-4o-mini"],
        "双均线策略", "cn:600519", "cn_stock", rounds=2, mock_mode=True,
    )
    assert comparison.mode == "mock"
    assert [m.status for m in comparison.per_model] == ["ok", "ok"]

    # 各模型独立 run_id（含模型 slug，互不影响）
    run_ids = [m.run_id for m in comparison.ok_models]
    assert len(set(run_ids)) == 2
    assert all(comparison.run_id in rid for rid in run_ids)

    # 独立落盘：每模型产物目录独立（write_comparison_artifacts 返回 str 根目录）
    root = Path(write_comparison_artifacts(comparison, out))
    model_dirs = sorted(p.name for p in (root / "models").iterdir())
    assert len(model_dirs) == 2
    for m in comparison.ok_models:
        assert m.artifacts.get("debate_json") and m.artifacts.get("audit_json")
        assert m.artifacts.get("final_json")
        assert Path(m.artifacts["final_json"]).exists()
        # 各模型产物路径确实指向不同目录
    dirs = {Path(m.artifacts["final_json"]).parent.name for m in comparison.ok_models}
    assert len(dirs) == 2


def test_single_model_key_missing_skipped_not_block(
    monkeypatch, tmp_path: Path
):
    """真实模式：某模型密钥缺失 -> 该模型 skipped（标注原因），不中断其他模型。

    打桩 ``_run_single_model`` 以隔离「密钥门控」与「LLM 执行」：本用例只验证
    编排层的密钥判定（缺 key 跳过、有 key 放行），可用模型的运行结果以合成值代替，
    避免离线 CI 下真实调 LiteLLM 失败。
    """
    monkeypatch.delenv("QUANT_ASST_LLM_MOCK", raising=False)
    _clear_llm_keys(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test")
    s = _mock_settings(tmp_path)

    import core.comparison as _cmp

    def _fake_run_single(settings, model, run_id_base, symbol, market, user_input,
                         hypothesis, rounds, threshold, mock_mode):
        return ModelRunResult(
            model=model, status="ok", run_id=f"{run_id_base}__{model}",
            debate_outcome={"verdict": {"decision": "revise"}},
            final_report={"final_decision": "revise", "overall_risk_level": "medium",
                         "credibility_score": 60,
                         "risk_gate": {"trade_suggestion_allowed": True}},
            usage={"prompt_tokens": 1, "completion_tokens": 1, "calls": 1},
        )

    monkeypatch.setattr(_cmp, "_run_single_model", _fake_run_single)

    comparison = run_model_comparison(
        s, ["deepseek/deepseek-chat", "openai/gpt-4o-mini"],
        "双均线策略", "cn:600519", "cn_stock", mock_mode=False,
    )
    by_model = {m.model: m for m in comparison.per_model}
    # deepseek 缺密钥 -> skipped；openai 有密钥 -> ok
    assert by_model["deepseek/deepseek-chat"].status == "skipped"
    assert "DEEPSEEK_API_KEY" in by_model["deepseek/deepseek-chat"].reason
    assert by_model["openai/gpt-4o-mini"].status == "ok"
    # 跳过不影响其他模型运行
    assert len(comparison.ok_models) == 1


def test_all_models_missing_raises(monkeypatch, tmp_path: Path):
    """真实模式：全部模型密钥缺失 -> 抛 AllModelsSkippedError（报错退出）。"""
    monkeypatch.delenv("QUANT_ASST_LLM_MOCK", raising=False)
    _clear_llm_keys(monkeypatch)
    s = _mock_settings(tmp_path)

    with pytest.raises(AllModelsSkippedError):
        run_model_comparison(
            s, ["deepseek/deepseek-chat", "openai/gpt-4o-mini"],
            "双均线策略", "cn:600519", "cn_stock", mock_mode=False,
        )


def test_run_requires_at_least_one_model(tmp_path: Path):
    with pytest.raises(ValueError):
        run_model_comparison(
            _mock_settings(tmp_path), [], "双均线", "cn:600519", "cn_stock", mock_mode=True
        )


def test_mock_multi_model_deterministic(monkeypatch, tmp_path: Path):
    """mock 下同一输入两次运行，渲染报告逐字一致（耗时恒 0.0、usage 确定性估算）。"""
    monkeypatch.setenv("QUANT_ASST_LLM_MOCK", "1")
    s = _mock_settings(tmp_path)
    kwargs = dict(
        user_input="双均线策略", symbol="cn:600519", market="cn_stock",
        rounds=2, mock_mode=True,
    )
    c1 = run_model_comparison(s, ["deepseek/deepseek-chat", "openai/gpt-4o-mini"], **kwargs)
    c2 = run_model_comparison(s, ["deepseek/deepseek-chat", "openai/gpt-4o-mini"], **kwargs)
    assert c1.run_id == c2.run_id
    md1 = render_comparison_markdown(c1, "zh")
    md2 = render_comparison_markdown(c2, "zh")
    assert md1 == md2
    # mock 下耗时恒 0.0（确定性）
    assert all(m.elapsed_seconds == 0.0 for m in c1.ok_models)


# ---------------------------------------------------------------------------
# report.comparison：对比报告结构与双语键
# ---------------------------------------------------------------------------


def _mk_ok(model: str, decision: str, risk: str, allowed: bool = True) -> ModelRunResult:
    gate = {"trade_suggestion_allowed": allowed}
    fr = {"final_decision": decision, "overall_risk_level": risk,
          "credibility_score": 60, "risk_gate": gate}
    return ModelRunResult(model=model, status="ok", final_report=fr,
                          usage={"prompt_tokens": 10, "completion_tokens": 5, "calls": 3})


def _mk_skipped(model: str, reason: str) -> ModelRunResult:
    return ModelRunResult(model=model, status="skipped", reason=reason)


def _comparison(per_model) -> ComparisonResult:
    return ComparisonResult(
        run_id="cmp-test", symbol="cn:600519", market="cn_stock",
        user_input="双均线策略", rounds=2,
        models=[m.model for m in per_model], mode="mock",
        per_model=list(per_model),
    )


def test_report_structure_and_disagreement():
    """对比报告结构：标题 / 对比表 / 跳过 / 一致 / 分歧节齐全（分歧单独列出）。"""
    comp = _comparison([
        _mk_ok("model-a", "revise", "medium"),
        _mk_ok("model-b", "blocked", "critical", allowed=False),
        _mk_skipped("model-c", "OPENAI_API_KEY 未配置"),
    ])
    md = render_comparison_markdown(comp, "zh")
    assert "# 多模型辩论对比报告：cn:600519" in md
    assert "## 各模型裁决 / 风险 / 建议 对比（3 模型）" in md
    assert "## 跳过的模型（1 个）" in md
    assert "model-c" in md and "OPENAI_API_KEY 未配置" in md
    assert "## 结论一致与分歧汇总" in md
    # 决策维度分歧（revise vs blocked）
    assert "分歧" in md and "最终决策" in md
    # 一致性说明：不做加权仲裁
    assert "不做加权仲裁" in md
    # 各模型取值并列
    assert "model-a" in md and "model-b" in md


def test_report_all_consistent_no_disagreement():
    """各模型取值一致时，分歧节标注「未出现分歧」。"""
    comp = _comparison([
        _mk_ok("model-a", "revise", "medium"),
        _mk_ok("model-b", "revise", "medium"),
    ])
    md = render_comparison_markdown(comp, "zh")
    assert "未出现分歧" in md
    assert "一致" in md


def test_report_all_skipped_placeholder():
    """全部模型跳过时，对比表给出占位说明。"""
    comp = _comparison([
        _mk_skipped("model-a", "r1"),
        _mk_skipped("model-b", "r2"),
    ])
    md = render_comparison_markdown(comp, "zh")
    assert "全部模型被跳过" in md


def test_report_bilingual_key_coverage():
    """38 个 cmp.* 键在 zh/en 目录均存在且非空（Step K 键集合一致性守护）。"""
    cmp_keys = [k for k in MESSAGES_ZH if k.startswith("cmp.")]
    assert len(cmp_keys) == 38, f"cmp 键数量 {len(cmp_keys)} != 38"
    for key in cmp_keys:
        assert key in MESSAGES_EN, f"{key} 缺失英文"
        assert MESSAGES_ZH[key].strip() and MESSAGES_EN[key].strip(), f"{key} 为空"


def test_report_language_switching():
    """同一对比结果，zh/en 渲染随语言切换（关键节标题不同）。"""
    comp = _comparison([_mk_ok("model-a", "revise", "medium"), _mk_ok("model-b", "blocked", "critical")])
    zh = render_comparison_markdown(comp, "zh")
    en = render_comparison_markdown(comp, "en")
    assert "多模型辩论对比报告" in zh
    assert "Multi-Model Debate Comparison Report" in en
    assert "Conclusion" not in en or "Agreement and Disagreement Summary" in en


def test_write_comparison_report_persists(
    monkeypatch, tmp_path: Path
):
    """对比报告落盘到 output/comparison/<run_id>/comparison.md（文件名无时间戳，确定性）。"""
    monkeypatch.setenv("QUANT_ASST_LLM_MOCK", "1")
    s = _mock_settings(tmp_path)
    out = tmp_path / "out"
    comp = run_model_comparison(
        s, ["deepseek/deepseek-chat", "openai/gpt-4o-mini"],
        "双均线策略", "cn:600519", "cn_stock", rounds=2, mock_mode=True,
    )
    path = write_comparison_report(comp, out, "zh")
    p = Path(path)
    assert p.exists()
    assert p.parent.name == comp.run_id
    assert p.parent.parent.name == "comparison"
    content = p.read_text(encoding="utf-8")
    assert "# 多模型辩论对比报告" in content
