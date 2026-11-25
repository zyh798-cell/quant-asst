import { LANG_STORAGE_KEY, LANGS, type Lang } from '@/i18n/dict'

/**
 * 语言解析与持久化：与 React 解耦的纯函数，便于直接测试。
 */

/** 读取浏览器首选语言：以 `zh` 开头即判为中文，其余一律英文。 */
export function detectBrowserLang(navigatorLike?: Pick<Navigator, 'language'>): Lang {
  const tag = ((navigatorLike ?? (typeof navigator !== 'undefined' ? navigator : undefined))?.language ?? '')
    .trim()
    .toLowerCase()
  return tag.startsWith('zh') ? 'zh' : 'en'
}

/** 读取持久化语言；无效值或未设置时返回 null，由调用方决定回退策略。 */
export function readStoredLang(storage: Pick<Storage, 'getItem'>): Lang | null {
  try {
    const raw = storage.getItem(LANG_STORAGE_KEY)
    return LANGS.includes(raw as Lang) ? (raw as Lang) : null
  } catch {
    // 隐私模式 / 禁用存储：静默降级为未设置，不影响渲染
    return null
  }
}

function syncDocumentLang(lang: Lang): void {
  if (typeof document !== 'undefined') {
    document.documentElement.lang = lang === 'zh' ? 'zh-CN' : 'en'
  }
}

export { LANG_STORAGE_KEY, LANGS, syncDocumentLang }

/** 存储替身：测试中作为 localStorage 的最小实现。 */
export function makeMemoryStorage(initial?: Record<string, string>) {
  const map = new Map(Object.entries(initial ?? {}))
  return {
    getItem: (key: string) => (map.has(key) ? map.get(key)! : null),
    setItem: (key: string, value: string) => void map.set(key, String(value)),
    removeItem: (key: string) => void map.delete(key),
    clear: () => map.clear(),
    _map: map,
  }
}
