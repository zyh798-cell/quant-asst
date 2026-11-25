import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'

import { DICTS, LANGS, type Dict, type Lang } from '@/i18n/dict'
import { LANG_STORAGE_KEY, detectBrowserLang, syncDocumentLang } from '@/i18n/lang'

export { detectBrowserLang, readStoredLang } from '@/i18n/lang'
export { LANG_STORAGE_KEY, LANGS } from '@/i18n/dict'
export type { Dict, Lang } from '@/i18n/dict'

export interface I18nController {
  readonly lang: Lang
  dict(): Dict
  switch(next: Lang): Lang
}

interface InternalI18nController extends I18nController {
  toggle(): Lang
}

export interface I18nDeps {
  storage?: Partial<Pick<Storage, 'getItem' | 'setItem'>>
  navigator?: Pick<Navigator, 'language'>
}

/** 测试替身允许抛出异常，这里统一吞掉以模拟隐私模式。 */
function safeGet(storage: Partial<Pick<Storage, 'getItem'>> | undefined): Lang | null {
  if (!storage?.getItem) return null
  try {
    const raw = storage.getItem(LANG_STORAGE_KEY)
    return LANGS.includes(raw as Lang) ? (raw as Lang) : null
  } catch {
    return null
  }
}

/**
 * 语言控制器（不依赖 React）：纯逻辑，便于测试直接驱动。
 * 默认参数读取全局 localStorage / navigator，测试可注入受控替身。
 */
export function createI18nController(deps: I18nDeps = {}): InternalI18nController {
  const storage = deps.storage ?? (typeof window !== 'undefined' ? window.localStorage : undefined)
  const nav = deps.navigator ?? (typeof navigator !== 'undefined' ? navigator : undefined)

  let current: Lang = safeGet(storage) ?? detectBrowserLang(nav)
  syncDocumentLang(current)

  return {
    get lang() {
      return current
    },
    dict() {
      return DICTS[current] ?? DICTS.zh
    },
    switch(next: Lang): Lang {
      current = next
      if (storage?.setItem) {
        try {
          storage.setItem(LANG_STORAGE_KEY, next)
        } catch {
          // 存储不可用只影响下次访问的默认值
        }
      }
      syncDocumentLang(next)
      return current
    },
    toggle(): Lang {
      return this.switch(current === 'zh' ? 'en' : 'zh')
    },
  }
}

export interface I18nContextValue extends I18nController {
  t: Dict
  setLang: (lang: Lang) => void
  toggleLang: () => void
}

export const I18nContext = createContext<I18nContextValue | null>(null)

/** 在组件树根部调用一次，向下提供字典与切换能力。 */
export function useI18nProvider(deps?: I18nDeps): I18nContextValue {
  const controller = useMemo(() => createI18nController(deps), [deps])
  const [lang, setLangState] = useState<Lang>(controller.lang)

  const setLang = useCallback(
    (next: Lang) => {
      controller.switch(next)
      setLangState(controller.lang)
    },
    [controller],
  )

  const toggleLang = useCallback(() => {
    controller.toggle()
    setLangState(controller.lang)
  }, [controller])

  const value = useMemo<I18nContextValue>(
    () => ({ ...controller, t: controller.dict(), setLang, toggleLang }),
    // `lang` 是 dict() 的唯一输入：切换后必须重建上下文值
    [controller, lang, setLang, toggleLang],
  )

  // 首次挂载同步 <html lang>，保证屏幕阅读器与拼写检查语言正确
  useEffect(() => {
    syncDocumentLang(lang)
  }, [lang])

  return value
}

/** 取当前字典；在 Provider 之外使用时回退到中文，避免渲染崩溃。 */
export function useT(): Dict {
  const ctx = useContext(I18nContext)
  return ctx?.t ?? DICTS.zh
}

/** 取当前语言与切换能力（语言控件专用）。 */
export function useLang(): Pick<I18nContextValue, 'lang' | 'setLang' | 'toggleLang'> {
  const ctx = useContext(I18nContext)
  if (!ctx) {
    return { lang: 'zh', setLang: () => {}, toggleLang: () => {} }
  }
  return { lang: ctx.lang, setLang: ctx.setLang, toggleLang: ctx.toggleLang }
}
