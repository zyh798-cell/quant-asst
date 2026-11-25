import { create } from 'zustand'

import { createAnalysis, fetchAnalysis, fetchReport, reportUrl } from '@/lib/api'
import { stageData, toAudit, toBacktest, toDebate, toFinal } from '@/lib/mappers'
import {
  buildMockAudit,
  buildMockBacktest,
  buildMockDebate,
  buildMockReport,
} from '@/mocks/backtest'
import type {
  AuditBrief,
  BacktestResult,
  DebateBrief,
  FinalBrief,
  ReportBrief,
  RunConfig,
  Stage,
  StageId,
  SummaryKey,
} from '@/types'
import type { AnalysisStatusResponse, StageStatus } from '@/types/api'

/**
 * 阶段定义只保留标识与时长；标签与摘要文案由语言字典在渲染层提供，
 * 这样切换语言时无需重建 store 状态。
 */
const STAGE_DEFS: ReadonlyArray<{ id: StageId; duration: number }> = [
  { id: 'parse', duration: 520 },
  { id: 'backtest', duration: 820 },
  { id: 'debate', duration: 900 },
  { id: 'audit', duration: 720 },
  { id: 'risk', duration: 420 },
  { id: 'report', duration: 520 },
]

const INITIAL_STAGES: Stage[] = STAGE_DEFS.map((d) => ({
  id: d.id,
  status: 'pending',
}))

/**
 * 浏览器本地时区的 YYYY-MM-DD（与 <input type="date"> 一致）。
 * 不用 toISOString()：那是 UTC，东八区 08:00 前会取到前一天。
 */
function localDateISO(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

/** 默认回测窗口：结束日 = 当天，开始日 = 7 天前（浏览器本地时区）。 */
function defaultDates(): { periodStart: string; periodEnd: string } {
  const end = new Date()
  const start = new Date(end)
  start.setDate(end.getDate() - 7)
  return { periodStart: localDateISO(start), periodEnd: localDateISO(end) }
}

function makeDefaultConfig(): RunConfig {
  return {
    strategy: '双均线策略，5 日线上穿 20 日线买入，死叉卖出',
    symbol: 'cn:600519',
    market: 'cn_stock',
    ...defaultDates(),
    // 与后端默认一致：A 股一手 100 股，茅台约 15 万元/手，10 万资金会因买不起一手而零成交
    initialCapital: 1_000_000,
    mock: true,
  }
}

const DEFAULT_CONFIG: RunConfig = makeDefaultConfig()

type Phase = 'idle' | 'running' | 'done' | 'failed'
type Backend = 'local' | 'remote'

interface StudioState {
  config: RunConfig
  stages: Stage[]
  phase: Phase
  error: string | null
  backend: Backend
  taskId: string | null
  notice: string | null
  result: BacktestResult | null
  debate: DebateBrief | null
  audit: AuditBrief | null
  final: FinalBrief | null
  report: ReportBrief | null
  setConfig: (patch: Partial<RunConfig>) => void
  run: () => Promise<void>
  reset: () => void
}

let runToken = 0
const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms))

/** 后端阶段状态 -> 前端展示态（skipped 当前不会出现，归入等待） */
function toUiStatus(status: StageStatus): StageStatus {
  return status === 'skipped' ? 'pending' : status
}

