import type {
  AnalysisCreateRequest,
  AnalysisStatusResponse,
  ReportFormat,
} from '@/types/api'

const DEFAULT_BASE = 'http://localhost:8000'

/** 健康检查超时：真实模式前置探测的等待上限 */
export const HEALTH_TIMEOUT_MS = 2000

/** 业务请求超时：后端可达但响应慢时不应误判为不可达 */
export const REQUEST_TIMEOUT_MS = 30_000

/** 后端地址：默认本地 8000，可用 VITE_API_BASE 覆盖 */
export function apiBase(): string {
  // 测试环境（rolldown 打包）没有 import.meta.env，回落到默认地址
  const raw = (import.meta.env ?? {}).VITE_API_BASE
  return typeof raw === 'string' && raw.trim() ? raw.replace(/\/+$/, '') : DEFAULT_BASE
}

/**
 * 失败分类：渲染层据此选择文案，同时保留原始原因供排查。
 * - offline  连续两次探测不可达 / 探测超时（多为后端未启动）
 * - network  请求直接失败（浏览器网络错误，如 Failed to fetch / Load failed）
 * - http     后端有响应但状态码非 2xx
 * - task     后端报告任务本身执行失败
 */
export type FailureKind = 'offline' | 'network' | 'http' | 'task'

export interface RequestFailure {
  kind: FailureKind
  /** 具体原因（HTTP 状态、响应体或浏览器原始错误文案），原样展示不做美化 */
  detail: string
}

export class ApiRequestError extends Error {
  readonly kind: FailureKind
  readonly detail: string

  constructor(kind: FailureKind, detail: string) {
    super(detail)
    this.name = 'ApiRequestError'
    this.kind = kind
    this.detail = detail
  }
}

function describe(err: unknown): string {
  if (err instanceof Error) {
    // AbortController 触发的中断带 name='AbortError'
    if (err.name === 'AbortError') return 'request timed out'
    return err.message || err.name
  }
  return String(err)
}

/** 带超时的 fetch：超时归为 offline，其余网络异常归为 network。导出以便单测覆盖超时分支。 */
export async function fetchWithTimeout(
  url: string,
  init: RequestInit | undefined,
  fetchImpl: typeof fetch,
  timeoutMs: number,
): Promise<Response> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  try {
    return await fetchImpl(url, { ...init, signal: controller.signal })
  } catch (err) {
    if (err instanceof Error && err.name === 'AbortError') {
      throw new ApiRequestError('offline', `request timed out after ${timeoutMs}ms`)
    }
    throw new ApiRequestError('network', describe(err))
  } finally {
    clearTimeout(timer)
  }
}

/**
 * 探测后端是否可达（GET /api/health，默认 2s 超时）。
 * 任何异常都返回 false，不抛出——调用方只需知道「能不能用」。
 */
export async function checkHealth(
  fetchImpl: typeof fetch = fetch,
  timeoutMs: number = HEALTH_TIMEOUT_MS,
): Promise<boolean> {
  try {
    const res = await fetchWithTimeout(`${apiBase()}/api/health`, undefined, fetchImpl, timeoutMs)
    return res.ok
  } catch {
    return false
  }
}

/** 把任意异常折算成可展示的失败结构（未知异常按网络错误处理，保守归类）。 */
export function toRequestFailure(err: unknown): RequestFailure {
  if (err instanceof ApiRequestError) return { kind: err.kind, detail: err.detail }
  return { kind: 'network', detail: err instanceof Error ? err.message : String(err) }
}

async function errorMessage(res: Response): Promise<string> {
  try {
    const body: unknown = await res.json()
    if (typeof body === 'object' && body !== null) {
      const detail = (body as { detail?: unknown }).detail
      if (typeof detail === 'string') return detail
    }
  } catch {
    // 非 JSON 响应时退回状态码文案
  }
  return `HTTP ${res.status}`
}

/** POST /api/analyses —— 创建任务并后台执行 */
export async function createAnalysis(
  input: AnalysisCreateRequest,
): Promise<AnalysisStatusResponse> {
  const res = await fetchWithTimeout(
    `${apiBase()}/api/analyses`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(input),
    },
    fetch,
    REQUEST_TIMEOUT_MS,
  )
  if (!res.ok) throw new ApiRequestError('http', await errorMessage(res))
  return (await res.json()) as AnalysisStatusResponse
}

/** GET /api/analyses/{id} —— 轮询任务状态与阶段产物 */
export async function fetchAnalysis(id: string): Promise<AnalysisStatusResponse> {
  const res = await fetchWithTimeout(
    `${apiBase()}/api/analyses/${encodeURIComponent(id)}`,
    undefined,
    fetch,
    REQUEST_TIMEOUT_MS,
  )
  if (!res.ok) throw new ApiRequestError('http', await errorMessage(res))
  return (await res.json()) as AnalysisStatusResponse
}

/** 报告直链（浏览器可打开，CORS 已由后端放行） */
export function reportUrl(id: string, format: ReportFormat): string {
  return `${apiBase()}/api/analyses/${encodeURIComponent(id)}/report?format=${format}`
}

/** GET /api/analyses/{id}/report —— 取报告正文 */
export async function fetchReport(id: string, format: ReportFormat): Promise<string> {
  const res = await fetchWithTimeout(reportUrl(id, format), undefined, fetch, REQUEST_TIMEOUT_MS)
  if (!res.ok) throw new ApiRequestError('http', await errorMessage(res))
  return res.text()
}
