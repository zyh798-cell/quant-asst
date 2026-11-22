import type {
  AnalysisCreateRequest,
  AnalysisStatusResponse,
  ReportFormat,
} from '@/types/api'

const DEFAULT_BASE = 'http://localhost:8000'

/** 后端地址：默认本地 8000，可用 VITE_API_BASE 覆盖 */
export function apiBase(): string {
  const raw = import.meta.env.VITE_API_BASE
  return typeof raw === 'string' && raw.trim() ? raw.replace(/\/+$/, '') : DEFAULT_BASE
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
  return `请求失败（HTTP ${res.status}）`
}

/** POST /api/analyses —— 创建任务并后台执行 */
export async function createAnalysis(
  input: AnalysisCreateRequest,
): Promise<AnalysisStatusResponse> {
  const res = await fetch(`${apiBase()}/api/analyses`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  })
  if (!res.ok) throw new Error(await errorMessage(res))
  return (await res.json()) as AnalysisStatusResponse
}

/** GET /api/analyses/{id} —— 轮询任务状态与阶段产物 */
export async function fetchAnalysis(id: string): Promise<AnalysisStatusResponse> {
  const res = await fetch(`${apiBase()}/api/analyses/${encodeURIComponent(id)}`)
  if (!res.ok) throw new Error(await errorMessage(res))
  return (await res.json()) as AnalysisStatusResponse
}

/** 报告直链（浏览器可打开，CORS 已由后端放行） */
export function reportUrl(id: string, format: ReportFormat): string {
  return `${apiBase()}/api/analyses/${encodeURIComponent(id)}/report?format=${format}`
}

/** GET /api/analyses/{id}/report —— 取报告正文 */
export async function fetchReport(id: string, format: ReportFormat): Promise<string> {
  const res = await fetch(reportUrl(id, format))
  if (!res.ok) throw new Error(await errorMessage(res))
  return res.text()
}
