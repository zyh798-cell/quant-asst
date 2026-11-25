/**
 * i18n 语言切换测试：持久化、首次跟随浏览器语言、字典完整性。
 * 运行：npm run test:unit（rolldown 打包后交给 Node 执行）
 */
import { assertEquals, assertIncludes, reportSummary, test } from '../testkit'
import {
  DICTS,
  LANG_STORAGE_KEY,
  decisionLabel,
  interpolate,
  riskLabel,
} from '../dict'
import { createI18nController, detectBrowserLang } from '../index'
import { makeMemoryStorage } from '../lang'

test('zh / en 字典键集合完全一致', () => {
  const zhKeys = Object.keys(DICTS.zh).sort()
  const enKeys = Object.keys(DICTS.en).sort()
  assertEquals(zhKeys.length, enKeys.length, '字典条目数不一致')
  assertEquals(JSON.stringify(zhKeys), JSON.stringify(enKeys), 'zh / en 键集合不一致')
})

test('首次访问跟随 navigator.language（zh 开头判为中文）', () => {
  assertEquals(detectBrowserLang({ language: 'zh-CN' }), 'zh')
  assertEquals(detectBrowserLang({ language: 'zh' }), 'zh')
  assertEquals(detectBrowserLang({ language: 'en-US' }), 'en')
  assertEquals(detectBrowserLang({ language: '' }), 'en')
})

test('无持久化时按浏览器语言初始化，且不写存储', () => {
  const storage = makeMemoryStorage()
  const ctrl = createI18nController({ storage, navigator: { language: 'zh-CN' } })
  assertEquals(ctrl.lang, 'zh')
  assertEquals(storage.getItem(LANG_STORAGE_KEY), null, '初始化不应写存储')
})

test('切换语言即时生效并持久化到 localStorage', () => {
  const storage = makeMemoryStorage()
  const ctrl = createI18nController({ storage, navigator: { language: 'en-US' } })

  assertEquals(ctrl.switch('zh'), 'zh')
  assertEquals(ctrl.lang, 'zh')
  assertEquals(storage.getItem(LANG_STORAGE_KEY), 'zh')
  assertEquals(ctrl.dict().navCapability, '能力')

  ctrl.toggle()
  assertEquals(ctrl.lang, 'en')
  assertEquals(storage.getItem(LANG_STORAGE_KEY), 'en')
  assertEquals(ctrl.dict().navCapability, 'Capabilities')
})

test('重建控制器时读取已保存语言（优先于浏览器语言）', () => {
  const storage = makeMemoryStorage({ [LANG_STORAGE_KEY]: 'en' })
  const ctrl = createI18nController({ storage, navigator: { language: 'zh-CN' } })
  assertEquals(ctrl.lang, 'en')
  assertIncludes(ctrl.dict().heroTitle, 'Multi-agent')
})

test('无效持久化值被忽略并回落到浏览器语言', () => {
  const storage = makeMemoryStorage({ [LANG_STORAGE_KEY]: 'fr' })
  const ctrl = createI18nController({ storage, navigator: { language: 'zh-CN' } })
  assertEquals(ctrl.lang, 'zh')
})

test('存储读写异常不影响渲染（隐私模式降级）', () => {
  const brokenStorage = {
    getItem: () => {
      throw new Error('SecurityError')
    },
    setItem: () => {
      throw new Error('SecurityError')
    },
  }
  const ctrl = createI18nController({ storage: brokenStorage, navigator: { language: 'zh-CN' } })
  assertEquals(ctrl.lang, 'zh')
  assertEquals(ctrl.switch('en'), 'en')
  assertEquals(ctrl.lang, 'en')
})

test('插值替换占位符，缺失键保留原占位符', () => {
  assertEquals(
    interpolate('回测完成：{n} 笔成交，{d} 个交易日', { n: 12, d: 30 }),
    '回测完成：12 笔成交，30 个交易日',
  )
  assertEquals(interpolate('{a}-{b}', { a: 'x' }), 'x-{b}')
})

test('风险级别与决策映射到当前语言', () => {
  assertEquals(riskLabel(DICTS.zh, 'critical'), '致命')
  assertEquals(riskLabel(DICTS.en, 'critical'), 'Critical')
  assertEquals(riskLabel(DICTS.en, 'unknown'), 'unknown')
  assertEquals(decisionLabel(DICTS.zh, 'blocked'), '阻断')
  assertEquals(decisionLabel(DICTS.en, 'revise'), 'Revise')
})

const result = reportSummary()
declare const process: { exitCode: number }
if (result.failed > 0) process.exitCode = 1
