/**
 * 前端类型：与后端 Pydantic 模型（core/schemas.py）字段对齐。
 * 后端接口层返回的 JSON 直接对应这些类型，不在此重复定义业务口径。
 */

export interface BacktestMetrics {
  total_return: number
  annual_return: number | null
  max_drawdown: number
  sharpe: number | null
  win_rate: number | null
  /** 盈亏比（盈利总额 / 亏损总额），后端未提供时为 null */
  profit_factor: number | null
  n_trades: number
  n_days: number
}

export interface EquityPoint {
  date: string
  nav: number
  drawdown: number
}

export interface Trade {
  date: string
  side: 'buy' | 'sell'
  price: number
  shares: number
  amount: number
  pnl: number | null
}

export interface BacktestResult {
  symbol: string
  market: string
  period_start: string
  period_end: string
  metrics: BacktestMetrics
  equity: EquityPoint[]
  trades: Trade[]
  /** 样例数据须可识别（GUIDELINES.md 1.6） */
  sample: boolean
}

export type RiskLevel = 'low' | 'medium' | 'high' | 'critical'
export type Decision = 'adopt' | 'revise' | 'reject' | 'blocked'

export interface AuditFinding {
  category: string
  title: string
  severity: RiskLevel
  recommendation: string
}

export interface AuditBrief {
  overall_risk_level: RiskLevel
  risk_grade_label: string
  findings: AuditFinding[]
  tradability: 'allowed' | 'restricted' | 'prohibited'
}

export interface DebateBrief {
  credibility_score: number
  decision: Decision
  consensus: string[]
  disagreements: string[]
  bull_points: string[]
  bear_points: string[]
  risk_findings: string[]
  rationale: string
}

export interface ReportBrief {
  markdown: string
  html_url: string | null
}

/** 阶段标识与状态由接口层 DTO 统一给出（server/schemas.py） */
import type { StageId, StageStatus } from '@/types/api'

export type { StageId, StageStatus } from '@/types/api'

/**
 * 前端视图阶段的展示文案：store 保存结构化摘要，标签与插值在渲染层完成，
 * 以便切换语言时不重建状态。
 */
export interface Stage {
  id: StageId
  label?: string
  status: StageStatus
  summary?: string
  summaryKey?: SummaryKey
  summaryVars?: Record<string, string | number>
}

export type SummaryKey =
  | 'parse'
  | 'backtest'
  | 'backtestFallback'
  | 'debate'
  | 'debateFallback'
  | 'audit'
  | 'auditFallback'
  | 'risk'
  | 'riskFallback'
  | 'report'

/** 风控综合结论（server 阶段 risk 的 final_report 子集） */
export interface FinalBrief {
  final_decision: Decision
  credibility_score: number
  overall_risk_level: RiskLevel
  risk_banner: string
  trade_advisory: string
  executive_summary: string
}

export interface RunConfig {
  strategy: string
  symbol: string
  market: string
  periodStart: string
  periodEnd: string
  initialCapital: number
  mock: boolean
}
