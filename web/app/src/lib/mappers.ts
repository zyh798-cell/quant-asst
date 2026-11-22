/**
 * 后端阶段产物 -> 前端业务类型的归一映射。
 * 后端字段口径见 core/schemas.py；此处只做形状转换，不新增业务结论。
 */

import type {
  AuditBrief,
  BacktestResult,
  DebateBrief,
  Decision,
  EquityPoint,
  FinalBrief,
  RiskLevel,
  Trade,
} from '@/types'
import type { StageArtifact } from '@/types/api'

type Dict = Record<string, unknown>

function dict(value: unknown): Dict {
  return typeof value === 'object' && value !== null ? (value as Dict) : {}
}

function array(value: unknown): unknown[] {
  return Array.isArray(value) ? value : []
}

function number(value: unknown, fallback = 0): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback
}

function text(value: unknown, fallback = ''): string {
  return typeof value === 'string' ? value : fallback
}

interface BacktestMetricsDto {
  total_return: number
  annual_return: number | null
  max_drawdown: number
  sharpe: number | null
  win_rate: number | null
  n_trades: number
  n_days: number
}

interface BacktestDto {
  symbol: string
  market: string
  period_start: string
  period_end: string
  overall: BacktestMetricsDto
  equity_curve: { dates?: string[]; nav?: number[] }
  trades: Trade[]
}

/** 回测阶段产物 -> 前端 BacktestResult（后端数据，sample=false） */
export function toBacktest(data: Dict): BacktestResult {
  const dto = data as unknown as BacktestDto
  const overall = dto.overall ?? ({} as BacktestMetricsDto)
  const dates = Array.isArray(dto.equity_curve?.dates) ? dto.equity_curve.dates : []
  const navs = Array.isArray(dto.equity_curve?.nav) ? dto.equity_curve.nav : []

  let peak = 1
  const equity: EquityPoint[] = dates.map((date, index) => {
    const nav = number(navs[index], 1)
    peak = Math.max(peak, nav)
    return { date, nav, drawdown: (nav - peak) / peak }
  })

  const trades: Trade[] = array(dto.trades).map((item) => {
    const row = dict(item)
    const side = text(row.side) === 'sell' ? 'sell' : 'buy'
    return {
      date: text(row.date),
      side,
      price: number(row.price),
      shares: number(row.shares),
      amount: number(row.amount),
      pnl: typeof row.pnl === 'number' ? row.pnl : null,
    }
  })

  // 盈亏比后端未直接给出，按卖出笔的已实现盈亏汇总（口径与样例数据一致）
  const sells = trades.filter((t) => t.side === 'sell')
  const winSum = sells.reduce((acc, t) => acc + Math.max(t.pnl ?? 0, 0), 0)
  const lossSum = sells.reduce((acc, t) => acc + Math.max(-(t.pnl ?? 0), 0), 0)

  return {
    symbol: text(dto.symbol),
    market: text(dto.market),
    period_start: text(dto.period_start),
    period_end: text(dto.period_end),
    metrics: {
      total_return: number(overall.total_return),
      annual_return: typeof overall.annual_return === 'number' ? overall.annual_return : null,
      max_drawdown: number(overall.max_drawdown),
      sharpe: typeof overall.sharpe === 'number' ? overall.sharpe : null,
      win_rate: typeof overall.win_rate === 'number' ? overall.win_rate : null,
      profit_factor: lossSum > 0 ? winSum / lossSum : null,
      n_trades: number(overall.n_trades),
      n_days: number(overall.n_days),
    },
    equity,
    trades,
    sample: false,
  }
}

interface DebateDto {
  rounds: number
  verdict: {
    credibility_score: number
    decision: Decision
    consensus: string[]
    disagreements: string[]
    rationale: string
  }
  bull_final: { points?: { claim: string }[] }
  bear_final: { points?: { claim: string }[] }
  risk_checks: { findings?: { issue: string }[] }[]
}

/** 辩论阶段产物 -> 前端 DebateBrief */
export function toDebate(data: Dict): DebateBrief {
  const dto = data as unknown as DebateDto
  const verdict = dto.verdict ?? ({} as DebateDto['verdict'])
  return {
    credibility_score: number(verdict.credibility_score),
    decision: verdict.decision ?? 'revise',
    consensus: array(verdict.consensus).map((v) => text(v)),
    disagreements: array(verdict.disagreements).map((v) => text(v)),
    bull_points: array(dto.bull_final?.points).map((v) => text(dict(v).claim)),
    bear_points: array(dto.bear_final?.points).map((v) => text(dict(v).claim)),
    risk_findings: array(dto.risk_checks).flatMap((check) =>
      array(dict(check).findings).map((f) => text(dict(f).issue)),
    ),
    rationale: text(verdict.rationale),
  }
}

interface AuditDto {
  overall_risk_level: RiskLevel
  risk_grade_label: string
  tradability: 'allowed' | 'restricted' | 'prohibited'
  findings: { category: string; title: string; severity: RiskLevel; recommendation: string }[]
}

/** 审计阶段产物 -> 前端 AuditBrief */
export function toAudit(data: Dict): AuditBrief {
  const dto = data as unknown as AuditDto
  const level = text(dto.overall_risk_level) as RiskLevel
  const tradability = text(dto.tradability) as AuditDto['tradability']
  return {
    overall_risk_level: ['low', 'medium', 'high', 'critical'].includes(level)
      ? level
      : 'low',
    risk_grade_label: text(dto.risk_grade_label),
    tradability: ['allowed', 'restricted', 'prohibited'].includes(tradability)
      ? tradability
      : 'restricted',
    findings: array(dto.findings).map((item) => {
      const row = dict(item)
      const severity = text(row.severity) as RiskLevel
      return {
        category: text(row.category),
        title: text(row.title),
        severity: ['low', 'medium', 'high', 'critical'].includes(severity)
          ? severity
          : 'low',
        recommendation: text(row.recommendation),
      }
    }),
  }
}

interface RiskDto {
  risk_gate: { risk_level: string; trade_suggestion_allowed: boolean }
  final_report: {
    final_decision: Decision
    credibility_score: number
    overall_risk_level: RiskLevel
    risk_banner: string
    trade_advisory: string
    executive_summary: string
  }
}

/** 风控阶段产物 -> 前端 FinalBrief */
export function toFinal(data: Dict): FinalBrief | null {
  const dto = data as unknown as RiskDto
  const report = dto.final_report
  if (!report) return null
  const decision = text(report.final_decision) as Decision
  const level = text(report.overall_risk_level) as RiskLevel
  return {
    final_decision: ['adopt', 'revise', 'reject', 'blocked'].includes(decision)
      ? decision
      : 'revise',
    credibility_score: number(report.credibility_score),
    overall_risk_level: ['low', 'medium', 'high', 'critical'].includes(level)
      ? level
      : 'low',
    risk_banner: text(report.risk_banner),
    trade_advisory: text(report.trade_advisory),
    executive_summary: text(report.executive_summary),
  }
}

/** 取指定阶段的产物字典（未产出时返回空字典） */
export function stageData(
  stages: StageArtifact[],
  id: StageArtifact['stage'],
): Dict {
  const found = stages.find((s) => s.stage === id)
  return found && typeof found.data === 'object' && found.data !== null
    ? (found.data as Dict)
    : {}
}
