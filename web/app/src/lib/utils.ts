import { clsx, type ClassValue } from 'clsx'
import { extendTailwindMerge } from 'tailwind-merge'

/**
 * 自定义令牌里同时存在 `--text-*`（字号）与 `--color-*`（颜色），
 * 两者都会生成 `text-xxx` 工具类。tailwind-merge 默认无法区分，
 * 会把后出现的一个当作冲突丢弃（例如 `text-white` 被 `text-label` 覆盖）。
 * 这里显式声明分组，保证颜色类与字号类共存。
 */
const FONT_SIZES = ['caption', 'display', 'hero', 'label', 'micro', 'section', 'section-lg', 'title']
const TEXT_COLORS = [
  'accent',
  'accent-ink',
  'accent-soft',
  'bg',
  'body',
  'critical',
  'critical-ink',
  'danger',
  'danger-ink',
  'danger-soft',
  'info',
  'info-ink',
  'info-soft',
  'ink',
  'muted',
  'rule',
  'rule-strong',
  'scene-blush',
  'scene-skin',
  'semantic-critical',
  'semantic-high',
  'semantic-low',
  'semantic-medium',
  'success',
  'success-ink',
  'success-soft',
  'surface',
  'warning',
  'warning-ink',
  'warning-soft',
]

const tw = extendTailwindMerge({
  extend: {
    classGroups: {
      'font-size': [{ text: FONT_SIZES }],
      'text-color': [{ text: TEXT_COLORS }],
    },
  },
})

export function cn(...inputs: ClassValue[]) {
  return tw(clsx(inputs))
}
