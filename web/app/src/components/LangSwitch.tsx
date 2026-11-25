import { cn } from '@/lib/utils'
import { useLang } from '@/i18n'

/**
 * 中 / EN 分段控件（TOKENS.md 2.1：小控件用 --radius-sm、--text-label、正文字体；
 * 选中态用浅底 + 墨变体文字，不引入第二套色板）。
 */
export function LangSwitch({ className }: { className?: string }) {
  const { lang, setLang } = useLang()

  return (
    <div
      className={cn('lang-switch', className)}
      role="group"
      aria-label="切换语言 / Switch language"
    >
      <button
        type="button"
        className={cn('lang-switch__item', lang === 'zh' && 'is-active')}
        aria-pressed={lang === 'zh'}
        onClick={() => setLang('zh')}
      >
        中文
      </button>
      <button
        type="button"
        className={cn('lang-switch__item', lang === 'en' && 'is-active')}
        aria-pressed={lang === 'en'}
        onClick={() => setLang('en')}
      >
        EN
      </button>
    </div>
  )
}
