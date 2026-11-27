/**
 * 零依赖的极小断言库。测试入口由 `npm run test:unit` 用 rolldown 打成单文件后执行，
 * 不引入 vitest / playwright，保持 web/app 依赖树轻量。
 */

let passed = 0
let failed = 0
const failures: string[] = []

export function assert(condition: unknown, message?: string): asserts condition {
  if (!condition) {
    throw new Error(message || 'assertion failed')
  }
}

export function assertEquals<T>(actual: T, expected: T, message?: string): void {
  if (actual !== expected) {
    throw new Error(
      message ?? `expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`,
    )
  }
}

export function assertIncludes(haystack: string, needle: string, message?: string): void {
  if (!haystack.includes(needle)) {
    throw new Error(
      message ??
        `expected ${JSON.stringify(haystack)} to include ${JSON.stringify(needle)}`,
    )
  }
}

export interface TestSummary {
  passed: number
  failed: number
}

/** 打印汇总并返回结果，由运行脚本决定退出码。 */
export function reportSummary(): TestSummary {
  console.log(`\n${passed} passed, ${failed} failed`)
  if (failed > 0) {
    console.log('\nFailures:')
    for (const f of failures) console.log(` - ${f}`)
  }
  return { passed, failed }
}

/** 异步用例：返回 Promise，由调用方 await（测试入口使用顶层 await）。 */
export async function testAsync(name: string, fn: () => void | Promise<void>): Promise<void> {
  try {
    await fn()
    passed += 1
    console.log(`  ok   ${name}`)
  } catch (err) {
    failed += 1
    const message = err instanceof Error ? err.message : String(err)
    failures.push(`${name}: ${message}`)
    console.log(`  FAIL ${name}\n       ${message}`)
  }
}

export function test(name: string, fn: () => void): void {
  try {
    fn()
    passed += 1
    console.log(`  ok   ${name}`)
  } catch (err) {
    failed += 1
    const message = err instanceof Error ? err.message : String(err)
    failures.push(`${name}: ${message}`)
    console.log(`  FAIL ${name}\n       ${message}`)
  }
}
