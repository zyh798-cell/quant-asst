/**
 * API 层失败分类测试：健康检查不可达、超时归类、网络异常与响应体原因。
 * 运行：npm run test:unit（rolldown 打包后交给 Node 执行）
 */
import {
  assertEquals,
  assertIncludes,
  reportSummary,
  testAsync,
} from '@/i18n/testkit'
import {
  ApiRequestError,
  checkHealth,
  fetchWithTimeout,
  toRequestFailure,
  type FailureKind,
} from '../api'

/** 拒绝的 mock fetch：模拟后端未启动时浏览器的 Load failed / Failed to fetch。 */
function rejectingFetch(): typeof fetch {
  return (() => Promise.reject(new TypeError('Load failed'))) as unknown as typeof fetch
}

/** 立即可达的 mock fetch，返回最小 Response 形状。 */
function okFetch(ok: boolean, body?: unknown): typeof fetch {
  return (() =>
    Promise.resolve({
      ok,
      status: ok ? 200 : 500,
      json: () => Promise.resolve(body),
    }) as unknown as Response) as unknown as typeof fetch
}

await testAsync('健康检查在 fetch 拒绝时返回 false（不抛出）', async () => {
  const reachable = await checkHealth(rejectingFetch(), 50)
  assertEquals(reachable, false, '后端不可达应判定为 false')
})

await testAsync('健康检查在后端可达时返回 true', async () => {
  assertEquals(await checkHealth(okFetch(true), 50), true)
})

await testAsync('健康检查在非 2xx 响应时返回 false', async () => {
  assertEquals(await checkHealth(okFetch(false), 50), false)
})

await testAsync('fetchWithTimeout 把超时归类为 offline', async () => {
  // 挂起的 fetch：只在 signal abort 时以 AbortError 拒绝，验证超时分支
  const hanging = ((_url: string, init?: RequestInit) =>
    new Promise((_resolve, reject) => {
      init?.signal?.addEventListener('abort', () => {
        reject(Object.assign(new Error('aborted'), { name: 'AbortError' }))
      })
    })) as unknown as typeof fetch

  let caught: unknown
  try {
    await fetchWithTimeout('http://x/api/health', undefined, hanging, 5)
  } catch (err) {
    caught = err
  }
  if (!(caught instanceof ApiRequestError)) throw new Error('应抛出 ApiRequestError')
  const kind: FailureKind = caught.kind
  assertEquals(kind, 'offline', '超时应归类为 offline')
  assertIncludes(caught.detail, 'timed out')
})

await testAsync('fetchWithTimeout 把直接失败归类为 network 并保留原文案', async () => {
  let caught: unknown
  try {
    await fetchWithTimeout('http://x/api/health', undefined, rejectingFetch(), 50)
  } catch (err) {
    caught = err
  }
  if (!(caught instanceof ApiRequestError)) throw new Error('应抛出 ApiRequestError')
  assertEquals(caught.kind, 'network')
  assertIncludes(caught.detail, 'Load failed')
})

await testAsync('toRequestFailure 保留已知分类，未知异常保守归为 network', () => {
  const known = toRequestFailure(new ApiRequestError('http', 'symbol not found'))
  assertEquals(known.kind, 'http')
  assertEquals(known.detail, 'symbol not found')

  const unknown = toRequestFailure(new Error('unexpected'))
  assertEquals(unknown.kind, 'network')
  assertEquals(unknown.detail, 'unexpected')
})

const result = reportSummary()
declare const process: { exitCode: number }
if (result.failed > 0) process.exitCode = 1
