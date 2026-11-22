/**
 * 后端接口层 DTO（与 server/schemas.py 一一对应）。
 * 阶段产物 data 为弱类型字典，由 store/mappers 归一为本仓业务类型。
 */

export type StageId = 'parse' | 'backtest' | 'debate' | 'audit' | 'risk' | 'report'
export type AnalysisStatus =
  | 'pending'
  | 'running'
  | 'stage_done'
  | 'failed'
  | 'completed'
export type StageStatus = 'pending' | 'running' | 'done' | 'failed' | 'skipped'
export type RunMode = 'mock' | 'real'
export type SandboxMode = 'local' | 'docker'
export type ReportFormat = 'md' | 'html'

/** POST /api/analyses 请求体 */
export interface AnalysisCreateRequest {
  strategy: string
  symbol: string
  market: string
  period_start: string
  period_end: string
  mode: RunMode
  sandbox: SandboxMode
  debate_rounds: number
  risk_threshold: string
  initial_capital: number
}

/** 单阶段产物（结构化输出 + 进度元数据） */
export interface StageArtifact {
  stage: StageId
  status: StageStatus
  started_at: string | null
  finished_at: string | null
  summary: string
  data: Record<string, unknown>
}

/** 报告引用 */
export interface ReportRef {
  markdown_path: string | null
  html_path: string | null
  json_path: string | null
  available_formats: ReportFormat[]
}

/** 请求回显（不含任何密钥） */
export interface AnalysisRequestEcho {
  strategy: string
  symbol: string
  market: string
  period_start: string
  period_end: string
  mode: RunMode
  sandbox: SandboxMode
  debate_rounds: number
  risk_threshold: string
  initial_capital: number
}

/** GET /api/analyses/{id} 响应 */
export interface AnalysisStatusResponse {
  id: string
  status: AnalysisStatus
  mode: RunMode
  sandbox: SandboxMode
  created_at: string
  updated_at: string
  current_stage: StageId | null
  stages: StageArtifact[]
  error: string | null
  notice: string | null
  report: ReportRef | null
  request: AnalysisRequestEcho | null
}
