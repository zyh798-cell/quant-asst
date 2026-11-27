/**
 * store 行为测试：mock / 真实模式切换与后端探测的联动。
 * 运行：npm run test:unit（rolldown 打包后交给 Node 执行）
 */
import { assertEquals, reportSummary, testAsync } from '@/i18n/testkit'
import { useStudioStore } from '../studio'

/** 拒绝的 mock fetch：模拟后端未启动。 */
function rejectingFetch(): typeof fetch {
  return (() => Promise.reject(new TypeError('Load failed'))) as unknown as typeof fetch
}

await testAsync('切到真实模式时探测后端，不可达则标记 backendReady=false', async () => {
  useStudioStore.setState((s) => ({ config: { ...s.config, mock: true }, backendReady: null }))
  const original = globalThis.fetch
  globalThis.fetch = rejectingFetch()
  try {
    await useStudioStore.getState().toggleMock()
  } finally {
    globalThis.fetch = original
  }
  assertEquals(useStudioStore.getState().config.mock, false, '应切到真实模式')
  assertEquals(
    useStudioStore.getState().backendReady,
    false,
    '后端不可达时应记录 backendReady=false',
  )
})

await testAsync('切回 mock 时清空探测结果', async () => {
  useStudioStore.setState((s) => ({ config: { ...s.config, mock: false }, backendReady: false }))
  await useStudioStore.getState().toggleMock()
  assertEquals(useStudioStore.getState().config.mock, true, '应切回 mock')
  assertEquals(useStudioStore.getState().backendReady, null, 'mock 模式下不应保留探测结果')
})

const result = reportSummary()
declare const process: { exitCode: number }
if (result.failed > 0) process.exitCode = 1