export const useStudioStore = create<StudioState>()((set, get) => {
  const patchStage = (id: StageId, patch: Partial<Stage>) => {
    set((s) => ({
      stages: s.stages.map((st) => (st.id === id ? { ...st, ...patch } : st)),
    }))
  }

  const resetResults = () =>
    set({
      stages: INITIAL_STAGES,
      error: null,
      result: null,
      debate: null,
      audit: null,
      final: null,
      report: null,
      taskId: null,
      notice: null,
    })

  /** 用后端快照增量更新阶段与产物（每阶段完成即渲染，不等全部结束） */
  const applySnapshot = (body: AnalysisStatusResponse) => {
    set((s) => {
      const stages = s.stages.map((st) => {
        const remote = body.stages.find((r) => r.stage === st.id)
        if (!remote) return st
        const status = toUiStatus(remote.status)
        // 已完成的阶段不回头（避免轮询乱序导致状态回退）
        if (st.status === 'done') return st
        return {
          ...st,
          status,
          summary: remote.summary || st.summary,
        }
      })

      const result =
        body.stages.find((r) => r.stage === 'backtest' && r.status === 'done') &&
        !s.result
          ? toBacktest(stageData(body.stages, 'backtest'))
          : s.result
      const debateReady = body.stages.some(
        (r) => r.stage === 'debate' && r.status === 'done',
      )
      const auditReady = body.stages.some((r) => r.stage === 'audit' && r.status === 'done')

      return {
        stages,
        result,
        debate: debateReady ? toDebate(stageData(body.stages, 'debate')) : s.debate,
        audit: auditReady ? toAudit(stageData(body.stages, 'audit')) : s.audit,
        final: body.status === 'completed'
          ? toFinal(stageData(body.stages, 'risk'))
          : s.final,
        notice: body.notice,
        report:
          body.status === 'completed' && body.report
            ? {
                markdown: '',
                html_url: body.report.available_formats.includes('html')
                  ? reportUrl(body.id, 'html')
                  : null,
              }
            : s.report,
      }
    })
  }

  /** 真实模式：创建任务 + 轮询 + 增量渲染 */
  const runRemote = async (token: number) => {
    const { config } = get()
    const alive = () => token === runToken

    set({ phase: 'running', backend: 'remote', error: null })
    const created = await createAnalysis({
      strategy: config.strategy,
      symbol: config.symbol,
      market: config.market,
      period_start: config.periodStart,
      period_end: config.periodEnd,
      mode: 'real',
      sandbox: 'local',
      debate_rounds: 3,
      risk_threshold: 'high',
      initial_capital: config.initialCapital,
    })
    if (!alive()) return
    set({ taskId: created.id, notice: created.notice, stages: INITIAL_STAGES })

    // 轮询：运行中每 1.5s 拉一次，阶段完成即增量渲染
    for (;;) {
      await sleep(1500)
      if (!alive()) return
      let body: AnalysisStatusResponse
      try {
        body = await fetchAnalysis(created.id)
      } catch (err) {
        if (!alive()) return
        throw err
      }
      if (!alive()) return
      applySnapshot(body)

      if (body.status === 'failed') {
        throw new Error(body.error || 'task failed')
      }
      if (body.status === 'completed') break
    }

    // 报告正文按需拉取（失败不阻断展示）
    try {
      const markdown = await fetchReport(created.id, 'md')
      if (!alive()) return
      const htmlUrl = get().report?.html_url ?? null
      set({ report: { markdown, html_url: htmlUrl } })
    } catch {
      if (!alive()) return
    }
    set({ phase: 'done' })
  }

  return {
    config: DEFAULT_CONFIG,
    stages: INITIAL_STAGES,
    phase: 'idle',
    error: null,
    backend: 'local',
    taskId: null,
    notice: null,
    result: null,
    debate: null,
    audit: null,
    final: null,
    report: null,

    setConfig: (patch) => set((s) => ({ config: { ...s.config, ...patch } })),

    run: async () => {
      const token = ++runToken
      const { config } = get()
      const alive = () => token === runToken

      resetResults()
      set({ phase: 'running', backend: 'local' })

      // 样例数据在本地确定性生成；真实模式交由 server/ 接口层（Step B）
      const result = config.mock ? buildMockBacktest(config) : null
      const debate = config.mock ? buildMockDebate() : null
      const audit = config.mock ? buildMockAudit() : null

      try {
        if (!config.mock) {
          await runRemote(token)
          return
        }

        for (const def of STAGE_DEFS) {
          if (!alive()) return
        patchStage(def.id, { status: 'running', summary: '' })
        await sleep(def.duration)
        if (!alive()) return
        const summary = summaryFor(def.id, result, debate, audit)
        patchStage(def.id, { status: 'done', ...summary })
        }

        set({
          phase: 'done',
          backend: 'local',
          result,
          debate,
          audit,
          report: result && debate && audit ? buildMockReport(result, debate, audit) : null,
        })
      } catch (err) {
        if (!alive()) return
        const message = err instanceof Error ? err.message : 'task execution failed'
        set({ phase: 'failed', error: message })
      }
    },

    reset: () => {
      runToken += 1
      // 恢复默认配置（含按当天重算的默认日期窗口），再清空结果
      set({ phase: 'idle', backend: 'local', config: makeDefaultConfig() })
      resetResults()
    },
  }
})

/**
 * 阶段摘要的结构化描述：渲染层按当前语言字典插值，避免 store 依赖语言状态。
 */
function summaryFor(
  id: StageId,
  result: BacktestResult | null,
  debate: DebateBrief | null,
  audit: AuditBrief | null,
): { summaryKey?: SummaryKey; summaryVars?: Record<string, string | number> } {
  switch (id) {
    case 'parse':
      return { summaryKey: 'parse' }
    case 'backtest':
      return result
        ? { summaryKey: 'backtest', summaryVars: { n: result.metrics.n_trades, d: result.metrics.n_days } }
        : { summaryKey: 'backtestFallback' }
    case 'debate':
      return debate
        ? {
            summaryKey: 'debate',
            summaryVars: { decision: debate.decision, score: debate.credibility_score },
          }
        : { summaryKey: 'debateFallback' }
    case 'audit':
      return audit
        ? {
            summaryKey: 'audit',
            summaryVars: { risk: audit.risk_grade_label, n: audit.findings.length },
          }
        : { summaryKey: 'auditFallback' }
    case 'risk':
      return { summaryKey: audit ? 'risk' : 'riskFallback' }
    case 'report':
      return { summaryKey: 'report' }
    default:
      return {}
  }
}
